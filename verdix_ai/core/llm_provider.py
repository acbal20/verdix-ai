#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Soporte multi-proveedor de LLM: Groq, OpenAI y Ollama (local).
"""

import os
import json
import requests
from typing import List, Dict, Optional, Any

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    import openai
except ImportError:
    openai = None

from verdix_ai.config import (
    obtener_api_key, PROVEEDORES_DISPONIBLES,
    CONFIG_DEFAULT,
)


class LLMProvider:
    """Proveedor de LLM unificado."""

    def __init__(self, proveedor: str = "auto", modelo: Optional[str] = None):
        self.proveedor = proveedor.lower()
        self.modelo = modelo
        self.api_key = None
        self._client = None
        self._resolved = None
        self._inicializar()

    def _resolver_auto(self):
        # Prioridad: claves configuradas -> ollama local -> local
        for p in ("groq", "openai"):
            if obtener_api_key(p):
                return p
        # probar ollama
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.5)
            if r.status_code == 200:
                return "ollama"
        except Exception:
            pass
        return "local"

    def _inicializar(self):
        prov = self._resolver_auto() if self.proveedor == "auto" else self.proveedor
        if prov not in PROVEEDORES_DISPONIBLES:
            prov = "local"
        self._resolved = prov
        self.api_key = obtener_api_key(prov) if prov in ("groq", "openai", "ollama") else None
        self.modelo = self.modelo or CONFIG_DEFAULT.get(f"modelo_{prov}", CONFIG_DEFAULT.get("modelo_groq", "default"))

        if prov == "groq" and Groq and self.api_key:
            self._client = Groq(api_key=self.api_key)
        elif prov == "openai" and openai and self.api_key:
            openai.api_key = self.api_key
            self._client = openai.OpenAI(api_key=self.api_key)
        elif prov == "ollama":
            self._client = "ollama"
        elif prov == "local":
            self._client = "local"
        else:
            self._client = "local"
            self._resolved = "local"

    def disponible(self) -> bool:
        return self._client is not None

    def nombre_proveedor(self) -> str:
        return self._resolved or self.proveedor

    def chat(
        self,
        mensajes: List[Dict[str, str]],
        temperatura: float = 0.2,
        max_tokens: int = 4000,
        formato_json: bool = False,
    ) -> str:
        prov = self.nombre_proveedor()
        if prov == "local":
            return self._chat_local(mensajes, formato_json=formato_json)
        if not self.disponible():
            return self._chat_local(mensajes, formato_json=formato_json)

        try:
            if prov == "groq":
                return self._chat_groq(mensajes, temperatura, max_tokens, formato_json)
            elif prov == "openai":
                return self._chat_openai(mensajes, temperatura, max_tokens, formato_json)
            elif prov == "ollama":
                return self._chat_ollama(mensajes, temperatura, max_tokens, formato_json)
        except Exception as e:
            # Fallback automático: no bloquear al usuario por falta de API/key
            return self._chat_local(mensajes, formato_json=formato_json, error=str(e))
        return self._chat_local(mensajes, formato_json=formato_json)

    def _chat_groq(self, mensajes, temperatura, max_tokens, formato_json):
        kwargs = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": temperatura,
            "max_tokens": max_tokens,
        }
        if formato_json:
            kwargs["response_format"] = {"type": "json_object"}
        completion = self._client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content.strip()

    def _chat_openai(self, mensajes, temperatura, max_tokens, formato_json):
        kwargs = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": temperatura,
            "max_tokens": max_tokens,
        }
        if formato_json:
            kwargs["response_format"] = {"type": "json_object"}
        completion = self._client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content.strip()

    def _chat_ollama(self, mensajes, temperatura, max_tokens, formato_json):
        payload = {
            "model": self.modelo,
            "messages": mensajes,
            "stream": False,
            "options": {
                "temperature": temperatura,
                "num_predict": max_tokens,
            },
        }
        if formato_json:
            payload["format"] = "json"
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "")


    def _chat_local(self, mensajes, formato_json=False, error: Optional[str] = None) -> str:
        """Modo local sin API: responde comandos básicos y guía al usuario."""
        user = ""
        for m in reversed(mensajes):
            if m.get("role") == "user":
                user = str(m.get("content", ""))
                break
        text = user.strip()
        low = text.lower()

        def j(obj):
            return json.dumps(obj, ensure_ascii=False)

        if low in ("ayuda", "help", "/help"):
            return j({"action": "chat", "message": "Modo local activo (sin API key). Puedo ejecutar acciones directas: 'lista archivos', 'lee <archivo>', 'crea archivo <ruta> con ...', 'ejecuta <comando>', 'busca web <query>', 'estado mahoraga'. Para IA completa, configura GROQ_API_KEY u OpenAI/Ollama, pero no es obligatorio."})
        if "estado mahoraga" in low or low == "mahoraga":
            return j({"action": "mahoraga_status"})
        if low.startswith("lista") or "listar archivos" in low or "list dir" in low:
            ruta = "."
            m = re.search(r"(?:en|de)\s+([~/\.\w\-]+)", text)
            if m:
                ruta = m.group(1)
            return j({"action": "list_dir", "ruta": ruta, "profundidad": 2})
        if low.startswith("lee ") or low.startswith("leer "):
            m = re.search(r"(?:lee|leer)\s+(.+)", text, re.I)
            if m:
                return j({"action": "read_file", "filename": m.group(1).strip().strip('"\'')})
        if low.startswith("verifica ") or "verificar archivo" in low:
            m = re.search(r"verifica[r]?\s+(.+)", text, re.I)
            if m:
                return j({"action": "verify_file", "filename": m.group(1).strip().strip('"\'')})
        if low.startswith("ejecuta ") or low.startswith("corre "):
            m = re.search(r"(?:ejecuta|corre)\s+(.+)", text, re.I)
            if m:
                return j({"action": "terminal", "command": m.group(1).strip()})
        if low.startswith("busca web ") or low.startswith("buscar web "):
            m = re.search(r"busca[r]? web\s+(.+)", text, re.I)
            if m:
                return j({"action": "search_web", "query": m.group(1).strip()})
        if low.startswith("crea archivo ") or low.startswith("crear archivo "):
            m = re.search(r"(?:crea|crear) archivo\s+([^\n]+?)(?:\s+con\s+|\n)([\s\S]+)$", text, re.I)
            if m:
                return j({"action": "create_file", "filename": m.group(1).strip().strip('"\' '), "content": m.group(2)})
        if low.startswith("github resumen"):
            return j({"action": "github_resumen"})
        if low.startswith("vercel resumen"):
            return j({"action": "vercel_resumen"})

        if any(k in low for k in ["crea un", "genera un", "hazme un", "script", "programa", "código", "codigo"]):
            return j({"action": "chat", "message": "Estoy en modo local sin IA externa. Puedo crear archivos si me das el contenido exacto. Ejemplo: 'crea archivo hola.py con print(\"hola\")'. Para generación automática de código, puedes configurar una API key o instalar Ollama, pero no es obligatorio."})
        if "error" in low or "arregla" in low or "fix" in low:
            return j({"action": "chat", "message": "Modo local: puedo verificar/ejecutar archivos y mostrar errores. Dime: 'verifica archivo.py' o 'ejecuta python archivo.py'. Para auto-reparación inteligente, activa un proveedor LLM opcional."})

        msg = "Modo local activo (sin API key). Puedo hacer acciones directas: listar/leer/verificar/crear archivos, ejecutar comandos, buscar web y ver estado. Escribe 'ayuda' para ejemplos."
        if error:
            msg += f" (Fallback automático por error de proveedor: {error[:120]})"
        return j({"action": "chat", "message": msg})
