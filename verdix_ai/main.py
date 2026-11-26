#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERDIX AI Terminal - v30.0 (Máximo Potencial)
Creado por NOX | Powered by Groq / OpenAI / Ollama

Sistema multi-agente autónomo con:
  - VERDIX-Programador, VERDIX-Revisor, VERDIX-Orquestador
  - Sandbox de verificación previa + auto-arreglo antes de inyectar
  - Integración GitHub y Vercel
  - Contexto de proyecto persistente
  - Memoria de conversación y caché
  - Soporte multi-proveedor de LLM
"""

import os
import sys
import json
import re
import argparse
import signal
import getpass
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any, List

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.align import Align
    from rich.text import Text
    from rich.live import Live
except ImportError:
    Console = Panel = Prompt = Confirm = Align = Text = Live = None

# --- Configuración VERDIX ---
from verdix_ai.config import (
    VERSION, NOMBRE, RUTA_VERDIX, DB_MEMORIA, DB_ERRORES,
    COLOR_PRIMARIO, COLOR_PELIGRO, COLOR_EXITO, COLOR_ADVERTENCIA,
    es_clave_valida, obtener_api_key,
)

# --- Núcleo de herramientas y sandbox ---
import verdix_ai.core.tool_registry as tool_registry
from verdix_ai.core.tool_registry import (
    ejecutar_herramienta, listar_herramientas,
    inicializar_executor,
)
from verdix_ai.core.sandbox import verificador, SandboxResult
from verdix_ai.core.mahoraga import mahoraga

# --- Multi-agente ---
from verdix_ai.agents import (
    ProgramadorAgent, RevisorAgent, OrquestadorAgent,
    flujo_multiagente, guardar_codigo_flujo,
)

# --- Integraciones externas ---
from verdix_ai.github_integration import (
    github_resumen, github_list_repos, github_create_repo,
    github_upload_file, github_create_issue,
)
from verdix_ai.vercel_integration import (
    vercel_resumen, vercel_list_deployments, vercel_deploy_directorio,
)

# --- Contexto de proyecto ---
from verdix_ai.core.project_context import contexto

# --- LLM multi-proveedor ---
from verdix_ai.core.llm_provider import LLMProvider

# ==========================================
# ESTADO GLOBAL
# ==========================================
console = Console() if Console else None
registro_acciones: List[Dict[str, Any]] = []
llm_provider: Optional[LLMProvider] = None
historial: List[Dict[str, str]] = []


def agregar_registro(tipo: str, detalle: str, exito: bool, mensaje: str):
    registro_acciones.append({
        "tipo": tipo,
        "detalle": detalle,
        "exito": exito,
        "mensaje": mensaje,
        "fecha": datetime.now().isoformat(),
    })


def obtener_registros() -> List[Dict[str, Any]]:
    return list(registro_acciones)


# ==========================================
# LLM CHAT (para auto-arreglador y respuestas)
# ==========================================
def llm_chat(mensaje: str, temperatura: float = 0.2,
             formato_json: bool = True) -> str:
    """Envía un mensaje al proveedor de LLM activo."""
    if not llm_provider or not llm_provider.disponible():
        return json.dumps({
            "action": "chat",
            "message": "❌ No hay proveedor de LLM configurado. Falta API key."
        })
    return llm_provider.chat(
        [{"role": "user", "content": mensaje}],
        temperatura=temperatura,
        max_tokens=4000,
        formato_json=formato_json,
    )


def llm_chat_con_historial(mensajes: List[Dict[str, str]],
                           temperatura: float = 0.2,
                           formato_json: bool = True) -> str:
    if not llm_provider or not llm_provider.disponible():
        return json.dumps({
            "action": "chat",
            "message": "❌ No hay proveedor de LLM configurado. Falta API key."
        })
    return llm_provider.chat(
        mensajes,
        temperatura=temperatura,
        max_tokens=4000,
        formato_json=formato_json,
    )


# ==========================================
# BASES DE DATOS (memoria y errores)
# ==========================================
import sqlite3
import hashlib
from pathlib import Path


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


def limpiar_cache_expirado(ttl_horas: int = 24):
    """Elimina entradas de caché expiradas."""
    try:
        conn = _conectar_memoria()
        limite = (datetime.now() - timedelta(hours=ttl_horas)).isoformat()
        conn.execute("DELETE FROM cache WHERE fecha < ?", (limite,))
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


def obtener_lecciones() -> str:
    try:
        conn = _conectar_errores()
        cur = conn.execute("SELECT comando, error FROM errores ORDER BY id DESC LIMIT 3")
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return ""
    if not rows:
        return ""
    lecciones = "\n=== LECCIONES APRENDIDAS ===\n"
    for cmd, err in rows:
        lecciones += f"- Fallo: {cmd[:60]}... | Error: {err[:60]}...\n"
    return lecciones


# ==========================================
# SEGURIDAD
# ==========================================
def analizar_peligro(comando: str) -> bool:
    import re
    peligrosos = [
        r'\bsudo\b', r'\brm\b', r'\bmv\b', r'\bdd\b', r'\bmkfs\b',
        r'\bchmod\b', r'\bchown\b', r'\bapt\b', r'\bpip\b',
        r'\bcurl\b', r'\bwget\b', r'\bnc\b', r'\bnetcat\b',
        r'>', r'>>', r'\bbash\s+-c\b', r'\bsh\s+-c\b',
        r'\bformat\b', r'\bfdisk\b', r'\bshred\b',
    ]
    interactivos = [
        r'\bnano\b', r'\bvim\b', r'\bvi\b', r'\bhtop\b',
        r'\btop\b', r'\bless\b', r'\bmore\b', r'\bemacs\b',
    ]
    return any(re.search(p, comando, re.IGNORECASE) for p in peligrosos + interactivos)


# ==========================================
# PROCESADOR DE ACCIONES (con sandbox)
# ==========================================
def procesar_respuesta(respuesta_raw: str):
    if not respuesta_raw or not respuesta_raw.strip():
        return

    try:
        limpio = re.sub(r'```json\s*|\s*```', '', respuesta_raw).strip()
        match = re.search(r'(\{.*\}|\[.*\])', limpio, re.DOTALL)
        if match:
            limpio = match.group(1)
        data = json.loads(limpio)
        acciones = [data] if isinstance(data, dict) else data
    except json.JSONDecodeError:
        if console:
            console.print(Panel(respuesta_raw, title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
        return
    except Exception as e:
        if console:
            console.print(f"[bold red]Error parseando respuesta:[/] {e}")
        return

    for accion_data in acciones:
        accion = accion_data.get("action")

        # --- CHAT ---
        if accion == "chat":
            msg = accion_data.get("message", "")
            if console:
                console.print(Panel(msg, title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
            else:
                print(f"VERDIX AI: {msg}")
            agregar_registro("chat", msg, True, msg)

        # --- MULTI-AGENTE ---
        elif accion == "multi_agent_flow":
            peticion = accion_data.get("peticion", "")
            archivo = accion_data.get("archivo", "")
            max_ciclos = int(accion_data.get("max_ciclos", 5))
            if console:
                console.print(Panel(
                    f"[bold magenta]🤖 Flujo multi-agente[/]\nPetición: {peticion}\nArchivo: {archivo or '(por definir)'}\nMáx. ciclos: {max_ciclos}",
                    title="[bold green]VERDIX Multi-Agente[/]", border_style="green"))
            resultado = flujo_multiagente(peticion, archivo if archivo else None, max_ciclos)
            exito = resultado.get("aprobado", False)
            mensaje = (
                f"{resultado['mensaje']}\n"
                f"Ciclos: {resultado['ciclos']} | Aprobado: {'✅ Sí' if exito else '❌ No'}\n"
                f"Archivo: {resultado['archivo']}"
            )
            if console:
                console.print(Panel(mensaje, title="[bold green]Resultado Multi-Agente[/]",
                                    border_style="green" if exito else "red"))
            guardado = guardar_codigo_flujo(resultado.get("archivo") or archivo or "programa.py", resultado.get("codigo", ""))
            if console:
                console.print(f"[bold]{guardado}[/]")
            agregar_registro("multi_agent_flow", resultado.get("archivo") or archivo or "(sin archivo)", exito and "✅" in guardado, guardado)

        # --- TERMINAL (con sandbox) ---
        elif accion == "terminal":
            cmd = accion_data.get("command", "") or accion_data.get("comando", "")
            password = accion_data.get("password", None)
            if not cmd:
                continue
            if analizar_peligro(cmd):
                if console:
                    console.print(f"[bold red]⚠️ PELIGRO:[/] {cmd}")
                    if not Confirm.ask("¿Ejecutar comando peligroso?"):
                        console.print("[yellow]⏭️ Cancelado.[/]")
                        continue
                    password = password or getpass.getpass("Contraseña de sudo: ")
            if console:
                console.print(f"[dim]⚡ Ejecutando en sandbox: {cmd}[/]")
            if tool_registry.tool_executor:
                resultado = tool_registry.tool_executor.ejecutar("terminal", comando=cmd, password=password)
            else:
                resultado = ejecutar_herramienta("terminal", comando=cmd, password=password)
            if console:
                console.print(Panel(resultado, title="Resultado Terminal",
                                    border_style="green" if "✅" in resultado else "red"))
            exito = "✅" in resultado or "⚡" in resultado
            agregar_registro("terminal", cmd, exito, resultado)

        # --- ARCHIVOS (con sandbox) ---
        elif accion in ("create_file", "edit_file"):
            filename = accion_data.get("filename", "")
            content = accion_data.get("content", "")
            if not filename:
                continue
            if tool_registry.tool_executor:
                resultado = tool_registry.tool_executor.ejecutar(accion, filename=filename, content=content)
            else:
                resultado = ejecutar_herramienta(accion, filename=filename, content=content)
            if console:
                exito = "✅" in resultado
                console.print(Panel(resultado, title="Archivo",
                                    border_style="green" if exito else "red"))
            exito = "✅" in resultado
            agregar_registro(accion, filename, exito, resultado)

        elif accion == "read_file":
            filename = accion_data.get("filename", "")
            contenido = ejecutar_herramienta("read_file", filename=filename)
            if console:
                console.print(Panel(contenido[:5000], title=f"Archivo: {filename}",
                                    border_style="blue"))
            agregar_registro("read_file", filename, True, contenido[:100])

        elif accion == "verify_file":
            filename = accion_data.get("filename", "")
            resultado = ejecutar_herramienta("verify_file", filename=filename)
            if console:
                console.print(Panel(resultado, title="Verificación",
                                    border_style="blue" if "✅" in resultado else "red"))
            agregar_registro("verify_file", filename, "✅" in resultado, resultado)

        elif accion == "list_dir":
            ruta = accion_data.get("ruta", ".")
            profundidad = int(accion_data.get("profundidad", 2))
            resultado = ejecutar_herramienta("list_dir", ruta=ruta, profundidad=profundidad)
            if console:
                console.print(Panel(resultado, title=f"Directorio: {ruta}",
                                    border_style="blue"))
            agregar_registro("list_dir", ruta, True, resultado[:100])

        elif accion == "search_files":
            patron = accion_data.get("patron", "")
            ruta = accion_data.get("ruta", ".")
            extension = accion_data.get("extension", ".py")
            resultado = ejecutar_herramienta("search_files", patron=patron, ruta=ruta, extension=extension)
            if console:
                console.print(Panel(resultado, title="Búsqueda en archivos",
                                    border_style="blue"))
            agregar_registro("search_files", patron, True, resultado[:100])

        # --- PAQUETES (con sandbox) ---
        elif accion == "install_system_package":
            paquete = accion_data.get("package", "") or accion_data.get("paquete", "")
            metodo = accion_data.get("method", "pip") or accion_data.get("metodo", "pip")
            if tool_registry.tool_executor:
                resultado = tool_registry.tool_executor.ejecutar("install_package", paquete=paquete, metodo=metodo)
            else:
                resultado = ejecutar_herramienta("install_package", paquete=paquete, metodo=metodo)
            if console:
                exito = "✅" in resultado
                console.print(Panel(resultado, title="Instalación",
                                    border_style="cyan" if exito else "red"))
            exito = "✅" in resultado
            agregar_registro("install_package", f"{paquete} ({metodo})", exito, resultado)

        # --- IMÁGENES ---
        elif accion == "generate_image":
            prompt = accion_data.get("prompt", "")
            resultado = ejecutar_herramienta("generate_image", prompt=prompt)
            if console:
                exito = "✅" in resultado
                console.print(Panel(resultado, title="Imagen",
                                    border_style="magenta" if exito else "red"))
            exito = "✅" in resultado
            agregar_registro("generate_image", prompt, exito, resultado)

        elif accion == "edit_image":
            archivo = accion_data.get("filename", "") or accion_data.get("archivo_entrada", "")
            accion_img = accion_data.get("edit_type", "") or accion_data.get("accion", "")
            salida = accion_data.get("archivo_salida", None)
            resultado = ejecutar_herramienta("edit_image", archivo_entrada=archivo,
                                             accion=accion_img, archivo_salida=salida)
            if console:
                exito = "✅" in resultado
                console.print(Panel(resultado, title="Editar Imagen",
                                    border_style="magenta" if exito else "red"))
            exito = "✅" in resultado
            agregar_registro("edit_image", archivo, exito, resultado)

        # --- WEB ---
        elif accion == "search_web":
            query = accion_data.get("query", "")
            resultado = ejecutar_herramienta("search_web", query=query)
            if console:
                console.print(Panel(resultado, title="Búsqueda Web",
                                    border_style="yellow"))
            agregar_registro("search_web", query, True, resultado[:100])

        # --- PYTHON (con sandbox) ---
        elif accion == "run_python":
            filename = accion_data.get("filename", "")
            if not filename:
                continue
            if tool_registry.tool_executor:
                resultado = tool_registry.tool_executor.ejecutar("run_python", filename=filename)
            else:
                resultado = ejecutar_herramienta("run_python", filename=filename)
            if console:
                exito = "✅" in resultado
                console.print(Panel(resultado, title="Python",
                                    border_style="green" if exito else "red"))
            exito = "✅" in resultado
            agregar_registro("run_python", filename, exito, resultado)

        # --- GITHUB ---
        elif accion == "github_resumen":
            mensaje = github_resumen()
            if console:
                console.print(Panel(mensaje, title="[bold blue]GitHub[/]", border_style="blue"))
            agregar_registro("github_resumen", "resumen", True, mensaje)

        elif accion == "github_list_repos":
            res = github_list_repos()
            if isinstance(res, dict) and res.get("status") == 200:
                lineas = [f"📁 Repositorios ({len(res['data'])}):"]
                for r in res["data"][:20]:
                    privada = "🔒" if r.get("private") else "🌍"
                    lineas.append(f"  {privada} {r['full_name']} — {r.get('description') or 'sin desc'}")
                mensaje = "\n".join(lineas)
                exito = True
            else:
                mensaje = f"❌ Error listando repos: {res}"
                exito = False
            if console:
                console.print(Panel(mensaje, title="[bold blue]GitHub[/]",
                                    border_style="blue" if exito else "red"))
            agregar_registro("github_list_repos", "listar", exito, mensaje)

        elif accion == "github_create_repo":
            nombre_repo = accion_data.get("nombre", "")
            descripcion = accion_data.get("descripcion", "")
            privado = accion_data.get("privado", True)
            res = github_create_repo(nombre_repo, descripcion, privado)
            if isinstance(res, dict) and res.get("status") in (201, 200):
                mensaje = f"✅ Repositorio '{nombre_repo}' creado en GitHub."
                exito = True
            else:
                mensaje = f"❌ Error creando repo: {res}"
                exito = False
            if console:
                console.print(Panel(mensaje, title="[bold blue]GitHub[/]",
                                    border_style="blue" if exito else "red"))
            agregar_registro("github_create_repo", nombre_repo, exito, mensaje)

        elif accion == "github_upload_file":
            usuario = accion_data.get("usuario", "")
            repo = accion_data.get("repo", "")
            ruta = accion_data.get("ruta", "")
            contenido = accion_data.get("contenido", "")
            if contenido is None:
                contenido = ""
            mensaje_commit = accion_data.get("mensaje_commit", None)
            rama = accion_data.get("rama", "main") or "main"
            res = github_upload_file(usuario, repo, ruta, str(contenido), mensaje_commit, rama)
            if isinstance(res, dict) and res.get("status") in (200, 201):
                mensaje = f"✅ Archivo '{ruta}' subido a {usuario}/{repo}."
                exito = True
            else:
                mensaje = f"❌ Error subiendo archivo: {res}"
                exito = False
            if console:
                console.print(Panel(mensaje, title="[bold blue]GitHub Upload[/]",
                                    border_style="blue" if exito else "red"))
            agregar_registro("github_upload_file", f"{usuario}/{repo}/{ruta}", exito, mensaje)

        elif accion == "github_create_issue":
            usuario = accion_data.get("usuario", "")
            repo = accion_data.get("repo", "")
            titulo = accion_data.get("titulo", "")
            cuerpo = accion_data.get("cuerpo", "")
            etiquetas = accion_data.get("etiquetas", None)
            res = github_create_issue(usuario, repo, titulo, cuerpo, etiquetas)
            if isinstance(res, dict) and res.get("status") == 201:
                num = res["data"].get("number")
                mensaje = f"✅ Issue #{num} creado en {usuario}/{repo}."
                exito = True
            else:
                mensaje = f"❌ Error creando issue: {res}"
                exito = False
            if console:
                console.print(Panel(mensaje, title="[bold blue]GitHub Issue[/]",
                                    border_style="blue" if exito else "red"))
            agregar_registro("github_create_issue", f"{usuario}/{repo}", exito, mensaje)

        # --- VERCEL ---
        elif accion == "vercel_resumen":
            mensaje = vercel_resumen()
            if console:
                console.print(Panel(mensaje, title="[bold purple]Vercel[/]", border_style="purple"))
            agregar_registro("vercel_resumen", "resumen", True, mensaje)

        elif accion == "vercel_list_deployments":
            res = vercel_list_deployments()
            if isinstance(res, dict) and res.get("status") == 200:
                lineas = [f"🚀 Despliegues recientes ({len(res['data'])}):"]
                for d in res["data"][:10]:
                    estado = d.get("readyState", "desconocido")
                    url = d.get("url", "")
                    lineas.append(f"  • {d.get('name')} — {estado} — https://{url}")
                mensaje = "\n".join(lineas)
                exito = True
            else:
                mensaje = f"❌ Error listando despliegues: {res}"
                exito = False
            if console:
                console.print(Panel(mensaje, title="[bold purple]Vercel[/]",
                                    border_style="purple" if exito else "red"))
            agregar_registro("vercel_list_deployments", "listar", exito, mensaje)

        elif accion == "vercel_deploy":
            ruta = accion_data.get("ruta", "")
            nombre_proy = accion_data.get("nombre", "")
            publica = accion_data.get("publica", True)
            if not ruta or not os.path.exists(ruta):
                mensaje = f"❌ Ruta no válida: {ruta}"
                exito = False
            else:
                res = vercel_deploy_directorio(ruta, nombre_proy, publica)
                if isinstance(res, dict) and res.get("status") in (200, 201):
                    d = res["data"]
                    url = d.get("url") or d.get("alias", [""])[0]
                    mensaje = f"✅ Desplegado en Vercel: https://{url}"
                    exito = True
                else:
                    mensaje = f"❌ Error desplegando: {res}"
                    exito = False
            if console:
                console.print(Panel(mensaje, title="[bold purple]Vercel Deploy[/]",
                                    border_style="purple" if exito else "red"))
            agregar_registro("vercel_deploy", ruta, exito, mensaje)

        # --- AUTO-MEJORA (con sandbox) ---
        elif accion == "self_improve":
            desc = accion_data.get("description", "")
            codigo = accion_data.get("code", "")
            if console:
                console.print(f"\n[bold magenta]🧬 Auto-mejora:[/] {desc}")
            # Verificar en sandbox antes de aplicar al archivo real
            from verdix_ai.core.sandbox import verificador as verif_sb
            sb_result = verif_sb.verificar_crear_archivo(
                __file__, codigo, llm_chat
            )
            if sb_result.exitoso:
                mensaje = (
                    f"✅ Auto-mejora verificada en sandbox ({sb_result.intentos} intento(s)).\n"
                    f"📋 El código fue validado sintácticamente.\n"
                    f"⚠️ Para aplicar los cambios, reinicia VERDIX con el nuevo código."
                )
                if console:
                    console.print(Panel(mensaje, title="Auto-mejora",
                                        border_style="green"))
                agregar_registro("self_improve", desc, True, mensaje)
            else:
                mensaje = f"❌ Auto-mejora rechazada por sandbox: {sb_result.mensaje}"
                if console:
                    console.print(Panel(mensaje, title="Auto-mejora",
                                        border_style="red"))
                agregar_registro("self_improve", desc, False, mensaje)

        # --- PROYECTO ---
        elif accion == "proyecto_crear":
            nombre = accion_data.get("nombre", "")
            ruta = accion_data.get("ruta", "./")
            desc = accion_data.get("descripcion", "")
            mensaje = contexto.crear_proyecto(nombre, ruta, desc)
            if console:
                console.print(Panel(mensaje, title="Proyecto",
                                    border_style="green" if "✅" in mensaje else "red"))
            agregar_registro("proyecto_crear", nombre, "✅" in mensaje, mensaje)

        elif accion == "proyecto_activar":
            nombre = accion_data.get("nombre", "")
            mensaje = contexto.activar_proyecto(nombre)
            if console:
                console.print(Panel(mensaje, title="Proyecto",
                                    border_style="green" if "✅" in mensaje else "red"))
            agregar_registro("proyecto_activar", nombre, "✅" in mensaje, mensaje)

        elif accion == "proyecto_listar":
            proyectos = contexto.listar_proyectos()
            if proyectos:
                lineas = [f"📂 Proyectos ({len(proyectos)}):"]
                for p in proyectos:
                    lineas.append(f"  • {p['nombre']} — {p['ruta']}")
                mensaje = "\n".join(lineas)
            else:
                mensaje = "✅ No hay proyectos creados."
            if console:
                console.print(Panel(mensaje, title="Proyectos", border_style="blue"))
            agregar_registro("proyecto_listar", "listar", True, mensaje)

        elif accion == "proyecto_contexto":
            clave = accion_data.get("clave", "")
            valor = accion_data.get("valor", "")
            if valor:
                contexto.guardar_contexto(clave, valor)
                mensaje = f"✅ Contexto guardado: {clave} = {valor}"
            else:
                valor_actual = contexto.obtener_contexto(clave)
                mensaje = f"{clave} = {valor_actual}" if valor_actual is not None else f"❌ No hay contexto para '{clave}'."
            if console:
                console.print(Panel(mensaje, title="Contexto Proyecto", border_style="blue"))
            agregar_registro("proyecto_contexto", clave, True, mensaje)

        # --- SISTEMA ---
        elif accion == "herramientas":
            lista = listar_herramientas()
            lineas = [f"🛠️ Herramientas disponibles ({len(lista)}):"]
            for h in lista:
                pel = " ⚠️" if h.get("peligroso") else ""
                lineas.append(f"  • {h['nombre']}{pel} — {h['descripcion']}")
            mensaje = "\n".join(lineas)
            if console:
                console.print(Panel(mensaje, title="Herramientas", border_style="blue"))
            agregar_registro("herramientas", "listar", True, mensaje)

        elif accion == "historial_sandbox":
            hist = tool_registry.tool_executor.obtener_historial_sandbox() if tool_registry.tool_executor else []
            if hist:
                lineas = [f"🛡️ Historial Sandbox ({len(hist)}):"]
                for h in hist[-10:]:
                    estado = "✅" if h["exito"] else "❌"
                    lineas.append(f"  {estado} {h['tipo']}: {h['objetivo'][:50]} ({h['intentos']} int.)")
                mensaje = "\n".join(lineas)
            else:
                mensaje = "✅ Sin historial de sandbox."
            if console:
                console.print(Panel(mensaje, title="Sandbox", border_style="blue"))
            agregar_registro("historial_sandbox", "ver", True, mensaje)

        elif accion == "mahoraga_status":
            eventos = mahoraga.recent(20)
            if eventos:
                lineas = [f"🌀 Mahoraga eventos ({len(eventos)}):"]
                for e in eventos[-20:]:
                    estado = "✅" if e["ok"] else "❌"
                    lineas.append(f"  {estado} [{e['kind']}] {e['detail']}")
                mensaje = "\n".join(lineas)
            else:
                mensaje = "🌀 Mahoraga activo, sin eventos aún."
            if console:
                console.print(Panel(mensaje, title="Mahoraga", border_style="magenta"))
            agregar_registro("mahoraga_status", "ver", True, mensaje)

        elif accion == "mahoraga_auto":
            objetivo = accion_data.get("objetivo", "") or accion_data.get("peticion", "") or accion_data.get("description", "")
            archivo = accion_data.get("archivo", "") or accion_data.get("filename", "") or "mahoraga_output.py"
            max_ciclos = int(accion_data.get("max_ciclos", 5))
            resultado = flujo_multiagente(objetivo, archivo, max_ciclos)
            ok_flow = bool(resultado.get("aprobado"))
            codigo = resultado.get("codigo", "")
            if codigo and archivo.endswith(".py"):
                ok_fix, codigo_fix, ev = mahoraga.auto_fix_python(codigo, llm_chat)
                resultado["codigo"] = codigo_fix
                resultado["aprobado"] = ok_flow and ok_fix
                mahoraga.log("mahoraga_auto_fix", ok_fix, objetivo, ev)
            mahoraga.log("mahoraga_auto", bool(resultado.get("aprobado")), objetivo, resultado.get("mensaje", ""))
            guardado = guardar_codigo_flujo(resultado.get("archivo") or archivo, resultado.get("codigo", ""))
            mensaje = f"Objetivo: {objetivo}\nAprobado: {resultado.get('aprobado')}\n{guardado}\n{resultado.get('mensaje','')}"
            if console:
                console.print(Panel(mensaje, title="Mahoraga Auto", border_style="magenta"))
            agregar_registro("mahoraga_auto", objetivo, bool(resultado.get("aprobado")) and "✅" in guardado, mensaje)

        else:
            if accion is None or accion == "chat":
                # El modelo respondió como chat sin acción específica
                mensaje = accion_data.get("message", "") if isinstance(accion_data, dict) else ""
                if not mensaje:
                    mensaje = respuesta_raw.strip()
                if console:
                    console.print(Panel(mensaje, title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
                else:
                    print(f"VERDIX AI: {mensaje}")
                agregar_registro("chat", mensaje, True, mensaje)
            else:
                if console:
                    console.print(f"[yellow]Acción no reconocida: {accion}[/]")
                agregar_registro("desconocida", str(accion), False, str(accion_data))


# ==========================================
# SPLASH
# ==========================================
def mostrar_splash(no_splash: bool = False):
    if no_splash or not console:
        return
    os.system('clear')
    infinito = (
        "[bold bright_green]      ∞      ∞      ∞[/]\n"
        "[bold bright_green]    ∞   ∞  ∞   ∞  ∞   ∞[/]\n"
        "[bold bright_green]   ∞     ∞∞     ∞∞     ∞[/]\n"
        "[bold bright_green]    ∞   ∞  ∞   ∞  ∞   ∞[/]\n"
        "[bold bright_green]      ∞      ∞      ∞[/]\n"
    )
    console.print(Align.center(Panel(
        f"{infinito}\n"
        f"[bold bright_green]{NOMBRE}[/]\n"
        f"[dim]Creado por NOX | v{VERSION} | Multi-Agente + Sandbox + GitHub + Vercel[/]\n",
        border_style="bright_green", padding=(1, 10))))
    import time
    time.sleep(0.6)
    os.system('clear')


# ==========================================
# MANEJO DE SEÑALES
# ==========================================
def manejar_senal(sig, frame):
    if console:
        console.print("\n[bold yellow]👋 Saliendo de VERDIX AI...[/]")
    _mostrar_resumen_final()
    sys.exit(0)


def _mostrar_resumen_final():
    if console and registro_acciones:
        console.print("\n[bold bright_green]═══ RESUMEN DE SESIÓN VERDIX ═══[/]")
        total = len(registro_acciones)
        exitos = sum(1 for r in registro_acciones if r["exito"])
        for r in registro_acciones[-20:]:
            estado = "✅" if r["exito"] else "❌"
            console.print(f"[dim]{r['fecha'][:19]}[/] {estado} [{r['tipo']}] {r['detalle'][:60]}")
        console.print(f"\n[bold]Total:[/] {total} acciones  |  "
                      f"[green]Éxitos:[/] {exitos}  |  "
                      f"[red]Fallos:[/] {total - exitos}")
        console.print("[bold bright_green]═══════════════════════════════[/]\n")
    elif console:
        console.print("\n[bold bright_green]No se ejecutó ninguna acción en esta sesión.[/]\n")


# ==========================================
# SYSTEM PROMPT
# ==========================================
def construir_system_prompt() -> str:
    lecciones = obtener_lecciones()
    proyecto_activo = f"Proyecto activo: {contexto.proyecto_actual} ({contexto.ruta_actual})" if contexto.proyecto_actual else "Ningún proyecto activo."
    return f'''Eres {NOMBRE} v{VERSION}, el arquitecto del ecosistema VERDIX. CREADO POR NOX.
Tienes acceso al sistema (usuario actual), puedes crear archivos, ejecutar comandos, y desplegar en GitHub y Vercel.

{proyecto_activo}

=== REGLAS DE ORO ===
1. SIEMPRE responde con un objeto JSON puro. NO escribas pensamientos ni texto antes del JSON.
2. CADA acción que modifique el sistema (create_file, edit_file, terminal, install_package, run_python) DEBE pasar primero por el sandbox. El sistema verificará automáticamente antes de inyectar al sistema real. Si falla, se auto-arregla hasta 5 veces.
3. Si creas un archivo, el sistema lo verificará en sandbox antes de guardarlo realmente.
4. Si un comando falla en el sandbox, el sistema intentará arreglarlo automáticamente.
5. NUNCA uses comillas alrededor de rutas con `~`.
6. Antes de decir que terminaste, asegúrate de que el sandbox haya aprobado la acción.

=== PROVEEDORES LLM ===
Puedes usar Groq, OpenAI o Ollama según la configuración del usuario.

=== ACCIONES PERMITIDAS ===
- {{"action": "chat", "message": "respuesta"}}
- {{"action": "terminal", "command": "comando", "password": "contraseña_sudo_si_se_necesita"}}
- {{"action": "create_file", "filename": "ruta", "content": "codigo"}}
- {{"action": "edit_file", "filename": "ruta", "content": "codigo"}}
- {{"action": "read_file", "filename": "ruta"}}
- {{"action": "verify_file", "filename": "ruta"}}
- {{"action": "list_dir", "ruta": ".", "profundidad": 2}}
- {{"action": "search_files", "patron": "texto", "ruta": ".", "extension": ".py"}}
- {{"action": "install_system_package", "package": "nombre", "method": "pip|apt"}}
- {{"action": "generate_image", "prompt": "desc"}}
- {{"action": "edit_image", "filename": "ruta", "edit_type": "blanco_negro|desenfoque|invertir|redimensionar", "archivo_salida": "opcional"}}
- {{"action": "search_web", "query": "busqueda"}}
- {{"action": "run_python", "filename": "ruta"}}
- {{"action": "multi_agent_flow", "peticion": "que construir", "archivo": "resultado.py", "max_ciclos": 5}}
- {{"action": "self_improve", "description": "cambio", "code": "codigo Python"}}
- {{"action": "github_resumen"}}
- {{"action": "github_list_repos"}}
- {{"action": "github_create_repo", "nombre": "repo", "descripcion": "desc", "privado": true}}
- {{"action": "github_upload_file", "usuario": "user", "repo": "repo", "ruta": "archivo.py", "contenido": "codigo", "mensaje_commit": "msg", "rama": "main"}}
- {{"action": "github_create_issue", "usuario": "user", "repo": "repo", "titulo": "titulo", "cuerpo": "desc", "etiquetas": ["bug"]}}
- {{"action": "vercel_resumen"}}
- {{"action": "vercel_list_deployments"}}
- {{"action": "vercel_deploy", "ruta": "./proyecto", "nombre": "mi-proyecto", "publica": true}}
- {{"action": "proyecto_crear", "nombre": "nombre", "ruta": "./", "descripcion": "desc"}}
- {{"action": "proyecto_activar", "nombre": "nombre"}}
- {{"action": "proyecto_listar"}}
- {{"action": "proyecto_contexto", "clave": "key", "valor": "valor"}}
- {{"action": "herramientas"}}
- {{"action": "historial_sandbox"}}
- {{"action": "mahoraga_status"}}
- {{"action": "mahoraga_auto", "objetivo": "qué construir/arreglar", "archivo": "salida.py", "max_ciclos": 5}}

=== MAHORAGA / ADAPTATIVO ===
- Si una acción falla, adapta el enfoque: simplifica, cambia herramienta, divide en pasos, reintenta con evidencia.
- Usa mahoraga_auto para tareas de construcción/arreglo autónomo con verificación.
- Nunca afirmes éxito sin evidencia (salida, archivo verificado, test/sintaxis).

=== MULTI-AGENTE ===
Puedes usar multi_agent_flow para construir código con verificación automática:
1. VERDIX-Programador escribe el código
2. VERDIX-Revisor lo revisa y aprueba o rechaza
3. Si rechaza, vuelve al Programador (máximo 5 ciclos)
4. Si aprueba, se guarda automáticamente

{lecciones}
'''


# ==========================================
# MAIN
# ==========================================
def main():
    global llm_provider, historial

    parser = argparse.ArgumentParser(description="VERDIX AI Terminal - Sistema Multi-Agente")
    parser.add_argument("--version", action="store_true", help="Mostrar versión y salir")
    parser.add_argument("--no-splash", action="store_true", help="Omitir pantalla de bienvenida")
    parser.add_argument("--clear-cache", action="store_true", help="Limpiar historial y caché")
    parser.add_argument("--proveedor", choices=["auto", "groq", "openai", "ollama", "local"], default=os.environ.get("VERDIX_PROVEEDOR","auto"),
                        help="Proveedor de LLM (default: groq)")
    parser.add_argument("--modelo", default=None, help="Modelo específico del proveedor")
    args = parser.parse_args()

    if args.version:
        print(f"{NOMBRE} v{VERSION}")
        return 0

    if args.clear_cache:
        limpiar_historial()
        historial = []
        if console:
            console.print("[bold yellow]🧹 Memoria y caché borrados.[/]")

    if not args.modelo:
        env_modelos = os.environ.get("VERDIX_MODELOS", "")
        if env_modelos:
            args.modelo = env_modelos.split(",")[0].strip()

    # Inicializar proveedor LLM
    modelo = args.modelo
    try:
        llm_provider = LLMProvider(proveedor=args.proveedor, modelo=modelo)
        if console and llm_provider and llm_provider.nombre_proveedor() == "local":
            console.print("[bold yellow]ℹ️ Modo local activo: no se requiere API key. Para IA completa, configura GROQ_API_KEY/OPENAI_API_KEY o usa Ollama.[/]")
    except Exception as e:
        if console:
            console.print(f"[bold red]Error inicializando LLM:[/] {e}")
        llm_provider = None

    # Inicializar executor de herramientas con sandbox
    inicializar_executor(llm_chat=llm_chat, max_intentos=5)

    signal.signal(signal.SIGINT, manejar_senal)

    # No bloquear: modo auto/local funciona sin API key.
    if not es_clave_valida(args.proveedor) and console:
        console.print(f"[bold yellow]⚠️ Proveedor {args.proveedor} sin credenciales; usando modo local.[/]")
        args.proveedor = "local"

    limpiar_cache_expirado()
    historial = [{"role": "system", "content": construir_system_prompt()}] + cargar_historial()

    mostrar_splash(no_splash=args.no_splash)
    if console:
        console.print(Panel(
            f"[bold bright_green]{NOMBRE} Code v{VERSION}[/]\n"
            f"[dim]Creado por NOX | Multi-Agente + Sandbox + GitHub + Vercel[/]\n"
            f"Escribe 'salir' para terminar.\n"
            f"Proveedor: {llm_provider.nombre_proveedor() if llm_provider else args.proveedor} | Modelo: {llm_provider.modelo if llm_provider else "N/A"}",
            border_style="bright_green"))
    else:
        print(f"{NOMBRE} Code v{VERSION} - Creado por NOX")

    while True:
        try:
            if console:
                proyecto_tag = f" [{contexto.proyecto_actual}]" if contexto.proyecto_actual else ""
                prompt = Prompt.ask(f"\n[bold green]NOX{proyecto_tag}[/]")
            else:
                prompt = input(f"\nNOX> ")
            if prompt is None:
                break
            if prompt.lower() in ['salir', 'exit', 'quit']:
                break
            if prompt.lower() == 'limpiar':
                limpiar_historial()
                historial = [{"role": "system", "content": construir_system_prompt()}]
                if console:
                    console.print("[bold yellow]🧹 Memoria y caché borrados.[/]")
                continue
            if prompt.lower() == 'herramientas':
                if console:
                    lista = listar_herramientas()
                    lineas = [f"🛠️ Herramientas ({len(lista)}):"]
                    for h in lista:
                        pel = " ⚠️" if h.get("peligroso") else ""
                        lineas.append(f"  • {h['nombre']}{pel} — {h['descripcion']}")
                    console.print(Panel("\n".join(lineas), title="Herramientas", border_style="blue"))
                continue
            if not prompt.strip():
                continue

            # Caché
            cache = get_cache(prompt)
            if cache:
                if console:
                    console.print("[bold cyan]📦 Desde caché (0 tokens):[/]")
                procesar_respuesta(cache)
                continue

            guardar_mensaje("user", prompt)
            historial.append({"role": "user", "content": prompt})
            historial_reducido = [historial[0]] + historial[-6:] if len(historial) > 6 else historial

            status = console.status("[bold yellow]Pensando...") if console else None
            if status:
                status.start()
            try:
                respuesta_raw = llm_chat_con_historial(
                    historial_reducido,
                    temperatura=0.2,
                    formato_json=True,
                )
            except Exception:
                if console:
                    console.print("[dim yellow]⚠️ Reintentando sin JSON estricto...[/]")
                respuesta_raw = llm_chat_con_historial(
                    historial_reducido,
                    temperatura=0.2,
                    formato_json=False,
                )
                match = re.search(r'(\{.*\})', respuesta_raw, re.DOTALL)
                if match:
                    respuesta_raw = match.group(1)
            finally:
                if status:
                    status.stop()

            guardar_mensaje("assistant", respuesta_raw)
            historial.append({"role": "assistant", "content": respuesta_raw})
            save_cache(prompt, respuesta_raw)

            procesar_respuesta(respuesta_raw)
        except KeyboardInterrupt:
            break
        except Exception as e:
            if console:
                console.print(f"[bold red]Error crítico:[/] {e}")
            else:
                print(f"Error crítico: {e}")

    _mostrar_resumen_final()


if __name__ == "__main__":
    main()

# === FIN DE NUEVAS FUNCIONES ===