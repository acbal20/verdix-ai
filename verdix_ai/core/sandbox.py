#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sandbox de verificación automática para VERDIX.
Ningún cambio se aplica al sistema real sin pasar primero por pruebas aisladas.
Si falla, se intenta reparar automáticamente hasta N veces.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import ast
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from verdix_ai.config import RUTA_HOME, VERSION
import re

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError:
    Console = Panel = Confirm = None

console = Console() if Console else None


class SandboxResult:
    def __init__(self, exitoso: bool, mensaje: str, salida: str = "",
                 archivo_sandbox: Optional[str] = None,
                 intentos: int = 0):
        self.exitoso = exitoso
        self.mensaje = mensaje
        self.salida = salida
        self.archivo_sandbox = archivo_sandbox
        self.intentos = intentos


class Sandbox:
    """
    Entorno aislado para probar cambios antes de inyectarlos.
    Crea un directorio temporal donde se ejecutan las acciones.
    """

    def __init__(self, max_intentos: int = 3):
        self.max_intentos = max_intentos
        self.ruta_sandbox: Optional[str] = None
        self.archivos_creados: List[str] = []
        self.comandos_ejecutados: List[str] = []

    def _crear(self):
        if self.ruta_sandbox is None:
            self.ruta_sandbox = tempfile.mkdtemp(prefix="verdix_sandbox_")
            os.makedirs(self.ruta_sandbox, exist_ok=True)

    def _limpiar(self):
        if self.ruta_sandbox and os.path.exists(self.ruta_sandbox):
            shutil.rmtree(self.ruta_sandbox, ignore_errors=True)
            self.ruta_sandbox = None
        self.archivos_creados.clear()
        self.comandos_ejecutados.clear()

    def mapear_ruta(self, ruta_real: str) -> str:
        """Mapea una ruta real a su equivalente dentro del sandbox."""
        self._crear()
        ruta_abs = os.path.abspath(os.path.expanduser(ruta_real))
        home_abs = os.path.abspath(os.path.expanduser("~"))
        if ruta_abs.startswith(home_abs + os.sep):
            rel = os.path.relpath(ruta_abs, home_abs)
        else:
            rel = os.path.basename(ruta_abs)
        return os.path.join(self.ruta_sandbox, rel)

    def escribir_archivo(self, ruta_real: str, contenido: str) -> str:
        self._crear()
        ruta_sb = self.mapear_ruta(ruta_real)
        Path(ruta_sb).parent.mkdir(parents=True, exist_ok=True)
        Path(ruta_sb).write_text(contenido, encoding="utf-8")
        self.archivos_creados.append(ruta_sb)
        return ruta_sb

    def leer_archivo(self, ruta_sb: str) -> str:
        try:
            return Path(ruta_sb).read_text(encoding="utf-8")
        except Exception as e:
            return f"❌ Error leyendo {ruta_sb}: {e}"

    def ejecutar_comando(self, comando: str, password: Optional[str] = None) -> Tuple[int, str]:
        """
        Ejecuta un comando en un directorio temporal de sandbox.
        NOTA: No es un contenedor aislado; comandos peligrosos se bloquean por patrón.
        """
        import re
        self.comandos_ejecutados.append(comando)
        patrones_bloqueados = [
            r'\brm\b', r'\bmkfs\b', r'\bdd\b', r'\bshutdown\b', r'\breboot\b',
            r'\bhalt\b', r'\bpoweroff\b', r'\b:init\b', r'>\s*/dev/', r'\bchmod\b',
            r'\bchown\b', r'\bkill\b', r'\bpkill\b', r'\bsystemctl\b', r'\bservice\b',
            r'\bmount\b', r'\bumount\b', r'\bfdisk\b', r'\bparted\b',
        ]
        if any(re.search(p, comando, re.IGNORECASE) for p in patrones_bloqueados):
            return 1, "❌ Comando bloqueado en sandbox por seguridad."
        comando_limpio = comando.replace("sudo ", "").strip()
        try:
            res = subprocess.run(
                comando_limpio, shell=True,
                cwd=self.ruta_sandbox,
                capture_output=True, text=True, timeout=120
            )
            salida = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
            return res.returncode, salida.strip() or "(sin salida)"
        except Exception as e:
            return 1, f"❌ Error ejecutando en sandbox: {e}"

    def validar_python(self, ruta_sb: str) -> Tuple[bool, str]:
        try:
            ast.parse(Path(ruta_sb).read_text(encoding="utf-8"))
            return True, "✅ Sintaxis Python válida"
        except SyntaxError as e:
            return False, f"❌ Error de sintaxis: {e}"

    def destruir(self):
        self._limpiar()


class AutoArreglador:
    """
    Intenta arreglar código fallido usando el LLM, hasta max_intentos veces.
    """

    def __init__(self, llm_chat: Callable[[str], str], max_intentos: int = 3):
        self.llm_chat = llm_chat
        self.max_intentos = max_intentos

    def arreglar_codigo(self, codigo_roto: str, error: str,
                        contexto: str = "") -> Tuple[bool, str]:
        """
        Devuelve (exitoso, codigo_arreglado).
        """
        for intento in range(1, self.max_intentos + 1):
            if console:
                console.print(f"[bold yellow]🔧 Auto-arreglo intento {intento}/{self.max_intentos}...[/]")
            prompt = (
                f"El siguiente código Python tiene un error:\n"
                f"--- ERROR ---\n{error}\n"
                f"--- CÓDIGO ROTO ---\n{codigo_roto}\n"
                f"--- CONTEXTO ---\n{contexto}\n"
                f"Devuelve SOLO el código Python corregido, sin explicaciones, sin markdown, sin ```python."
            )
            try:
                respuesta = self.llm_chat(prompt)
                # Limpiar posibles bloques de código
                codigo_limpio = respuesta.strip()
                codigo_limpio = codigo_limpio.replace("```python", "").replace("```", "").strip()
                # Validar sintaxis
                ast.parse(codigo_limpio)
                return True, codigo_limpio
            except SyntaxError as e:
                error = str(e)
                codigo_roto = codigo_limpio
                continue
            except Exception as e:
                error = str(e)
                continue
        return False, codigo_roto


class VerificadorPrevio:
    """
    Ejecuta una acción en el sandbox, verifica que funcione,
    y solo entonces autoriza la inyección al sistema real.
    """

    def __init__(self, max_intentos: int = 3):
        self.max_intentos = max_intentos
        self.historial_verificaciones: List[Dict[str, Any]] = []

    def verificar_crear_archivo(self, ruta_real: str, contenido: str,
                                llm_chat: Callable[[str], str]) -> SandboxResult:
        """
        Prueba crear un archivo en sandbox, valida sintaxis si es Python,
        y devuelve si es seguro inyectar.
        """
        sb = Sandbox(max_intentos=self.max_intentos)
        intentos = 0
        contenido_actual = contenido

        while intentos < self.max_intentos:
            intentos += 1
            try:
                ruta_sb = sb.escribir_archivo(ruta_real, contenido_actual)
                # Validar sintaxis si es Python
                if ruta_real.endswith(".py"):
                    valido, msg = sb.validar_python(ruta_sb)
                    if not valido:
                        # Intentar arreglar
                        ok, codigo_fix = AutoArreglador(llm_chat, self.max_intentos).arreglar_codigo(
                            contenido_actual, msg, contexto="crear_archivo")
                        if ok:
                            contenido_actual = codigo_fix
                            continue
                        else:
                            sb.destruir()
                            return SandboxResult(False, msg, archivo_sandbox=ruta_sb, intentos=intentos)
                # Si llegó aquí, pasó las pruebas
                self._registrar(ruta_real, "create_file", True, intentos, contenido_actual)
                sb.destruir()
                return SandboxResult(True, f"✅ Verificado en sandbox ({intentos} intento(s)).",
                                     archivo_sandbox=ruta_sb, intentos=intentos)
            except Exception as e:
                sb.destruir()
                return SandboxResult(False, f"❌ Error en sandbox: {e}", intentos=intentos)

        sb.destruir()
        return SandboxResult(False, f"❌ No se pudo verificar tras {self.max_intentos} intentos.", intentos=intentos)

    def verificar_comando(self, comando: str,
                          llm_chat: Callable[[str], str]) -> SandboxResult:
        """
        Prueba un comando en sandbox. Si falla, intenta arreglar el comando.
        """
        sb = Sandbox(max_intentos=self.max_intentos)
        intentos = 0
        comando_actual = comando

        while intentos < self.max_intentos:
            intentos += 1
            codigo_ret, salida = sb.ejecutar_comando(comando_actual)
            if codigo_ret == 0:
                self._registrar(comando, "terminal", True, intentos, comando_actual)
                sb.destruir()
                return SandboxResult(True, f"✅ Comando verificado ({intentos} intento(s)).\n{salida}",
                                     intentos=intentos)
            else:
                # Intentar arreglar comando con LLM
                ok, comando_fix = AutoArreglador(llm_chat, self.max_intentos).arreglar_codigo(
                    comando_actual, salida, contexto="comando_terminal")
                if ok:
                    comando_actual = comando_fix
                    continue
                else:
                    self._registrar(comando, "terminal", False, intentos, comando_actual)
                    sb.destruir()
                    return SandboxResult(False, salida, intentos=intentos)

        sb.destruir()
        return SandboxResult(False, f"❌ Comando falló tras {self.max_intentos} intentos.", intentos=intentos)

    def _registrar(self, objetivo: str, tipo: str, exito: bool,
                   intentos: int, detalle: str):
        self.historial_verificaciones.append({
            "objetivo": objetivo,
            "tipo": tipo,
            "exito": exito,
            "intentos": intentos,
            "detalle": detalle[:200],
            "fecha": datetime.now().isoformat(),
        })

    def obtener_historial(self) -> List[Dict[str, Any]]:
        return list(self.historial_verificaciones)


# Instancia global del verificador
verificador = VerificadorPrevio()

def verificar_y_inyectar(tipo_accion: str,
                         ejecutar_real: Callable[[], str],
                         sandbox_result: SandboxResult) -> str:
    """
    Si el sandbox fue exitoso, ejecuta la acción real y devuelve su resultado.
    Si falló, devuelve el error del sandbox sin tocar el sistema real.
    """
    if not sandbox_result.exitoso:
        return f"❌ {sandbox_result.mensaje}\n🛡️ No se inyectó al sistema real (bloqueado por sandbox)."

    try:
        resultado_real = ejecutar_real()
        return f"✅ {sandbox_result.mensaje}\n🚀 Inyectado al sistema real:\n{resultado_real}"
    except Exception as e:
        return f"❌ Error al inyectar al sistema real: {e}"
