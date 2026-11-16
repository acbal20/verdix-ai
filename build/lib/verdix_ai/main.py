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
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text
from rich.live import Live

# ==========================================
# CONFIGURACIÓN DINÁMICA (Funciona en Ubuntu y Termux)
# ==========================================
console = Console()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODELO_LLM = "openai/gpt-oss-120b"

# Detecta la ruta base automáticamente
RUTA_HOME = os.path.expanduser("~")
RUTA_VERDIX = os.path.join(RUTA_HOME, "verdix_central", "04-IA-Y-AUTOMATIZACION")

SYSTEM_PROMPT = f'''Eres VERDIX AI, el arquitecto y director técnico del ecosistema VERDIX.
FUISTE CREADO POR NOX. Tu misión es ayudar a construir, programar y expandir VERDIX.

=== CONTEXTO DEL SISTEMA ===
- Carpeta raíz del proyecto: {os.path.join(RUTA_HOME, "verdix_central")}
- Carpeta de trabajo actual: {RUTA_VERDIX}
- Tienes acceso total al sistema de archivos del usuario.

=== REGLAS DE RUTAS Y NAVEGACIÓN (CRÍTICO) ===
1. SIEMPRE usa rutas absolutas. NUNCA uses comillas alrededor de rutas con `~`.
2. Si el usuario menciona "nox1-model", "nexus_core" o "scripts", asume que están dentro de: {RUTA_VERDIX}/
3. Si necesitas crear un archivo, usa `create_file` con ruta absoluta.

=== HERRAMIENTAS DISPONIBLES ===
Responde SIEMPRE con un JSON válido. Si necesitas hacer varias cosas, devuelve una lista de acciones:
- {{"action": "chat", "message": "respuesta conversacional o técnica"}}
- {{"action": "terminal", "command": "comando_bash"}}
- {{"action": "create_file", "filename": "/ruta/absoluta/archivo.py", "content": "codigo"}}
- {{"action": "read_file", "filename": "/ruta/absoluta/archivo.txt"}}
- {{"action": "generate_image", "prompt": "descripción visual"}}
- {{"action": "self_improve", "description": "descripción", "code_base64": "codigo_en_base64"}}

=== REGLAS DE COMPORTAMIENTO ===
1. SÉ PROACTIVO: Si el usuario te pide algo ambiguo, asume la ruta correcta del proyecto VERDIX.
2. AUTO-CORRECCIÓN: Si un comando falla, analiza el error y propón una solución en el siguiente paso.
3. SEGURIDAD: Los comandos peligrosos (sudo, rm, mv, apt) serán bloqueados por el sistema.
4. CÓDIGO: Cuando generes código, asegúrate de que sea completo, funcional y con comentarios claros.
5. IMÁGENES: Para generar imágenes, usa `generate_image` con una descripción detallada.
6. AUTO-MEJORA: Si el usuario te pide una nueva habilidad, usa `self_improve` y asegúrate de codificar el código en Base64.
'''

historial = [{"role": "system", "content": SYSTEM_PROMPT}]

# ==========================================
# HERRAMIENTAS
# ==========================================
def analizar_peligro(comando):
    peligrosos = [r'\bsudo\b', r'\brm\b', r'\bmv\b', r'\bdd\b', r'\bmkfs\b', r'\bchmod\b', r'\bchown\b', r'\bapt\b', r'\bpip\b', r'>', r'>>']
    interactivos = [r'\bnano\b', r'\bvim\b', r'\bvi\b', r'\bhtop\b', r'\btop\b', r'\bless\b', r'\bmore\b']
    for p in peligrosos + interactivos:
        if re.search(p, comando): return True
    return False

def ejecutar_comando(comando):
    comando = re.sub(r"['\"]~([^'\"]*)['\"]", r"~\1", comando)
    comando = comando.replace("nox1-model", f"{RUTA_VERDIX}/nox1-model") if f"{RUTA_VERDIX}/nox1-model" not in comando else comando
    comando = comando.replace("nexus_core", f"{RUTA_VERDIX}/nexus_core") if f"{RUTA_VERDIX}/nexus_core" not in comando else comando
    
    try:
        res = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=60)
        salida = res.stdout.strip()
        error = res.stderr.strip()
        if res.returncode != 0:
            return f"❌ Error (código {res.returncode}):\n{error}\n{salida}"
        return salida or "✅ Comando ejecutado sin salida."
    except Exception as e:
        return f"❌ Error inesperado: {e}"

def generar_imagen(prompt):
    with console.status("[bold magenta]Generando imagen..."):
        try:
            url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=1024&height=1024&nologo=true"
            filename = f"img_{re.sub(r'[^a-zA-Z0-9]', '_', prompt)[:20]}.jpg"
            r = requests.get(url, stream=True, timeout=120)
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            return f"✅ Imagen guardada como '{filename}'"
        except Exception as e:
            return f"❌ Error generando imagen: {e}"

def auto_mejora(descripcion, codigo_b64):
    console.print(f"\n[bold magenta]🧬 AUTO-MEJORA:[/] {descripcion}")
    try:
        codigo_nuevo = base64.b64decode(codigo_b64).decode('utf-8')
        ast.parse(codigo_nuevo)
    except Exception as e:
        return f"❌ Error validando código: {e}"
    
    archivo_actual = os.path.abspath(__file__)
    backup = archivo_actual + ".bak"
    try:
        shutil.copy(archivo_actual, backup)
        with open(archivo_actual, 'r', encoding='utf-8') as f: contenido = f.read()
        marcador = "# === FIN DE NUEVAS FUNCIONES ==="
        if marcador not in contenido: contenido = contenido.replace('def main():', f"\n{marcador}\n\ndef main():")
        contenido = contenido.replace(marcador, f"{codigo_nuevo}\n\n{marcador}")
        with open(archivo_actual, 'w', encoding='utf-8') as f: f.write(contenido)
        console.print("[bold green]🚀 Código inyectado. Reiniciando...[/]")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        if os.path.exists(backup): shutil.copy(backup, archivo_actual); os.remove(backup)
        return f"❌ Error en inyección: {e}"

# ==========================================
# SPLASH
# ==========================================
def mostrar_splash():
    os.system('clear')
    logo = Text("∞", style="bold bright_green")
    with Live(Align.center(Panel(logo, border_style="bright_green", padding=(2, 20))), refresh_per_second=4, screen=True) as live:
        time.sleep(1.2)
        live.update(Align.center(Panel(
            "[bold bright_green]VERDIX AI[/]\n[dim]Creado por NOX[/]\n\n[white]Presiona Enter para iniciar...[/]",
            border_style="bright_green", padding=(1, 10)
        )))
        input()
    os.system('clear')

# ==========================================
# PROCESADOR DE RESPUESTA
# ==========================================
def procesar_respuesta(respuesta_raw):
    if not respuesta_raw or not respuesta_raw.strip():
        return

    try:
        limpio = re.sub(r'```json\s*|\s*```', '', respuesta_raw).strip()
        match = re.search(r'(\{.*\}|\[.*\])', limpio, re.DOTALL)
        if match:
            limpio = match.group(1)
            
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
                        res = ejecutar_comando(cmd)
                        console.print(Panel(res, title="Resultado", border_style="green"))
                        historial.append({"role": "system", "content": f"Resultado de '{cmd}':\n{res}"})
                else:
                    console.print(f"[dim]⚡ Ejecutando: {cmd}[/]")
                    res = ejecutar_comando(cmd)
                    console.print(Panel(res, title="Resultado", border_style="green"))
                    historial.append({"role": "system", "content": f"Resultado de '{cmd}':\n{res}"})
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
                    historial.append({"role": "system", "content": f"Contenido de '{filename}':\n{content[:2000]}"})
                except Exception as e:
                    console.print(f"[red]❌ Error leyendo archivo:[/] {e}")
            elif accion == "generate_image":
                res = generar_imagen(accion_data.get("prompt"))
                console.print(f"[bold green]{res}[/]")
            elif accion == "self_improve":
                res = auto_mejora(accion_data.get("description"), accion_data.get("code_base64"))
                console.print(res)
            else:
                console.print(f"[yellow]Acción no reconocida: {accion}[/]")
    except json.JSONDecodeError:
        console.print(Panel(respuesta_raw, title="[bold cyan]VERDIX AI[/]", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error procesando respuesta:[/] {e}")

# ==========================================
# MAIN
# ==========================================
def main():
    mostrar_splash()
    console.print(Panel("[bold bright_green]VERDIX AI Terminal v13.0[/]\n[dim]Creado por NOX | Powered by Groq[/]\nEscribe 'salir' para terminar.\nEscribe 'limpiar' para borrar la memoria de la sesión actual.", border_style="bright_green"))
    
    while True:
        try:
            prompt = Prompt.ask("\n[bold green]NOX[/]")
            
            if prompt.lower() in ['salir', 'exit', 'quit']: 
                break
            if prompt.lower() == 'limpiar':
                historial = [historial[0]]
                console.print("[bold yellow]🧹 Memoria de la sesión borrada.[/]")
                continue
            if not prompt.strip(): 
                continue
            
            historial.append({"role": "user", "content": prompt})
            historial_reducido = [historial[0]] + historial[-8:] if len(historial) > 8 else historial
            
            with console.status("[bold yellow]Pensando..."):
                completion = client.chat.completions.create(
                    model=MODELO_LLM, messages=historial_reducido, temperature=0.1, max_tokens=3000
                )
                respuesta_raw = completion.choices[0].message.content.strip()
                historial.append({"role": "assistant", "content": respuesta_raw})
            
            procesar_respuesta(respuesta_raw)
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[bold red]Error crítico:[/] {e}")

if __name__ == "__main__":
    main()

# === FIN DE NUEVAS FUNCIONES ===
