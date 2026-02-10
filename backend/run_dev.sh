#!/bin/bash
# Quick start script for backend development

echo "🚀 Starting Data Insights Copilot Backend..."
echo "=========================================="
echo ""

# Ensure we are in the backend directory
cd "$(dirname "$0")"

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    if [ -f ../.env.example ]; then
        echo "📝 Copying from root .env.example..."
        cp ../.env.example .env
    elif [ -f .env.example ]; then
         echo "📝 Copying from backend .env.example..."
         cp .env.example .env
    else
        echo "❌ No .env.example found. Please create .env manually."
        exit 1
    fi
fi

# Activate Virtual Environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
else
    echo "⚠️  Virtual environment not found."
    echo "🔨 Creating new venv..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "✓ Environment activated"
echo "✓ Starting FastAPI server on http://0.0.0.0:8000"
echo ""
echo "📚 API Documentation: http://localhost:8000/api/v1/docs"
echo "=========================================="
echo ""

# Run from project root to ensure correct module resolution
cd ..
python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
