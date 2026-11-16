import os
import sys
import json
import re
import subprocess
import time
import shutil
import base64
import ast
import requests
import random
import sqlite3
import hashlib
from datetime import datetime
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text
from rich.live import Live

# ==========================================
# CONFIGURACIÓN
# ==========================================
console = Console()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODELO_LLM = "openai/gpt-oss-20b"  # Modelo más obediente para JSON
MODELO_RAPIDO = "openai/gpt-oss-20b"
RUTA_HOME = os.path.expanduser("~")
RUTA_VERDIX = os.path.join(RUTA_HOME, "verdix_central", "04-IA-Y-AUTOMATIZACION")
DB_MEMORIA = os.path.join(RUTA_VERDIX, "verdix_memory.db")
DB_ERRORES = os.path.join(RUTA_VERDIX, "verdix_errores.db")
ultima_imagen_generada = None

# ==========================================
# BASES DE DATOS
# ==========================================
def init_dbs():
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS historial
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT, contenido TEXT, fecha TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cache
                 (key TEXT PRIMARY KEY, respuesta TEXT)''')
    conn.commit()
    conn.close()
    conn = sqlite3.connect(DB_ERRORES)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS errores
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, comando TEXT, error TEXT, fecha TEXT)''')
    conn.commit()
    conn.close()

def guardar_mensaje(rol, contenido):
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute("INSERT INTO historial (rol, contenido, fecha) VALUES (?, ?, ?)", (rol, contenido, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def cargar_historial(limite=10):
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute("SELECT rol, contenido FROM historial ORDER BY id DESC LIMIT ?", (limite,))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def limpiar_historial():
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute("DELETE FROM historial")
    c.execute("DELETE FROM cache")
    conn.commit()
    conn.close()

def get_cache(prompt):
    key = hashlib.md5(prompt.encode()).hexdigest()
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute("SELECT respuesta FROM cache WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_cache(prompt, respuesta):
    key = hashlib.md5(prompt.encode()).hexdigest()
    conn = sqlite3.connect(DB_MEMORIA)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cache (key, respuesta) VALUES (?, ?)", (key, respuesta))
    conn.commit()
    conn.close()

def guardar_error(comando, error):
    conn = sqlite3.connect(DB_ERRORES)
    c = conn.cursor()
    c.execute("INSERT INTO errores (comando, error, fecha) VALUES (?, ?, ?)", (comando, error, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def obtener_lecciones():
    conn = sqlite3.connect(DB_ERRORES)
    c = conn.cursor()
    c.execute("SELECT comando, error FROM errores ORDER BY id DESC LIMIT 3")
    rows = c.fetchall()
    conn.close()
    if not rows: return ""
    lecciones = "\n=== LECCIONES APRENDIDAS ===\n"
    for cmd, err in rows:
        lecciones += f"- Falló: {cmd[:60]}... | Error: {err[:60]}...\n"
    return lecciones

init_dbs()
historial = [{"role": "system", "content": ""}] + cargar_historial()

SYSTEM_PROMPT = f'''Eres VERDIX AI, el arquitecto del ecosistema VERDIX. CREADO POR NOX.
Tienes acceso al sistema (sudo), puedes instalar, crear archivos y ejecutar comandos.

=== REGLAS DE ORO ===
1. SIEMPRE responde con un objeto JSON puro. NO escribas pensamientos ni texto antes del JSON.
2. Si creas un archivo, verifícalo con `verify_file` antes de decir que terminaste.
3. Si un comando falla, lee el error y arréglalo (máximo 3 intentos).
4. NUNCA uses comillas alrededor de rutas con `~`.
5. Si te piden ejecutar una función de Python, usa `run_python` con un archivo que la importe, o usa `terminal` con `python -c "from verdix_ai.main import funcion; print(funcion())"`.

=== ACCIONES PERMITIDAS ===
- {{"action": "chat", "message": "respuesta"}}
- {{"action": "terminal", "command": "comando"}}
- {{"action": "create_file", "filename": "ruta", "content": "codigo"}}
- {{"action": "edit_file", "filename": "ruta", "content": "codigo"}}
- {{"action": "read_file", "filename": "ruta"}}
- {{"action": "verify_file", "filename": "ruta"}}
- {{"action": "install_system_package", "package": "nombre", "method": "apt|pip"}}
- {{"action": "generate_image", "prompt": "desc"}}
- {{"action": "edit_image", "filename": "ruta", "edit_type": "blanco_negro|desenfoque|invertir|redimensionar"}}
- {{"action": "search_web", "query": "búsqueda"}}
- {{"action": "run_python", "filename": "ruta"}}
- {{"action": "adb_devices"}}
- {{"action": "adb_install", "apk_path": "ruta"}}
- {{"action": "create_apk"}}
- {{"action": "self_improve", "description": "descripción del cambio", "code": "código Python de la nueva función o modificación"}}

=== AUTO-MEJORA CONTROLADA ===
Cuando uses `self_improve`, el código nuevo se probará primero en un sandbox aislado. Si funciona, se aplicará. Si no, se intentará reparar hasta 3 veces.

{obtener_lecciones()}
'''
historial[0]["content"] = SYSTEM_PROMPT

# ==========================================
# HERRAMIENTAS
# ==========================================
def analizar_peligro(comando):
    peligrosos = [r'\bsudo\b', r'\brm\b', r'\bmv\b', r'\bdd\b', r'\bmkfs\b', r'\bchmod\b', r'\bchown\b', r'\bapt\b', r'\bpip\b', r'>', r'>>']
    interactivos = [r'\bnano\b', r'\bvim\b', r'\bvi\b', r'\bhtop\b', r'\btop\b', r'\bless\b', r'\bmore\b']
    return any(re.search(p, comando) for p in peligrosos + interactivos)

def ejecutar_comando(comando):
    comando = re.sub(r"['\"]~([^'\"]*)['\"]", r"~\1", comando)
    try:
        res = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=120)
        salida = res.stdout.strip() or res.stderr.strip()
        if res.returncode != 0:
            guardar_error(comando, salida)
            return f"❌ ERROR: {salida}\n💡 Intenta corregirlo."
        return salida or "✅ Comando ejecutado."
    except Exception as e:
        guardar_error(comando, str(e))
        return f"❌ Error: {e}"

def crear_archivo(filename, content):
    try:
        filename = os.path.expanduser(filename)
        dirname = os.path.dirname(filename)
        if dirname: os.makedirs(dirname, exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f: f.write(content)
        if os.path.exists(filename):
            return f"✅ Archivo '{filename}' creado ({os.path.getsize(filename)} bytes)."
        return f"❌ Archivo no se creó."
    except Exception as e:
        guardar_error(f"crear {filename}", str(e))
        return f"❌ Error: {e}"

def verificar_archivo(filename):
    filename = os.path.expanduser(filename)
    if not os.path.exists(filename):
        return f"❌ '{filename}' NO existe."
    size = os.path.getsize(filename)
    if size == 0: return f"⚠️ '{filename}' está vacío."
    if filename.endswith('.py'):
        try:
            with open(filename, 'r', encoding='utf-8') as f: contenido = f.read()
            ast.parse(contenido)
            return f"✅ '{filename}' válido ({size} bytes)."
        except SyntaxError as e:
            return f"❌ '{filename}' ERROR de sintaxis: {e}. Corrígelo."
    return f"✅ '{filename}' existe ({size} bytes)."

def leer_archivo(filename):
    try:
        with open(os.path.expanduser(filename), 'r', encoding='utf-8') as f: return f.read()[:3000]
    except Exception as e: return f"❌ Error: {e}"

def instalar_paquete(paquete, metodo="apt"):
    console.print(f"[bold cyan]📦 Instalando {paquete} con {metodo}...[/]")
    try:
        if metodo == "apt": cmd = f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {paquete}"
        elif metodo == "pip": cmd = f"{sys.executable} -m pip install {paquete}"
        else: return f"❌ Método '{metodo}' no soportado."
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if res.returncode == 0: return f"✅ '{paquete}' instalado."
        guardar_error(cmd, res.stderr)
        return f"❌ Error: {res.stderr[:500]}"
    except Exception as e: return f"❌ Error: {e}"

def generar_imagen(prompt):
    global ultima_imagen_generada
    with console.status("[bold magenta]Generando imagen..."):
        urls = [
            f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=1024&height=1024&nologo=true&seed={random.randint(1, 99999)}",
            f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=512&height=512&nologo=true&model=flux"
        ]
        filename = f"img_{re.sub(r'[^a-zA-Z0-9]', '_', prompt)[:20]}.jpg"
        ruta_absoluta = os.path.abspath(filename)
        for url in urls:
            try:
                r = requests.get(url, stream=True, timeout=60)
                if r.status_code == 200:
                    with open(ruta_absoluta, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                    ultima_imagen_generada = ruta_absoluta
                    return f"✅ Imagen guardada: {ruta_absoluta}"
            except: pass
        return "❌ Error generando imagen."

def editar_imagen(archivo_entrada, accion, archivo_salida=None):
    global ultima_imagen_generada
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        instalar_paquete("Pillow", "pip")
        from PIL import Image, ImageFilter, ImageOps
    try:
        if not archivo_entrada or archivo_entrada.lower() in ["ultima", "última"]:
            archivo_entrada = ultima_imagen_generada
        if not archivo_entrada: return "❌ No hay imagen previa."
        img = Image.open(os.path.expanduser(archivo_entrada))
        if accion == "blanco_negro": img = ImageOps.grayscale(img)
        elif accion == "desenfoque": img = img.filter(ImageFilter.BLUR)
        elif accion == "invertir": img = ImageOps.invert(img.convert("RGB"))
        elif accion == "redimensionar": img = img.resize((800, 600))
        if not archivo_salida: archivo_salida = f"editada_{os.path.basename(archivo_entrada)}"
        ruta_salida = os.path.abspath(os.path.expanduser(archivo_salida))
        img.save(ruta_salida)
        return f"✅ Imagen editada: {ruta_salida}"
    except Exception as e: return f"❌ Error: {e}"

def buscar_web(query):
    try:
        from ddgs import DDGS
    except ImportError:
        instalar_paquete("ddgs", "pip")
        from ddgs import DDGS
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=5))
            return "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
    except Exception as e: return f"❌ Error: {e}"

def ejecutar_python(filename):
    try:
        res = subprocess.run([sys.executable, os.path.expanduser(filename)], capture_output=True, text=True, timeout=120)
        return res.stdout.strip() or res.stderr.strip() or "✅ Ejecutado."
    except Exception as e: return f"❌ Error: {e}"

def adb_devices():
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=30)
        return res.stdout.strip()
    except FileNotFoundError:
        instalar_paquete("adb", "apt")
        return "✅ ADB instalado. Reintenta."

def adb_install(apk_path):
    try:
        res = subprocess.run(["adb", "install", os.path.expanduser(apk_path)], capture_output=True, text=True, timeout=120)
        return res.stdout.strip() or res.stderr.strip()
    except FileNotFoundError:
        instalar_paquete("adb", "apt")
        return "✅ ADB instalado. Reintenta."

def crear_apk():
    apk_dir = os.path.join(RUTA_VERDIX, "verdix_ai_package")
    if not os.path.exists(os.path.join(apk_dir, "buildozer.spec")):
        return "❌ No existe buildozer.spec."
    console.print("[bold yellow]🔨 Ejecutando buildozer...[/]")
    try:
        env = os.environ.copy()
        if "JAVA_HOME" not in env: env["JAVA_HOME"] = "/usr/lib/jvm/java-17-openjdk-amd64"
        res = subprocess.run(["buildozer", "-v", "android", "debug"], cwd=apk_dir, capture_output=True, text=True, timeout=3600, env=env)
        if res.returncode == 0: return "✅ APK generada en 'bin/'."
        guardar_error("buildozer", res.stderr)
        return f"❌ Error APK: {res.stderr[-500:]}"
    except Exception as e: return f"❌ Error: {e}"

# ==========================================
# AUTO-MEJORA CONTROLADA (SANDBOX)
# ==========================================
def auto_mejora_controlada(descripcion, codigo_nuevo):
    console.print(f"\n[bold magenta]🧬 AUTO-MEJORA CONTROLADA:[/] {descripcion}")
    archivo_real = os.path.abspath(__file__)
    archivo_sandbox = archivo_real + ".sandbox"
    
    try:
        ast.parse(codigo_nuevo)
    except SyntaxError as e:
        return f"❌ Error de sintaxis en el código nuevo: {e}. Abortando."
    
    shutil.copy(archivo_real, archivo_sandbox)
    console.print("[dim]📋 Copia sandbox creada.[/]")
    
    try:
        with open(archivo_sandbox, 'r', encoding='utf-8') as f:
            contenido = f.read()
        marcador = "# === FIN DE NUEVAS FUNCIONES ==="
        if marcador not in contenido:
            contenido = contenido.replace('if __name__ == "__main__":', f"\n{marcador}\n\nif __name__ == \"__main__\":")
        contenido = contenido.replace(marcador, f"{codigo_nuevo}\n\n{marcador}")
        with open(archivo_sandbox, 'w', encoding='utf-8') as f:
            f.write(contenido)
        console.print("[dim]💉 Código inyectado en el sandbox.[/]")
    except Exception as e:
        os.remove(archivo_sandbox)
        return f"❌ Error inyectando en sandbox: {e}"
    
    console.print("[dim]🧪 Probando sandbox...[/]")
    try:
        res = subprocess.run([sys.executable, "-c", f"import ast; ast.parse(open('{archivo_sandbox}').read())"],
                             capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            return _reparar_y_reintentar(descripcion, codigo_nuevo, archivo_real, archivo_sandbox, res.stderr)
    except Exception as e:
        return f"❌ Error ejecutando sandbox: {e}"
    
    console.print("[bold green]✅ Sandbox validado. Aplicando al archivo real...[/]")
    shutil.copy(archivo_real, archivo_real + ".bak")
    shutil.move(archivo_sandbox, archivo_real)
    console.print("[bold green]🚀 Cambios aplicados. Reiniciando...[/]")
    time.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def _reparar_y_reintentar(descripcion, codigo_nuevo, archivo_real, archivo_sandbox, error):
    codigo_actual = codigo_nuevo
    for intento in range(1, 4):
        console.print(f"[bold yellow]🔧 Intento de reparación {intento}/3...[/]")
        prompt_reparacion = (
            "El código Python tiene un error: " + str(error) + 
            " | Código roto: " + codigo_actual + 
            " | Por favor, corrige el código y devuélvelo SOLO con el código corregido, sin explicaciones."
        )
        try:
            completion = client.chat.completions.create(
                model=MODELO_LLM,
                messages=[{"role": "user", "content": prompt_reparacion}],
                temperature=0.0,
                max_tokens=3000
            )
            codigo_reparado = completion.choices[0].message.content.strip()
            codigo_reparado = re.sub(r"```python\s*|\s*```", "", codigo_reparado).strip()
            try:
                ast.parse(codigo_reparado)
            except SyntaxError as e:
                error = str(e)
                codigo_actual = codigo_reparado
                continue
            if os.path.exists(archivo_sandbox):
                os.remove(archivo_sandbox)
            return auto_mejora_controlada(descripcion, codigo_reparado)
        except Exception as e:
            console.print(f"[red]Error en reparación: {e}[/]")
            error = str(e)
    if os.path.exists(archivo_sandbox):
        os.remove(archivo_sandbox)
    return "❌ No se pudo reparar el código después de 3 intentos. Archivo original intacto."

# ==========================================
# SPLASH
# ==========================================
def mostrar_splash():
    os.system('clear')
    logo = Text("∞", style="bold bright_green")
    with Live(Align.center(Panel(logo, border_style="bright_green", padding=(2, 20))), refresh_per_second=4, screen=True) as live:
        time.sleep(1.0)
        live.update(Align.center(Panel("[bold bright_green]VERDIX AI[/]\n[dim]Creado por NOX[/]\n\n[white]Presiona Enter...[/]", border_style="bright_green", padding=(1, 10))))
        input()
    os.system('clear')

# ==========================================
# PROCESADOR
# ==========================================
def procesar_respuesta(respuesta_raw):
    if not respuesta_raw or not respuesta_raw.strip(): return
    try:
        limpio = re.sub(r'```json\s*|\s*```', '', respuesta_raw).strip()
        match = re.search(r'(\{.*\}|\[.*\])', limpio, re.DOTALL)
        if match: limpio = match.group(1)
        data = json.loads(limpio)
        acciones = [data] if isinstance(data, dict) else data
        for accion_data in acciones:
            accion = accion_data.get("action")
            if accion == "chat":
                console.print(Panel(accion_data.get('message'), title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
            elif accion == "terminal":
                cmd = accion_data.get("command")
                if analizar_peligro(cmd):
                    console.print(f"[bold red]⚠️ PELIGRO:[/] {cmd}")
                    if Confirm.ask("¿Ejecutar?"): console.print(Panel(ejecutar_comando(cmd), title="Resultado", border_style="green"))
                else:
                    console.print(f"[dim]⚡ Ejecutando: {cmd}[/]")
                    console.print(Panel(ejecutar_comando(cmd), title="Resultado", border_style="green"))
            elif accion == "create_file":
                console.print(f"[bold green]{crear_archivo(accion_data.get('filename'), accion_data.get('content', ''))}[/]")
            elif accion == "edit_file":
                console.print(f"[bold green]{crear_archivo(accion_data.get('filename'), accion_data.get('content', ''))}[/]")
            elif accion == "verify_file":
                console.print(f"[bold green]{verificar_archivo(accion_data.get('filename'))}[/]")
            elif accion == "read_file":
                console.print(Panel(leer_archivo(accion_data.get('filename')), title="Archivo", border_style="blue"))
            elif accion == "generate_image":
                console.print(f"[bold green]{generar_imagen(accion_data.get('prompt'))}[/]")
            elif accion == "edit_image":
                filename = accion_data.get("filename", "")
                if filename.lower() in ["", "ultima", "última"]: filename = None
                console.print(f"[bold green]{editar_imagen(filename, accion_data.get('edit_type'))}[/]")
            elif accion == "search_web":
                console.print(Panel(buscar_web(accion_data.get("query")), title="Web", border_style="yellow"))
            elif accion == "run_python":
                console.print(Panel(ejecutar_python(accion_data.get("filename")), title="Python", border_style="green"))
            elif accion == "install_system_package":
                console.print(Panel(instalar_paquete(accion_data.get("package"), accion_data.get("method", "apt")), title="Instalación", border_style="cyan"))
            elif accion == "adb_devices":
                console.print(Panel(adb_devices(), title="ADB", border_style="blue"))
            elif accion == "adb_install":
                console.print(Panel(adb_install(accion_data.get("apk_path")), title="ADB Install", border_style="blue"))
            elif accion == "create_apk":
                console.print(Panel(crear_apk(), title="APK", border_style="magenta"))
            elif accion == "self_improve":
                console.print(auto_mejora_controlada(accion_data.get("description", ""), accion_data.get("code", "")))
            else:
                console.print(f"[yellow]Acción no reconocida: {accion}[/]")
    except json.JSONDecodeError:
        console.print(Panel(respuesta_raw, title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")

# ==========================================
# MAIN
# ==========================================
def main():
    global historial, ultima_imagen_generada
    mostrar_splash()
    console.print(Panel("[bold bright_green]VERDIX Code v25.0[/]\n[dim]Creado por NOX | Powered by Groq[/]\nEscribe 'salir' para terminar.\nAuto-Mejora Controlada + Caché + Modelo Rápido.", border_style="bright_green"))
    
    while True:
        try:
            prompt = Prompt.ask("\n[bold green]NOX[/]")
            if prompt.lower() in ['salir', 'exit', 'quit']: break
            if prompt.lower() == 'limpiar':
                limpiar_historial()
                historial = [{"role": "system", "content": SYSTEM_PROMPT}]
                console.print("[bold yellow]🧹 Memoria y caché borrados.[/]")
                continue
            if not prompt.strip(): continue
            
            cache = get_cache(prompt)
            if cache:
                console.print("[bold cyan]📦 Desde caché (0 tokens):[/]")
                procesar_respuesta(cache)
                continue
            
            guardar_mensaje("user", prompt)
            historial.append({"role": "user", "content": prompt})
            historial_reducido = [historial[0]] + historial[-4:] if len(historial) > 4 else historial
            
            with console.status("[bold yellow]Pensando..."):
                try:
                    completion = client.chat.completions.create(
                        model=MODELO_RAPIDO,
                        messages=historial_reducido,
                        temperature=0.1,
                        max_tokens=3000,
                        response_format={"type": "json_object"}
                    )
                    respuesta_raw = completion.choices[0].message.content.strip()
                except Exception as e:
                    console.print(f"[dim yellow]⚠️ Reintentando sin formato JSON estricto...[/]")
                    completion = client.chat.completions.create(
                        model=MODELO_RAPIDO,
                        messages=historial_reducido,
                        temperature=0.1,
                        max_tokens=3000
                    )
                    respuesta_raw = completion.choices[0].message.content.strip()
                    match = re.search(r'(\{.*\})', respuesta_raw, re.DOTALL)
                    if match: respuesta_raw = match.group(1)
                
                guardar_mensaje("assistant", respuesta_raw)
                historial.append({"role": "assistant", "content": respuesta_raw})
                save_cache(prompt, respuesta_raw)
            
            procesar_respuesta(respuesta_raw)
        except KeyboardInterrupt: break
        except Exception as e: console.print(f"[bold red]Error crítico:[/] {e}")

if __name__ == "__main__":
    main()

# === FIN DE NUEVAS FUNCIONES ===
