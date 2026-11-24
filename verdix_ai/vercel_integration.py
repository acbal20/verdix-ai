#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integración VERDIX ↔ Vercel
Requiere las variables de entorno:
  VERCEL_TOKEN   (token de API de Vercel)
  VERCEL_TEAM_ID (opcional, ID del equipo si es necesario)
"""

import os
import json
import requests

VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
VERCEL_TEAM_ID = os.environ.get("VERCEL_TEAM_ID")
VERCEL_API = "https://api.vercel.com"

headers = {
    "Authorization": f"Bearer {VERCEL_TOKEN}" if VERCEL_TOKEN else "",
    "Content-Type": "application/json",
}


def _req(method, url, payload=None, params=None):
    if not VERCEL_TOKEN:
        return {"error": "Falta VERCEL_TOKEN en el entorno."}
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=60)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=payload, params=params, timeout=60)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, params=params, timeout=60)
        else:
            return {"error": f"Método {method} no soportado."}
        try:
            return {"status": r.status_code, "data": r.json()}
        except Exception:
            return {"status": r.status_code, "data": r.text}
    except Exception as e:
        return {"error": str(e)}


def vercel_user():
    """Devuelve información del usuario autenticado en Vercel."""
    return _req("GET", f"{VERCEL_API}/v2/user")


def vercel_projects():
    """Lista los proyectos de Vercel."""
    params = {}
    if VERCEL_TEAM_ID:
        params["teamId"] = VERCEL_TEAM_ID
    return _req("GET", f"{VERCEL_API}/v10/projects", params=params)


def vercel_deploy_directorio(ruta_directorio, nombre_proyecto=None, publica=True):
    """
    Despliega un directorio local en Vercel usando la API de implementaciones.
    Nota: Vercel prefiere recibir los archivos comprimidos o individualmente.
    Esta función hace un despliegue simple enviando los archivos del directorio.
    """
    import glob
    import mimetypes

    archivos = []
    for path in glob.glob(os.path.join(ruta_directorio, "**", "*"), recursive=True):
        if os.path.isfile(path):
            rel = os.path.relpath(path, ruta_directorio)
            try:
                with open(path, "rb") as f:
                    contenido = f.read()
                archivos.append({
                    "file": rel,
                    "data": contenido.decode("utf-8", errors="replace"),
                })
            except Exception:
                # Archivos binarios: se omiten en este despliegue simple de texto
                pass

    if not archivos:
        return {"error": "No se encontraron archivos de texto en el directorio."}

    payload = {
        "name": nombre_proyecto or os.path.basename(ruta_directorio) or "verdix-deploy",
        "files": archivos,
    }
    if publica:
        payload["public"] = True

    params = {}
    if VERCEL_TEAM_ID:
        params["teamId"] = VERCEL_TEAM_ID

    return _req("POST", f"{VERCEL_API}/v13/deployments", payload=payload, params=params)


def vercel_list_deployments():
    """Lista los despliegues recientes."""
    params = {"limit": 10}
    if VERCEL_TEAM_ID:
        params["teamId"] = VERCEL_TEAM_ID
    return _req("GET", f"{VERCEL_API}/v13/deployments", params=params)


def vercel_resumen():
    """Devuelve un resumen breve de Vercel."""
    user = vercel_user()
    proyectos = vercel_projects()
    salida = []
    if isinstance(user, dict) and user.get("status") == 200:
        d = user["data"]
        salida.append(f"☁️ Vercel usuario: {d.get('username') or d.get('email') or 'desconocido'}")
    else:
        salida.append("❌ No se pudo autenticar con Vercel.")
    if isinstance(proyectos, dict) and proyectos.get("status") == 200:
        lista = proyectos["data"]
        salida.append(f"🚀 Proyectos: {len(lista)}")
        for p in lista[:10]:
            salida.append(f"  • {p.get('name')} — {p.get('links', {}).get('domains', [''])[0] or 'sin dominio'}")
    else:
        salida.append("❌ No se pudo listar proyectos.")
    return "\n".join(salida)
