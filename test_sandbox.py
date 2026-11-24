#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueba del sistema sandbox y multi-agente de VERDIX (sin API key real).
"""
import sys
import os
import ast

sys.path.insert(0, '/home/nox/verdix-ai')
os.environ.setdefault('GROQ_API_KEY', 'gsk_TEST')

from verdix_ai.core.sandbox import Sandbox, AutoArreglador, VerificadorPrevio
from verdix_ai.core.tool_registry import (
    herramienta_crear_archivo, herramienta_verificar_archivo,
    herramienta_ejecutar_python, herramienta_terminal,
    ToolExecutor, inicializar_executor
)

# --- Prueba 1: Sandbox crear archivo válido ---
print("=" * 60)
print("PRUEBA 1: Sandbox - archivo Python válido")
print("=" * 60)
sb = Sandbox()
ruta = sb.escribir_archivo("test_hola.py", "print('Hola VERDIX')\n")
valido, msg = sb.validar_python(ruta)
print(f"  Resultado: {'✅ Válido' if valido else '❌ Inválido'} - {msg}")
sb.destruir()

# --- Prueba 2: Sandbox archivo con error de sintaxis ---
print("\n" + "=" * 60)
print("PRUEBA 2: Sandbox - archivo con error de sintaxis")
print("=" * 60)
sb = Sandbox()
ruta = sb.escribir_archivo("test_roto.py", "print('Hola'\n")  # Falta paréntesis
valido, msg = sb.validar_python(ruta)
print(f"  Resultado: {'✅ Válido' if valido else '❌ Inválido'} - {msg}")
sb.destruir()

# --- Prueba 3: Auto-arreglador con mock ---
print("\n" + "=" * 60)
print("PRUEBA 3: Auto-arreglador (mock)")
print("=" * 60)

def llm_mock(prompt):
    # Simular que el LLM devuelve código corregido
    if "print('Hola'" in prompt:
        return "print('Hola corregido')\n"
    return prompt

arreglador = AutoArreglador(llm_mock, max_intentos=3)
codigo_roto = "print('Hola'\n"
error = "SyntaxError: unexpected EOF"
ok, codigo_fix = arreglador.arreglar_codigo(codigo_roto, error)
print(f"  Código original: {repr(codigo_roto)}")
print(f"  Código arreglado: {repr(codigo_fix)}")
print(f"  ¿Exitoso?: {'✅ Sí' if ok else '❌ No'}")

# --- Prueba 4: VerificadorPrevio ---
print("\n" + "=" * 60)
print("PRUEBA 4: VerificadorPrevio - crear archivo")
print("=" * 60)
verificador = VerificadorPrevio(max_intentos=3)
resultado = verificador.verificar_crear_archivo(
    "/tmp/verdix_test_prueba.py",
    "print('Funciona')\n",
    llm_mock
)
print(f"  Exitoso: {'✅ Sí' if resultado.exitoso else '❌ No'}")
print(f"  Mensaje: {resultado.mensaje}")
print(f"  Intentos: {resultado.intentos}")

# --- Prueba 5: Verificador con código roto (debe arreglar) ---
print("\n" + "=" * 60)
print("PRUEBA 5: VerificadorPrevio - código roto con auto-arreglo")
print("=" * 60)
resultado2 = verificador.verificar_crear_archivo(
    "/tmp/verdix_test_roto.py",
    "print('Hola'\n",  # SyntaxError
    llm_mock
)
print(f"  Exitoso: {'✅ Sí' if resultado2.exitoso else '❌ No'}")
print(f"  Mensaje: {resultado2.mensaje}")
print(f"  Intentos: {resultado2.intentos}")

# --- Prueba 6: ToolExecutor ---
print("\n" + "=" * 60)
print("PRUEBA 6: ToolExecutor con sandbox")
print("=" * 60)
executor = ToolExecutor(llm_chat=llm_mock, max_intentos=3)
resultado_exec = executor.ejecutar("create_file", filename="/tmp/verdix_exec_test.py", content="print('Ejecutor OK')\n")
print(f"  Resultado: {resultado_exec}")

# --- Prueba 7: Contexto de proyecto ---
print("\n" + "=" * 60)
print("PRUEBA 7: Contexto de proyecto")
print("=" * 60)
from verdix_ai.core.project_context import contexto
mensaje = contexto.crear_proyecto("test-proyecto", "/tmp/verdix_test_proyecto", "Proyecto de prueba")
print(f"  {mensaje}")
mensaje2 = contexto.activar_proyecto("test-proyecto")
print(f"  {mensaje2}")
contexto.guardar_contexto("version", "1.0.0")
valor = contexto.obtener_contexto("version")
print(f"  Contexto recuperado: version = {valor}")

print("\n" + "=" * 60)
print("TODAS LAS PRUEBAS COMPLETADAS")
print("=" * 60)