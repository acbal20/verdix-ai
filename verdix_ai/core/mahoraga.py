#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mahoraga: modo adaptativo/automático para VERDIX.
Detecta fallos, prueba alternativas, registra evidencia y se auto-repara.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AdaptationEvent:
    ts: str
    kind: str
    ok: bool
    detail: str
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MahoragaEngine:
    """Motor de adaptación automática."""

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self.events: List[AdaptationEvent] = []

    def log(self, kind: str, ok: bool, detail: str, evidence: str = "") -> AdaptationEvent:
        ev = AdaptationEvent(datetime.now().isoformat(), kind, ok, detail, evidence[:2000])
        self.events.append(ev)
        return ev

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.events[-n:]]

    def adapt_text(self, producer: Callable[[int, Optional[str]], str], validator: Callable[[str], tuple[bool, str]]) -> tuple[bool, str, str]:
        """
        Ejecuta producer(intent, last_error) hasta que validator lo apruebe.
        Devuelve (ok, resultado, evidencia).
        """
        last_error = None
        evidence = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = producer(attempt, last_error)
            except Exception as e:
                last_error = str(e)
                evidence.append(f"intento {attempt}: excepción productor: {e}")
                self.log("adapt_text", False, f"intento {attempt} productor", last_error)
                continue
            ok, msg = validator(result)
            evidence.append(f"intento {attempt}: {'ok' if ok else 'fail'} - {msg}")
            self.log("adapt_text", ok, f"intento {attempt}", msg)
            if ok:
                return True, result, "\n".join(evidence)
            last_error = msg
        return False, result if 'result' in locals() else "", "\n".join(evidence)

    def validate_python(self, code: str) -> tuple[bool, str]:
        try:
            ast.parse(code)
            return True, "sintaxis OK"
        except SyntaxError as e:
            return False, f"SyntaxError línea {e.lineno}: {e.msg}"

    def sandbox_run(self, files: Dict[str, str], command: str, timeout: int = 60) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory(prefix="verdix_mahoraga_") as tmp:
            root = Path(tmp)
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            try:
                proc = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
                out = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
                ok = proc.returncode == 0
                self.log("sandbox_run", ok, command, out[:1500])
                return ok, out or f"exit={proc.returncode}"
            except subprocess.TimeoutExpired:
                self.log("sandbox_run", False, command, "timeout")
                return False, "timeout"
            except Exception as e:
                self.log("sandbox_run", False, command, str(e))
                return False, str(e)

    def auto_fix_python(self, code: str, llm_chat: Callable[[str], str]) -> tuple[bool, str, str]:
        current = code
        evidence = []
        for attempt in range(1, self.max_attempts + 1):
            ok, msg = self.validate_python(current)
            evidence.append(f"intento {attempt}: {msg}")
            if ok:
                self.log("auto_fix_python", True, f"intento {attempt}", msg)
                return True, current, "\n".join(evidence)
            prompt = (
                "Corrige este código Python. Devuelve SOLO el código corregido, sin markdown.\n"
                f"ERROR:\n{msg}\n\nCODIGO:\n{current}"
            )
            try:
                fixed = llm_chat(prompt)
                fixed = fixed.strip().replace("```python", "").replace("```", "").strip()
                if not fixed:
                    raise ValueError("respuesta vacía")
                current = fixed
            except Exception as e:
                evidence.append(f"intento {attempt}: fallo LLM: {e}")
                self.log("auto_fix_python", False, f"intento {attempt} llm", str(e))
        ok, msg = self.validate_python(current)
        self.log("auto_fix_python", ok, "final", msg)
        return ok, current, "\n".join(evidence)

    def choose_provider(self, candidates: List[str], available: Callable[[str], bool]) -> Optional[str]:
        for p in candidates:
            try:
                if available(p):
                    self.log("choose_provider", True, p)
                    return p
            except Exception as e:
                self.log("choose_provider", False, p, str(e))
        self.log("choose_provider", False, "none")
        return None


# instancia global
mahoraga = MahoragaEngine(max_attempts=int(os.environ.get("VERDIX_MAX_INTENTOS", "5") or "5"))
