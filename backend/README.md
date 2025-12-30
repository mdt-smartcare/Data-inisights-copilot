# RAG Chatbot Backend API

Production-ready FastAPI backend service for the FHIR RAG Chatbot, providing intelligent clinical data analysis through hybrid retrieval (SQL + Vector Search).

---

## 🏗️ Architecture

```
┌─────────────────┐
│  React Frontend │
└────────┬────────┘
         │ HTTP/REST
         ▼
┌─────────────────────────────────────────┐
│         FastAPI Backend (Port 8000)      │
│  ┌──────────────────────────────────┐  │
│  │     Agent Service (RAG)          │  │
│  │  ┌────────────┐  ┌────────────┐ │  │
│  │  │ SQL Agent  │  │ RAG Search │ │  │
│  │  └─────┬──────┘  └──────┬─────┘ │  │
│  └────────┼─────────────────┼───────┘  │
└───────────┼─────────────────┼──────────┘
            │                 │
       ┌────▼────┐      ┌────▼─────┐
       │ Postgres│      │ ChromaDB │
       │  (SQL)  │      │ (Vectors)│
       └─────────┘      └──────────┘
```

---

## 📋 Features

- ✅ **RESTful API** - OpenAPI/Swagger documented endpoints
- ✅ **JWT Authentication** - Secure token-based auth
- ✅ **Hybrid RAG Pipeline** - SQL + Vector semantic search
- ✅ **Automatic Chart Generation** - JSON-based visualizations
- ✅ **Structured Logging** - JSON logs for observability
- ✅ **Health Monitoring** - Dependency health checks
- ✅ **CORS Enabled** - Ready for React frontend
- ✅ **Type Safety** - Pydantic validation on all I/O
- ✅ **Modular Design** - Clean separation of concerns
- ✅ **Test Coverage** - Automated pytest suite

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.9+
- PostgreSQL database (running)
- ChromaDB index (pre-built at `../data/indexes/chroma_db_advanced`)
- BGE-M3 model (downloaded at `../models/bge-m3`)

### 2. Environment Setup

```bash
cd backend

# Copy environment template
cp .env.example .env

# Edit .env with your values
nano .env
```

**Required environment variables:**
```bash
OPENAI_API_KEY=sk-your-actual-key-here
SECRET_KEY=$(openssl rand -hex 32)  # Generate secure key
DB_PASSWORD=your-secure-password
```

### 3. Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Run the Server

```bash
# Development mode (with auto-reload)
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Production mode
python -m backend.app
```

### 5. Verify Installation

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status":"healthy","version":"1.0.0",...}
```

---

## 📚 API Documentation

### Interactive Docs

Once the server is running:

- **Swagger UI:** http://localhost:8000/api/v1/docs
- **ReDoc:** http://localhost:8000/api/v1/redoc

### Authentication Flow

```bash
# 1. Login to get JWT token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'

# Response:
# {"access_token":"eyJhbGc...","token_type":"bearer","username":"admin","expires_in":1800}

# 2. Use token in subsequent requests
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"query":"How many patients have hypertension?"}'
```

### Core Endpoints

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `POST` | `/api/v1/auth/login` | ❌ No | Get JWT token |
| `POST` | `/api/v1/chat` | ✅ Yes | Query the RAG chatbot |
| `POST` | `/api/v1/feedback` | ✅ Yes | Submit user feedback |
| `GET` | `/api/v1/health` | ❌ No | Health check |

### Example: Chat Request

```json
POST /api/v1/chat
Authorization: Bearer <token>

{
  "query": "How many patients have hypertension?"
}
```

**Response:**
```json
{
  "answer": "There are 245 patients with diagnosed hypertension...",
  "chart_data": {
    "title": "HTN Distribution",
    "type": "pie",
    "data": {"labels": ["Stage 1", "Stage 2"], "values": [120, 125]}
  },
  "suggested_questions": [
    "What is the average age of hypertensive patients?",
    "Show glucose levels for diabetic patients"
  ],
  "reasoning_steps": [...],
  "embedding_info": {...},
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-12-30T10:30:00Z"
}
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=html

# Run specific test file
pytest backend/tests/test_chat_api.py

# Run tests in verbose mode
pytest -v

# Skip integration tests (requires live services)
pytest -m "not skip"
```

---

## 📁 Project Structure

```
backend/
├── app.py                    # FastAPI entrypoint
├── config.py                 # Settings & environment management
├── requirements.txt          # Dependencies
├── .env.example             # Environment template
├── README.md                # This file
│
├── api/
│   ├── deps.py              # Dependency injection (auth)
│   └── routes/
│       ├── auth.py          # POST /login
│       ├── chat.py          # POST /chat
│       ├── feedback.py      # POST /feedback
│       └── health.py        # GET /health
│
├── core/
│   ├── security.py          # JWT & password hashing
│   └── logging.py           # Structured JSON logging
│
├── models/
│   ├── schemas.py           # Pydantic request/response models
│   └── db_models.py         # SQLAlchemy ORM (future)
│
├── services/
│   ├── agent_service.py     # Main RAG orchestration
│   ├── embeddings.py        # BGE-M3 wrapper
│   ├── vector_store.py      # ChromaDB interface
│   └── sql_service.py       # PostgreSQL queries
│
└── tests/
    ├── conftest.py          # Pytest fixtures
    ├── test_chat_api.py     # API integration tests
    └── test_agent_service.py # Service unit tests
```

---

## 🔧 Configuration

### Key Settings (`.env`)

```bash
# API Configuration
API_V1_PREFIX=/api/v1
DEBUG=false

# Security
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Embeddings
EMBEDDING_MODEL_PATH=./models/bge-m3
VECTOR_DB_PATH=./data/indexes/chroma_db_advanced

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 🔐 Default Users

**Temporary hardcoded users** (will be migrated to database):

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin` | Admin |
| `analyst` | `analyst2024` | Analyst |
| `viewer` | `view123` | Viewer |

---

## 🐛 Debugging

### Enable Debug Mode

```bash
# In .env
DEBUG=true
LOG_LEVEL=DEBUG
```

### View Logs

```bash
# Real-time logs
tail -f ../logs/backend.log

# Pretty-print JSON logs
tail -f ../logs/backend.log | jq .
```

### Common Issues

**Issue:** `ModuleNotFoundError: No module named 'backend'`  
**Solution:** Run from project root: `python -m backend.app` or use `PYTHONPATH=.`

**Issue:** `Could not validate credentials`  
**Solution:** Ensure `SECRET_KEY` is at least 32 characters

**Issue:** `Database connection failed`  
**Solution:** Check PostgreSQL is running and `DATABASE_URL` is correct

**Issue:** `Vector store not found`  
**Solution:** Verify ChromaDB index exists at `VECTOR_DB_PATH`

---

## 🚢 Deployment

### Docker (Recommended)

```dockerfile
# Coming soon - Dockerfile will be provided
```

### Manual Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Set production environment
export DEBUG=false
export LOG_LEVEL=INFO

# Run with gunicorn (production ASGI server)
gunicorn backend.app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 📈 Performance

- **Average Response Time:** ~2-3s (depends on LLM)
- **Concurrent Requests:** Supports async operations
- **Rate Limiting:** 60 requests/minute (configurable)

---

## 🤝 Integration with Frontend

### React/Next.js Example

```typescript
const API_BASE = 'http://localhost:8000/api/v1';

// Login
const loginResponse = await fetch(`${API_BASE}/auth/login`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username: 'admin', password: 'admin'})
});
const {access_token} = await loginResponse.json();

// Chat query
const chatResponse = await fetch(`${API_BASE}/chat`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({query: 'How many patients have HTN?'})
});
const data = await chatResponse.json();
console.log(data.answer);
```

---

## 📝 Development Workflow

1. **Make changes** to backend code
2. **Run tests:** `pytest`
3. **Check formatting:** (optional) `black backend/`
4. **Verify API:** Visit `/api/v1/docs`
5. **Check logs:** `tail -f ../logs/backend.log`

---

## 🔄 Next Steps / Roadmap

- [ ] Migrate users from hardcoded dict to PostgreSQL table
- [ ] Add rate limiting middleware
- [ ] Implement refresh tokens
- [ ] Add request ID propagation
- [ ] Set up CI/CD pipeline
- [ ] Add Dockerfile & docker-compose
- [ ] Implement response caching
- [ ] Add metrics/monitoring (Prometheus)

---

## 📞 Support

For issues or questions:
- Check the [API documentation](http://localhost:8000/api/v1/docs)
- Review logs in `../logs/backend.log`
- Verify health endpoint: `GET /api/v1/health`

---

**Built with:** FastAPI • LangChain • PostgreSQL • ChromaDB • BGE-M3
