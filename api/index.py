from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
import os
import platform

app = FastAPI(title="VERDIX AI", version="30.0.0")


def _env_status():
    return {
        "groq": bool(os.environ.get("GROQ_API_KEY")),
        "github": bool(os.environ.get("GITHUB_TOKEN")),
        "vercel": bool(os.environ.get("VERCEL_TOKEN")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "ollama": bool(os.environ.get("OLLAMA_API_KEY")),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "verdix-ai",
        "version": "30.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/info")
def info():
    env = _env_status()
    return {
        "name": "VERDIX AI",
        "version": "30.0.0",
        "description": "Sistema multi-agente autónomo creado por NOX. Funciona en modo local sin API key.",
        "features": [
            "Modo local sin API key (auto/local)",
            "Multi-agente con verificación",
            "Sandbox y auto-reparación (Mahoraga)",
            "Integración GitHub y Vercel",
            "Contexto de proyecto y memoria SQLite",
            "CLI multiplataforma",
        ],
        "env": env,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }


@app.get("/", response_class=HTMLResponse)
def home():
    env = _env_status()
    def badge(ok, label):
        cls = "ok" if ok else "off"
        txt = "configurado" if ok else "opcional"
        return f'<span class="badge {cls}"><span class="dot"></span>{label}: {txt}</span>'

    badges = "".join([
        badge(env["groq"], "Groq"),
        badge(env["openai"], "OpenAI"),
        badge(env["ollama"], "Ollama"),
        badge(env["github"], "GitHub"),
        badge(env["vercel"], "Vercel"),
    ])

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta name="description" content="VERDIX AI v30 - sistema multi-agente autónomo con modo local sin API key."/>
  <title>VERDIX AI v30</title>
  <style>
    :root{{--bg:#07100d;--bg2:#0d1714;--card:#111c18;--line:#214238;--text:#eafff4;--muted:#9cc0b0;--accent:#7dffb2;--accent2:#39d98a;--warn:#ffcc66;--off:#5d746b}}
    *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:radial-gradient(1200px 500px at 20% -10%,#163528,transparent),linear-gradient(180deg,#07100d,#050b09);color:var(--text)}}
    .wrap{{max-width:1060px;margin:0 auto;padding:40px 20px 64px}}
    .hero{{display:grid;grid-template-columns:1.3fr .9fr;gap:20px;align-items:stretch}}
    .card{{background:linear-gradient(180deg,rgba(255,255,255,.02),transparent),var(--card);border:1px solid var(--line);border-radius:20px;padding:28px;box-shadow:0 20px 60px rgba(0,0,0,.28)}}
    .eyebrow{{display:inline-flex;gap:8px;align-items:center;padding:7px 12px;border-radius:999px;background:#0a1d17;border:1px solid #1f4638;color:var(--accent);font-size:13px;font-weight:600}}
    h1{{margin:14px 0 10px;font-size:clamp(34px,6vw,56px);line-height:1;letter-spacing:-.03em}} h1 span{{color:var(--accent)}}
    p{{color:var(--muted);line-height:1.65}} .lead{{font-size:17px;max-width:62ch}}
    .badges{{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}}
    .badge{{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;font-size:13px;border:1px solid var(--line);background:#0b1613;color:#dff7ea}}
    .badge .dot{{width:8px;height:8px;border-radius:50%;background:var(--off)}} .badge.ok .dot{{background:var(--accent);box-shadow:0 0 0 4px rgba(125,255,178,.12)}} .badge.off .dot{{background:#6d877d}}
    .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:20px}}
    .mini{{padding:18px;border-radius:16px;border:1px solid var(--line);background:#0c1714}} .mini h3{{margin:0 0 6px;font-size:15px}} .mini p{{margin:0;font-size:14px}}
    .kpi{{display:grid;gap:12px}} .kpi .item{{padding:16px;border:1px solid var(--line);border-radius:14px;background:#0c1714}} .kpi .label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}} .kpi .value{{font-size:20px;font-weight:700;margin-top:4px;color:var(--accent)}}
    .section{{margin-top:20px}} h2{{margin:0 0 12px;font-size:22px}} code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
    pre{{margin:0;background:#08120f;border:1px solid var(--line);border-radius:14px;padding:18px;overflow:auto;color:#dff7ea;font-size:14px;line-height:1.6}}
    .cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}} .links a{{color:var(--accent);text-decoration:none}} .links a:hover{{text-decoration:underline}}
    .endpoint{{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #19342a}} .endpoint:last-child{{border-bottom:0;padding-bottom:0}} .method{{color:var(--accent);font-weight:700;font-size:13px}}
    .status{{margin-top:14px;padding:12px 14px;border-radius:12px;background:#091613;border:1px solid #1d3b30;color:var(--muted);font-size:14px}}
    footer{{margin-top:24px;color:#7f9e90;font-size:13px}} .oktxt{{color:var(--accent)}}
    @media (max-width:900px){{.hero,.cols,.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <section class="card">
        <div class="eyebrow">🌀 v30.0 · Mahoraga adaptativo</div>
        <h1>VERDIX <span>AI</span></h1>
        <p class="lead">Sistema multi-agente autónomo creado por NOX. Funciona en <strong class="oktxt">modo local sin API key</strong>, y si configuras proveedores externos puede usar IA completa, GitHub y Vercel.</p>
        <div class="badges">{badges}</div>
        <div class="grid">
          <div class="mini"><h3>Sin API key</h3><p>Arranca en modo auto/local. Los usuarios no necesitan claves para probar el CLI.</p></div>
          <div class="mini"><h3>Mahoraga</h3><p>Adapta, reintenta y valida con evidencia antes de dar cambios por buenos.</p></div>
          <div class="mini"><h3>Multiplataforma</h3><p>CLI Python para Linux/Windows/macOS; esta web solo expone estado.</p></div>
        </div>
      </section>
      <aside class="card kpi">
        <div class="item"><div class="label">Servicio</div><div class="value" id="svc">VERDIX AI</div></div>
        <div class="item"><div class="label">Estado API</div><div class="value" id="health">comprobando...</div></div>
        <div class="item"><div class="label">Versión</div><div class="value">30.0.0</div></div>
        <div class="item"><div class="label">Modo</div><div class="value">Local-first</div></div>
      </aside>
    </div>

    <div class="cols section">
      <section class="card">
        <h2>Instalación rápida</h2>
        <pre>git clone https://github.com/acbal20/verdix-ai.git
cd verdix-ai
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# Windows PowerShell: .venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
python -m verdix_ai.main</pre>
        <div class="status">✅ No necesitas configurar <code>.env</code> ni API keys para empezar. Las claves son opcionales para IA externa.</div>
      </section>
      <section class="card links">
        <h2>Endpoints</h2>
        <div class="endpoint"><div><div class="method">GET /</div><div>Panel de estado</div></div><a href="/">abrir</a></div>
        <div class="endpoint"><div><div class="method">GET /api/health</div><div>Healthcheck JSON</div></div><a href="/api/health">abrir</a></div>
        <div class="endpoint"><div><div class="method">GET /api/info</div><div>Información y capacidades</div></div><a href="/api/info">abrir</a></div>
        <div class="status" id="info">Cargando info...</div>
      </section>
    </div>
    <footer>VERDIX AI · Creado por NOX · Las claves configuradas se detectan solo como estado booleano, nunca se exponen.</footer>
  </div>
  <script>
    async function load() {{
      try {{
        const h = await fetch('/api/health').then(r=>r.json());
        document.getElementById('health').textContent = h.status === 'ok' ? 'OK' : 'Error';
        document.getElementById('svc').textContent = h.service || 'VERDIX AI';
        const i = await fetch('/api/info').then(r=>r.json());
        document.getElementById('info').textContent = 'Features: ' + (i.features||[]).slice(0,4).join(' · ');
      }} catch (e) {{
        document.getElementById('health').textContent = 'sin respuesta';
        document.getElementById('info').textContent = 'No se pudo cargar /api/info';
      }}
    }}
    load();
  </script>
</body>
</html>"""
