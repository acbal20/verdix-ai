# VERDIX

## ¿Qué es VERDIX?

**VERDIX** es el ecosistema integral de desarrollo creado por **Nox** para la automatización inteligente, IA y despliegue de aplicaciones móviles. Incluye:
- **verdixcode**: una librería Python que facilita la interacción con los modelos de IA y la gestión de datos.
- Un **servidor web** basado en FastAPI que expone una interfaz de chat minimalista.
- Herramientas para **generar APKs** Android mediante Buildozer, listas para ser instaladas en dispositivos.

---

## Instalación de `verdixcode`

bash
# Clonar el repositorio principal (si aún no lo tienes)
git clone https://github.com/acbal20/verdix-ai.git
cd verdix-ai

# Crear un entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate

# Instalar la librería verdixcode y sus dependencias
pip install -e ./verdixcode


> **Nota:** `verdixcode` está disponible como paquete editable (`-e`) para que puedas modificarlo y volver a instalar sin perder cambios.

---

## Ejecutar la aplicación web (FastAPI)

1. **Instalar dependencias** (solo la primera vez):
bash
   pip install fastapi uvicorn torch transformers sentencepiece

2. **Iniciar el servidor**:
bash
   cd verdix_central/04-IA-Y-AUTOMATIZACION
   nohup uvicorn app:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &

3. **Comprobar que funciona**:
bash
   curl -I http://127.0.0.1:8000/

   Deberías recibir un `200 OK` y el HTML de la página de chat.

---

## Generar la APK de VERDIX

### Prerrequisitos
- **Android SDK** configurado (ver sección *Configuración del Android SDK* más abajo).
- **Buildozer** instalado (`pip install buildozer`).
- **Java JDK 17** (`sudo apt install openjdk-17-jdk`).
- Herramientas de compilación (`sudo apt install git zip unzip libncurses5-dev libstdc++6`).

### Pasos para compilar
1. **Entrar al directorio del paquete**:
bash
   cd verdix_ai_package

2. **Inicializar Buildozer (solo la primera vez)**:
bash
   buildozer init

   Edita el archivo `buildozer.spec` según tus necesidades (por ejemplo, `package.name`, `package.domain`, permisos, etc.).
3. **Compilar la APK**:
bash
   buildozer -v android debug

   El proceso descargará el NDK, SDK y todas las dependencias necesarias. Al finalizar, la APK se encontrará en `bin/` con un nombre similar a `verdix_ai_package-0.1-debug.apk`.
4. **Instalar la APK en un dispositivo conectado** (opcional):
bash
   adb install -r bin/verdix_ai_package-0.1-debug.apk


### Solución de problemas comunes
- **Error de SDK no encontrado**: asegúrate de que la variable `ANDROID_SDK_ROOT` apunte a `~/Android/Sdk` y que `platform-tools` esté en el `PATH`.
- **Falta de licencias**: ejecuta `yes | $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --licenses`.
- **Problemas de memoria**: usa `buildozer android clean` antes de volver a compilar.

---

## Configuración del Android SDK (resumen rápido)
bash
# Instalar paquetes necesarios
sudo apt update && sudo apt install -y adb fastboot openjdk-17-jdk wget unzip

# Descargar Command Line Tools
mkdir -p ~/Android/Sdk/cmdline-tools
wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/cmdline-tools.zip
unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline-tools-temp
mv /tmp/cmdline-tools-temp/cmdline-tools ~/Android/Sdk/cmdline-tools/latest
rm -rf /tmp/cmdline-tools.zip /tmp/cmdline-tools-temp

# Configurar variables de entorno (añadir a ~/.bashrc o ~/.zshrc)
export ANDROID_SDK_ROOT=~/Android/Sdk
export PATH=$PATH:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools

# Aceptar licencias e instalar platform-tools
yes | sdkmanager --sdk_root=$ANDROID_SDK_ROOT "platform-tools"
yes | sdkmanager --sdk_root=$ANDROID_SDK_ROOT --licenses


---

## ¡Listo!
Con estos pasos tendrás **VERDIX** funcionando tanto en la web como en dispositivos Android. Si necesitas más información, revisa la documentación interna del proyecto o abre un *issue* en el repositorio.
