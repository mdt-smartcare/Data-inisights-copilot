# FHIR RAG API - Modular Monolith

Modern three-layer modular monolith architecture for FHIR RAG (Retrieval Augmented Generation) API.

## Architecture

- **Clean Architecture** with three layers:
  - **Presentation**: FastAPI routes, request/response handling
  - **Application**: Business logic, use cases, orchestration
  - **Infrastructure**: Database, external APIs, file systems

- **Agent-Centric Configuration**: Each agent has dedicated configs for chunking, PII, RAG, embeddings, LLM providers

- **Tech Stack**:
  - FastAPI + Uvicorn
  - SQLAlchemy 2.0 (async ORM)
  - PostgreSQL + asyncpg
  - Pydantic v2 for validation
  - OpenTelemetry for tracing
  - Structlog for logging

## Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# Required: OPENAI_API_KEY, POSTGRES_* settings
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

```bash
# Make sure PostgreSQL is running
# Database will be initialized on first startup

# Run migrations (when implemented)
# alembic upgrade head
```

### 4. Run Development Server

**Linux/Mac:**
```bash
chmod +x run_dev.sh
./run_dev.sh
```

**Windows:**
```batch
run_dev.bat
```

**Or directly:**
```bash
uvicorn app.app:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access API

- **API Documentation**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **Health Check**: http://localhost:8000/health

## Project Structure

```
backend-modmono/
├── app/
│   ├── core/                      # Shared infrastructure
│   │   ├── auth/                  # Authentication & permissions
│   │   ├── config/                # Configuration & defaults
│   │   ├── database/              # Database connection & ORM
│   │   ├── models/                # Shared Pydantic models
│   │   └── utils/                 # Logging, tracing, exceptions
│   │
│   ├── modules/                   # Domain modules
│   │   ├── users/                 # User management & auth
│   │   ├── agents/                # Agent management (largest module)
│   │   ├── chat/                  # Chat & query execution
│   │   ├── embeddings/            # Embedding jobs & vector stores
│   │   ├── ingestion/             # Data ingestion & SQL queries
│   │   └── observability/         # Audit logs & monitoring
│   │
│   └── app.py                     # FastAPI application entry point
│
├── tests/                         # Test suite (mirrors app/)
├── data/                          # Data storage (gitignored)
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
└── README.md                      # This file
```

## Configuration

### Environment Variables

Key settings in `.env`:

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=copilot
POSTGRES_USER=copilot_user
POSTGRES_PASSWORD=copilot_password

# Security
SECRET_KEY=your-secret-key-change-in-production
OPENAI_API_KEY=sk-...

# OIDC (optional)
OIDC_ISSUER_URL=https://keycloak.example.com/realms/myrealm
OIDC_CLIENT_ID=fhir-rag-api

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### System Defaults

Agent creation defaults defined in `app/core/config/defaults.py`:
- Chunking: parent/child chunks, overlap
- PII exclusion rules
- RAG parameters (top_k, similarity threshold)
- Embedding models (OpenAI text-embedding-3-small)
- LLM defaults (GPT-4o-mini)

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test types
pytest -m unit
pytest -m integration
```

### Code Quality

```bash
# Format code
black app/
isort app/

# Lint
flake8 app/

# Type checking
mypy app/
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## Module Implementation Status

- ✅ **Core Infrastructure**: Database, auth, logging, tracing, exceptions
- ✅ **System Defaults**: Agent configuration templates
- 🚧 **Users Module**: Auth, RBAC, OIDC (pending implementation)
- 🚧 **Agents Module**: Agent CRUD, configs (pending implementation)
- 🚧 **Chat Module**: Query execution, RAG (pending implementation)
- 🚧 **Embeddings Module**: Vector stores, jobs (pending implementation)
- 🚧 **Ingestion Module**: File upload, SQL queries (pending implementation)
- 🚧 **Observability Module**: Audit logs, metrics (pending implementation)

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Deployment

See `Dockerfile` for production deployment configuration.

```bash
# Build Docker image
docker build -t fhir-rag-api .

# Run container
docker run -p 8000:8000 --env-file .env fhir-rag-api
```

## License

Proprietary - All Rights Reserved
