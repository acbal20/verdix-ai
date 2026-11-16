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
from datetime import datetime
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text
from rich.live import Live

# ==========================================
# CONFIGURACIÓN Y MEMORIA PERSISTENTE
# ==========================================
console = Console()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODELO_LLM = "openai/gpt-oss-120b"
RUTA_HOME = os.path.expanduser("~")
RUTA_VERDIX = os.path.join(RUTA_HOME, "verdix_central", "04-IA-Y-AUTOMATIZACION")

# Base de datos para historial
DB_PATH = os.path.join(RUTA_VERDIX, "verdix_memory.db")
# Archivo de estado (última imagen, etc.)
STATE_PATH = os.path.join(RUTA_VERDIX, "verdix_state.json")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS historial
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rol TEXT, contenido TEXT, fecha TEXT)''')
    conn.commit()
    conn.close()

def guardar_mensaje(rol, contenido):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO historial (rol, contenido, fecha) VALUES (?, ?, ?)",
              (rol, contenido, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def cargar_historial(limite=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rol, contenido FROM historial ORDER BY id DESC LIMIT ?", (limite,))
    rows = c.fetchall()
    conn.close()
    # Invertir para que queden en orden cronológico
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def limpiar_historial():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM historial")
    conn.commit()
    conn.close()

def guardar_estado(clave, valor):
    try:
        with open(STATE_PATH, 'r') as f:
            estado = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        estado = {}
    estado[clave] = valor
    with open(STATE_PATH, 'w') as f:
        json.dump(estado, f)

def cargar_estado(clave, default=None):
    try:
        with open(STATE_PATH, 'r') as f:
            estado = json.load(f)
        return estado.get(clave, default)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

# Inicializar memoria
init_db()
historial = [{"role": "system", "content": ""}] + cargar_historial()
ultima_imagen_generada = cargar_estado("ultima_imagen")

SYSTEM_PROMPT = f'''Eres VERDIX AI, el arquitecto y director técnico del ecosistema VERDIX.
FUISTE CREADO POR NOX. Tienes acceso total al sistema (sudo) y puedes instalar lo que necesites.
Puedes recordar conversaciones pasadas porque tienes una base de datos SQLite.

=== HERRAMIENTAS DISPONIBLES ===
Responde SIEMPRE con un JSON válido. Si necesitas varias acciones, devuelve una lista:
- {{"action": "chat", "message": "respuesta"}}
- {{"action": "terminal", "command": "comando_bash"}}
- {{"action": "create_file", "filename": "ruta/archivo.py", "content": "codigo"}}
- {{"action": "read_file", "filename": "ruta/archivo.txt"}}
- {{"action": "generate_image", "prompt": "descripción visual"}}
- {{"action": "edit_image", "filename": "ruta/imagen.jpg", "edit_type": "blanco_negro|desenfoque|invertir|redimensionar"}}
- {{"action": "read_pdf", "filename": "ruta/documento.pdf"}}
- {{"action": "read_docx", "filename": "ruta/documento.docx"}}
- {{"action": "search_web", "query": "búsqueda"}}
- {{"action": "run_python", "filename": "ruta/script.py"}}
- {{"action": "install_system_package", "package": "nombre", "method": "apt|snap|pip|npm"}}
- {{"action": "adb_devices"}}
- {{"action": "adb_install", "apk_path": "ruta/apk"}}
- {{"action": "adb_shell", "command": "cmd"}}
- {{"action": "fastboot_devices"}}
- {{"action": "fastboot_flash", "partition": "boot", "image": "ruta.img"}}
- {{"action": "setup_android_sdk"}}
- {{"action": "create_apk"}}
- {{"action": "self_improve", "description": "desc", "code_base64": "codigo_base64"}}

=== REGLAS CRÍTICAS ===
1. Si falta una herramienta, usa `install_system_package`.
2. Si buildozer falla, usa `setup_android_sdk`.
3. NUNCA uses comillas alrededor de rutas con `~`.
4. Recuerda: tienes memoria persistente. Si el usuario pregunta "¿qué hablamos ayer?", consulta tu historial.
'''

historial[0]["content"] = SYSTEM_PROMPT

# ==========================================
# HERRAMIENTAS
# ==========================================
def instalar_paquete(paquete, metodo="apt"):
    console.print(f"[bold cyan]📦 Instalando {paquete} con {metodo}...[/]")
    try:
        if metodo == "apt":
            cmd = f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {paquete}"
        elif metodo == "snap":
            cmd = f"sudo snap install {paquete}"
        elif metodo == "pip":
            cmd = f"{sys.executable} -m pip install {paquete}"
        elif metodo == "npm":
            cmd = f"sudo npm install -g {paquete}"
        else:
            return f"❌ Método '{metodo}' no soportado."
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if res.returncode == 0:
            return f"✅ Paquete '{paquete}' instalado."
        return f"❌ Error instalando '{paquete}': {res.stderr[:500]}"
    except Exception as e:
        return f"❌ Error: {e}"

def configurar_android_sdk():
    console.print("[bold yellow]🤖 Configurando Android SDK...[/]")
    for pkg in ["wget", "unzip", "openjdk-17-jdk", "lib32stdc++6", "lib32z1"]:
        instalar_paquete(pkg, "apt")
    
    sdk_dir = os.path.join(RUTA_HOME, "Android", "Sdk")
    os.makedirs(sdk_dir, exist_ok=True)
    cmdline_tools_url = "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
    zip_path = os.path.join(RUTA_HOME, "cmdline-tools.zip")
    
    if not os.path.exists(zip_path):
        subprocess.run(f"wget -q {cmdline_tools_url} -O {zip_path}", shell=True)
    
    if not os.path.exists(os.path.join(sdk_dir, "cmdline-tools", "latest")):
        os.makedirs(os.path.join(sdk_dir, "cmdline-tools"), exist_ok=True)
        subprocess.run(f"unzip -q {zip_path} -d {sdk_dir}/cmdline-tools/", shell=True)
        src = os.path.join(sdk_dir, "cmdline-tools", "cmdline-tools")
        dst = os.path.join(sdk_dir, "cmdline-tools", "latest")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
    
    env_vars = f'\nexport ANDROID_HOME="{sdk_dir}"\nexport ANDROID_SDK_ROOT="{sdk_dir}"\nexport PATH="$PATH:{sdk_dir}/cmdline-tools/latest/bin:{sdk_dir}/platform-tools"\n'
    with open(os.path.join(RUTA_HOME, ".bashrc"), "a") as f:
        f.write(env_vars)
    
    os.environ["ANDROID_HOME"] = sdk_dir
    os.environ["ANDROID_SDK_ROOT"] = sdk_dir
    os.environ["PATH"] = os.environ["PATH"] + f":{sdk_dir}/cmdline-tools/latest/bin:{sdk_dir}/platform-tools"
    
    sdkmanager = os.path.join(sdk_dir, "cmdline-tools", "latest", "bin", "sdkmanager")
    if os.path.exists(sdkmanager):
        subprocess.run(f"yes | {sdkmanager} --licenses", shell=True, capture_output=True)
        subprocess.run(f"{sdkmanager} 'platform-tools' 'platforms;android-33' 'build-tools;33.0.2'", shell=True, capture_output=True)
    
    return "✅ Android SDK configurado. Reinicia la terminal para aplicar los cambios."

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
                    guardar_estado("ultima_imagen", ruta_absoluta)
                    try: subprocess.Popen(["xdg-open", ruta_absoluta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except: pass
                    return f"✅ Imagen guardada en: {ruta_absoluta}"
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
        guardar_estado("ultima_imagen", ruta_salida)
        return f"✅ Imagen editada: {ruta_salida}"
    except Exception as e:
        return f"❌ Error: {e}"

def leer_pdf(filename):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        instalar_paquete("PyPDF2", "pip")
        from PyPDF2 import PdfReader
    try:
        reader = PdfReader(os.path.expanduser(filename))
        text = "\n".join([page.extract_text() for page in reader.pages])
        return text[:5000] + "..." if len(text) > 5000 else text
    except Exception as e:
        return f"❌ Error leyendo PDF: {e}"

def leer_docx(filename):
    try:
        from docx import Document
    except ImportError:
        instalar_paquete("python-docx", "pip")
        from docx import Document
    try:
        doc = Document(os.path.expanduser(filename))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text[:5000] + "..." if len(text) > 5000 else text
    except Exception as e:
        return f"❌ Error leyendo DOCX: {e}"

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
    except Exception as e:
        return f"❌ Error buscando en web: {e}"

def ejecutar_python(filename):
    try:
        res = subprocess.run([sys.executable, os.path.expanduser(filename)], capture_output=True, text=True, timeout=120)
        return res.stdout.strip() or res.stderr.strip() or "✅ Script ejecutado."
    except Exception as e:
        return f"❌ Error ejecutando Python: {e}"

def adb_devices():
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=30)
        return res.stdout.strip() if res.returncode == 0 else f"❌ Error: {res.stderr}"
    except FileNotFoundError:
        instalar_paquete("adb", "apt")
        return "✅ ADB instalado. Vuelve a intentarlo."

def adb_install(apk_path):
    try:
        if not os.path.exists(os.path.expanduser(apk_path)):
            return f"❌ El archivo APK no existe: {apk_path}"
        res = subprocess.run(["adb", "install", os.path.expanduser(apk_path)], capture_output=True, text=True, timeout=120)
        return res.stdout.strip() if res.returncode == 0 else f"❌ Error: {res.stderr}"
    except FileNotFoundError:
        instalar_paquete("adb", "apt")
        return "✅ ADB instalado. Vuelve a intentarlo."

def adb_shell(command):
    try:
        res = subprocess.run(["adb", "shell", command], capture_output=True, text=True, timeout=30)
        return res.stdout.strip() if res.returncode == 0 else f"❌ Error: {res.stderr}"
    except FileNotFoundError:
        instalar_paquete("adb", "apt")
        return "✅ ADB instalado. Vuelve a intentarlo."

def fastboot_devices():
    try:
        res = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=30)
        return res.stdout.strip() if res.returncode == 0 else f"❌ Error: {res.stderr}"
    except FileNotFoundError:
        instalar_paquete("fastboot", "apt")
        return "✅ Fastboot instalado. Vuelve a intentarlo."

def fastboot_flash(partition, image):
    try:
        res = subprocess.run(["fastboot", "flash", partition, os.path.expanduser(image)], capture_output=True, text=True, timeout=300)
        return res.stdout.strip() if res.returncode == 0 else f"❌ Error: {res.stderr}"
    except FileNotFoundError:
        instalar_paquete("fastboot", "apt")
        return "✅ Fastboot instalado. Vuelve a intentarlo."

def crear_apk():
    console.print("[bold yellow]📱 Preparando entorno para APK...[/]")
    sdk_dir = os.path.join(RUTA_HOME, "Android", "Sdk")
    if not os.path.exists(os.path.join(sdk_dir, "platform-tools", "adb")):
        console.print("[bold red]Android SDK no encontrado. Ejecutando setup_android_sdk...[/]")
        configurar_android_sdk()
        return "⚠️ Android SDK instalado. Reinicia la terminal y vuelve a intentarlo."
    
    instalar_paquete("buildozer cython", "pip")
    
    apk_dir = os.path.join(RUTA_VERDIX, "verdix_ai_package")
    if not os.path.exists(os.path.join(apk_dir, "buildozer.spec")):
        spec_content = """[app]
title = VERDIX AI
package.name = verdixai
package.domain = org.verdix
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,groq,rich,requests,pillow,ddgs,PyPDF2,python-docx
orientation = portrait
osx.python_version = 3
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
"""
        with open(os.path.join(apk_dir, "buildozer.spec"), "w") as f:
            f.write(spec_content)
    
    main_py = """from verdix_ai.main import main
if __name__ == '__main__':
    main()
"""
    with open(os.path.join(apk_dir, "main.py"), "w") as f:
        f.write(main_py)
    
    try:
        env = os.environ.copy()
        if "JAVA_HOME" not in env:
            env["JAVA_HOME"] = "/usr/lib/jvm/java-17-openjdk-amd64"
        if "ANDROID_HOME" not in env:
            env["ANDROID_HOME"] = sdk_dir
        if "ANDROID_SDK_ROOT" not in env:
            env["ANDROID_SDK_ROOT"] = sdk_dir
            
        res = subprocess.run(["buildozer", "-v", "android", "debug"], cwd=apk_dir, capture_output=True, text=True, timeout=3600, env=env)
        if res.returncode == 0:
            return "✅ APK generada. Busca el archivo .apk en la carpeta 'bin/'."
        else:
            return f"❌ Error generando APK: {res.stderr[-500:]}"
    except Exception as e:
        return f"❌ Error: {e}"

def auto_mejora(descripcion, codigo_b64):
    console.print(f"\n[bold magenta]🧬 AUTO-MEJORA:[/] {descripcion}")
    try:
        codigo_nuevo = base64.b64decode(codigo_b64).decode('utf-8')
        ast.parse(codigo_nuevo)
    except Exception as e:
        return f"❌ Error validando código: {e}"
    
    archivo_actual = os.path.abspath(__file__)
    try:
        shutil.copy(archivo_actual, archivo_actual + ".bak")
        with open(archivo_actual, 'r', encoding='utf-8') as f: contenido = f.read()
        marcador = "# === FIN DE NUEVAS FUNCIONES ==="
        if marcador not in contenido: contenido = contenido.replace('def main():', f"\n{marcador}\n\ndef main():")
        contenido = contenido.replace(marcador, f"{codigo_nuevo}\n\n{marcador}")
        with open(archivo_actual, 'w', encoding='utf-8') as f: f.write(contenido)
        console.print("[bold green]🚀 Código inyectado. Reiniciando...[/]")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        return f"❌ Error en inyección: {e}"

# ==========================================
# SPLASH Y PROCESAMIENTO
# ==========================================
def mostrar_splash():
    os.system('clear')
    logo = Text("∞", style="bold bright_green")
    with Live(Align.center(Panel(logo, border_style="bright_green", padding=(2, 20))), refresh_per_second=4, screen=True) as live:
        time.sleep(1.0)
        live.update(Align.center(Panel("[bold bright_green]VERDIX AI[/]\n[dim]Creado por NOX[/]\n\n[white]Presiona Enter...[/]", border_style="bright_green", padding=(1, 10))))
        input()
    os.system('clear')

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
                    if Confirm.ask("¿Ejecutar?"):
                        console.print(Panel(ejecutar_comando(cmd), title="Resultado", border_style="green"))
                else:
                    console.print(f"[dim]⚡ Ejecutando: {cmd}[/]")
                    console.print(Panel(ejecutar_comando(cmd), title="Resultado", border_style="green"))
            elif accion == "create_file":
                filename = os.path.expanduser(accion_data.get("filename"))
                dirname = os.path.dirname(filename)
                if dirname: os.makedirs(dirname, exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f: f.write(accion_data.get("content", ""))
                console.print(f"[bold green]✅ Archivo '{filename}' creado.[/]")
            elif accion == "read_file":
                filename = os.path.expanduser(accion_data.get("filename"))
                try:
                    with open(filename, 'r', encoding='utf-8') as f: content = f.read()
                    console.print(Panel(content[:1000], title=f"📄 {filename}", border_style="blue"))
                except Exception as e: console.print(f"[red]❌ Error:[/] {e}")
            elif accion == "generate_image":
                console.print(f"[bold green]{generar_imagen(accion_data.get('prompt'))}[/]")
            elif accion == "edit_image":
                filename = accion_data.get("filename", "")
                if filename.lower() in ["", "ultima", "última"]: filename = None
                console.print(f"[bold green]{editar_imagen(filename, accion_data.get('edit_type'))}[/]")
            elif accion == "read_pdf":
                console.print(Panel(leer_pdf(accion_data.get("filename")), title="📄 PDF", border_style="magenta"))
            elif accion == "read_docx":
                console.print(Panel(leer_docx(accion_data.get("filename")), title="📝 DOCX", border_style="magenta"))
            elif accion == "search_web":
                console.print(Panel(buscar_web(accion_data.get("query")), title="🌐 Búsqueda Web", border_style="yellow"))
            elif accion == "run_python":
                console.print(Panel(ejecutar_python(accion_data.get("filename")), title="🐍 Python", border_style="green"))
            elif accion == "install_system_package":
                console.print(Panel(instalar_paquete(accion_data.get("package"), accion_data.get("method", "apt")), title="📦 Instalación", border_style="cyan"))
            elif accion == "adb_devices":
                console.print(Panel(adb_devices(), title="📱 ADB Devices", border_style="blue"))
            elif accion == "adb_install":
                console.print(Panel(adb_install(accion_data.get("apk_path")), title="📱 ADB Install", border_style="blue"))
            elif accion == "adb_shell":
                console.print(Panel(adb_shell(accion_data.get("command")), title="📱 ADB Shell", border_style="blue"))
            elif accion == "fastboot_devices":
                console.print(Panel(fastboot_devices(), title="⚡ Fastboot Devices", border_style="blue"))
            elif accion == "fastboot_flash":
                console.print(Panel(fastboot_flash(accion_data.get("partition"), accion_data.get("image")), title="⚡ Fastboot Flash", border_style="red"))
            elif accion == "setup_android_sdk":
                console.print(Panel(configurar_android_sdk(), title="🤖 Android SDK", border_style="yellow"))
            elif accion == "create_apk":
                console.print(Panel(crear_apk(), title="📱 APK", border_style="magenta"))
            elif accion == "self_improve":
                console.print(auto_mejora(accion_data.get("description"), accion_data.get("code_base64")))
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
    console.print(Panel("[bold bright_green]VERDIX Code v20.0[/]\n[dim]Creado por NOX | Powered by Groq[/]\nEscribe 'salir' para terminar.\nMemoria persistente activada. Tu historial se guarda en verdix_memory.db.", border_style="bright_green"))
    
    # Cargar estado persistente
    ultima_imagen_generada = cargar_estado("ultima_imagen")
    
    while True:
        try:
            prompt = Prompt.ask("\n[bold green]NOX[/]")
            if prompt.lower() in ['salir', 'exit', 'quit']: break
            if prompt.lower() == 'limpiar':
                limpiar_historial()
                historial = [{"role": "system", "content": SYSTEM_PROMPT}]
                console.print("[bold yellow]🧹 Memoria borrada.[/]")
                continue
            if not prompt.strip(): continue
            
            # Guardar mensaje en la BD
            guardar_mensaje("user", prompt)
            historial.append({"role": "user", "content": prompt})
            historial_reducido = [historial[0]] + historial[-8:] if len(historial) > 8 else historial
            
            with console.status("[bold yellow]Pensando..."):
                completion = client.chat.completions.create(
                    model=MODELO_LLM, messages=historial_reducido, temperature=0.1, max_tokens=3000
                )
                respuesta_raw = completion.choices[0].message.content.strip()
                guardar_mensaje("assistant", respuesta_raw)
                historial.append({"role": "assistant", "content": respuesta_raw})
            
            procesar_respuesta(respuesta_raw)
        except KeyboardInterrupt: break
        except Exception as e: console.print(f"[bold red]Error crítico:[/] {e}")

if __name__ == "__main__":
    main()

# === FIN DE NUEVAS FUNCIONES ===
