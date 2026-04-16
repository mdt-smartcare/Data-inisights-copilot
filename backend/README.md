# FHIR RAG API - Modular Monolith

Modern three-layer modular monolith architecture for FHIR RAG (Retrieval Augmented Generation) API.

> **Architecture Update (2026-03-31):** Modules now use **flat file structure** instead of nested presentation/application/infrastructure folders. Three-layer architecture is maintained through code organization (models.py, repository.py, service.py, schemas.py, routes.py).

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
│   ├── modules/                   # Domain modules (flat file structure)
│   │   ├── users/
│   │   │   ├── models.py          # ORM models (infrastructure)
│   │   │   ├── repository.py     # Data access (infrastructure)
│   │   │   ├── service.py         # Business logic (application)
│   │   │   ├── schemas.py         # Pydantic DTOs (presentation)
│   │   │   ├── auth_routes.py     # Auth endpoints (presentation)
│   │   │   └── routes.py          # User endpoints (presentation)
│   │   │
│   │   ├── agents/                # Agent management
│   │   │   ├── models.py          # AgentModel, SystemPromptModel, etc.
│   │   │   ├── repository.py     # Agent data access
│   │   │   ├── service.py         # Agent business logic
│   │   │   ├── schemas.py         # Agent DTOs
│   │   │   └── routes.py          # Agent API endpoints
│   │   │
│   │   ├── observability/         # Audit logs & monitoring
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── routes.py
│   │   │
│   │   ├── chat/                  # (pending implementation)
│   │   ├── embeddings/            # (pending implementation)
│   │   └── ingestion/             # (pending implementation)
│   │
│   └── app.py                     # FastAPI application entry point
│
├── tests/                         # Test suite (mirrors app/)
├── data/                          # Data storage (gitignored)
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
└── README.md                      # This file
```

**Module Organization:**
- Each module uses **flat file structure** (no nested subdirectories)
- Files are organized by responsibility:
  - `models.py` - SQLAlchemy ORM models (infrastructure layer)
  - `repository.py` - Database queries and data access (infrastructure layer)
  - `service.py` - Business logic and orchestration (application layer)
  - `schemas.py` - Pydantic request/response models (presentation layer)
  - `routes.py` - FastAPI endpoints (presentation layer)
- Three-layer architecture is maintained through code organization, not folder structure

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
- ✅ **Users Module**: User CRUD, authentication, RBAC (JWT + OIDC)
  - 13 endpoints: login, me, user management, password operations
- ✅ **Observability Module**: Audit logging, system monitoring
  - 3 endpoints: query logs, recent logs, user activity
- ✅ **Agents Module**: Agent CRUD, full configuration management
  - 28 endpoints: CRUD, user access, 8 config types, system prompts
- 🚧 **Chat Module**: Query execution, RAG pipeline (pending)
- 🚧 **Embeddings Module**: Vector stores, embedding jobs (pending)
- 🚧 **Ingestion Module**: File upload, SQL queries (pending)

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
