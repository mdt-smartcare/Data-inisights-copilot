# Plan: Three-Layer Modular Monolith Backend Restructure (UPDATED)

**TL;DR:** Migrate FHIR RAG backend to clean architecture modular monolith in `backend-modmono/app/` with shared `/core` infrastructure and 6 domain modules. Each agent has dedicated configuration (chunking, PII, RAG, embedding, LLM, prompts) - new agents inherit system defaults. Use repository pattern per module, three-layer architecture (presentation/application/infrastructure).

> **Architecture Update (2026-03-31):** Modules now use **flat file structure** (models.py, repository.py, service.py, schemas.py, routes.py) instead of nested presentation/application/infrastructure folders. Three-layer architecture principles are maintained through code organization and dependency flow.

---

## Architecture Overview

**Note:** As of 2026-03-31, modules now use **flat file structure** instead of nested presentation/application/infrastructure folders. The three-layer architecture is maintained through code organization.

```
backend-modmono/
  /app                           ← Application code
    /core                        ← Minimal shared infrastructure
      /auth                      ← Auth decorators, security utils
        permissions.py
        security.py
      /database                  ← DB connection, base repository
        connection.py
        base_repository.py
      /models                    ← Truly shared models only
        auth.py                  ← User, Role, TokenData
        audit.py                 ← AuditEvent, AuditAction
        common.py                ← BaseResponse, ErrorResponse
      /utils                     ← Cross-cutting utilities
        logging.py
        tracing.py
        error_codes.py
        cancellation.py
      /config                    ← System defaults for new agents
        defaults.py              ← Default chunking, PII, RAG, embedding, LLM configs
      __init__.py
    
    /modules                     ← Domain modules (FLAT FILE STRUCTURE)
      /users                     ← User management & RBAC
        models.py                ← ORM models (infrastructure)
        repository.py            ← Data access (infrastructure)
        service.py               ← Business logic (application)
        schemas.py               ← Pydantic DTOs (presentation)
        auth_routes.py           ← Auth endpoints (presentation)
        routes.py                ← User mgmt endpoints (presentation)
      
      /agents                    ← Agent CRUD + ALL agent configs ⭐
        models.py                ← AgentModel, SystemPromptModel, PromptConfigModel (infrastructure)
        repository.py            ← Agent & config data access (infrastructure)
        service.py               ← Agent CRUD, config management (application)
        schemas.py               ← Agent/config DTOs (presentation)
        routes.py                ← 28 endpoints: CRUD, access, config, prompts (presentation)
      
      /chat                      ← RAG query pipeline (pending)
        models.py
        repository.py
        service.py               ← RAG orchestrator, intent router
        schemas.py
        routes.py                ← /chat, /feedback
      
      /embeddings                ← Embedding jobs, providers, vector store (pending)
        models.py
        repository.py
        service.py               ← Job service, batch processor
        schemas.py
        routes.py                ← /embedding-jobs, /embedding-progress
        providers.py             ← BGE, OpenAI, SentenceTransformer providers
      
      /ingestion                 ← Data ingestion & SQL (pending)
        models.py
        repository.py
        service.py               ← SQL service, file query service
        schemas.py
        routes.py                ← /data, /ingest, /vector-db
      
      /observability            ← Audit, tracing, notifications ✅ IMPLEMENTED
        models.py                ← AuditLogModel (infrastructure)
        repository.py            ← Audit queries (infrastructure)
        service.py               ← Centralized audit logging (application)
        schemas.py               ← Audit DTOs (presentation)
        routes.py                ← /audit/* endpoints (presentation)
    
    app.py                       ← FastAPI entry point
    config.py                    ← App-level config (DB URL, CORS, max upload size, rate limits)
    __init__.py
  
  requirements.txt
  Dockerfile
  pytest.ini
  /tests                         ← Mirrors /app/modules
  /docs
  /scripts
```

**Layer Responsibilities (Clean Architecture/DDD):**
- **Presentation**: FastAPI routes, request/response validation, HTTP concerns
- **Application**: Business logic, use cases, orchestration between services
- **Infrastructure**: External dependencies (DB, APIs, file systems, caching)

**Module Organization (Flat File Structure):**
- Each module contains files organized by responsibility, not folders
- `models.py` - SQLAlchemy ORM models (infrastructure layer)
- `repository.py` - Database queries and data access (infrastructure layer)
- `service.py` - Business logic and orchestration (application layer)
- `schemas.py` - Pydantic request/response models (presentation layer)
- `routes.py` - FastAPI endpoints (presentation layer)
- Three-layer architecture is maintained through code organization and dependency flow

**Agent-Centric Configuration:**
- Each agent has its own dedicated config (chunking, PII, medical context, vector store, RAG, embedding model, LLM provider, system prompts)
- New agents inherit system defaults from `/core/config/defaults.py` on creation
- Each agent can use different LLM providers (OpenAI, Claude, local models, etc.)
- All config endpoints are under `/agents/{agent_id}/config/*` and `/agents/{agent_id}/llm`, `/agents/{agent_id}/embedding`, etc.

**Global Settings (in `/app/config.py`):**
- Database connection string
- CORS settings
- Max file upload size
- Rate limiting
- Observability config (logging level, tracing endpoints)
- Authentication/security settings

---

## Implementation Phases

### **Phase 1: Core Infrastructure & Scaffolding** *(Foundation)*

1. Create directory structure in `backend-modmono/app/` with all module folders and empty `__init__.py` files

2. Set up `/core` infrastructure:
   - `/core/database/` - DB connection manager, base repository pattern
   - `/core/auth/` - Permission decorators, security utils  
   - `/core/utils/` - Logging, tracing, error codes, cancellation
   - `/core/config/defaults.py` - Default configurations for new agents

3. Migrate shared models to `/core/models/`:
   - `auth.py` - User, Role, TokenData (from backend/models/schemas.py)
   - `audit.py` - AuditEvent, AuditAction (from backend/services/audit_service.py)
   - `base.py` - BaseResponse, Pagination
   - `common.py` - Common DTOs, error schemas

4. Create `app.py` entry point with FastAPI setup, middleware, router registration placeholders

5. Create `config.py` with app-level configuration (DB, CORS, file upload limits, rate limiting)

*Steps 2-3 can run in parallel*

---

### **Phase 2: Foundation Modules** *(Users, Audit, System Defaults)*

#### **Step 6: Users & Auth Module** 
*Depends on: Phase 1*

**Files to create (flat structure):**
- `models.py` - UserModel ORM (from backend/models/schemas.py)
- `repository.py` - User database operations (from backend/database/queries.py)
- `service.py` - User business logic, role assignment
- `schemas.py` - UserCreate, UserUpdate, UserResponse DTOs
- `auth_routes.py` - Authentication endpoints (from backend/api/routes/auth.py)
- `routes.py` - User management endpoints (from backend/api/routes/users.py)

**Migration tasks:**
- Migrate `backend/api/routes/auth.py` → `auth_routes.py`
- Migrate `backend/api/routes/users.py` → `routes.py`
- Migrate `backend/services/authorization_service.py` → `service.py`
- Extract user queries from `backend/database/queries.py` → `repository.py`
- Extract audit logging calls to use core audit service

**Dependencies:** core.database, core.auth, core.models.auth

---

#### **Step 7: Observability Module (Audit only)**
*Depends on: Phase 1, parallel with step 6*

**Status:** ✅ IMPLEMENTED

**Files created:**
- `models.py` - AuditLogModel ORM
- `repository.py` - Audit log queries with filters
- `service.py` - Centralized audit logging service
- `schemas.py` - AuditLog DTOs
- `routes.py` - 3 audit query endpoints

**Presentation layer:**
- Migrate `backend/api/routes/audit.py` → `app/modules/observability/presentation/audit_routes.py`
- WebSocket: `backend/api/websocket/notifications.py` → `app/modules/observability/presentation/notification_ws.py`

**Application layer:**
- Migrate `backend/services/audit_service.py` → `app/modules/observability/application/audit_service.py`
- Migrate `backend/services/notification_service.py` → `app/modules/observability/application/notification_service.py`

**Infrastructure layer:**
- Create `audit_repository.py` for audit_logs table
- Create `notification_repository.py` for notifications table

**Dependencies:** core.database, core.models.audit

---

#### **Step 8: System Defaults Setup**
*Depends on: Phase 1, parallel with steps 6-7*

**Create `/core/config/defaults.py` with:**
- Default chunking config (parent_chunk_size, child_chunk_size, overlap, min_length)
- Default PII rules (global_exclude_columns, exclude_tables)
- Default medical context (terminology_mappings, clinical_flag_prefixes)
- Default vector store config (type, collection naming pattern)
- Default RAG config (top_k_initial, top_k_final, hybrid_weights, reranking)
- Default embedding config (provider, model, dimension)
- Default LLM config (provider, model, temperature, max_tokens)
- Default system prompt template

**Sources:** Extract from current `backend/config/embedding_config.yaml` and database defaults

*Steps 6, 7, 8 can run in parallel*

---

### **Phase 3: Core Business Modules** *(Agents, Embeddings, Chat)*

#### **Step 9: Agents Module** (LARGEST MODULE - owns all agent config)
*Depends on: Users module, System defaults (step 8)*

**Status:** ✅ IMPLEMENTED

**Files created (flat structure):**
- `models.py` - AgentModel, UserAgentModel, SystemPromptModel, PromptConfigModel
- `repository.py` - Agent & config data access with 20+ methods
- `service.py` - Agent CRUD, config management (all 8 config types)
- `schemas.py` - Agent/config DTOs (310 lines) - AgentCreate, AgentUpdate, all config types
- `routes.py` - 28 API endpoints: CRUD, user access, configs, prompts

**New route structure:**
```
# Agent CRUD
GET    /agents
POST   /agents                              ← Inherits defaults from core.config.defaults
GET    /agents/{agent_id}
PUT    /agents/{agent_id}
DELETE /agents/{agent_id}

# User access management (4 endpoints)
POST   /agents/{agent_id}/users             ← Grant access
DELETE /agents/{agent_id}/users/{user_id}  ← Revoke access
PUT    /agents/{agent_id}/users/{user_id}/role
GET    /agents/{agent_id}/users

# Agent-specific configuration (13 endpoints)
GET    /agents/{agent_id}/config
PUT    /agents/{agent_id}/config
GET    /agents/{agent_id}/config/chunking
PUT    /agents/{agent_id}/config/chunking
GET    /agents/{agent_id}/config/embedding
PUT    /agents/{agent_id}/config/embedding
GET    /agents/{agent_id}/config/rag
PUT    /agents/{agent_id}/config/rag
GET    /agents/{agent_id}/config/llm
PUT    /agents/{agent_id}/config/llm

# Agent-specific system prompts (3 endpoints)
POST   /agents/{agent_id}/prompts
POST   /agents/{agent_id}/prompts/{prompt_id}/activate
GET    /agents/{agent_id}/prompts/active
```

**Migration tasks completed:**
- Agent CRUD with default initialization from `/core/config/defaults.py`
- Agent-level configs stored as JSON in `prompt_configs` table
- System prompt versioning and activation
- User-agent RBAC (3-tier: user/editor/admin)
- Configuration caching per-agent

**Dependencies:** modules.users, core.config.defaults, core.database

---

#### **Step 10: Embeddings Module**
*Depends on: Agents module*

**Presentation layer:**
- Migrate `backend/api/routes/embedding_settings.py` → `app/modules/embeddings/presentation/settings_routes.py`
- Migrate `backend/api/routes/embedding_progress.py` → `app/modules/embeddings/presentation/progress_routes.py`
- Migrate websocket `backend/api/websocket/embedding_progress.py` → `app/modules/embeddings/presentation/progress_ws.py`

**Application layer:**
- Migrate `backend/services/embedding_job_service.py` → `app/modules/embeddings/application/job_service.py`
- Migrate `backend/services/embedding_batch_processor.py` → `app/modules/embeddings/application/batch_processor.py`
- Migrate `backend/services/embedding_checkpoint_service.py` → `app/modules/embeddings/application/checkpoint_service.py`
- Migrate `backend/services/embedding_document_generator.py` → `app/modules/embeddings/application/document_generator.py`

**Infrastructure layer:**
- Migrate `backend/services/embedding_providers.py` → `app/modules/embeddings/infrastructure/providers/`
  - `base_provider.py`
  - `bge_provider.py`
  - `openai_provider.py`
  - `sentence_transformer_provider.py`
- Migrate `backend/services/embeddings.py` → `app/modules/embeddings/infrastructure/embedding_client.py`
- Migrate `backend/services/embedding_registry.py` → `app/modules/embeddings/infrastructure/model_registry.py`
- Migrate `backend/services/vector_store.py` → `app/modules/embeddings/infrastructure/vector_store_client.py`
- Migrate `backend/services/chroma_service.py` → `app/modules/embeddings/infrastructure/chroma_client.py`
- Create `job_repository.py` for embedding_jobs, embedding_checkpoints tables

**Dependencies:** modules.agents (gets agent embedding config), modules.observability (notifications), core.utils.cancellation

---

#### **Step 11: Chat & Query Module**
*Depends on: Agents, Embeddings, Ingestion (SQL service)*

**Presentation layer:**
- Migrate `backend/api/routes/chat.py` → `app/modules/chat/presentation/routes.py`
- Migrate `backend/api/routes/feedback.py` → `app/modules/chat/presentation/feedback_routes.py`
- Create `schemas.py` for ChatRequest, ChatResponse, ReasoningStep, ChartData

**Application layer:**
- Extract RAG orchestration from `backend/services/agent_service.py` → `app/modules/chat/application/rag_orchestrator.py`
  - Fetches agent config from agents module
  - Uses agent's LLM provider config
- Migrate `backend/services/intent_router.py` → `app/modules/chat/application/intent_router.py`
- Migrate `backend/services/followup_service.py` → `app/modules/chat/application/followup_service.py`
- Migrate `backend/services/reflection_service.py` → `app/modules/chat/application/reflection_service.py`
- Create `feedback_service.py` for feedback collection

**Infrastructure layer:**
- Migrate `backend/services/llm_providers.py` → `app/modules/chat/infrastructure/llm_providers/`
  - `base_provider.py`
  - `openai_provider.py`
  - `anthropic_provider.py`
  - etc.
- Create `feedback_repository.py` for feedback table
- Query dependencies will reference `modules.ingestion.application.sql_service`

**Dependencies:** modules.agents (get agent config, LLM config), modules.embeddings (vector search), modules.ingestion (SQL service), modules.observability (audit)

---

### **Phase 4: Supporting Modules** *(Ingestion, Observability)*

#### **Step 12: Ingestion Module**
*Depends on: Agents module (for agent-specific DB connections)*

**Presentation layer:**
- Migrate `backend/api/routes/data.py` → `app/modules/ingestion/presentation/data_routes.py`
- Migrate `backend/api/routes/ingestion.py` → `app/modules/ingestion/presentation/ingestion_routes.py`
- Migrate `backend/api/routes/vector_db.py` → `app/modules/ingestion/presentation/vector_routes.py`

**Application layer:**
- Migrate `backend/services/sql_service.py` → `app/modules/ingestion/application/sql_service.py`
- Migrate `backend/services/file_query_service.py` → `app/modules/ingestion/application/file_query_service.py`
- Migrate `backend/services/file_sql_service.py` → `app/modules/ingestion/application/file_sql_service.py`
- Migrate `backend/services/schedule_manager.py` → `app/modules/ingestion/application/schedule_service.py`

**Infrastructure layer:**
- Create `file_storage.py` for file upload handling
- Create `duckdb_client.py` for DuckDB operations
- Create `db_connection_manager.py` for user database connections

**Dependencies:** modules.agents (agent config for DB connection), modules.embeddings (for vector ingestion), core.database

---

#### **Step 13: Complete Observability Module**
*Depends on: Phase 1-3 (adds tracing infrastructure)*

**Presentation layer:**
- Migrate `backend/api/routes/observability.py` → add to `app/modules/observability/presentation/observability_routes.py`
- Migrate `backend/api/routes/health.py` → `app/modules/observability/presentation/health_routes.py`

**Application layer:**
- Migrate `backend/services/observability_service.py` → `app/modules/observability/application/observability_service.py`

**Infrastructure layer:**
- Create `tracing_client.py` for Langfuse integration
- Already has audit_repository and notification_repository from step 7

**Dependencies:** core.utils.tracing, core.database

---

### **Phase 5: Integration & Testing**

#### **Step 14: Wire Up App Entry Point**
*Depends on: All modules*

1. Update `app/app.py`:
   - Import and register all module routers
   - Set up middleware (CORS, auth, error handling)
   - Initialize core services (DB, logging, tracing)
   - Mount websocket endpoints
2. Create dependency injection for shared services
3. Set up health check aggregation
4. Configure OpenAPI documentation with tags per module

---

#### **Step 15: Configuration & Environment**
*Parallel with step 14*

1. Create `app/config.py` for app-level configuration
   - Database connection (from env)
   - CORS settings
   - Max file upload size
   - Rate limiting
   - Observability endpoints
2. Port environment variables from `backend/.env.example`
3. Create `backend-modmono/requirements.txt` (copy from `backend/requirements.txt`)
4. Create `backend-modmono/Dockerfile` (adapt from `Dockerfile.backend`)
5. Create `backend-modmono/run_dev.sh` for local development

---

#### **Step 16: Pipeline & RAG Components**
*Depends on: Chat, Embeddings modules*

Migrate supporting components not covered in main modules:

1. Migrate `backend/pipeline/` → `app/modules/embeddings/infrastructure/pipeline/`
2. Migrate `backend/rag/` → `app/modules/chat/infrastructure/retrieval/`
3. Migrate `backend/vector_stores/` → `app/modules/embeddings/infrastructure/vector_stores/`

---

#### **Step 17: Test Migration**
*Depends on: All modules*

1. Create test structure mirroring module structure:
   ```
   backend-modmono/tests/
     /unit
       /modules
         /users
         /agents
         /chat
         /embeddings
         /ingestion
         /observability
     /integration
     /e2e
   ```
2. Migrate tests from `backend/tests/` to new structure
3. Update imports and fixtures
4. Create pytest configuration

---

## Verification Steps

**Per Module (after each):**
1. Import check: `python -c "from app.modules.{module_name} import *"` (no circular deps)
2. Route registration: Start app, check `/docs` for module endpoints
3. Database: Test repository CRUD operations
4. Logging: Verify structured logs with module context

**After Phase 2 (Foundation):**
1. Test user authentication flow: `/auth/me` endpoint
2. Test RBAC: Admin-only endpoint with regular user (should fail)
3. Test audit logging: Verify entries in audit_logs table
4. Test system defaults: Create new agent, verify configs populated from defaults

**After Phase 3 (Core Business):**
1. Test agent creation with defaults: Create agent → verify all configs populated
2. Test agent config update: Update agent chunking config → verify persisted and cached
3. Test agent LLM selection: Set agent to use Claude → verify RAG uses that provider
4. Test full RAG flow: Chat request → fetches agent config → intent routing → response
5. Test embedding job: Create job for agent → monitor websocket → verify vector storage
6. Test per-agent prompts: Update agent prompt → verify used in RAG

**After Phase 5 (Complete):**
1. Integration tests: Run full test suite
2. API compatibility: Verify endpoints work (routes may change, e.g., `/config` → `/agents/{id}/config`)
3. Performance: Compare response times with old backend
4. Database: Verify no schema changes needed (same tables)
5. Docker build & run
6. Load test: Concurrent requests to multiple agents

**Final validation:**
```bash
cd backend-modmono && ./run_dev.sh
pytest tests/integration/
tail -f logs/app.log

# Test multi-agent scenarios:
# - Create two agents with different LLM providers
# - Send queries to both, verify each uses its own LLM
# - Update one agent's chunking config, verify isolated from other agent
```

---

## Critical Files Reference

**Core Infrastructure:**
- `backend/database/base_repository.py` → `/core/database/base_repository.py`
- `backend/core/permissions.py` → `/core/auth/permissions.py`
- `backend/core/logging.py` → `/core/utils/logging.py`
- `backend/core/tracing.py` → `/core/utils/tracing.py`
- `backend/config/embedding_config.yaml` → Extract to `/core/config/defaults.py`

**Module Migrations (key files):**
- **Users**: `api/routes/users.py`, `services/authorization_service.py`
- **Agents** (LARGEST): `api/routes/agents.py`, `api/routes/config.py`, `api/routes/llm_settings.py`, `services/agent_service.py`, `services/config_service.py`
- **Chat**: `api/routes/chat.py`, `services/agent_service.py` (RAG orchestration parts)
- **Embeddings**: 8 files in `api/routes/embedding_*.py`, `services/embedding_*.py`
- **Ingestion**: `api/routes/data.py`, `api/routes/ingestion.py`, `services/sql_service.py`
- **Observability**: `api/routes/audit.py`, `services/audit_service.py`

---

## Decisions & Assumptions

**Architecture Decisions:**
- **Hybrid shared models**: User, Role, AuditEvent in `/core/models`; module-specific DTOs in modules
- **Repository per module**: Each module owns its data access layer, extends core's BaseRepository
- **Clean Architecture**: Presentation (routes) → Application (services) → Infrastructure (repos/clients)
- **Module-by-module**: Iterate through phases, not big-bang rewrite
- **Same database schema**: New structure uses existing tables, no schema changes
- **Agent-centric config**: Each agent has dedicated configs; new agents inherit from `/core/config/defaults.py`
- **Per-agent LLM providers**: Each agent can use different LLM providers (OpenAI, Claude, local models, etc.)
- **Keep /app folder**: For now, can be flattened later if desired

**Assumptions:**
1. `backend-modmono` starts empty - no conflicts with existing code
2. Old `backend/` remains untouched during migration for reference
3. Python 3.10+ with FastAPI, SQLAlchemy, Pydantic v2
4. Tests will be migrated after core functionality works
5. Frontend needs API route updates: `/config/*` → `/agents/{agent_id}/config/*` (breaking change)

**Included in scope:**
- All routes, services, models migration
- Core infrastructure setup
- Module structure with three layers each
- Agent-specific configuration system
- Configuration and entry point
- Test structure (but not writing new tests)

**Excluded from scope:**
- Frontend changes (API routes WILL change)
- Database migrations (using same schema, but may need agent_configs table modifications)
- Deployment configuration changes
- Documentation updates (can be separate task)
- Performance optimization (same performance expected)

---

## Dependencies Graph

```
Phase 1 (Core)
  ↓
Phase 2: Foundation Modules
  ├─ Users (step 6)
  ├─ Observability/Audit (step 7) ← parallel with Users
  └─ System Defaults (step 8) ← parallel with Users, Audit
  ↓
Phase 3: Core Business
  ├─ Agents (step 9) ← depends on Users, System Defaults
  ├─ Embeddings (step 10) ← depends on Agents
  └─ Chat (step 11) ← depends on Agents, Embeddings, (Ingestion's SQL service)
  ↓
Phase 4: Supporting
  ├─ Ingestion (step 12) ← depends on Agents (agent DB connections)
  └─ Observability complete (step 13) ← depends on Phase 1-3
  ↓
Phase 5: Integration
  ├─ App entry point (step 14)
  ├─ Config/env (step 15) ← parallel with step 14
  ├─ Pipeline/RAG components (step 16)
  └─ Tests (step 17)
```

**Parallel execution opportunities:**
- Steps 6, 7, 8 can be done in parallel (independent)
- Steps 14, 15 can be done in parallel
- Within Phase 1, steps 2-3 can be parallelized

---

## Further Considerations

1. **Database connection pooling**: Share core's single connection pool to avoid exhausting database connections. All modules get connections from `core.database`.
   
2. **Circular dependencies**: Use dependency injection and interface/protocol pattern. Define interfaces in application layer, implementations in infrastructure. Use FastAPI's `Depends()` for runtime injection.

3. **Websocket management**: Each module registers websocket routes in presentation layer. Core provides websocket manager utility in `/core/utils/websocket.py`.

4. **Test migration strategy**: Migrate critical tests with each module for validation, comprehensive test migration in Phase 5 step 17.

5. **System defaults inheritance**: On agent creation, copy defaults from `/core/config/defaults.py` into `agent_configs` table. Agents can then customize independently without affecting other agents.

6. **Config hot-reload per-agent**: When agent config changes, invalidate only that agent's cache. Use TTL-based caching similar to old backend's `settings_service`, but per-agent-id.

7. **Frontend API breaking changes**: Frontend will need updates for config routes: `/config/chunking` → `/agents/{agent_id}/config/chunking`. Consider API versioning or proxy routes for backward compatibility during transition.

8. **Agent config storage**: Store all agent configs in `agent_configs` table as JSONB column for flexibility, or create separate columns for each config type. JSONB allows dynamic schema evolution.

---

**READY TO START IMPLEMENTATION**: Plan is comprehensive and approved. Begin with Phase 1 (Core Infrastructure). Switch to implementation mode or ask specific questions about any step before proceeding.
