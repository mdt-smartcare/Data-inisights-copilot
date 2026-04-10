# SQL Training Examples Guidelines

> **Version:** 1.0  
> **Last Updated:** April 2026  
> **Maintainers:** Data Insights Team

This document provides comprehensive guidelines for creating, maintaining, and contributing SQL training examples used in the NL2SQL few-shot learning system.

---

## Table of Contents

1. [Overview](#overview)
2. [Training Example Format](#training-example-format)
3. [Quality Standards](#quality-standards)
4. [Category Definitions](#category-definitions)
5. [Common Patterns Reference](#common-patterns-reference)
6. [Privacy Requirements](#privacy-requirements)
7. [Testing Your Examples](#testing-your-examples)
8. [Contribution Process](#contribution-process)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The NL2SQL system uses few-shot learning to improve SQL generation accuracy. Training examples are question-SQL pairs that are retrieved based on semantic similarity and injected into the LLM prompt to guide SQL generation.

**Key Principles:**
- Examples should be **domain-agnostic** (no specific business data)
- Examples must be **privacy-safe** (no PII or real values)
- SQL must be **syntactically valid** for DuckDB/PostgreSQL
- Questions should be **natural language** (not SQL-like)

---

## Training Example Format

### JSON Structure

Each training example must follow this structure:

```json
{
  "question": "Show the first record for each customer",
  "sql": "WITH ranked AS (\n  SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at) AS rn\n  FROM records\n)\nSELECT * FROM ranked WHERE rn = 1",
  "category": "deduplication",
  "tags": ["window_function", "cte", "first_value"],
  "description": "Get first record per entity using ROW_NUMBER in CTE pattern"
}
```

### Required Fields

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `question` | string | Natural language question | 10-500 characters, no SQL keywords as primary words |
| `sql` | string | Corresponding SQL query | Valid DuckDB/PostgreSQL syntax, SELECT only |
| `category` | string | Primary category | Must be from allowed categories list |
| `tags` | array | Additional tags | 1-10 tags, lowercase, underscore-separated |
| `description` | string | Brief explanation | 10-200 characters, explains the pattern |

### Category Naming Conventions

- Use `snake_case` for all categories
- Categories should be broad enough to group similar patterns
- Each example should have exactly ONE primary category

### Tag Taxonomy

Tags provide fine-grained classification. Use these conventions:

**SQL Feature Tags:**
- `window_function`, `cte`, `subquery`, `join`, `union`
- `group_by`, `having`, `order_by`, `limit`
- `case_when`, `coalesce`, `nullif`

**Operation Tags:**
- `count`, `sum`, `average`, `min`, `max`
- `filter`, `sort`, `deduplicate`, `aggregate`

**Pattern Tags:**
- `first_value`, `last_value`, `consecutive`, `streak`
- `comparison`, `trend`, `percentage`, `ranking`

**Domain Tags (Generic):**
- `temporal`, `date_filter`, `interval`
- `numeric`, `text`, `boolean`

---

## Quality Standards

### SQL Syntax Requirements

#### Must Follow:
```sql
-- GOOD: Use CTEs for window functions in filters
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY date) AS rn
  FROM records
)
SELECT * FROM ranked WHERE rn = 1;

-- GOOD: Use 3-argument DATEDIFF for DuckDB
SELECT DATEDIFF('day', start_date, end_date) AS days_between FROM events;

-- GOOD: Use INTERVAL syntax for date arithmetic
SELECT * FROM records WHERE created_at >= CURRENT_DATE - INTERVAL '90 days';

-- GOOD: Use DATE_TRUNC for date grouping
SELECT DATE_TRUNC('month', created_at) AS month, COUNT(*) FROM records GROUP BY 1;
```

#### Must Avoid:
```sql
-- BAD: Window function in WHERE clause
SELECT * FROM records WHERE ROW_NUMBER() OVER (ORDER BY date) = 1;

-- BAD: Aggregate in WHERE clause
SELECT * FROM records WHERE COUNT(*) > 5;

-- BAD: 2-argument DATEDIFF (wrong for DuckDB)
SELECT DATEDIFF(start_date, end_date) FROM events;

-- BAD: DATE_SUB function (not supported in DuckDB)
SELECT * FROM records WHERE created_at > DATE_SUB(CURRENT_DATE, 90);

-- BAD: MONTH() function (use DATE_TRUNC or EXTRACT instead)
SELECT MONTH(created_at) FROM records;
```

### Natural Language Question Requirements

#### Good Questions:
```
"Show the first reading for each patient"
"Find customers with more than 5 orders"
"What is the average value by category?"
"Compare this month to last month"
"Find consecutive days with high values"
```

#### Bad Questions (Too SQL-like):
```
"SELECT COUNT WHERE status = active"
"Group by category and sum values"
"JOIN customers with orders"
"Use ROW_NUMBER to get first record"
```

### Domain-Agnostic Requirements

Examples should use **generic entity names** that can apply to any domain:

| Instead of... | Use... |
|---------------|--------|
| `patient_id` | `entity_id`, `record_id`, `id` |
| `diagnosis_code` | `category`, `type`, `classification` |
| `hospital_name` | `location`, `site`, `source` |
| `blood_pressure` | `measurement`, `value`, `reading` |

---

## Category Definitions

### `aggregation`
**Description:** Basic aggregation queries with GROUP BY, counts, sums, averages.

**When to use:**
- Simple COUNT, SUM, AVG, MIN, MAX operations
- GROUP BY queries without complex window functions
- Basic filtering with aggregates (HAVING)

**Example:**
```json
{
  "question": "What is the total count by category?",
  "sql": "SELECT category, COUNT(*) AS total FROM records GROUP BY category ORDER BY total DESC",
  "category": "aggregation",
  "tags": ["count", "group_by"]
}
```

### `temporal_comparison`
**Description:** Queries comparing values across different time periods.

**When to use:**
- Comparing first vs. last values
- Period-over-period comparisons (this month vs. last month)
- Before/after analysis

**Example:**
```json
{
  "question": "Compare initial and latest values for each entity",
  "sql": "WITH ranked AS (\n  SELECT entity_id, value, created_at,\n    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at ASC) AS first_rn,\n    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC) AS last_rn\n  FROM measurements\n)\nSELECT \n  f.entity_id,\n  f.value AS initial_value,\n  l.value AS latest_value,\n  l.value - f.value AS change\nFROM ranked f\nJOIN ranked l ON f.entity_id = l.entity_id\nWHERE f.first_rn = 1 AND l.last_rn = 1",
  "category": "temporal_comparison",
  "tags": ["comparison", "window_function", "cte", "first_value", "last_value"]
}
```

### `consecutive_streak`
**Description:** Detecting consecutive occurrences or streaks in data.

**When to use:**
- Finding consecutive days/records meeting a condition
- Streak detection and counting
- Gap analysis in sequences

**Example:**
```json
{
  "question": "Find entities with 3 or more consecutive high readings",
  "sql": "WITH numbered AS (\n  SELECT entity_id, value, recorded_at,\n    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY recorded_at) AS rn\n  FROM readings WHERE value > 100\n),\ngrouped AS (\n  SELECT *, rn - ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY recorded_at) AS grp\n  FROM numbered\n)\nSELECT entity_id, COUNT(*) AS streak_length, MIN(recorded_at) AS streak_start\nFROM grouped\nGROUP BY entity_id, grp\nHAVING COUNT(*) >= 3",
  "category": "consecutive_streak",
  "tags": ["consecutive", "streak", "window_function", "cte"]
}
```

### `rolling_calculation`
**Description:** Rolling/moving aggregations over time windows.

**When to use:**
- Moving averages (7-day, 30-day, etc.)
- Running totals
- Trailing period calculations

**Example:**
```json
{
  "question": "Calculate the 7-day moving average of daily values",
  "sql": "SELECT date, value,\n  AVG(value) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS moving_avg_7d\nFROM daily_metrics\nORDER BY date",
  "category": "rolling_calculation",
  "tags": ["moving_average", "window_function", "rolling"]
}
```

### `statistical_analysis`
**Description:** Statistical calculations like percentiles, z-scores, outlier detection.

**When to use:**
- Z-score calculations
- Percentile/quartile analysis
- Outlier detection
- Variance/standard deviation

**Example:**
```json
{
  "question": "Find outliers more than 2 standard deviations from the mean",
  "sql": "WITH stats AS (\n  SELECT AVG(value) AS mean_val, STDDEV(value) AS std_val\n  FROM measurements\n)\nSELECT m.*, (m.value - s.mean_val) / NULLIF(s.std_val, 0) AS z_score\nFROM measurements m, stats s\nWHERE ABS((m.value - s.mean_val) / NULLIF(s.std_val, 0)) > 2",
  "category": "statistical_analysis",
  "tags": ["z_score", "outlier", "statistics", "stddev"]
}
```

### `deduplication`
**Description:** Getting unique or latest records per entity.

**When to use:**
- Latest record per entity
- First record per entity
- Distinct with additional columns

**Example:**
```json
{
  "question": "Get the most recent record for each entity",
  "sql": "WITH latest AS (\n  SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC) AS rn\n  FROM records\n)\nSELECT * FROM latest WHERE rn = 1",
  "category": "deduplication",
  "tags": ["latest", "deduplicate", "window_function", "cte"]
}
```

### `episode_detection`
**Description:** Identifying episodes, sessions, or activity periods with gaps.

**When to use:**
- Session identification based on inactivity gaps
- Episode boundaries
- Activity period detection

**Example:**
```json
{
  "question": "Identify activity sessions with more than 30 minutes between events",
  "sql": "WITH with_gaps AS (\n  SELECT *,\n    CASE WHEN DATEDIFF('minute', LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time), event_time) > 30\n         THEN 1 ELSE 0 END AS new_session\n  FROM events\n),\nwith_session_id AS (\n  SELECT *, SUM(new_session) OVER (PARTITION BY user_id ORDER BY event_time) AS session_id\n  FROM with_gaps\n)\nSELECT user_id, session_id, MIN(event_time) AS session_start, MAX(event_time) AS session_end, COUNT(*) AS event_count\nFROM with_session_id\nGROUP BY user_id, session_id",
  "category": "episode_detection",
  "tags": ["session", "gap_analysis", "window_function", "cte"]
}
```

### `comparison`
**Description:** Direct comparisons between groups, categories, or benchmarks.

**When to use:**
- Comparing category A vs. category B
- Above/below average comparisons
- Benchmark comparisons

**Example:**
```json
{
  "question": "Find entities with values above the overall average",
  "sql": "SELECT entity_id, value\nFROM measurements\nWHERE value > (SELECT AVG(value) FROM measurements)",
  "category": "comparison",
  "tags": ["subquery", "average", "filter"]
}
```

### `window_functions`
**Description:** General window function patterns not covered by other categories.

**When to use:**
- RANK, DENSE_RANK patterns
- LAG/LEAD for previous/next value access
- NTILE for bucketing

**Example:**
```json
{
  "question": "Rank entities by value within each category",
  "sql": "SELECT entity_id, category, value,\n  RANK() OVER (PARTITION BY category ORDER BY value DESC) AS rank_in_category\nFROM measurements",
  "category": "window_functions",
  "tags": ["rank", "partition", "window_function"]
}
```

### `date_functions`
**Description:** Date manipulation, extraction, and formatting.

**When to use:**
- Date extraction (year, month, day)
- Date arithmetic
- Date formatting and truncation

**Example:**
```json
{
  "question": "Count records by month",
  "sql": "SELECT DATE_TRUNC('month', created_at) AS month, COUNT(*) AS record_count\nFROM records\nGROUP BY DATE_TRUNC('month', created_at)\nORDER BY month",
  "category": "date_functions",
  "tags": ["date_trunc", "group_by", "temporal"]
}
```

---

## Common Patterns Reference

### 1. Window Function in CTE Pattern

**When to use:** When you need to filter based on window function results (ROW_NUMBER, RANK, etc.)

**Correct Pattern:**
```sql
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC) AS rn
  FROM records
)
SELECT * FROM ranked WHERE rn = 1;
```

**Common Mistake:**
```sql
-- WRONG: Window function directly in WHERE
SELECT * FROM records
WHERE ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC) = 1;
```

---

### 2. First/Last Value Comparison

**When to use:** Comparing the first and last records for each entity.

**Correct Pattern:**
```sql
WITH ranked AS (
  SELECT entity_id, value, created_at,
    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at ASC) AS first_rn,
    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC) AS last_rn
  FROM measurements
)
SELECT 
  f.entity_id,
  f.value AS first_value,
  l.value AS last_value,
  l.value - f.value AS change
FROM ranked f
JOIN ranked l ON f.entity_id = l.entity_id
WHERE f.first_rn = 1 AND l.last_rn = 1;
```

**Common Mistake:**
```sql
-- WRONG: Using FIRST_VALUE/LAST_VALUE in WHERE clause
SELECT * FROM measurements
WHERE value = FIRST_VALUE(value) OVER (PARTITION BY entity_id ORDER BY created_at);
```

---

### 3. Consecutive Streak Detection

**When to use:** Finding consecutive occurrences meeting a condition.

**Correct Pattern (Row Number Difference Technique):**
```sql
WITH filtered AS (
  -- Step 1: Filter to only rows meeting condition
  SELECT entity_id, value, recorded_at,
    ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY recorded_at) AS rn
  FROM readings
  WHERE value > 100  -- the condition
),
grouped AS (
  -- Step 2: Create groups using ROW_NUMBER difference
  SELECT *,
    rn - ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY recorded_at) AS grp
  FROM filtered
)
-- Step 3: Aggregate by groups
SELECT 
  entity_id, 
  COUNT(*) AS streak_length,
  MIN(recorded_at) AS streak_start,
  MAX(recorded_at) AS streak_end
FROM grouped
GROUP BY entity_id, grp
HAVING COUNT(*) >= 3  -- minimum streak length
ORDER BY streak_length DESC;
```

**Why it works:** When you have consecutive dates that all meet a condition, subtracting two row numbers (one from all rows, one from filtered rows) gives the same value for consecutive rows.

---

### 4. Date Difference Calculations

**When to use:** Calculating time between two dates.

**Correct Pattern (DuckDB):**
```sql
-- For days between dates
SELECT DATEDIFF('day', start_date, end_date) AS days_between FROM events;

-- For hours
SELECT DATEDIFF('hour', start_time, end_time) AS hours_between FROM events;

-- Alternative using subtraction (returns INTERVAL)
SELECT end_date - start_date AS date_diff FROM events;
```

**Common Mistakes:**
```sql
-- WRONG: 2-argument DATEDIFF
SELECT DATEDIFF(start_date, end_date) FROM events;

-- WRONG: Using DATE_SUB (not supported)
SELECT DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY) FROM events;
```

---

### 5. Rolling Aggregations

**When to use:** Moving averages, running totals, trailing sums.

**Correct Pattern:**
```sql
-- 7-day moving average
SELECT 
  date,
  value,
  AVG(value) OVER (
    ORDER BY date 
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS moving_avg_7d
FROM daily_metrics;

-- Running total
SELECT 
  date,
  value,
  SUM(value) OVER (ORDER BY date) AS running_total
FROM daily_metrics;

-- 30-day trailing sum
SELECT 
  date,
  value,
  SUM(value) OVER (
    ORDER BY date 
    RANGE BETWEEN INTERVAL '30 days' PRECEDING AND CURRENT ROW
  ) AS trailing_30d_sum
FROM daily_metrics;
```

---

### 6. Z-Score/Outlier Detection

**When to use:** Finding statistical outliers.

**Correct Pattern:**
```sql
WITH stats AS (
  SELECT 
    AVG(value) AS mean_val,
    STDDEV(value) AS std_val
  FROM measurements
  WHERE value IS NOT NULL
)
SELECT 
  m.*,
  (m.value - s.mean_val) / NULLIF(s.std_val, 0) AS z_score
FROM measurements m
CROSS JOIN stats s
WHERE ABS((m.value - s.mean_val) / NULLIF(s.std_val, 0)) > 2;  -- More than 2 std devs
```

**Important:** Always use `NULLIF(std_val, 0)` to prevent division by zero.

---

### 7. Episode Detection

**When to use:** Identifying sessions or periods of activity separated by gaps.

**Correct Pattern:**
```sql
WITH with_prev AS (
  SELECT *,
    LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) AS prev_time
  FROM events
),
with_gap_flag AS (
  SELECT *,
    CASE 
      WHEN prev_time IS NULL THEN 1  -- First event is new session
      WHEN DATEDIFF('minute', prev_time, event_time) > 30 THEN 1  -- Gap > 30 min
      ELSE 0 
    END AS is_new_session
  FROM with_prev
),
with_session AS (
  SELECT *,
    SUM(is_new_session) OVER (PARTITION BY user_id ORDER BY event_time) AS session_id
  FROM with_gap_flag
)
SELECT 
  user_id,
  session_id,
  MIN(event_time) AS session_start,
  MAX(event_time) AS session_end,
  COUNT(*) AS event_count,
  DATEDIFF('minute', MIN(event_time), MAX(event_time)) AS duration_minutes
FROM with_session
GROUP BY user_id, session_id;
```

---

### 8. State Transition Tracking

**When to use:** Tracking when values change from one state to another.

**Correct Pattern:**
```sql
WITH with_prev AS (
  SELECT *,
    LAG(status) OVER (PARTITION BY entity_id ORDER BY changed_at) AS prev_status
  FROM status_history
)
SELECT 
  entity_id,
  prev_status,
  status AS new_status,
  changed_at AS transition_time
FROM with_prev
WHERE prev_status IS DISTINCT FROM status;  -- Handles NULL comparisons
```

---

### 9. Hierarchical Comparisons

**When to use:** Comparing individual values to group aggregates.

**Correct Pattern:**
```sql
-- Compare each record to its category average
SELECT 
  entity_id,
  category,
  value,
  AVG(value) OVER (PARTITION BY category) AS category_avg,
  value - AVG(value) OVER (PARTITION BY category) AS diff_from_avg,
  ROUND(100.0 * value / NULLIF(AVG(value) OVER (PARTITION BY category), 0), 2) AS pct_of_avg
FROM measurements;

-- Compare to global average
SELECT 
  entity_id,
  category,
  value,
  AVG(value) OVER () AS global_avg,
  value - AVG(value) OVER () AS diff_from_global
FROM measurements;
```

---

### 10. Complex Deduplication

**When to use:** Getting one record per entity with specific selection logic.

**Pattern: Latest Record Per Entity:**
```sql
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY entity_id 
      ORDER BY updated_at DESC, id DESC  -- Tiebreaker
    ) AS rn
  FROM records
)
SELECT * FROM ranked WHERE rn = 1;
```

**Pattern: Best Record Per Entity (by score):**
```sql
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY entity_id 
      ORDER BY score DESC, created_at DESC
    ) AS rn
  FROM records
)
SELECT * FROM ranked WHERE rn = 1;
```

**Pattern: First Non-Null Value:**
```sql
SELECT DISTINCT ON (entity_id)
  entity_id,
  COALESCE(value_a, value_b, value_c) AS first_non_null
FROM records
WHERE COALESCE(value_a, value_b, value_c) IS NOT NULL
ORDER BY entity_id, created_at;
```

---

## Privacy Requirements

### Absolute Rules

1. **NO real data values** - Never include actual values from production data
2. **NO identifiable column names** - Avoid production-specific column names
3. **NO specific dates** - Use relative dates (`CURRENT_DATE - INTERVAL '30 days'`)
4. **NO numeric IDs** - Use placeholders or generic references
5. **NO names or identifiers** - No person names, MRNs, SSNs, etc.

### Acceptable vs. Unacceptable Examples

#### Column Names

| Unacceptable | Acceptable |
|--------------|------------|
| `patient_mrn` | `entity_id` |
| `diagnosis_icd10_code` | `category_code` |
| `john_smith_hospital` | `location_name` |
| `ssn`, `national_id` | `identifier` |

#### Values in SQL

| Unacceptable | Acceptable |
|--------------|------------|
| `WHERE name = 'John Smith'` | `WHERE category = 'type_a'` |
| `WHERE date = '2025-03-15'` | `WHERE date >= CURRENT_DATE - INTERVAL '30 days'` |
| `WHERE id = 12345678` | `WHERE id = ?` or just `WHERE id IS NOT NULL` |
| `WHERE status = 'ADMITTED_ICU'` | `WHERE status = 'active'` |

#### Questions

| Unacceptable | Acceptable |
|--------------|------------|
| "Find John Smith's records" | "Find records for a specific entity" |
| "Show patients at Memorial Hospital" | "Show records by location" |
| "Count diagnoses with ICD-10 code E11" | "Count records by category" |

### Generic Placeholder Values

Use these generic values when examples need specific values:

```sql
-- Status values
'active', 'inactive', 'pending', 'completed', 'cancelled'

-- Category values
'category_a', 'category_b', 'type_1', 'type_2'

-- Numeric thresholds
100, 50, 0, -1  -- Use round numbers

-- Date references
CURRENT_DATE
CURRENT_DATE - INTERVAL '30 days'
CURRENT_DATE - INTERVAL '1 year'
DATE_TRUNC('month', CURRENT_DATE)
```

---

## Testing Your Examples

### 1. Validate SQL Syntax

Use the validation script:

```bash
cd backend-modmono
conda activate fhir_rag_env
python -m app.scripts.test_training_api
```

Or test directly in Python:

```python
from app.modules.sql_examples.routes import TrainingExampleCreate

# This will validate the example
example = TrainingExampleCreate(
    question="Your question here",
    sql="SELECT * FROM records WHERE value > 100",
    category="aggregation",
    tags=["filter"]
)
print("Validation passed!")
```

### 2. Test SQL Execution

Test your SQL against a sample database:

```python
import duckdb

conn = duckdb.connect(':memory:')

# Create test table
conn.execute("""
    CREATE TABLE records (
        id INTEGER,
        entity_id VARCHAR,
        value FLOAT,
        category VARCHAR,
        created_at TIMESTAMP
    )
""")

# Insert sample data
conn.execute("""
    INSERT INTO records VALUES
    (1, 'E001', 100.5, 'A', '2026-01-01'),
    (2, 'E001', 105.2, 'A', '2026-01-02'),
    (3, 'E002', 95.0, 'B', '2026-01-01')
""")

# Test your SQL
result = conn.execute("YOUR SQL HERE").fetchall()
print(result)
```

### 3. Test via API

```bash
# Add example via API
curl -X POST http://localhost:8000/api/v1/training/examples \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "question": "Your question",
    "sql": "SELECT * FROM records",
    "category": "aggregation",
    "tags": ["test"]
  }'

# Search to verify it's retrievable
curl "http://localhost:8000/api/v1/training/examples/search?question=Your+question" \
  -H "Authorization: Bearer <token>"
```

### 4. Measure Impact on Accuracy

Run the test suite before and after adding examples:

```bash
# Before adding examples
python -m app.scripts.run_sql_tests \
  --input tests.csv \
  --output report_before.md \
  --save-results results_before.json

# Add your examples...

# After adding examples
python -m app.scripts.run_sql_tests \
  --input tests.csv \
  --output report_after.md \
  --save-results results_after.json

# Compare results
python -m app.scripts.analyze_test_results \
  --input results_after.json \
  --output analysis.md
```

---

## Contribution Process

### Step 1: Identify the Need

Check the failure analysis report to identify which patterns need more examples:

```bash
python -m app.scripts.analyze_test_results \
  --input latest_results.json \
  --output analysis.md
```

Look for:
- High-frequency error types
- Categories with low success rates
- Patterns not covered by existing examples

### Step 2: Create Examples

1. Create a JSON file with your examples:

```json
{
  "examples": [
    {
      "question": "...",
      "sql": "...",
      "category": "...",
      "tags": ["..."],
      "description": "..."
    }
  ]
}
```

2. Validate each example:
   - SQL executes without errors
   - Question is natural language
   - Category is appropriate
   - No PII or production data

### Step 3: Test Locally

```bash
# Validate format
python -c "
import json
from app.modules.sql_examples.routes import TrainingExampleCreate

with open('my_examples.json') as f:
    data = json.load(f)

for ex in data['examples']:
    TrainingExampleCreate(**ex)
    print(f'Valid: {ex[\"question\"][:50]}...')
"
```

### Step 4: Submit for Review

1. Create a pull request with:
   - The JSON file with new examples
   - Test results showing improvement
   - Description of what patterns are covered

2. Review criteria:
   - [ ] All examples pass validation
   - [ ] SQL is syntactically correct
   - [ ] No privacy violations
   - [ ] Category assignments are correct
   - [ ] Examples cover the identified gaps
   - [ ] Test accuracy improves (or at least doesn't regress)

### Step 5: Upload Approved Examples

```bash
# Bulk upload via API
curl -X POST http://localhost:8000/api/v1/training/bulk \
  -H "Authorization: Bearer <admin_token>" \
  -F "file=@approved_examples.json"
```

Or use the script:

```bash
python -m app.scripts.train_sql_examples --input approved_examples.json
```

---

## Troubleshooting

### Common Validation Errors

**"Question contains potential PII patterns"**
- Remove any names, emails, phone numbers, IDs from the question
- Use generic entity references

**"SQL cannot contain DELETE/DROP/INSERT statements"**
- Training examples must be SELECT queries only
- Remove any data modification statements

**"Category must be one of..."**
- Use only allowed categories (see Category Definitions)
- Check spelling and use snake_case

**"SQL must start with SELECT or WITH"**
- Ensure SQL begins with SELECT or WITH (for CTEs)
- Comments at the start are allowed (`-- comment`)

### SQL Execution Errors

**"window functions are not allowed in WHERE clause"**
- Wrap the window function in a CTE
- See Pattern #1: Window Function in CTE Pattern

**"DATEDIFF expected 3 arguments"**
- Use `DATEDIFF('day', start, end)` format
- See Pattern #4: Date Difference Calculations

**"function date_sub does not exist"**
- Use `date - INTERVAL 'X days'` instead
- See Pattern #4: Date Difference Calculations

**"column X must appear in GROUP BY clause"**
- Add the column to GROUP BY, or
- Wrap it in an aggregate function (MAX, MIN, ANY_VALUE)

---

## Quick Reference Card

### DuckDB SQL Rules

```sql
-- Date arithmetic
CURRENT_DATE - INTERVAL '30 days'    -- NOT DATE_SUB()
DATEDIFF('day', start, end)          -- 3 arguments required

-- Date extraction
DATE_TRUNC('month', date_col)        -- NOT MONTH()
EXTRACT(YEAR FROM date_col)          -- Alternative

-- Window functions: ALWAYS use CTE
WITH cte AS (SELECT *, ROW_NUMBER() OVER (...) AS rn FROM t)
SELECT * FROM cte WHERE rn = 1

-- Boolean
WHERE is_active = TRUE               -- NOT = 1 or = 'true'

-- NULL comparison
WHERE col IS NULL                    -- NOT = NULL
WHERE col IS NOT NULL                -- NOT != NULL
```

### Example Template

```json
{
  "question": "[Natural language question - no SQL terms]",
  "sql": "[Valid DuckDB/PostgreSQL SELECT query]",
  "category": "[One of: aggregation, temporal_comparison, consecutive_streak, rolling_calculation, statistical_analysis, deduplication, episode_detection, comparison, window_functions, date_functions]",
  "tags": ["[relevant]", "[tags]", "[here]"],
  "description": "[Brief explanation of what pattern this demonstrates]"
}
```

---

## Appendix: Allowed Categories

| Category | Description |
|----------|-------------|
| `aggregation` | COUNT, SUM, AVG, GROUP BY queries |
| `temporal_comparison` | First vs. last, period comparisons |
| `consecutive_streak` | Detecting consecutive occurrences |
| `rolling_calculation` | Moving averages, running totals |
| `statistical_analysis` | Z-scores, percentiles, outliers |
| `deduplication` | Latest/first record per entity |
| `episode_detection` | Session/activity period detection |
| `comparison` | Group vs. group, vs. benchmark |
| `window_functions` | RANK, LAG, LEAD patterns |
| `date_functions` | Date manipulation and extraction |
| `joins` | Multi-table join patterns |
| `subqueries` | Nested query patterns |
| `cte_patterns` | Complex CTE usage |

---

*Document maintained by the Data Insights Team. For questions, contact the team lead or submit an issue.*
