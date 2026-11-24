import os
import json
import sqlite3
from typing import List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Cargar modelo y tokenizador (asumiendo que están disponibles vía HuggingFace)
from transformers import AutoModelForCausalLM, AutoTokenizer

# Ruta del modelo y tokenizador (ajustar si se encuentran en otro lugar)
MODEL_NAME = "nox-1/v0.2"
TOKENIZER_NAME = "nox-1-tokenizer/v2"

app = FastAPI()

# Inicializar modelo y tokenizador al iniciar la aplicación
try:
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
except Exception as e:
    # Si falla la carga, registrar el error y continuar (el endpoint /generate fallará)
    tokenizer = None
    model = None
    print(f"[ERROR] No se pudo cargar el modelo/tokenizador: {e}")

# Conexión a la base de datos de historial (SQLite)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "verdix_memory.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class GenerateRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 100
    temperature: float = 0.7

@app.get("/", response_class=HTMLResponse)
async def root():
    """Devuelve una página HTML con una interfaz de chat oscuro y minimalista."""
    html_content = """
    <!DOCTYPE html>
    <html lang=\"es\">
    <head>
        <meta charset=\"UTF-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>VERDIX Chat</title>
        <style>
            body { background-color: #121212; color: #e0e0e0; font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
            #chat { flex: 1; overflow-y: auto; padding: 1rem; }
            .msg { margin-bottom: 0.8rem; }
            .user { color: #90caf9; }
            .bot { color: #a5d6a7; }
            #input { display: flex; padding: 0.5rem; background: #1e1e1e; }
            #input textarea { flex: 1; resize: none; background: #2c2c2c; color: #e0e0e0; border: none; padding: 0.5rem; border-radius: 4px; }
            #input button { margin-left: 0.5rem; background: #4caf50; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div id="chat"></div>
        <div id="input">
            <textarea id="prompt" rows="1" placeholder=\"Escribe tu mensaje...\"></textarea>
            <button onclick=\"sendMessage()\">Enviar</button>
        </div>
        <script>
            async function sendMessage() {
                const promptEl = document.getElementById('prompt');
                const userMsg = promptEl.value.trim();
                if (!userMsg) return;
                addMessage('user', userMsg);
                promptEl.value = '';
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: userMsg })
                });
                const data = await response.json();
                addMessage('bot', data.generated_text || 'Error al generar respuesta');
            }
            function addMessage(sender, text) {
                const chat = document.getElementById('chat');
                const div = document.createElement('div');
                div.className = 'msg ' + (sender === 'user' ? 'user' : 'bot');
                div.textContent = (sender === 'user' ? 'Tú: ' : 'VERDIX: ') + text;
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.post("/api/generate")
async def generate(request: GenerateRequest):
    """Genera texto a partir del *prompt* usando el modelo cargado."""
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Modelo no disponible")
    inputs = tokenizer.encode(request.prompt, return_tensors="pt")
    try:
        output_ids = model.generate(
            inputs,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
        generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        # Guardar en historial
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO history (timestamp, user_prompt, generated_text) VALUES (datetime('now'), ?, ?)",
            (request.prompt, generated_text)
        )
        conn.commit()
        conn.close()
        return JSONResponse(content={"generated_text": generated_text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history(limit: int = 50):
    """Devuelve los últimos *limit* registros del historial almacenado en SQLite."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT timestamp, user_prompt, generated_text FROM history ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    history = [
        {
            "timestamp": row["timestamp"],
            "prompt": row["user_prompt"],
            "response": row["generated_text"]
        }
        for row in rows
    ]
    return JSONResponse(content={"history": history})
