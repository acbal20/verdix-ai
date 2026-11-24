#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuración centralizada de VERDIX AI
"""

import os
from pathlib import Path

# Rutas base
RUTA_HOME = os.path.expanduser("~")
RUTA_VERDIX = Path(RUTA_HOME) / "verdix_central" / "04-IA-Y-AUTOMATIZACION"
RUTA_VERDIX.mkdir(parents=True, exist_ok=True)

RUTA_PROYECTOS = Path(RUTA_HOME) / "verdix_central" / "01-PROYECTOS"
RUTA_IA = Path(RUTA_HOME) / "verdix_central" / "04-IA-Y-AUTOMATIZACION"

# Bases de datos
DB_MEMORIA = str(RUTA_VERDIX / "verdix_memory.db")
DB_ERRORES = str(RUTA_VERDIX / "verdix_errores.db")
DB_PROYECTOS = str(RUTA_VERDIX / "verdix_proyectos.db")

# Versión
VERSION = "30.0"
NOMBRE = "VERDIX AI"

# Proveedores de LLM soportados
PROVEEDORES_DISPONIBLES = ["groq", "openai", "ollama"]

# Configuración por defecto
CONFIG_DEFAULT = {
    "proveedor": "groq",
    "modelo_groq": "openai/gpt-oss-20b",
    "modelo_openai": "gpt-4o-mini",
    "modelo_ollama": "llama3",
    "temperatura": 0.2,
    "max_tokens": 4000,
    "max_ciclos_agente": 5,
    "cache_ttl_horas": 24,
    "auto_mejora": True,
    "sandbox_seguro": True,
    "historial_max": 50,
}

# Claves de entorno
def obtener_api_key(proveedor="groq"):
    mapeo = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "ollama": "OLLAMA_API_KEY",
    }
    return os.environ.get(mapeo.get(proveedor, "GROQ_API_KEY"))

def obtener_github_token():
    return os.environ.get("GITHUB_TOKEN")

def obtener_vercel_token():
    return os.environ.get("VERCEL_TOKEN")

def obtener_vercel_team_id():
    return os.environ.get("VERCEL_TEAM_ID")

def es_clave_valida(proveedor="groq"):
    return bool(obtener_api_key(proveedor))

# Colores de tema VERDIX
COLOR_PRIMARIO = "bright_green"
COLOR_SECUNDARIO = "cyan"
COLOR_PELIGRO = "bold red"
COLOR_EXITO = "bold green"
COLOR_ADVERTENCIA = "bold yellow"
