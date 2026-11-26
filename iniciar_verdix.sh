#!/bin/bash
# ==========================================
# VERDIX AI - Script de Inicio Rápido
# ==========================================
set -e

echo "🚀 Iniciando VERDIX AI..."

# Activar entorno virtual si existe
if [ -f ~/verdix-env/bin/activate ]; then
    source ~/verdix-env/bin/activate
    echo "✅ Entorno virtual activado"
else
    echo "⚠️  Entorno virtual no encontrado en ~/verdix-env"
fi

# Cargar variables de entorno si existe .env
if [ -f ~/verdix-ai/.env ]; then
    export $(grep -v '^#' ~/verdix-ai/.env | xargs)
    echo "✅ Variables de entorno cargadas desde .env"
else
    echo "⚠️  No se encontró ~/verdix-ai/.env"
    echo "    Copia .env.example a .env y configura tus claves:"
    echo "    cp ~/verdix-ai/.env.example ~/verdix-ai/.env"
fi

# Verificar GROQ_API_KEY
if [ -z "$GROQ_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: Falta GROQ_API_KEY u OPENAI_API_KEY"
    echo "    Configura al menos una antes de continuar."
    exit 1
fi

# Ejecutar VERDIX
cd ~/verdix-ai
python -m verdix_ai.main "$@"
