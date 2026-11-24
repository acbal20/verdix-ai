#!/bin/bash
# ==========================================
# VERDIX AI - Configuración inicial
# ==========================================

echo "🔧 Configurando VERDIX AI..."

# Activar entorno virtual
if [ -f ~/verdix-env/bin/activate ]; then
    source ~/verdix-env/bin/activate
    echo "✅ Entorno virtual activado"
fi

# Instalar dependencias
echo "📦 Instalando dependencias Python..."
pip install -r requirements.txt || echo "⚠️  Error instalando dependencias"

# Crear .env si no existe
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Archivo .env creado desde .env.example"
    echo "⚠️  EDITA .env y agrega tus claves reales antes de ejecutar verdixcode"
else
    echo "✅ .env ya existe"
fi

# Hacer ejecutables
chmod +x deploy.sh
chmod +x iniciar_verdix.sh

echo ""
echo "╔═════════════════════════════════════════════════╗"
echo "║         Configuración completada               ║"
echo "╚═════════════════════════════════════════════════╝"
echo ""
echo "Próximos pasos:"
echo "  1. Edita .env con tus claves API reales"
echo "  2. source .env"
echo "  3. verdixcode          (para usar el asistente)"
echo "  4. ./deploy.sh         (para subir a GitHub y desplegar en Vercel)"
