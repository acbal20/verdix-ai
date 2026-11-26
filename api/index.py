from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from datetime import datetime
import os

app = FastAPI(title="VERDIX AI", version="30.0.0")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "verdix-ai",
        "version": "30.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/info")
def info():
    return {
        "name": "VERDIX AI",
        "version": "30.0.0",
        "description": "Sistema multi-agente autónomo creado por NOX",
        "features": [
            "multi-agent flow",
            "sandbox verification",
            "GitHub integration",
            "Vercel integration",
            "project context",
            "SQLite memory/cache",
        ],
        "env": {
            "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "github_configured": bool(os.environ.get("GITHUB_TOKEN")),
            "vercel_configured": bool(os.environ.get("VERCEL_TOKEN")),
        },
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>VERDIX AI</title>
  <style>
    body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0b1110;color:#e6fff2;margin:0}
    .wrap{max-width:900px;margin:0 auto;padding:48px 20px}
    .card{background:#121a18;border:1px solid #1f3a32;border-radius:16px;padding:28px}
    h1{margin:0 0 8px;font-size:40px;color:#7dffb2} p{color:#b7d5c7}
    pre{background:#09110f;border:1px solid #1f3a32;border-radius:10px;padding:16px;overflow:auto}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:20px}
    .item{padding:14px;border:1px solid #1f3a32;border-radius:12px;background:#0f1715}
    a{color:#7dffb2}
  </style>
</head>
<body>
  <div class="wrap"><div class="card">
    <h1>VERDIX AI v30.0</h1>
    <p>Sistema multi-agente autónomo creado por NOX. Endpoint web para estado; CLI completo local.</p>
    <div class="grid">
      <div class="item"><strong>Health</strong><br><a href="/api/health">/api/health</a></div>
      <div class="item"><strong>Info</strong><br><a href="/api/info">/api/info</a></div>
      <div class="item"><strong>CLI</strong><br><code>verdixcode</code></div>
    </div>
    <h3>Instalación local</h3>
    <pre>git clone https://github.com/acbal20/verdix-ai.git
cd verdix-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m verdix_ai.main</pre>
  </div></div>
</body></html>"""
