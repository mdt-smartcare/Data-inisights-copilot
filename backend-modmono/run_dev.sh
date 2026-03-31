#!/bin/bash
# Development server startup script

# Exit on error
set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
RELOAD=${RELOAD:-true}

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting FHIR RAG API Development Server...${NC}"
echo -e "${GREEN}Host: ${HOST}${NC}"
echo -e "${GREEN}Port: ${PORT}${NC}"
echo -e "${GREEN}Reload: ${RELOAD}${NC}"
echo ""

# Run uvicorn with reload for development
if [ "$RELOAD" = "true" ]; then
    uvicorn app.app:app \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        --reload-dir app \
        --log-level debug
else
    uvicorn app.app:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level info
fi
