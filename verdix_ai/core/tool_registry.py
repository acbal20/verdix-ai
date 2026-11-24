#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Registro y ejecución de herramientas de VERDIX.
Cada herramienta es una función registrada con metadatos para que el LLM la llame.
"""

import os
import sys
import json
import subprocess
import shutil
import base64
import getpass
import ast
import hashlib
import sqlite3
import glob
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Callable, Optional, List

from verdix_ai.config import (
    RUTA_HOME, RUTA_VERDIX, DB_MEMORIA, DB_ERRORES,
    COLOR_PRIMARIO, COLOR_PELIGRO, COLOR_EXITO, COLOR_ADVERTENCIA,
)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError:
    Console = Panel = Confirm = None

console = Console() if Console else None

registro_acciones: List[Dict[str, Any]] = []

# ==========================================
# UTILIDADES INTERNAS
# ==========================================
def _agregar_registro(tipo: str, detalle: str, exito: bool, mensaje: str):
    registro_acciones.append({
        "tipo": tipo,
        "detalle": detalle,
        "exito": exito,
        "mensaje": mensaje,
        "fecha": datetime.now().isoformat(),
    })

def _obtener_registros() -> List[Dict[str, Any]]:
    return list(registro_acciones)

def _limpiar_registros():
    registro_acciones.clear()

# ==========================================
# SEGURIDAD
# ==========================================
PATRONES_PELIGROSOS = [
    r'\bsudo\b', r'\brm\b', r'\bmv\b', r'\bdd\b', r'\bmkfs\b',
    r'\bchmod\b', r'\bchown\b', r'\bapt\b', r'\bpip\b',
    r'\bcurl\b', r'\bwget\b', r'\bnc\b', r'\bnetcat\b',
    r'>', r'>>', r'\bbash\s+-c\b', r'\bsh\s+-c\b',
    r'\bformat\b', r'\bfdisk\b', r'\bshred\b',
]
PATRONES_INTERACTIVOS = [
    r'\bnano\b', r'\bvim\b', r'\bvi\b', r'\bhtop\b',
    r'\btop\b', r'\bless\b', r'\bmore\b', r'\bemacs\b',
]


def analizar_peligro(comando: str) -> bool:
    import re
    return any(re.search(p, comando, re.IGNORECASE) for p in PATRONES_PELIGROSOS + PATRONES_INTERACTIVOS)


def es_ruta_segura(ruta: str) -> bool:
    """Evita path traversal fuera del home del usuario."""
    ruta_abs = os.path.abspath(os.path.expanduser(ruta))
    home_abs = os.path.abspath(RUTA_HOME)
    return ruta_abs.startswith(home_abs + os.sep) or ruta_abs == home_abs

# ==========================================
# BASES DE DATOS (memoria y errores)
# ==========================================
def _conectar_memoria():
    os.makedirs(os.path.dirname(DB_MEMORIA), exist_ok=True)
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS historial
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT, contenido TEXT, fecha TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cache
                 (key TEXT PRIMARY KEY, respuesta TEXT, fecha TEXT)''')
    conn.commit()
    return conn


def _conectar_errores():
    os.makedirs(os.path.dirname(DB_ERRORES), exist_ok=True)
    conn = sqlite3.connect(DB_ERRORES)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS errores
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, comando TEXT, error TEXT, fecha TEXT)''')
    conn.commit()
    return conn


def guardar_mensaje(rol: str, contenido: str):
    try:
        conn = _conectar_memoria()
        conn.execute("INSERT INTO historial (rol, contenido, fecha) VALUES (?, ?, ?)",
                     (rol, contenido, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def cargar_historial(limite: int = 50) -> List[Dict[str, str]]:
    try:
        conn = _conectar_memoria()
        cur = conn.execute("SELECT rol, contenido FROM historial ORDER BY id DESC LIMIT ?", (limite,))
        rows = cur.fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception:
        return []


def limpiar_historial():
    try:
        conn = _conectar_memoria()
        conn.execute("DELETE FROM historial")
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
    except Exception:
        pass


def guardar_error(comando: str, error: str):
    try:
        conn = _conectar_errores()
        conn.execute("INSERT INTO errores (comando, error, fecha) VALUES (?, ?, ?)",
                     (comando, error, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_cache(prompt: str, ttl_horas: int = 24) -> Optional[str]:
    key = hashlib.md5(prompt.encode()).hexdigest()
    try:
        conn = _conectar_memoria()
        cur = conn.execute("SELECT respuesta, fecha FROM cache WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        respuesta, fecha = row
        fecha_dt = datetime.fromisoformat(fecha)
        if datetime.now() - fecha_dt > timedelta(hours=ttl_horas):
            return None
        return respuesta
    except Exception:
        return None


def save_cache(prompt: str, respuesta: str):
    key = hashlib.md5(prompt.encode()).hexdigest()
    try:
        conn = _conectar_memoria()
        conn.execute("INSERT OR REPLACE INTO cache (key, respuesta, fecha) VALUES (?, ?, ?)",
                     (key, respuesta, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ==========================================
# HERRAMIENTAS DE SISTEMA
# ==========================================
def herramienta_terminal(comando: str, password: Optional[str] = None) -> str:
    """Ejecuta un comando de terminal. Comandos peligrosos requieren confirmación y contraseña."""
    if analizar_peligro(comando):
        if console:
            console.print(f"[bold red]⚠️ PELIGRO:[/] {comando}")
            if not Confirm.ask("¿Ejecutar comando peligroso?"):
                return "⏭️ Cancelado por el usuario."
            password = password or getpass.getpass("Ingrese contraseña de sudo: ")
    try:
        if password:
            cmd_final = comando if comando.strip().startswith("sudo ") else f"sudo -S {comando}"
            res = subprocess.run(cmd_final, shell=True, input=password + "\n",
                                 capture_output=True, text=True, timeout=120)
        else:
            res = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=120)
        salida = res.stdout.strip() or res.stderr.strip()
        if res.returncode != 0:
            guardar_error(comando, salida)
            return f"❌ ERROR: {salida}"
        return salida or "✅ Comando ejecutado."
    except Exception as e:
        guardar_error(comando, str(e))
        return f"❌ Error: {e}"


def herramienta_crear_archivo(filename: str, content: str) -> str:
    """Crea o sobrescribe un archivo."""
    if not es_ruta_segura(filename):
        return "❌ Ruta fuera del directorio de usuario no permitida."
    try:
        path = Path(os.path.expanduser(filename))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _agregar_registro("create_file", str(path), True, f"{path.stat().st_size} bytes")
        return f"✅ Archivo '{filename}' creado ({path.stat().st_size} bytes)."
    except Exception as e:
        _agregar_registro("create_file", filename, False, str(e))
        return f"❌ Error: {e}"


def herramienta_editar_archivo(filename: str, content: str) -> str:
    """Edita un archivo (mismo que crear/sobrescribir)."""
    return herramienta_crear_archivo(filename, content)


def herramienta_leer_archivo(filename: str, limite_bytes: int = 10000) -> str:
    """Lee el contenido de un archivo."""
    if not es_ruta_segura(filename):
        return "❌ Ruta no permitida."
    try:
        path = Path(os.path.expanduser(filename))
        if not path.exists():
            return f"❌ '{filename}' no existe."
        contenido = path.read_text(encoding="utf-8")[:limite_bytes]
        return contenido
    except Exception as e:
        return f"❌ Error: {e}"


def herramienta_verificar_archivo(filename: str) -> str:
    """Verifica que un archivo exista y tenga sintaxis válida si es Python."""
    if not es_ruta_segura(filename):
        return "❌ Ruta no permitida."
    path = Path(os.path.expanduser(filename))
    if not path.exists():
        return f"❌ '{filename}' no existe."
    if path.suffix == ".py":
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return f"✅ '{filename}' válido ({path.stat().st_size} bytes)."
        except SyntaxError as e:
            return f"❌ '{filename}' error de sintaxis: {e}"
    return f"✅ '{filename}' existe ({path.stat().st_size} bytes)."


def herramienta_listar_directorio(ruta: str = ".", profundidad: int = 2) -> str:
    """Lista archivos y carpetas de un directorio con estructura de árbol."""
    if not es_ruta_segura(ruta):
        return "❌ Ruta no permitida."
    base = Path(os.path.expanduser(ruta))
    if not base.exists():
        return f"❌ '{ruta}' no existe."

    lineas = []
    def _recorrer(directorio: Path, prefijo: str, nivel: int):
        if nivel > profundidad:
            return
        try:
            entradas = sorted(directorio.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for entrada in entradas:
            if entrada.name.startswith(".") and entrada.name not in (".git", ".env"):
                continue
            marca = "📁 " if entrada.is_dir() else "📄 "
            lineas.append(f"{prefijo}{marca}{entrada.name}")
            if entrada.is_dir() and nivel < profundidad:
                _recorrer(entrada, prefijo + "   ", nivel + 1)

    lineas.append(f"📂 {base.name}/")
    _recorrer(base, "", 0)
    return "\n".join(lineas)


def herramienta_buscar_en_archivos(patron: str, ruta: str = ".", extension: str = ".py") -> str:
    """Busca un patrón de texto en archivos de una extensión dada."""
    import re
    if not es_ruta_segura(ruta):
        return "❌ Ruta no permitida."
    base = Path(os.path.expanduser(ruta))
    resultados = []
    try:
        for archivo in base.rglob(f"*{extension}"):
            try:
                texto = archivo.read_text(encoding="utf-8", errors="ignore")
                for i, linea in enumerate(texto.splitlines(), 1):
                    if re.search(patron, linea, re.IGNORECASE):
                        resultados.append(f"{archivo}:{i}: {linea[:120]}")
            except Exception:
                continue
    except Exception as e:
        return f"❌ Error buscando: {e}"
    if not resultados:
        return f"✅ No se encontraron coincidencias para '{patrón}'."
    return "\n".join(resultados[:100])


def herramienta_instalar_paquete(paquete: str, metodo: str = "pip") -> str:
    """Instala un paquete con pip o apt (apt requiere sudo manual)."""
    if metodo == "pip":
        try:
            cmd = f"{sys.executable} -m pip install --user {paquete}"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if res.returncode == 0:
                return f"✅ '{paquete}' instalado con pip."
            return f"❌ Error pip: {res.stderr[:500]}"
        except Exception as e:
            return f"❌ Error: {e}"
    elif metodo == "apt":
        if console:
            console.print(f"[bold yellow]⚠️ Se requiere sudo para instalar '{paquete}' con apt.[/]")
            if Confirm.ask(f"¿Ejecutar 'sudo apt-get install -y {paquete}'?"):
                password = getpass.getpass("Contraseña de sudo: ")
                cmd = f"sudo -S apt-get install -y {paquete}"
                res = subprocess.run(cmd, shell=True, input=password + "\n",
                                     capture_output=True, text=True, timeout=300)
                if res.returncode == 0:
                    return f"✅ '{paquete}' instalado con apt."
                return f"❌ Error apt: {res.stderr[:500]}"
        return "ℹ️ Instalación cancelada."
    return f"❌ Método '{metodo}' no soportado."


def herramienta_generar_imagen(prompt: str) -> str:
    """Genera una imagen usando Pollinations AI."""
    import requests, random
    try:
        urls = [
            f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=1024&height=1024&nologo=true&seed={random.randint(1, 99999)}",
            f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=512&height=512&nologo=true&model=flux",
        ]
        nombre = f"img_{hashlib.md5(prompt.encode()).hexdigest()[:10]}.jpg"
        ruta = Path(os.path.abspath(nombre))
        for url in urls:
            try:
                r = requests.get(url, stream=True, timeout=60)
                if r.status_code == 200:
                    with open(ruta, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return f"✅ Imagen guardada: {ruta}"
            except Exception:
                continue
        return "❌ Error generando imagen."
    except Exception as e:
        return f"❌ Error: {e}"


def herramienta_editar_imagen(archivo_entrada: str, accion: str, archivo_salida: Optional[str] = None) -> str:
    """Edita una imagen (blanco_negro, desenfoque, invertir, redimensionar)."""
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        res = herramienta_instalar_paquete("Pillow", "pip")
        if "❌" in res:
            return res
        from PIL import Image, ImageFilter, ImageOps
    try:
        if not archivo_entrada or archivo_entrada.lower() in ("ultima", "última"):
            archivo_entrada = getattr(herramienta_editar_imagen, "_ultima", None)
        if not archivo_entrada:
            return "❌ No hay imagen previa."
        img = Image.open(os.path.expanduser(archivo_entrada))
        if accion == "blanco_negro":
            img = ImageOps.grayscale(img)
        elif accion == "desenfoque":
            img = img.filter(ImageFilter.BLUR)
        elif accion == "invertir":
            img = ImageOps.invert(img.convert("RGB"))
        elif accion == "redimensionar":
            img = img.resize((800, 600))
        else:
            return f"❌ Acción '{accion}' no soportada."
        salida = archivo_salida or f"editada_{Path(archivo_entrada).name}"
        ruta_salida = Path(os.path.abspath(salida))
        img.save(ruta_salida)
        herramienta_editar_imagen._ultima = str(ruta_salida)
        return f"✅ Imagen editada: {ruta_salida}"
    except Exception as e:
        return f"❌ Error: {e}"


def herramienta_buscar_web(query: str) -> str:
    """Búsqueda web simple usando DuckDuckGo."""
    try:
        from ddgs import DDGS
    except ImportError:
        res = herramienta_instalar_paquete("ddgs", "pip")
        if "❌" in res:
            return res
        from ddgs import DDGS
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=8))
            if not resultados:
                return "✅ No se encontraron resultados."
            return "\n".join([f"• {r.get('title','')}: {r.get('body','')}" for r in resultados])
    except Exception as e:
        return f"❌ Error en búsqueda web: {e}"


def herramienta_ejecutar_python(filename: str) -> str:
    """Ejecuta un archivo de Python."""
    if not es_ruta_segura(filename):
        return "❌ Ruta no permitida."
    try:
        res = subprocess.run([sys.executable, os.path.expanduser(filename)],
                             capture_output=True, text=True, timeout=120)
        salida = res.stdout.strip() or res.stderr.strip()
        return salida or "✅ Ejecutado sin salida."
    except Exception as e:
        return f"❌ Error: {e}"

# ==========================================
# REGISTRO DE HERRAMIENTAS
# ==========================================
HERRAMIENTAS: Dict[str, Dict[str, Any]] = {
    "terminal": {
        "func": herramienta_terminal,
        "descripcion": "Ejecuta comandos de terminal",
        "parametros": {"comando": "str", "password": "str (opcional)"},
        "peligroso": True,
    },
    "create_file": {
        "func": herramienta_crear_archivo,
        "descripcion": "Crea o sobrescribe un archivo de texto",
        "parametros": {"filename": "str", "content": "str"},
    },
    "edit_file": {
        "func": herramienta_editar_archivo,
        "descripcion": "Edita un archivo existente",
        "parametros": {"filename": "str", "content": "str"},
    },
    "read_file": {
        "func": herramienta_leer_archivo,
        "descripcion": "Lee el contenido de un archivo",
        "parametros": {"filename": "str", "limite_bytes": "int (opcional)"},
    },
    "verify_file": {
        "func": herramienta_verificar_archivo,
        "descripcion": "Verifica existencia y sintaxis de un archivo",
        "parametros": {"filename": "str"},
    },
    "list_dir": {
        "func": herramienta_listar_directorio,
        "descripcion": "Lista estructura de directorios",
        "parametros": {"ruta": "str (opcional)", "profundidad": "int (opcional)"},
    },
    "search_files": {
        "func": herramienta_buscar_en_archivos,
        "descripcion": "Busca patrón en archivos",
        "parametros": {"patron": "str", "ruta": "str (opcional)", "extension": "str (opcional)"},
    },
    "install_package": {
        "func": herramienta_instalar_paquete,
        "descripcion": "Instala paquetes pip o apt",
        "parametros": {"paquete": "str", "metodo": "str (pip|apt)"},
        "peligroso": True,
    },
    "generate_image": {
        "func": herramienta_generar_imagen,
        "descripcion": "Genera imagen a partir de texto",
        "parametros": {"prompt": "str"},
    },
    "edit_image": {
        "func": herramienta_editar_imagen,
        "descripcion": "Edita una imagen existente",
        "parametros": {"archivo_entrada": "str", "accion": "str", "archivo_salida": "str (opcional)"},
    },
    "search_web": {
        "func": herramienta_buscar_web,
        "descripcion": "Busca información en internet",
        "parametros": {"query": "str"},
    },
    "run_python": {
        "func": herramienta_ejecutar_python,
        "descripcion": "Ejecuta un script de Python",
        "parametros": {"filename": "str"},
    },
}


def obtener_herramienta(nombre: str) -> Optional[Callable]:
    entrada = HERRAMIENTAS.get(nombre)
    return entrada["func"] if entrada else None


def listar_herramientas() -> List[Dict[str, Any]]:
    return [{"nombre": k, **v} for k, v in HERRAMIENTAS.items()]


def ejecutar_herramienta(nombre: str, **kwargs) -> str:
    func = obtener_herramienta(nombre)
    if not func:
        return f"❌ Herramienta '{nombre}' no encontrada."
    try:
        return func(**kwargs)
    except Exception as e:
        return f"❌ Error ejecutando '{nombre}': {e}"


# ==========================================
# EJECUTOR CON SANDBOX Y AUTO-ARREGLO
# ==========================================
class ToolExecutor:
    """
    Ejecuta herramientas de VERDIX pasando primero por verificación en sandbox.
    Si falla, intenta auto-arreglar. Solo si pasa las pruebas se inyecta al sistema real.
    """

    def __init__(self, llm_chat: Callable[[str], str], max_intentos: int = 3):
        self.llm_chat = llm_chat
        self.max_intentos = max_intentos
        from verdix_ai.core.sandbox import verificador
        self.verificador = verificador
        self.verificador.max_intentos = max_intentos

    def ejecutar(self, nombre: str, **kwargs) -> str:
        """
        Ejecuta una herramienta con verificación previa en sandbox.
        """
        # Acciones que requieren verificación en sandbox antes de inyectar
        ACCIONES_SANDBOX = {
            "create_file", "edit_file", "terminal", "install_package", "run_python",
        }

        if nombre in ACCIONES_SANDBOX:
            return self._ejecutar_con_sandbox(nombre, **kwargs)
        else:
            # Lecturas, búsquedas, imágenes, etc. no modifican el sistema, se ejecutan directo
            return ejecutar_herramienta(nombre, **kwargs)

    def _ejecutar_con_sandbox(self, nombre: str, **kwargs) -> str:
        if nombre == "create_file" or nombre == "edit_file":
            filename = kwargs.get("filename", "")
            content = kwargs.get("content", "")
            if not filename:
                return "❌ Falta parámetro 'filename'."

            def accion_real():
                return ejecutar_herramienta(nombre, filename=filename, content=content)

            resultado_sb = self.verificador.verificar_crear_archivo(
                filename, content, self.llm_chat
            )
            return self._finalizar_inyeccion(nombre, filename, resultado_sb, accion_real)

        elif nombre == "terminal":
            comando = kwargs.get("comando", "")
            password = kwargs.get("password", None)
            if not comando:
                return "❌ Falta parámetro 'comando'."

            def accion_real():
                return ejecutar_herramienta("terminal", comando=comando, password=password)

            resultado_sb = self.verificador.verificar_comando(
                comando, self.llm_chat
            )
            return self._finalizar_inyeccion(nombre, comando, resultado_sb, accion_real)

        elif nombre == "install_package":
            paquete = kwargs.get("paquete", "")
            metodo = kwargs.get("metodo", "pip")
            if not paquete:
                return "❌ Falta parámetro 'paquete'."

            def accion_real():
                return ejecutar_herramienta("install_package", paquete=paquete, metodo=metodo)

            # Para instalación, verificamos que el paquete sea válido (nombre correcto)
            comando_verif = f"{sys.executable} -m pip install --user {paquete}" if metodo == "pip" else f"sudo apt-get install -y {paquete}"
            resultado_sb = self.verificador.verificar_comando(
                comando_verif, self.llm_chat
            )
            return self._finalizar_inyeccion(nombre, paquete, resultado_sb, accion_real)

        elif nombre == "run_python":
            filename = kwargs.get("filename", "")
            if not filename:
                return "❌ Falta parámetro 'filename'."

            def accion_real():
                return ejecutar_herramienta("run_python", filename=filename)

            resultado_sb = self.verificador.verificar_comando(
                f"{sys.executable} {filename}", self.llm_chat
            )
            return self._finalizar_inyeccion(nombre, filename, resultado_sb, accion_real)

        else:
            return ejecutar_herramienta(nombre, **kwargs)

    def _finalizar_inyeccion(self, nombre: str, objetivo: str,
                             resultado_sb, accion_real: Callable[[], str]) -> str:
        if not resultado_sb.exitoso:
            return (
                f"🛡️ [SANDBOX BLOQUEADO] {nombre} no pasó la verificación.\n"
                f"Razón: {resultado_sb.mensaje}\n"
                f"Ingentos: {resultado_sb.intentos}\n"
                f"No se modificó el sistema real."
            )

        try:
            resultado_real = accion_real()
            return (
                f"✅ [SANDBOX APROBADO] {nombre} verificado en {resultado_sb.intentos} intento(s).\n"
                f"🚀 Inyectado al sistema real:\n{resultado_real}"
            )
        except Exception as e:
            return f"❌ Error inyectando al sistema real: {e}"

    def obtener_historial_sandbox(self):
        return self.verificador.obtener_historial()


# Instancia global (se inicializa con llm_chat desde main)
tool_executor: Optional[ToolExecutor] = None


def inicializar_executor(llm_chat: Callable[[str], str], max_intentos: int = 3):
    global tool_executor
    tool_executor = ToolExecutor(llm_chat=llm_chat, max_intentos=max_intentos)
    return tool_executor
