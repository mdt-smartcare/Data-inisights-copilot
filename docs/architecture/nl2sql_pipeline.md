# NL2SQL Pipeline Architecture

> **Version:** 1.0  
> **Last Updated:** April 2026  
> **Author:** Data Insights Team

This document describes the architecture of the Natural Language to SQL (NL2SQL) pipeline, explaining how all components work together to convert user questions into accurate SQL queries.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture Diagram](#system-architecture-diagram)
3. [Query Flow](#query-flow)
4. [Components](#components)
5. [Data Flow](#data-flow)
6. [Configuration](#configuration)
7. [Accuracy Metrics](#accuracy-metrics)
8. [Deployment Architecture](#deployment-architecture)
9. [Extending the System](#extending-the-system)

---

## Overview

The NL2SQL pipeline converts natural language questions into SQL queries, executes them against configured databases, and returns formatted results with optional visualizations.

### Key Features

- **Intent Classification**: Routes queries to SQL, Vector, or Hybrid processing
- **Few-Shot Learning**: Retrieves similar Q&A examples to improve SQL accuracy
- **Query Relevance Checking**: Pre-filters irrelevant or PII-seeking queries
- **Schema Linking**: Maps natural language terms to database schema elements
- **Data Dictionary**: Provides business term definitions and default filters
- **SQL Validation**: Critiques and fixes generated SQL before execution
- **Chart Generation**: Automatically generates visualizations for suitable results

### Technology Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | FastAPI (Python 3.10+) |
| LLM Provider | OpenAI (GPT-4o, GPT-4o-mini) |
| Vector Database | Qdrant / ChromaDB |
| SQL Database | PostgreSQL / DuckDB |
| Embeddings | OpenAI text-embedding-ada-002 |
| ORM | SQLAlchemy 2.0 (async) |

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Chat UI     │  │ Settings    │  │ Analytics   │  │ Training Management     │ │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────┼───────────────────────────────────────────────────────────────────────┘
          │ HTTP/WebSocket
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND API (FastAPI)                                  │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                         Chat Service (Orchestrator)                       │   │
│  │  • Process incoming queries                                               │   │
│  │  • Coordinate all pipeline components                                     │   │
│  │  • Manage conversation memory                                             │   │
│  │  • Generate follow-up suggestions                                         │   │
│  └─────────────────────────────────┬────────────────────────────────────────┘   │
│                                    │                                             │
│    ┌───────────────────────────────┼───────────────────────────────────────┐    │
│    │                               ▼                                        │    │
│    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │    │
│    │  │ Intent          │  │ Relevance       │  │ Query           │        │    │
│    │  │ Classifier      │  │ Checker         │  │ Rewriter        │        │    │
│    │  │                 │  │                 │  │                 │        │    │
│    │  │ • A: SQL Only   │  │ • PII Detection │  │ • Context       │        │    │
│    │  │ • B: Vector     │  │ • Topic Check   │  │   Resolution    │        │    │
│    │  │ • C: Hybrid     │  │ • Syntax Check  │  │ • Memory        │        │    │
│    │  └────────┬────────┘  └────────┬────────┘  └─────────────────┘        │    │
│    │           │                    │                                       │    │
│    │           ▼                    ▼                                       │    │
│    │  ┌─────────────────────────────────────────────────────────────┐      │    │
│    │  │                      SQL Service                             │      │    │
│    │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │      │    │
│    │  │  │ Schema      │  │ Few-Shot    │  │ Data                │  │      │    │
│    │  │  │ Discovery   │  │ Retrieval   │  │ Dictionary          │  │      │    │
│    │  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │      │    │
│    │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │      │    │
│    │  │  │ Prompt      │  │ SQL         │  │ SQL                 │  │      │    │
│    │  │  │ Builder     │  │ Generator   │  │ Executor            │  │      │    │
│    │  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │      │    │
│    │  └─────────────────────────────────────────────────────────────┘      │    │
│    │                                                                        │    │
│    │                      QUERY PIPELINE                                    │    │
│    └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Vector Store   │  │  SQL Database   │  │  PostgreSQL     │
│  (Qdrant)       │  │  (DuckDB)       │  │  (App Data)     │
│                 │  │                 │  │                 │
│ • SQL Examples  │  │ • Clinical Data │  │ • Users         │
│ • Embeddings    │  │ • CSV Uploads   │  │ • Agents        │
│                 │  │                 │  │ • Configs       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Query Flow

### High-Level Flow

```
User Question
     │
     ▼
┌─────────────────────┐
│  1. Query Rewrite   │──── Resolve context from conversation history
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  2. Relevance Check │──── Reject PII requests, off-topic queries
└──────────┬──────────┘
           │ Pass
           ▼
┌─────────────────────┐
│  3. Intent Classify │──── Route to SQL (A), Vector (B), or Hybrid (C)
└──────────┬──────────┘
           │
     ┌─────┴─────┬─────────────┐
     │           │             │
     ▼           ▼             ▼
┌─────────┐ ┌─────────┐ ┌───────────┐
│ SQL (A) │ │Vector(B)│ │ Hybrid(C) │
└────┬────┘ └────┬────┘ └─────┬─────┘
     │           │             │
     └─────┬─────┴─────────────┘
           │
           ▼
┌─────────────────────┐
│  4. Schema Linking  │──── Map terms to tables/columns
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  5. Few-Shot        │──── Retrieve similar Q&A examples
│     Retrieval       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  6. Prompt Assembly │──── Build optimized prompt with all context
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  7. SQL Generation  │──── LLM generates SQL query
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  8. SQL Execution   │──── Execute against database
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  9. Response Format │──── Synthesize answer + generate chart
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 10. Analytics Log   │──── Log metrics (privacy-safe)
└─────────────────────┘
```

### Detailed Step-by-Step

#### Step 1: Query Rewrite
- Resolves pronouns and references using conversation history
- Example: "What about the female patients?" → "What is the count of female patients with high blood pressure?"

#### Step 2: Relevance Check
- **PII Detection**: Rejects queries asking for individual patient data
- **Context Check**: Ensures query relates to available database tables
- **Syntax Check**: Validates query is well-formed

#### Step 3: Intent Classification
Routes queries to appropriate handler:

| Intent | Description | Example |
|--------|-------------|---------|
| A (SQL Only) | Structured data queries | "How many patients have diabetes?" |
| B (Vector Only) | Document/narrative search | "Find clinical notes mentioning hypertension" |
| C (Hybrid) | SQL filter + vector search | "Show notes for male patients over 50" |

#### Step 4: Schema Linking
- Maps natural language terms to schema elements
- Resolves synonyms (e.g., "BP" → "avg_systolic", "avg_diastolic")
- Identifies relevant tables

#### Step 5: Few-Shot Retrieval
- Classifies query type (temporal, aggregation, etc.)
- Retrieves similar Q&A examples from vector store
- Provides pattern templates to guide SQL generation

#### Step 6: Prompt Assembly
Combines:
- System prompt with SQL rules
- Database schema
- Data dictionary context
- Few-shot examples
- User question

#### Step 7: SQL Generation
- LLM generates SQL based on assembled prompt
- Uses DuckDB/PostgreSQL-compatible syntax

#### Step 8: SQL Execution
- Executes generated SQL against configured data source
- Handles connection pooling and timeouts
- Enforces row limits

#### Step 9: Response Formatting
- Synthesizes natural language response
- Generates chart data if applicable
- Formats results as markdown tables

#### Step 10: Analytics Logging
- Logs execution metrics (no query content)
- Records success/failure for improvement analysis

---

## Components

### ChatService
**Location:** `backend-modmono/app/modules/chat/service.py`

The main orchestrator that coordinates all pipeline components.

```python
class ChatService:
    """
    Service for processing chat queries using RAG pipeline with intent routing.
    
    Flow:
    1. Classify query intent (SQL/Vector/Hybrid/Fallback)
    2. Route to appropriate handler
    3. Generate response with LLM
    4. Add conversation to memory
    5. Generate follow-up questions
    6. Generate chart visualizations
    """
```

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `process_query()` | Main entry point for query processing |
| `_handle_sql_intent()` | Processes Intent A (SQL only) queries |
| `_handle_vector_intent()` | Processes Intent B (vector search) queries |
| `_handle_hybrid_intent()` | Processes Intent C (hybrid) queries |
| `_synthesize_sql_response_with_chart()` | Formats SQL results with chart |

---

### SQLService
**Location:** `backend-modmono/app/modules/chat/sql_service.py`

Handles SQL generation and execution with few-shot learning.

```python
class SQLService:
    """
    Service for executing SQL queries against clinical data sources.
    
    Features:
    - Few-shot learning with similar SQL examples
    - Natural language to SQL conversion
    - Direct SQL execution
    - Result formatting for LLM consumption
    - Schema caching for performance
    """
```

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `query_async()` | Main NL2SQL entry point |
| `_get_few_shot_examples()` | Retrieves similar examples for few-shot |
| `_classify_query_type()` | Classifies query into category |
| `execute_query()` | Executes SQL and returns results |
| `get_schema_context()` | Gets database schema for prompt |

**DuckDB SQL Rules:**
```python
DUCKDB_SQL_RULES = """
1. Window functions CANNOT be used in WHERE clause - use CTE pattern
2. Aggregate functions CANNOT be used in WHERE clause - use HAVING
3. Date difference: DATEDIFF('day', start_date, end_date) with 3 arguments
4. Use DATE_TRUNC('month', date_col) for date truncation
5. Use INTERVAL '90 days' syntax for date arithmetic
6. For consecutive streak detection, use ROW_NUMBER difference technique
"""
```

---

### SQLExamplesStore
**Location:** `backend-modmono/app/modules/sql_examples/store.py`

Vector store for curated Q&A training pairs used in few-shot prompting.

```python
class SQLExamplesStore:
    """
    Vector store for curated SQL Q&A pairs.
    
    Features:
    - Supports Qdrant (production) and ChromaDB (development)
    - Automatic fallback if primary backend unavailable
    - Deterministic IDs using SHA256 for deduplication
    - Category and tag-based filtering
    """
```

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `add_example()` | Add a single Q&A training example |
| `add_examples_batch()` | Bulk add multiple examples |
| `get_similar_examples()` | Retrieve examples by similarity |
| `get_example_count()` | Get total stored examples |

**Example Flow:**
```
User: "Compare first and last blood pressure readings"
                    │
                    ▼
         ┌─────────────────────┐
         │ Embed Question      │
         │ (OpenAI Ada-002)    │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Vector Search       │
         │ (Qdrant/ChromaDB)   │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Return Top-3        │
         │ Similar Examples    │
         └─────────────────────┘
```

---

### QueryRelevanceChecker
**Location:** `backend-modmono/app/modules/chat/query/query_relevance_checker.py`

Pre-filters queries before SQL generation to reject irrelevant or unsafe queries.

```python
class QueryRelevanceChecker:
    """
    Pre-filters user queries to determine if they can be answered.
    
    Classifications:
    - RELEVANT: Can be answered with available data
    - IRRELEVANT:CONTEXT: Topic not covered by database
    - IRRELEVANT:PII: Requests personally identifiable information
    - IRRELEVANT:SYNTAX: Invalid or malformed query
    """
```

**Classification Flow:**
```
User Query
     │
     ▼
┌─────────────────┐
│ Local PII Check │──── Fast pattern matching for obvious PII
└────────┬────────┘
         │ Not obvious PII
         ▼
┌─────────────────┐
│ LLM Classify    │──── GPT-3.5-turbo for nuanced classification
└────────┬────────┘
         │
    ┌────┴────┬────────────┬────────────┐
    ▼         ▼            ▼            ▼
RELEVANT   PII         CONTEXT      SYNTAX
  │         │            │            │
  │         └────────────┴────────────┘
  │                      │
  ▼                      ▼
Continue              Reject with
Processing            Explanation
```

**PII Patterns Detected:**
- Name-based lookups: "Show me John Smith's records"
- Contact information requests: "What is patient's phone number"
- Export requests: "List all patient names"
- Individual identification: "Who is patient ID 12345"

---

### IntentClassifier
**Location:** `backend-modmono/app/modules/chat/intent_classifier.py`

Routes queries to SQL, Vector, or Hybrid processing based on query type.

```python
class IntentClassifier:
    """
    Classifies user queries into SQL, Vector, or Hybrid intents.
    
    Uses:
    1. Keyword heuristics (fast, no API call)
    2. LLM classification (accurate, for ambiguous cases)
    """
```

**Intent Keywords:**
```python
SQL_KEYWORDS = [
    'count', 'total', 'how many', 'average', 'sum',
    'rate', 'percentage', 'breakdown', 'distribution',
    'highest', 'lowest', 'top', 'bottom', 'trend'
]

VECTOR_KEYWORDS = [
    'notes', 'documents', 'clinical summaries',
    'find mentions', 'patient history', 'narrative'
]

HYBRID_KEYWORDS = [
    'patients over', 'patients under', 'patients aged',
    'male patients with', 'female patients with'
]
```

---

### DataDictionary
**Location:** `backend-modmono/app/modules/chat/query/data_dictionary.py`

Semantic enrichment layer mapping business terms to schema elements.

```python
class DataDictionary:
    """
    Semantic enrichment layer.
    
    Provides:
    - Business definitions (e.g., "active patient" → SQL condition)
    - Metric templates (e.g., "screening rate" → SQL expression)
    - Synonym resolution (user term → column/table name)
    - Default filters per table
    """
```

**Configuration File:** `backend-modmono/app/core/config/data_dictionary.yaml`

**Example Configuration:**
```yaml
business_definitions:
  active_patient:
    table: patient_tracker
    condition: "is_active = true AND is_deleted = false"
    description: "Patients currently enrolled in the program"
  
  elevated_bp:
    table: clinical_data_latest
    condition: "avg_systolic >= 140 OR avg_diastolic >= 90"
    description: "Blood pressure above normal range"

metric_templates:
  screening_rate:
    expression: "COUNT(DISTINCT CASE WHEN screened THEN patient_id END) * 100.0 / COUNT(DISTINCT patient_id)"
    description: "Percentage of patients who have been screened"

default_filters:
  patient_tracker:
    - "is_deleted = false"
  clinical_data:
    - "is_test_record = false"

synonyms:
  blood_pressure:
    - BP
    - systolic
    - diastolic
  diabetes:
    - DM
    - diabetic
    - blood sugar
```

---

### QueryAnalyticsService
**Location:** `backend-modmono/app/modules/observability/analytics_service.py`

Privacy-safe logging and analysis of query execution metrics.

```python
class QueryAnalyticsService:
    """
    Service for logging and analyzing query execution metrics.
    
    PRIVACY: Does NOT store actual query content.
    Only logs: categories, success/fail, timing, row counts
    """
```

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `log_query()` | Log query execution metrics |
| `get_summary()` | Get aggregate statistics |
| `get_error_analytics()` | Analyze error patterns |
| `get_improvement_suggestions()` | Generate improvement recommendations |

---

## Data Flow

### Few-Shot Example Retrieval

```
┌──────────────────────────────────────────────────────────────────┐
│                    Few-Shot Retrieval Flow                        │
└──────────────────────────────────────────────────────────────────┘

User Question: "Find patients with 3+ consecutive high BP readings"
                              │
                              ▼
                    ┌─────────────────┐
                    │ Classify Query  │
                    │ Type            │
                    │                 │
                    │ → "consecutive_ │
                    │    streak"      │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐          ┌─────────────────┐
    │ Category Search │          │ General Search  │
    │ (if < top_k)    │          │ (fallback)      │
    │                 │          │                 │
    │ Filter:         │          │ No filter       │
    │ category =      │          │                 │
    │ "consecutive_   │          │                 │
    │  streak"        │          │                 │
    └────────┬────────┘          └────────┬────────┘
             │                            │
             └──────────┬─────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │ Return Top-3    │
              │ Examples        │
              │                 │
              │ 1. Consecutive  │
              │    streak SQL   │
              │ 2. ROW_NUMBER   │
              │    pattern      │
              │ 3. CTE example  │
              └─────────────────┘
```

### Prompt Assembly

```
┌──────────────────────────────────────────────────────────────────┐
│                    Prompt Assembly Flow                           │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT                                                    │
│                                                                  │
│ You are a SQL expert...                                          │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ DUCKDB SQL RULES                                             │ │
│ │ 1. Window functions CANNOT be used in WHERE clause...       │ │
│ │ 2. Use DATEDIFF('day', start, end) with 3 arguments...      │ │
│ │ ...                                                          │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ DATA DICTIONARY CONTEXT                                      │ │
│ │ MANDATORY FILTERS:                                           │ │
│ │   - patient_tracker: is_deleted = false                     │ │
│ │ BUSINESS DEFINITIONS:                                        │ │
│ │   - elevated_bp: avg_systolic >= 140 OR avg_diastolic >= 90 │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ SIMILAR SQL EXAMPLES                                         │ │
│ │                                                              │ │
│ │ Example 1 (similarity: 0.92, category: consecutive_streak): │ │
│ │ Q: Find entities with 3+ consecutive high readings          │ │
│ │ SQL: WITH numbered AS (...)                                  │ │
│ │                                                              │ │
│ │ Example 2 (similarity: 0.85, category: window_functions):   │ │
│ │ Q: Get the latest record for each entity                    │ │
│ │ SQL: WITH ranked AS (...)                                    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ DATABASE SCHEMA                                              │ │
│ │ Tables:                                                      │ │
│ │ - clinical_data_latest: patient_id, avg_systolic, ...      │ │
│ │ - patient_tracker: id, gender, age, is_active, ...         │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ USER MESSAGE                                                     │
│                                                                  │
│ "Find patients with 3 or more consecutive high blood pressure   │
│  readings"                                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for LLM and embeddings | Required |
| `POSTGRES_HOST` | PostgreSQL host for app database | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | PostgreSQL database name | `data_insights` |
| `POSTGRES_USER` | PostgreSQL username | Required |
| `POSTGRES_PASSWORD` | PostgreSQL password | Required |
| `QDRANT_HOST` | Qdrant vector DB host | `localhost` |
| `QDRANT_PORT` | Qdrant port | `6333` |
| `VECTOR_STORE_TYPE` | Vector store backend (`qdrant` or `chroma`) | `qdrant` |
| `ENABLE_QUERY_RELEVANCE_CHECK` | Enable query pre-filtering | `true` |
| `DEBUG` | Enable debug mode | `false` |

### Configuration Files

| File | Purpose |
|------|---------|
| `app/core/config/data_dictionary.yaml` | Business term definitions, synonyms, default filters |
| `app/modules/sql_examples/training_examples.json` | Curated SQL training examples |
| `app/core/prompts.py` | System prompt templates |
| `alembic.ini` | Database migration configuration |

### System Prompts

Located in `backend-modmono/app/core/prompts.py`:

| Prompt | Purpose |
|--------|---------|
| `get_sql_generator_prompt()` | Main SQL generation system prompt |
| `get_intent_router_prompt()` | Intent classification prompt |
| `get_data_analyst_prompt()` | Response synthesis prompt |
| `get_chart_generator_prompt()` | Chart generation instructions |
| `get_rag_synthesis_prompt()` | RAG response synthesis |

---

## Accuracy Metrics

### Target Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| SQL Generation Accuracy | 90%+ | Generated SQL executes without error |
| Execution Success Rate | 95%+ | SQL returns valid results |
| Response Relevance | 85%+ | Answer correctly addresses question |
| Query Latency (P95) | < 5s | End-to-end response time |

### Measurement Methods

#### 1. Golden Dataset Evaluation

Maintain a golden dataset of question-SQL pairs:

```bash
# Run evaluation against golden dataset
python -m app.scripts.run_sql_tests \
  --input eval/datasets/golden_questions.csv \
  --output eval/reports/accuracy_report.md \
  --save-results eval/reports/results.json
```

#### 2. Automated Test Runner

```python
# Example test case
{
    "question": "How many patients have elevated blood pressure?",
    "expected_sql_pattern": "SELECT COUNT.*WHERE.*systolic.*>=.*140",
    "expected_columns": ["count"],
    "category": "aggregation"
}
```

#### 3. Analytics Dashboard

Monitor via analytics endpoints:

```bash
# Get accuracy summary
curl http://localhost:8000/api/v1/analytics/summary?days=7

# Get error patterns
curl http://localhost:8000/api/v1/analytics/errors

# Get improvement suggestions
curl http://localhost:8000/api/v1/analytics/improvement-suggestions
```

### Continuous Improvement Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                  Accuracy Improvement Loop                       │
└─────────────────────────────────────────────────────────────────┘

     ┌─────────────┐
     │ Run Tests   │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │ Analyze     │──── Identify failure patterns
     │ Failures    │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │ Add Training│──── Create new examples for failed patterns
     │ Examples    │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │ Re-Run      │──── Verify improvement
     │ Tests       │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │ Monitor     │──── Track production metrics
     │ Production  │
     └─────────────┘
            │
            └───────────────────┐
                                │
                                ▼
                        (Repeat cycle)
```

---

## Deployment Architecture

### Production Setup

```
┌─────────────────────────────────────────────────────────────────┐
│                    Production Architecture                       │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │ Load Balancer   │
                    │ (Nginx/Caddy)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ API Pod 1 │  │ API Pod 2 │  │ API Pod N │
       │ (FastAPI) │  │ (FastAPI) │  │ (FastAPI) │
       └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
  │ PostgreSQL  │    │ Qdrant      │    │ Redis       │
  │ (Primary)   │    │ (Vector DB) │    │ (Cache)     │
  │             │    │             │    │             │
  │ • Users     │    │ • SQL       │    │ • Sessions  │
  │ • Configs   │    │   Examples  │    │ • Query     │
  │ • Analytics │    │ • Doc       │    │   Cache     │
  │             │    │   Embeddings│    │             │
  └─────────────┘    └─────────────┘    └─────────────┘
```

### Docker Compose (Development)

```yaml
services:
  backend:
    build: ./backend-modmono
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_HOST=postgres
      - QDRANT_HOST=qdrant
    depends_on:
      - postgres
      - qdrant

  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant
    volumes:
      - qdrant_data:/qdrant/storage

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
```

---

## Extending the System

### Adding New Training Examples

1. Create examples following the [SQL Training Guidelines](../sql_training_guidelines.md)
2. Upload via API:

```bash
curl -X POST http://localhost:8000/api/v1/training/examples \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Find consecutive high readings",
    "sql": "WITH numbered AS (...) SELECT ...",
    "category": "consecutive_streak",
    "tags": ["window_function", "cte"]
  }'
```

### Adding New Query Categories

1. Add keywords to `IntentClassifier.QUERY_TYPE_KEYWORDS`
2. Add category to `ALLOWED_CATEGORIES` in training routes
3. Create training examples for the new category

### Adding New Data Sources

1. Create a DataSource via API
2. System automatically discovers schema
3. Configure data dictionary for business terms

### Customizing System Prompts

1. Edit prompts in `app/core/prompts.py`
2. Or configure per-agent prompts via Agent Config

---

## Appendix: Component Locations

| Component | Location |
|-----------|----------|
| ChatService | `app/modules/chat/service.py` |
| SQLService | `app/modules/chat/sql_service.py` |
| SQLExamplesStore | `app/modules/sql_examples/store.py` |
| IntentClassifier | `app/modules/chat/intent_classifier.py` |
| QueryRelevanceChecker | `app/modules/chat/query/query_relevance_checker.py` |
| DataDictionary | `app/modules/chat/query/data_dictionary.py` |
| PromptBuilder | `app/modules/chat/query/prompt_builder.py` |
| SchemaLinker | `app/modules/chat/query/schema_linker.py` |
| QueryPlanner | `app/modules/chat/query/query_planner.py` |
| QueryAnalyticsService | `app/modules/observability/analytics_service.py` |
| Training Routes | `app/modules/sql_examples/routes.py` |
| Analytics Routes | `app/modules/observability/analytics_routes.py` |

---

*Document maintained by the Data Insights Team. For questions or updates, contact the architecture team.*
