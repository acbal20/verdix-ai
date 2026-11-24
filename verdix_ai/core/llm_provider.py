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

    def __init__(self, proveedor: str = "groq", modelo: Optional[str] = None):
        self.proveedor = proveedor.lower()
        if self.proveedor not in PROVEEDORES_DISPONIBLES:
            raise ValueError(f"Proveedor no soportado: {self.proveedor}")

        self.modelo = modelo or CONFIG_DEFAULT.get(f"modelo_{self.proveedor}", "default")
        self.api_key = obtener_api_key(self.proveedor)
        self._client = None
        self._inicializar()

    def _inicializar(self):
        if self.proveedor == "groq" and Groq and self.api_key:
            self._client = Groq(api_key=self.api_key)
        elif self.proveedor == "openai" and openai and self.api_key:
            openai.api_key = self.api_key
            self._client = openai.OpenAI(api_key=self.api_key)
        elif self.proveedor == "ollama":
            # Ollama no requiere clave; se conecta a localhost:11434
            self._client = "ollama"

    def disponible(self) -> bool:
        return self._client is not None

    def chat(
        self,
        mensajes: List[Dict[str, str]],
        temperatura: float = 0.2,
        max_tokens: int = 4000,
        formato_json: bool = False,
    ) -> str:
        if not self.disponible():
            return json.dumps({
                "action": "chat",
                "message": f"❌ Proveedor {self.proveedor} no disponible. Falta API key o servicio.",
            })

        try:
            if self.proveedor == "groq":
                return self._chat_groq(mensajes, temperatura, max_tokens, formato_json)
            elif self.proveedor == "openai":
                return self._chat_openai(mensajes, temperatura, max_tokens, formato_json)
            elif self.proveedor == "ollama":
                return self._chat_ollama(mensajes, temperatura, max_tokens, formato_json)
        except Exception as e:
            return json.dumps({
                "action": "chat",
                "message": f"❌ Error en {self.proveedor}: {e}",
            })

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
