# Data Insights AI-Copilot

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI" />
</p>

A production-ready Enterprise RAG system featuring a FastAPI backend and React frontend. It provides intelligent clinical data analysis through Hybrid Retrieval, synthesizing both relational data (SQL Agent) and unstructured narratives (Vector Search).

---

## System Architecture

```text
┌─────────────────┐
│  React Frontend │
└────────┬────────┘
         │ HTTP/REST (Port 8000)
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                Agent Service Pipeline                 │  │
│  │                                                       │  │
│  │ ┌──────────────┐     ┌───────────┐    ┌─────────────┐ │  │
│  │ │ Intent Router├────►│ SQL Agent │    │ Vector RAG  │ │  │
│  │ │  (A / B / C) │     └─────┬─────┘    └──────┬──────┘ │  │
│  │ └──────────────┘           │                 │        │  │
│  └────────────────────────────┼─────────────────┼────────┘  │
│                               │                 │           │
│  ┌────────────────────────────┼─────────────────┼────────┐  │
│  │ SQLite (Internal Config)   │                 │        │  │
│  │ Celery/Redis (Jobs/Tasks)  │                 │        │  │
│  │ Celery Beat (Scheduled)    │                 │        │  │
│  └────────────────────────────┼─────────────────┼────────┘  │
└───────────────────────────────┼─────────────────┼───────────┘
                                │                 │
                        ┌───────▼───────┐   ┌─────▼──────┐
                        │ Clinical DB   │   │ Vector DB  │
                        │ (PostgreSQL/  │   │ (Qdrant/    │
                        │ MySQL)        │   │ Chroma)    │
                        └───────────────┘   └────────────┘
```

## Core Features

- **Hybrid RAG Pipeline:** Combines traditional SQL queries (for structured clinical aggregations) with scalable Vector semantic search (for unstructured narrative notes). 
- **Dynamic Intent Routing:** Automatically classifies user queries into Intent A (SQL), Intent B (Vector), or Intent C (Hybrid). 
- **Automated RAG Evaluation:** Standalone testing module mapping metrics for Retrieval hit-rates, SQL DataFrame execution equivalence, RAGAS text metrics, and custom G-Eval Clinical safety guardrails.
- **Enterprise Observability:** Fully instrumented with Langfuse tracing, token estimation, and process latency logging.
- **Background Processing:** Celery + Redis message queues handle parsing and embedding large document workloads asynchronously without blocking the main API.
- **Scheduled Tasks:** Celery Beat handles triggering cyclical vector updates and database synchronization tasks reliably across workers.
- **Authentication:** Dual-mode authentication supporting local JWT tokens or full OpenID Connect (OIDC/Keycloak).
- **Multi-tenant Data Connections:** Admin UI provisions dynamic DB connection strings per agent at runtime.
- **Automatic Web Charts:** JSON-based UI rendering translates analytical outputs directly into dynamic graphical charts and visualizations within the chat.

---

## Latest Evaluation Results (March 11, 2026)

Based on the standalone `eval/` framework running against the Golden Dataset:

- **1. Retrieval Performance:** 
  - **Hit Rate @ 5:** `80.0%`
  - **Mean Reciprocal Rank (MRR @ 5):** `0.44`
- **2. Intent Routing Accuracy:** `72.5%` (Avg Latency: ~155ms)
- **3. SQL Generative Accuracy:** `80.0%` (Execution Equivalence)
- **4. Clinical Safety Guardrails:** `100% Pass Rate` (Average Agent Safety Score: 4.5/5)
- **5. End-to-End Pipeline Performance:** 
  - **Total Latency:** `~501ms` 
  - **Response ROUGE-L:** `0.28`

For full details on the testing methodology, refer to the [eval/README.md](eval/README.md).

---

## Quick Start

### 1. Prerequisites

- Python 3.9+
- Node.js & npm (Frontend)
- Redis Server (Required for Celery Background jobs)
- OpenAI API Key
- (Optional) Clinical database (PostgreSQL/MySQL) - configured via UI

### 2. Environment Setup

```bash
cd backend

# Copy environment template
cp .env.example .env

# Edit .env with your specific values
nano .env
```

**Required environment variables:**
```bash
# Core parameters
OPENAI_API_KEY=sk-your-actual-key-here
SECRET_KEY=$(openssl rand -hex 32)
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 3. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Initialize Database

```bash
# Run migrations to create internal config tables
for f in migrations/*.sql; do sqlite3 backend/sqliteDb/copilot.db < "$f"; done
```

### 5. Start the Services

You must run the FastApi Backend, the Celery Queue, and the Frontend.

**Terminal 1 (FastAPI Server):**
```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 (Celery Background Worker & Beat):**
```bash
# Start worker
python -m celery -A app.core.celery_app worker --loglevel=info

# Start Beat (in another terminal or as background process)
python -m celery -A app.core.celery_app beat --loglevel=info
```

**Terminal 3 (React Frontend):**
```bash
npm install
npm run dev
```

### 6. Configure Runtime App Connections

1. Open http://localhost:5173 (frontend base url).
2. Navigate to **Settings > Database Connections**.
3. Add your clinical database string (PostgreSQL/MySQL/SQLite).
4. Create a **RAG Configuration** that binds the respective DB connection.
5. Set Model rules and **Publish** the configuration to begin routing queries!

---

## Project Documentation

For detailed technical guides and system documentation, please refer to our **[GitHub Wiki](https://github.com/Medtronic-LABS/data-insights-copilot/wiki)** or the local [docs/](docs/) directory:

| Guide | Description |
|-------|-------------|
| [**Setup & Installation**](docs/SETUP_STEP_BY_STEP.md) | Foolproof guide for local and Docker setup. |
| [**Agent Creation**](docs/AGENT_CREATION_GUIDE.md) | Step-by-step assistant configuration. |
| [**Ingestion & Indexing**](docs/INGESTION_GUIDE.md) | Managing vector and SQL data intake. |
| [**Backend Architecture**](docs/Backend.md) | Technical deep-dive into the modular monolith. |
| [**Database Schema**](docs/Database.md) | Core PostgreSQL and Qdrant table definitions. |
| [**Observability**](docs/Observability.md) | Tracing, logging, and QA Debug metadata. |
| [**Troubleshooting**](docs/Troubleshooting.md) | Common errors and how to fix them. |

---

## Configuration Architecture

### Infrastructure Settings (`.env`)
These settings require a server restart:
- `OPENAI_API_KEY` - OpenAI models authentication
- `SECRET_KEY` - JWT local token signing key
- `OIDC_ISSUER_URL` - Keycloak/OIDC upstream URL
- `CELERY_BROKER_URL` - Redis Queue Configs
- `LANGFUSE_PUBLIC_KEY` - APM & Telemetry Keys

### Runtime Settings (Configured via UI Database)
Update on the fly without server restarts:
- **LLM Settings:** Model Name, Temperature, Output limits
- **Embedding:** Provider rules, Dense models
- **Schedule Configs:** Document refresh intervals and Vector sync rules
- **Clinical Data Policies:** Medical Terminology mapping, PII column exclusion logic

---

## API Documentation

Once the backend is live, review endpoint documentation at:
- **Swagger UI:** http://localhost:8000/api/v1/docs
- **ReDoc:** http://localhost:8000/api/v1/redoc

### Core Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | Attain JWT token using basic auth |
| `POST` | `/api/v1/chat` | Issue queries to the primary RAG Router |
| `POST` | `/api/v1/ingest/upload` | Queue clinical files for Celery async embedding |
| `GET`  | `/api/v1/settings` | Acquire currently active model settings |
| `GET`  | `/api/v1/vector/status`| Poll for status of scheduled sync jobs |

---

## Project Structure

```
.
├── backend/
│   ├── app.py                      # FastAPI entrypoint
│   ├── config.py                   # Dotenv Environment configurations
│   ├── .env                        # Local Environment Configs
│   │
│   ├── api/routes/                 # Core API boundaries (Chat, Auth, Settings)
│   ├── services/
│   │   ├── agent_service.py        # Central Chat Agent Router (A/B/C)
│   │   ├── celery_worker.py        # Async Queue worker for Embeddings
│   │   ├── sql_service.py          # Clinical DB text-to-sql translation
│   │   └── vector_store.py         # Qdrant/ChromaDB execution logic
│   │
│   ├── sqliteDb/                   # Base Copilot System configs (users, rules)
│   └── migrations/                 # Schema updates
│
├── frontend/                       # React / Vite / Tailwind App
├── eval/                           # RAG Testing Framework (Ragas, Exten)
│   ├── datasets/                   # Golden Q&A JSON tests
│   ├── reports/                    # CI/CD HTML Dashboards
│   └── sql_eval/                   # SQL Data Equivalence Evaluator
│
└── requirements.txt                # Dependency tree
```

## Docker Deployment

To spin everything up (including Redis, Langfuse telemetry, and Backend API) quickly using Docker:

```bash
# Setup secrets internally
export OPENAI_API_KEY=sk-your-key
export SECRET_KEY=$(openssl rand -hex 32)
export DB_PASSWORD=admin-sec

# Spin up entire mesh
docker-compose up -d

# Verify system health
docker-compose logs -f backend
```
