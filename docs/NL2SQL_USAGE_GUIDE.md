# NL2SQL Accuracy Improvement System - Usage Guide

> **Version:** 1.0  
> **Last Updated:** April 2026  
> **Purpose:** Step-by-step guide for using all components of the NL2SQL accuracy improvement system

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Initial Setup](#initial-setup)
3. [Training Examples Management](#training-examples-management)
4. [Running Accuracy Tests](#running-accuracy-tests)
5. [Analyzing Test Results](#analyzing-test-results)
6. [Using the Analytics Dashboard](#using-the-analytics-dashboard)
7. [API Reference](#api-reference)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Navigate to backend
cd backend-modmono

# 2. Activate conda environment
conda activate fhir_rag_env

# 3. Apply database migrations
python -m alembic upgrade head

# 4. Load initial training examples
python -m app.scripts.train_sql_examples

# 5. Start the server
uvicorn app.app:app --reload --port 8000

# 6. View API docs
open http://localhost:8000/api/docs
```

---

## Initial Setup

### Prerequisites

- Python 3.10+
- Conda environment `fhir_rag_env`
- PostgreSQL database running
- Qdrant or ChromaDB for vector storage
- OpenAI API key configured

### Environment Variables

Create or update `.env` file in `backend-modmono/`:

```bash
# Required
OPENAI_API_KEY=sk-your-key-here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=data_insights
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# Vector Store (choose one)
VECTOR_STORE_TYPE=qdrant  # or 'chroma'
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Optional
ENABLE_QUERY_RELEVANCE_CHECK=true
DEBUG=false
```

### Database Setup

```bash
# Apply all migrations including the new analytics table
cd backend-modmono
python -m alembic upgrade head
```

### Verify Installation

```bash
# Run the test scripts to verify everything works
python -m app.scripts.test_training_api
python -m app.scripts.test_analytics_api
```

---

## Training Examples Management

### Understanding Training Examples

Training examples are question-SQL pairs used for few-shot learning. When a user asks a question, similar examples are retrieved and included in the LLM prompt to improve SQL generation accuracy.

**Example Structure:**
```json
{
  "question": "Find patients with 3+ consecutive high BP readings",
  "sql": "WITH numbered AS (...) SELECT ...",
  "category": "consecutive_streak",
  "tags": ["window_function", "cte", "consecutive"],
  "description": "Detect consecutive high readings using ROW_NUMBER"
}
```

### Loading Initial Examples

```bash
# Load all examples from training_examples.json
python -m app.scripts.train_sql_examples

# Load from a custom file
python -m app.scripts.train_sql_examples --input my_examples.json

# Force reload (clear existing and reload)
python -m app.scripts.train_sql_examples --force
```

### Adding Examples via API

#### Add Single Example

```bash
curl -X POST http://localhost:8000/api/v1/training/examples \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the average age by gender?",
    "sql": "SELECT gender, AVG(age) as avg_age FROM patients GROUP BY gender",
    "category": "aggregation",
    "tags": ["average", "group_by", "gender"],
    "description": "Calculate average age grouped by gender"
  }'
```

#### Bulk Upload Examples

```bash
# Upload from JSON file
curl -X POST http://localhost:8000/api/v1/training/bulk \
  -H "Authorization: Bearer <your_token>" \
  -F "file=@new_examples.json"
```

### Searching Examples

```bash
# Search by question similarity
curl "http://localhost:8000/api/v1/training/examples/search?question=average%20blood%20pressure&top_k=5" \
  -H "Authorization: Bearer <your_token>"

# Search with category filter
curl "http://localhost:8000/api/v1/training/examples/search?question=compare%20readings&category=temporal_comparison&top_k=3" \
  -H "Authorization: Bearer <your_token>"
```

### Listing and Managing Examples

```bash
# List all examples
curl "http://localhost:8000/api/v1/training/examples?skip=0&limit=50" \
  -H "Authorization: Bearer <your_token>"

# Get example by ID
curl "http://localhost:8000/api/v1/training/examples/{example_id}" \
  -H "Authorization: Bearer <your_token>"

# Delete example
curl -X DELETE "http://localhost:8000/api/v1/training/examples/{example_id}" \
  -H "Authorization: Bearer <your_token>"

# Get statistics
curl "http://localhost:8000/api/v1/training/stats" \
  -H "Authorization: Bearer <your_token>"
```

### Categories Reference

| Category | Description | Example Questions |
|----------|-------------|-------------------|
| `aggregation` | COUNT, SUM, AVG, GROUP BY | "How many patients?", "Average age by gender" |
| `temporal_comparison` | First vs last, period comparisons | "Compare initial and latest readings" |
| `consecutive_streak` | Consecutive occurrences | "Find 3+ consecutive high readings" |
| `rolling_calculation` | Moving averages, running totals | "7-day moving average" |
| `statistical_analysis` | Z-scores, percentiles, outliers | "Find outliers in blood pressure" |
| `deduplication` | Latest/first record per entity | "Get most recent reading per patient" |
| `window_functions` | RANK, LAG, LEAD patterns | "Rank patients by value" |
| `date_functions` | Date manipulation | "Count records by month" |

---

## Running Accuracy Tests

### Creating Test Cases

Create a CSV file with test cases:

```csv
question,expected_columns,category,tags,notes
"How many patients have high blood pressure?",count,aggregation,blood_pressure,Basic count query
"Show average systolic by age group",age_group;avg_systolic,aggregation,blood_pressure;age,Grouped aggregation
"Find patients with 3+ consecutive high readings",patient_id;streak_length,consecutive_streak,window_function,Complex pattern
```

Or use JSON format:

```json
{
  "test_cases": [
    {
      "question": "How many patients have high blood pressure?",
      "expected_columns": ["count"],
      "category": "aggregation",
      "notes": "Basic count query"
    }
  ]
}
```

### Running Tests

```bash
# Run with default settings
python -m app.scripts.run_sql_tests \
  --input app/scripts/sample_sql_tests.csv

# Run with custom output
python -m app.scripts.run_sql_tests \
  --input my_tests.csv \
  --output reports/accuracy_report.md \
  --save-results reports/results.json

# Run with specific agent/data source
python -m app.scripts.run_sql_tests \
  --input my_tests.csv \
  --agent-id "your-agent-uuid" \
  --data-source-id "your-datasource-uuid"

# Limit number of tests (for quick checks)
python -m app.scripts.run_sql_tests \
  --input my_tests.csv \
  --limit 10
```

### Understanding Test Output

The test runner generates:

1. **Markdown Report** (`accuracy_report.md`):
   - Overall statistics (pass rate, execution time)
   - Breakdown by category
   - Failed test details with error analysis
   - Improvement suggestions

2. **JSON Results** (`results.json`):
   - Detailed results for each test
   - Generated SQL
   - Execution metrics
   - Error information

**Sample Report Output:**
```markdown
# SQL Accuracy Test Report

## Summary
- Total Tests: 50
- Passed: 42 (84.0%)
- Failed: 8 (16.0%)
- Average Execution Time: 1.2s

## By Category
| Category | Passed | Failed | Pass Rate |
|----------|--------|--------|-----------|
| aggregation | 15 | 1 | 93.8% |
| temporal_comparison | 8 | 3 | 72.7% |
| consecutive_streak | 5 | 2 | 71.4% |

## Failed Tests
### Test: Find consecutive high readings
- **Error Type:** window_in_where
- **Error:** Window functions not allowed in WHERE clause
- **Suggested Fix:** Add CTE pattern training examples
```

---

## Analyzing Test Results

### Running the Analyzer

```bash
# Analyze recent test results
python -m app.scripts.analyze_test_results \
  --input reports/results.json \
  --output reports/analysis.md

# Analyze with custom error patterns
python -m app.scripts.analyze_test_results \
  --input reports/results.json \
  --patterns custom_patterns.json
```

### Understanding the Analysis

The analyzer provides:

1. **Error Pattern Analysis**
   - Groups failures by error type
   - Identifies root causes
   - Suggests specific fixes

2. **Category Performance**
   - Success rates by query category
   - Identifies weak areas

3. **Training Recommendations**
   - Specific examples to add
   - Priority ranking
   - Expected impact

**Sample Analysis Output:**
```markdown
# Test Results Analysis

## Error Patterns

### window_in_where (5 occurrences, 62.5% of failures)
**Root Cause:** LLM generating window functions directly in WHERE clause
**Fix:** Add more CTE pattern examples for window functions

**Suggested Training Example:**
{
  "question": "Get first record for each entity",
  "sql": "WITH ranked AS (SELECT *, ROW_NUMBER() OVER (...) AS rn FROM t) SELECT * FROM ranked WHERE rn = 1",
  "category": "deduplication"
}

### datediff_syntax (2 occurrences, 25.0% of failures)  
**Root Cause:** Using 2-argument DATEDIFF instead of 3-argument
**Fix:** Add DuckDB DATEDIFF examples with correct syntax
```

### Generating Training Examples from Failures

The analyzer can auto-generate training examples:

```bash
# Generate suggested training examples
python -m app.scripts.analyze_test_results \
  --input reports/results.json \
  --output reports/analysis.md \
  --generate-examples reports/suggested_training.json
```

Then review and upload:

```bash
# Review the suggested examples
cat reports/suggested_training.json

# Upload after review
curl -X POST http://localhost:8000/api/v1/training/bulk \
  -H "Authorization: Bearer <token>" \
  -F "file=@reports/suggested_training.json"
```

---

## Using the Analytics Dashboard

### Accessing Analytics

Analytics endpoints provide insights into query execution patterns without exposing actual query content (privacy-safe).

### Get Summary Statistics

```bash
# Get 7-day summary
curl "http://localhost:8000/api/v1/analytics/summary?days=7" \
  -H "Authorization: Bearer <your_token>"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "period_days": 7,
    "total_queries": 150,
    "success_rate": 0.85,
    "sql_generation_rate": 0.95,
    "sql_execution_rate": 0.89,
    "avg_execution_time_ms": 245,
    "by_category": {
      "aggregation": {"count": 50, "success_rate": 0.92},
      "temporal_comparison": {"count": 30, "success_rate": 0.73}
    },
    "by_error_type": {
      "window_in_where": 8,
      "column_not_found": 3
    }
  }
}
```

### Get Error Analytics

```bash
# Get top error patterns
curl "http://localhost:8000/api/v1/analytics/errors?days=7&limit=10" \
  -H "Authorization: Bearer <your_token>"
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "error_type": "window_in_where",
      "error_category": "syntax",
      "count": 8,
      "percentage": 0.35,
      "suggested_fix": "Add CTE pattern training examples for window functions"
    }
  ]
}
```

### Get Improvement Suggestions

```bash
# Get AI-generated improvement suggestions
curl "http://localhost:8000/api/v1/analytics/improvement-suggestions?days=7" \
  -H "Authorization: Bearer <your_token>"
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "priority": "high",
      "area": "error_pattern",
      "error_type": "window_in_where",
      "issue": "window_in_where errors: 8 occurrences (35%)",
      "suggestion": "Add CTE pattern training examples for window functions",
      "impact": "high"
    },
    {
      "priority": "medium",
      "area": "category_performance",
      "category": "temporal_comparison",
      "issue": "Category 'temporal_comparison' has 73% success rate",
      "suggestion": "Add more training examples for temporal comparison patterns",
      "impact": "medium"
    }
  ]
}
```

### Get Daily Trend

```bash
# Get 30-day trend
curl "http://localhost:8000/api/v1/analytics/trend?days=30" \
  -H "Authorization: Bearer <your_token>"
```

### Log Query Metrics (for testing)

```bash
# Manually log query metrics
curl -X POST "http://localhost:8000/api/v1/analytics/log" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query_category": "temporal_comparison",
    "query_complexity": "complex",
    "sql_generated": true,
    "sql_executed": true,
    "execution_success": false,
    "error_type": "window_in_where",
    "generation_time_ms": 150,
    "execution_time_ms": 0
  }'
```

---

## API Reference

### Training Examples API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/training/examples` | List all examples |
| `POST` | `/api/v1/training/examples` | Add single example |
| `GET` | `/api/v1/training/examples/{id}` | Get example by ID |
| `DELETE` | `/api/v1/training/examples/{id}` | Delete example |
| `GET` | `/api/v1/training/examples/search` | Search similar examples |
| `POST` | `/api/v1/training/bulk` | Bulk upload examples |
| `GET` | `/api/v1/training/stats` | Get statistics |
| `GET` | `/api/v1/training/categories` | List categories |

### Analytics API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/analytics/summary` | Get summary statistics |
| `GET` | `/api/v1/analytics/errors` | Get error analytics |
| `GET` | `/api/v1/analytics/improvement-suggestions` | Get improvement suggestions |
| `GET` | `/api/v1/analytics/trend` | Get daily trend |
| `POST` | `/api/v1/analytics/log` | Log query metrics |
| `GET` | `/api/v1/analytics/health` | Health check |

### Authentication

All API endpoints require authentication. Include the Bearer token:

```bash
-H "Authorization: Bearer <your_token>"
```

---

## Troubleshooting

### Common Issues

#### 1. "Vector store not initialized"

**Cause:** Qdrant/ChromaDB not running or not configured.

**Fix:**
```bash
# For Qdrant
docker run -p 6333:6333 qdrant/qdrant

# Or use ChromaDB (fallback)
export VECTOR_STORE_TYPE=chroma
```

#### 2. "No training examples found"

**Cause:** Examples not loaded into vector store.

**Fix:**
```bash
python -m app.scripts.train_sql_examples --force
```

#### 3. "Migration error"

**Cause:** Database migrations not applied.

**Fix:**
```bash
python -m alembic upgrade head
```

#### 4. "Module not found: pydantic_settings"

**Cause:** Using wrong Python environment.

**Fix:**
```bash
# Use conda environment
conda activate fhir_rag_env

# Or use python -m for alembic
python -m alembic upgrade head
```

#### 5. "Query relevance check failing"

**Cause:** OpenAI API key not configured.

**Fix:**
```bash
export OPENAI_API_KEY=sk-your-key-here
```

### Debugging Tips

#### Enable Debug Logging

```bash
export DEBUG=true
uvicorn app.app:app --reload --port 8000 --log-level debug
```

#### Check Vector Store Status

```python
from app.modules.sql_examples.store import get_sql_examples_store

store = get_sql_examples_store()
count = await store.get_example_count()
print(f"Examples in store: {count}")
```

#### Test Few-Shot Retrieval

```python
from app.modules.sql_examples.store import get_sql_examples_store

store = get_sql_examples_store()
examples = await store.get_similar_examples(
    question="How many patients have high blood pressure?",
    top_k=3
)
for ex in examples:
    print(f"Score: {ex['score']:.2f} - {ex['question']}")
```

### Getting Help

1. Check the [Architecture Documentation](architecture/nl2sql_pipeline.md)
2. Review the [Training Guidelines](sql_training_guidelines.md)
3. Check logs in `backend-modmono/logs/`
4. Open an issue in the repository

---

## Appendix: Complete Workflow Example

### End-to-End Accuracy Improvement Workflow

```bash
# Step 1: Set up environment
cd backend-modmono
conda activate fhir_rag_env
python -m alembic upgrade head

# Step 2: Load initial training examples
python -m app.scripts.train_sql_examples

# Step 3: Start server
uvicorn app.app:app --reload --port 8000 &

# Step 4: Run baseline tests
python -m app.scripts.run_sql_tests \
  --input app/scripts/sample_sql_tests.csv \
  --output reports/baseline_report.md \
  --save-results reports/baseline_results.json

# Step 5: Analyze failures
python -m app.scripts.analyze_test_results \
  --input reports/baseline_results.json \
  --output reports/analysis.md \
  --generate-examples reports/suggested_training.json

# Step 6: Review and add new examples
cat reports/suggested_training.json
# Edit if needed, then upload
curl -X POST http://localhost:8000/api/v1/training/bulk \
  -H "Authorization: Bearer <token>" \
  -F "file=@reports/suggested_training.json"

# Step 7: Re-run tests to measure improvement
python -m app.scripts.run_sql_tests \
  --input app/scripts/sample_sql_tests.csv \
  --output reports/improved_report.md \
  --save-results reports/improved_results.json

# Step 8: Compare results
echo "Baseline accuracy:"
grep "Pass Rate" reports/baseline_report.md
echo "Improved accuracy:"
grep "Pass Rate" reports/improved_report.md

# Step 9: Monitor production metrics
curl "http://localhost:8000/api/v1/analytics/summary?days=7" \
  -H "Authorization: Bearer <token>" | jq '.data.success_rate'

# Step 10: Get ongoing improvement suggestions
curl "http://localhost:8000/api/v1/analytics/improvement-suggestions" \
  -H "Authorization: Bearer <token>" | jq '.data[:3]'
```

### Continuous Improvement Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│                 Continuous Improvement Cycle                     │
└─────────────────────────────────────────────────────────────────┘

         ┌─────────────┐
         │ 1. Test     │ ◄──────────────────────────┐
         │ Current     │                            │
         │ Accuracy    │                            │
         └──────┬──────┘                            │
                │                                   │
                ▼                                   │
         ┌─────────────┐                            │
         │ 2. Analyze  │                            │
         │ Failures    │                            │
         └──────┬──────┘                            │
                │                                   │
                ▼                                   │
         ┌─────────────┐                            │
         │ 3. Generate │                            │
         │ Training    │                            │
         │ Examples    │                            │
         └──────┬──────┘                            │
                │                                   │
                ▼                                   │
         ┌─────────────┐                            │
         │ 4. Review   │                            │
         │ & Upload    │                            │
         └──────┬──────┘                            │
                │                                   │
                ▼                                   │
         ┌─────────────┐                            │
         │ 5. Verify   │────────────────────────────┘
         │ Improvement │
         └─────────────┘
```

---

*For more details, see the [Architecture Documentation](architecture/nl2sql_pipeline.md) and [Training Guidelines](sql_training_guidelines.md).*
