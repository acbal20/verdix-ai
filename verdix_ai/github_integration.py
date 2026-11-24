#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integración VERDIX ↔ GitHub
Requiere la variable de entorno GITHUB_TOKEN (Personal Access Token con scopes: repo, user).
"""

import os
import json
import base64
import requests
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_API = "https://api.github.com"

headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}" if GITHUB_TOKEN else "",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _req(method, url, payload=None):
    if not GITHUB_TOKEN:
        return {"error": "Falta GITHUB_TOKEN en el entorno."}
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=payload, timeout=30)
        elif method == "PUT":
            r = requests.put(url, headers=headers, json=payload, timeout=30)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=30)
        else:
            return {"error": f"Método {method} no soportado."}
        try:
            return {"status": r.status_code, "data": r.json()}
        except Exception:
            return {"status": r.status_code, "data": r.text}
    except Exception as e:
        return {"error": str(e)}


def github_me():
    """Devuelve información del usuario autenticado."""
    return _req("GET", f"{GITHUB_API}/user")


def github_list_repos():
    """Lista los repositorios del usuario autenticado."""
    return _req("GET", f"{GITHUB_API}/user/repos?per_page=100")


def github_create_repo(nombre, descripcion="", privado=True):
    """Crea un nuevo repositorio en GitHub."""
    payload = {
        "name": nombre,
        "description": descripcion,
        "private": privado,
        "auto_init": False,
    }
    return _req("POST", f"{GITHUB_API}/user/repos", payload)


def github_get_repo(usuario, repo):
    """Obtiene información de un repositorio."""
    return _req("GET", f"{GITHUB_API}/repos/{usuario}/{repo}")


def github_upload_file(usuario, repo, ruta_archivo, contenido, mensaje_commit=None, rama="main"):
    """
    Sube o actualiza un archivo en un repositorio de GitHub usando la API de contenidos.
    `contenido` debe ser un string (se codifica a base64 internamente).
    """
    path = f"{usuario}/{repo}/contents/{ruta_archivo}"
    url = f"{GITHUB_API}/repos/{path}"

    # Verificar si el archivo ya existe para obtener su SHA (necesario para actualizar)
    existente = _req("GET", url)
    sha = None
    if isinstance(existente, dict) and existente.get("status") == 200:
        sha = existente["data"].get("sha")

    contenido_b64 = base64.b64encode(contenido.encode("utf-8")).decode("utf-8")
    payload = {
        "message": mensaje_commit or f"VERDIX: actualizar {ruta_archivo}",
        "content": contenido_b64,
        "branch": rama,
    }
    if sha:
        payload["sha"] = sha

    return _req("PUT", url, payload)


def github_create_issue(usuario, repo, titulo, cuerpo, etiquetas=None):
    """Crea un issue en un repositorio."""
    payload = {
        "title": titulo,
        "body": cuerpo,
    }
    if etiquetas:
        payload["labels"] = etiquetas
    return _req("POST", f"{GITHUB_API}/repos/{usuario}/{repo}/issues", payload)


def github_resumen():
    """Devuelve un resumen breve del usuario y sus repos."""
    me = github_me()
    repos = github_list_repos()
    salida = []
    if isinstance(me, dict) and me.get("status") == 200:
        d = me["data"]
        salida.append(f"👤 Usuario: {d.get('login')} ({d.get('name') or 'sin nombre'})")
        salida.append(f"📦 Repos públicos: {d.get('public_repos')} | Privados: {d.get('total_private_repos')}")
    else:
        salida.append("❌ No se pudo autenticar con GitHub.")
    if isinstance(repos, dict) and repos.get("status") == 200:
        salida.append(f"\n📁 Tus repositorios (últimos {min(10, len(repos['data']))}):")
        for r in repos["data"][:10]:
            privada = "🔒" if r.get("private") else "🌍"
            salida.append(f"  {privada} {r['full_name']} — {r.get('description') or 'sin descripción'}")
    else:
        salida.append("❌ No se pudo listar repositorios.")
    return "\n".join(salida)
