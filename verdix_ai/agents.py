#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema multi-agente VERDIX
Agentes especializados que colaboran entre sí.
"""

import ast
import re
import json
import subprocess
import sys
import os
import time
from datetime import datetime

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError:
    Console = Panel = Confirm = None

console = Console() if Console else None

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if (Groq and GROQ_API_KEY) else None

MODELO = "openai/gpt-oss-20b"


class Agent:
    """Agente base de VERDIX."""
    def __init__(self, nombre, rol, system_prompt, modelo=MODELO):
        self.nombre = nombre
        self.rol = rol
        self.system_prompt = system_prompt
        self.modelo = modelo
        self.historial = [{"role": "system", "content": system_prompt}]

    def pensar(self, mensaje, temperatura=0.2, max_tokens=3000, formato_json=True):
        """Envía un mensaje al LLM y devuelve la respuesta cruda."""
        if not client:
            return "❌ No hay cliente Groq configurado. Falta GROQ_API_KEY."
        self.historial.append({"role": "user", "content": mensaje})
        # Mantener solo los últimos 6 mensajes + system
        recortado = [self.historial[0]] + self.historial[-6:]
        try:
            kwargs = {
                "model": self.modelo,
                "messages": recortado,
                "temperature": temperatura,
                "max_tokens": max_tokens,
            }
            if formato_json:
                kwargs["response_format"] = {"type": "json_object"}
            completion = client.chat.completions.create(**kwargs)
            respuesta = completion.choices[0].message.content.strip()
            self.historial.append({"role": "assistant", "content": respuesta})
            return respuesta
        except Exception as e:
            return f"❌ Error en {self.nombre}: {e}"


class ProgramadorAgent(Agent):
    """Agente que escribe y genera código."""
    def __init__(self):
        super().__init__(
            nombre="VERDIX-Programador",
            rol="Desarrollador de software",
            system_prompt=(
                "Eres VERDIX-Programador, un experto desarrollador de software. "
                "Tu trabajo es escribir código limpio, funcional y bien documentado. "
                "SIEMPRE responde con un objeto JSON puro con esta estructura:\n"
                '{"action": "chat", "message": "explicación de qué harás", "codigo": "código completo o vacío", '
                '"archivo": "ruta del archivo a crear/editar o vacío", "lenguaje": "python|javascript|etc o vacío"}\n'
                "No escribas texto fuera del JSON."
            ),
        )


class RevisorAgent(Agent):
    """Agente que revisa código, encuentra errores y sugiere correcciones."""
    def __init__(self):
        super().__init__(
            nombre="VERDIX-Revisor",
            rol="QA Engineer y revisor de código",
            system_prompt=(
                "Eres VERDIX-Revisor, un experto en calidad de software y seguridad. "
                "Tu trabajo es revisar código, encontrar errores de sintaxis, lógica, "
                "seguridad y buenas prácticas. SIEMPRE responde con un objeto JSON puro:\n"
                '{"action": "chat", "message": "revisión del código", "aprobado": true|false, '
                '"errores": ["lista de errores encontrados"], "correccion": "código corregido completo o vacío", '
                '"archivo": "ruta del archivo o vacío"}\n'
                "No escribas texto fuera del JSON."
            ),
        )


class OrquestadorAgent(Agent):
    """Agente que coordina el flujo entre programador y revisor."""
    def __init__(self):
        super().__init__(
            nombre="VERDIX-Orquestador",
            rol="Orquestador de flujos de desarrollo",
            system_prompt=(
                "Eres VERDIX-Orquestador. Coordinas el trabajo entre el Programador y el Revisor. "
                "Recibes una petición del usuario, la pasas al Programador, luego al Revisor, "
                "y si el Revisor no aprueba, devuelves al Programador para corregir (máximo 3 ciclos). "
                "SIEMPRE responde con un objeto JSON puro:\n"
                '{"action": "chat", "message": "estado del flujo", "siguiente": "programador|revisor|finalizar", '
                '"codigo": "código actual", "archivo": "ruta del archivo", "ciclo": número}\n'
                "No escribas texto fuera del JSON."
            ),
        )


def flujo_multiagente(peticion, archivo_destino=None, max_ciclos=3):
    """
    Ejecuta un flujo colaborativo:
    1. Orquestador recibe la petición
    2. Programador escribe código
    3. Revisor revisa y aprueba o rechaza
    4. Si rechaza, vuelve al Programador (hasta max_ciclos)
    5. Si aprueba, se guarda el archivo y se devuelve el resultado
    """
    programador = ProgramadorAgent()
    revisor = RevisorAgent()
    orquestador = OrquestadorAgent()

    ciclo = 0
    codigo_actual = ""
    aprobado = False
    mensaje_ultimo = ""

    while ciclo < max_ciclos and not aprobado:
        ciclo += 1

        if ciclo == 1:
            # Paso 1: Orquestador inicializa
            resp_orq = orquestador.pensar(
                f"Petición del usuario: {peticion}\nArchivo destino: {archivo_destino or 'no especificado'}\n"
                f"Inicia el flujo. Indica que el Programador debe escribir el código."
            )
            try:
                datos_orq = json.loads(resp_orq)
                mensaje_ultimo = datos_orq.get("message", "")
            except Exception:
                datos_orq = {}
                mensaje_ultimo = resp_orq

        # Paso 2: Programador escribe o corrige
        if ciclo == 1:
            msg_prog = (
                f"Escribe el código para: {peticion}\n"
                f"Archivo: {archivo_destino or 'programa.py'}\n"
                f"Mensaje del orquestador: {mensaje_ultimo}"
            )
        else:
            msg_prog = (
                f"El Revisor rechazó tu código anterior por estos errores: {errores_previos}\n"
                f"Corrige el código para: {peticion}\n"
                f"Archivo: {archivo_destino or 'programa.py'}\n"
                f"Código anterior:\n{codigo_actual}"
            )

        resp_prog = programador.pensar(msg_prog)
        try:
            datos_prog = json.loads(resp_prog)
            codigo_actual = datos_prog.get("codigo", "")
            archivo_destino = datos_prog.get("archivo", archivo_destino or "programa.py")
            mensaje_ultimo = datos_prog.get("message", "")
        except Exception:
            datos_prog = {}
            codigo_actual = resp_prog
            mensaje_ultimo = resp_prog

        # Paso 3: Revisor revisa
        resp_rev = revisor.pensar(
            f"Revisa este código:\n{codigo_actual}\n"
            f"Archivo: {archivo_destino}\n"
            f"¿Está correcto, funcional y seguro?"
        )
        try:
            datos_rev = json.loads(resp_rev)
            aprobado = datos_rev.get("aprobado", False)
            errores_previos = "; ".join(datos_rev.get("errores", []))
            mensaje_ultimo = datos_rev.get("message", "")
            if aprobado:
                codigo_final = datos_rev.get("correccion", codigo_actual)
            else:
                codigo_final = codigo_actual
        except Exception:
            aprobado = False
            errores_previos = "El revisor no devolvió JSON válido."
            mensaje_ultimo = resp_rev
            codigo_final = codigo_actual

    resultado = {
        "aprobado": aprobado,
        "ciclos": ciclo,
        "archivo": archivo_destino,
        "codigo": codigo_final,
        "mensaje": mensaje_ultimo,
    }
    return resultado


def guardar_codigo_flujo(archivo, codigo):
    """Guarda el código resultante del flujo en un archivo."""
    try:
        directorio = os.path.dirname(archivo)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        with open(archivo, "w", encoding="utf-8") as f:
            f.write(codigo)
        # Validar si es Python
        if archivo.endswith(".py"):
            ast.parse(codigo)
        return f"✅ Archivo '{archivo}' guardado ({len(codigo)} bytes)."
    except SyntaxError as e:
        return f"❌ Error de sintaxis al guardar '{archivo}': {e}"
    except Exception as e:
        return f"❌ Error guardando '{archivo}': {e}"
