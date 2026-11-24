#!/bin/bash
# ==========================================
# VERDIX AI - Script de Despliegue a GitHub y Vercel
# ==========================================
set -e

echo "╔════════════════════════════════════════════════╗"
echo "║     VERDIX AI - Despliegue a GitHub + Vercel   ║"
echo "║              Creado por NOX                    ║"
echo "╚═════════════════════════════════════════════════╝"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "verdix_ai/main.py" ]; then
    echo "❌ ERROR: Ejecuta este script desde ~/verdix-ai/"
    exit 1
fi

# -------------------------------------------------
# 1. Verificar variables de entorno
# -------------------------------------------------
echo "🔍 Verificando variables de entorno..."

MISSING=""
[ -z "$GROQ_API_KEY" ] && MISSING="$MISSING GROQ_API_KEY"
[ -z "$GITHUB_TOKEN" ] && MISSING="$MISSING GITHUB_TOKEN"
[ -z "$VERCEL_TOKEN" ] && MISSING="$MISSING VERCEL_TOKEN"

if [ -n "$MISSING" ]; then
    echo "❌ Faltan variables de entorno:$MISSING"
    echo ""
    echo "Configúralas antes de continuar:"
    echo "  export GROQ_API_KEY='tu_clave'"
    echo "  export GITHUB_TOKEN='tu_token_github'"
    echo "  export VERCEL_TOKEN='tu_token_vercel'"
    echo ""
    echo "O copia .env.example a .env y edítalo:"
    echo "  cp .env.example .env"
    echo "  source .env"
    exit 1
fi

echo "✅ Variables de entorno OK"
echo ""

# -------------------------------------------------
# 2. Git: Inicializar y subir a GitHub
# -------------------------------------------------
echo "📦 Configurando Git..."

if [ ! -d ".git" ]; then
    git init
    echo "✅ Git inicializado"
else
    echo "✅ Git ya está inicializado"
fi

git add .
git commit -m "VERDIX AI v30.0 - Multi-agente + Sandbox + GitHub + Vercel" || echo "⚠️  No hay cambios para commit o commit previo"

# Preguntar si quiere subir a GitHub remoto
echo ""
read -p "¿Subir a GitHub? (requiere GITHUB_TOKEN configurado) [s/N]: " SUBIR_GIT
if [[ "$SUBIR_GIT" =~ ^[Ss]$ ]]; then
    echo "🔗 Conectando a GitHub..."
    
    # Obtener usuario de GitHub
    GH_USER=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])" 2>/dev/null || echo "")
    
    if [ -z "$GH_USER" ]; then
        echo "❌ No se pudo obtener el usuario de GitHub. Verifica tu GITHUB_TOKEN."
    else
        echo "✅ Usuario GitHub: $GH_USER"
        
        # Preguntar nombre del repositorio
        read -p "Nombre del repositorio [verdix-ai]: " REPO_NAME
        REPO_NAME=${REPO_NAME:-verdix-ai}
        
        # Crear repositorio si no existe
        curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            https://api.github.com/user/repos \
            -d "{\"name\":\"$REPO_NAME\",\"private\":true,\"auto_init\":false}" > /dev/null 2>&1 || true
        
        # Agregar remote y subir
        git remote remove origin 2>/dev/null || true
        git remote add origin "https://$GITHUB_TOKEN@github.com/$GH_USER/$REPO_NAME.git"
        git branch -M main
        git push -u origin main || echo "⚠️  Error al push. Puede que el repositorio ya tenga contenido."
        
        echo "✅ Subido a GitHub: https://github.com/$GH_USER/$REPO_NAME"
    fi
else
    echo "⏭️  Se omite subida a GitHub."
fi

# -------------------------------------------------
# 3. Vercel: Desplegar
# -------------------------------------------------
echo ""
echo "☁️  Desplegando en Vercel..."

read -p "¿Desplegar en Vercel? (requiere VERCEL_TOKEN) [s/N]: " DESPLEGAR_VERCEL
if [[ "$DESPLEGAR_VERCEL" =~ ^[Ss]$ ]]; then
    # Instalar Vercel CLI si no está
    if ! command -v vercel &> /dev/null; then
        echo "📦 Instalando Vercel CLI..."
        npm install -g vercel || echo "⚠️  No se pudo instalar Vercel CLI vía npm"
    fi
    
    if command -v vercel &> /dev/null; then
        echo "🚀 Desplegando..."
        vercel deploy --prod --token "$VERCEL_TOKEN" || echo "⚠️  Error en despliegue de Vercel"
        echo "✅ Despliegue en Vercel completado"
    else
        echo "❌ Vercel CLI no disponible. Instálalo manualmente:"
        echo "   npm install -g vercel"
        echo "   Luego ejecuta: vercel deploy --prod --token \$VERCEL_TOKEN"
    fi
else
    echo "⏭️  Se omite despliegue en Vercel."
fi

echo ""
echo "╔═════════════════════════════════════════════════╗"
echo "║         Despliegue finalizado                  ║"
echo "╚═════════════════════════════════════════════════╝"
