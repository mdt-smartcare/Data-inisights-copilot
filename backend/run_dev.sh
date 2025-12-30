#!/bin/bash
# Quick start script for backend development

echo "🚀 Starting FHIR RAG Backend API..."
echo "=================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    echo "📝 Copying from .env.example..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit backend/.env and add:"
    echo "   - Your real OPENAI_API_KEY"
    echo "   - A secure SECRET_KEY (run: openssl rand -hex 32)"
    echo ""
    exit 1
fi

# Check if venv exists
if [ ! -d "../.venv" ]; then
    echo "⚠️  Virtual environment not found at ../.venv"
    echo "Creating new venv..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
else
    echo "✓ Using existing virtual environment"
    source ../.venv/bin/activate
fi

echo ""
echo "✓ Environment activated"
echo "✓ Starting FastAPI server on http://0.0.0.0:8000"
echo ""
echo "📚 API Documentation: http://localhost:8000/api/v1/docs"
echo "🏥 Health Check: http://localhost:8000/api/v1/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=================================="
echo ""

# Run from parent directory to ensure correct module resolution
cd ..
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
