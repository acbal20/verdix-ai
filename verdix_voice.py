import os
import sys
import json
import queue
import sounddevice as sd
import vosk
import pyttsx3
from groq import Groq

# ==========================================
# CONFIGURACIÓN
# ==========================================
MODEL_PATH = os.path.expanduser("~/vosk-model-es/vosk-model-small-es-0.42")
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODELO = "openai/gpt-oss-20b"

SYSTEM_PROMPT = """Eres VERDIX, un asistente de voz creado por NOX.
Responde de forma breve, natural y directa, como si estuvieras hablando.
No uses JSON ni formato técnico en tus respuestas de voz. Solo texto plano y conversacional."""

# Inicializar TTS
engine = pyttsx3.init()
engine.setProperty('rate', 160)
voices = engine.getProperty('voices')
for voice in voices:
    if 'spanish' in voice.name.lower() or 'es' in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

def hablar(texto):
    print(f"🤖 VERDIX: {texto}")
    engine.say(texto)
    engine.runAndWait()

def escuchar():
    model = vosk.Model(MODEL_PATH)
    q = queue.Queue()
    
    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        q.put(bytes(indata))
    
    print("🎤 Escuchando... (habla ahora)")
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype='int16',
                           channels=1, callback=callback):
        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                texto = result.get("text", "").strip()
                if texto:
                    print(f"👤 Tú: {texto}")
                    return texto

def procesar_peticion(prompt):
    try:
        completion = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Lo siento, hubo un error: {e}"

if __name__ == "__main__":
    hablar("Hola NOX, soy VERDIX, tu asistente personal. ¿En qué puedo ayudarte?")
    
    while True:
        try:
            texto = escuchar()
            if not texto:
                continue
            
            if any(palabra in texto.lower() for palabra in ["adiós", "salir", "detente", "para"]):
                hablar("Hasta luego, NOX.")
                break
            
            respuesta = procesar_peticion(texto)
            hablar(respuesta)
            
        except KeyboardInterrupt:
            hablar("Hasta luego.")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            hablar("Lo siento, hubo un error. Intenta de nuevo.")
