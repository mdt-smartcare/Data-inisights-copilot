# Data Insights AI-Copilot

Production-ready FastAPI backend service for the Data Insights AI-Copilot, providing intelligent data analysis through hybrid retrieval (SQL + Vector Search).

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
│  ┌──────────────────────────────────┐   │
│  │     Agent Service (RAG)          │   │
│  │  ┌────────────┐  ┌────────────┐  │   │
│  │  │ SQL Agent  │  │ RAG Search │  │   │
│  │  └─────┬──────┘  └──────┬─────┘  │   │
│  └────────┼─────────────────┼───────┘   │
│           │                 │           │
│  ┌────────▼─────────────────▼────────┐  │
│  │   SQLite (Config, Users, Settings) │  │
│  └───────────────────────────────────┘  │
└───────────┼─────────────────┼──────────┘
            │                 │
    ┌───────▼───────┐   ┌────▼─────┐
    │ Clinical DB   │   │ ChromaDB │
    │ (PostgreSQL)  │   │ (Vectors)│
    │ via db_conn   │   └──────────┘
    └───────────────┘
```

---

## 📋 Features

- ✅ **RESTful API** - OpenAPI/Swagger documented endpoints
- ✅ **JWT + OIDC Authentication** - Keycloak integration supported
- ✅ **Hybrid RAG Pipeline** - SQL + Vector semantic search
- ✅ **Automatic Chart Generation** - JSON-based visualizations
- ✅ **Dynamic Configuration** - Runtime settings via database
- ✅ **Multi-tenant Database Connections** - Configure via UI
- ✅ **Health Monitoring** - Dependency health checks
- ✅ **CORS Enabled** - Ready for React frontend

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.9+
- OpenAI API Key
- (Optional) Clinical database (PostgreSQL/MySQL) - configured via UI

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
# Only these are required in .env
OPENAI_API_KEY=sk-your-actual-key-here
SECRET_KEY=$(openssl rand -hex 32)  # Generate secure key
```

### 3. Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Initialize Database

```bash
# Run migrations to create tables
for f in migrations/*.sql; do sqlite3 backend/sqliteDb/copilot.db < "$f"; done
```

### 5. Run the Server

```bash
# Development mode (with auto-reload)
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Production mode
python -m backend.app
```

### 6. Configure Database Connection

1. Open http://localhost:3000 (frontend)
2. Go to **Settings > Database Connections**
3. Add your clinical database connection (PostgreSQL/MySQL)
4. Create a **RAG Configuration** that uses the connection
5. **Publish** the configuration

---

## 🔧 Configuration Architecture

### Infrastructure Settings (`.env`)
Required for server startup - cannot be changed at runtime:
- `OPENAI_API_KEY` - OpenAI API key
- `SECRET_KEY` - JWT signing key
- `OIDC_ISSUER_URL` - Keycloak URL (optional)
- `CORS_ORIGINS` - Allowed origins

### Runtime Settings (Database)
Configurable via frontend Settings page:
- **LLM**: model, temperature, max_tokens
- **Embedding**: provider, model, batch_size
- **RAG**: top_k, hybrid_weights, reranking
- **Chunking**: parent/child chunk sizes
- **Data Privacy**: PII column exclusions
- **Medical Context**: terminology mappings

### Clinical Database Connections
Managed via **Settings > Database Connections**:
- Add PostgreSQL/MySQL connections
- Assign to agents
- No hardcoded database URLs

---

## 📚 API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/api/v1/docs
- **ReDoc:** http://localhost:8000/api/v1/redoc

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | Get JWT token |
| `POST` | `/api/v1/chat` | Query the RAG chatbot |
| `GET` | `/api/v1/settings` | Get all settings |
| `PUT` | `/api/v1/settings/{category}` | Update settings |
| `GET` | `/api/v1/health` | Health check |

---

## 🐳 Docker Deployment

```bash
# Set required environment variables
export OPENAI_API_KEY=sk-your-key
export SECRET_KEY=$(openssl rand -hex 32)

# Start services
docker-compose up -d

# View logs
docker-compose logs -f backend
```

---

## 📁 Project Structure

```
backend/
├── app.py                    # FastAPI entrypoint
├── config.py                 # Infrastructure settings (.env)
├── .env.example              # Environment template
│
├── api/routes/               # API endpoints
├── services/
│   ├── settings_service.py   # Runtime config from DB
│   ├── agent_service.py      # RAG orchestration
│   ├── sql_service.py        # Clinical DB queries
│   └── vector_store.py       # ChromaDB interface
│
├── sqliteDb/
│   └── copilot.db            # Internal config database
│
└── migrations/               # SQL migrations
```

---

## 🔐 Authentication

Supports two modes:

1. **Local Auth** - Username/password with JWT tokens
2. **OIDC/Keycloak** - Set `OIDC_ISSUER_URL` in `.env`

---

**Built with:** FastAPI • LangChain • SQLite • ChromaDB • OpenAI
