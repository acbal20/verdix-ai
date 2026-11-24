#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contexto de proyecto actual: permite a VERDIX saber en qué proyecto está trabajando,
qué archivos tiene, y mantener estado por proyecto.
"""

import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from verdix_ai.config import RUTA_HOME, DB_PROYECTOS


class ProjectContext:
    """Gestiona el proyecto activo y su contexto."""

    def __init__(self):
        self.proyecto_actual: Optional[str] = None
        self.ruta_actual: Optional[str] = None
        self._db_path = DB_PROYECTOS
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS proyectos
                     (nombre TEXT PRIMARY KEY, ruta TEXT, fecha_creacion TEXT,
                      ultima_actividad TEXT, descripcion TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS contexto_proyecto
                     (proyecto TEXT, clave TEXT, valor TEXT, fecha TEXT,
                      PRIMARY KEY (proyecto, clave))''')
        conn.commit()
        conn.close()

    def listar_proyectos(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self._db_path)
        cur = conn.execute("SELECT nombre, ruta, descripcion, ultima_actividad FROM proyectos ORDER BY ultima_actividad DESC")
        rows = cur.fetchall()
        conn.close()
        return [
            {"nombre": r[0], "ruta": r[1], "descripcion": r[2] or "", "ultima_actividad": r[3] or ""}
            for r in rows
        ]

    def crear_proyecto(self, nombre: str, ruta: str, descripcion: str = "") -> str:
        ruta_abs = os.path.abspath(os.path.expanduser(ruta))
        os.makedirs(ruta_abs, exist_ok=True)
        ahora = datetime.now().isoformat()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("INSERT OR REPLACE INTO proyectos (nombre, ruta, fecha_creacion, ultima_actividad, descripcion) VALUES (?, ?, ?, ?, ?)",
                         (nombre, ruta_abs, ahora, ahora, descripcion))
            conn.commit()
            self.proyecto_actual = nombre
            self.ruta_actual = ruta_abs
            return f"✅ Proyecto '{nombre}' creado/activado en {ruta_abs}"
        except Exception as e:
            return f"❌ Error creando proyecto: {e}"
        finally:
            conn.close()

    def activar_proyecto(self, nombre: str) -> str:
        conn = sqlite3.connect(self._db_path)
        cur = conn.execute("SELECT ruta FROM proyectos WHERE nombre = ?", (nombre,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return f"❌ Proyecto '{nombre}' no existe."
        self.proyecto_actual = nombre
        self.ruta_actual = row[0]
        ahora = datetime.now().isoformat()
        conn = sqlite3.connect(self._db_path)
        conn.execute("UPDATE proyectos SET ultima_actividad = ? WHERE nombre = ?", (ahora, nombre))
        conn.commit()
        conn.close()
        return f"✅ Proyecto '{nombre}' activado ({row[0]})"

    def obtener_contexto(self, clave: str) -> Optional[str]:
        if not self.proyecto_actual:
            return None
        conn = sqlite3.connect(self._db_path)
        cur = conn.execute("SELECT valor FROM contexto_proyecto WHERE proyecto = ? AND clave = ?",
                           (self.proyecto_actual, clave))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def guardar_contexto(self, clave: str, valor: str):
        if not self.proyecto_actual:
            return
        ahora = datetime.now().isoformat()
        conn = sqlite3.connect(self._db_path)
        conn.execute("INSERT OR REPLACE INTO contexto_proyecto (proyecto, clave, valor, fecha) VALUES (?, ?, ?, ?)",
                     (self.proyecto_actual, clave, valor, ahora))
        conn.commit()
        conn.close()

    def obtener_estructura(self) -> str:
        if not self.ruta_actual:
            return "❌ No hay proyecto activo."
        from verdix_ai.core.tool_registry import herramienta_listar_directorio
        return herramienta_listar_directorio(self.ruta_actual, profundidad=3)


contexto = ProjectContext()
