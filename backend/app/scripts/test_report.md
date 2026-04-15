# SQL Test Report

**Generated:** 2026-04-09T15:22:44.832604

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 6 |
| Passed | 0 |
| Failed | 0 |
| Errors | 6 |
| Skipped | 0 |
| **Overall Accuracy** | **0.0%** |

## Results by Category

| Category | Passed | Failed | Errors | Skipped | Pass Rate |
|----------|--------|--------|--------|---------|-----------|
| general | 0 | 0 | 0 | 0 | 0.0% |

## Results by Complexity

| Complexity | Passed | Failed | Errors | Skipped | Pass Rate |
|------------|--------|--------|--------|---------|-----------|
| medium | 0 | 0 | 0 | 0 | 0.0% |

## Execution Statistics

| Metric | Value |
|--------|-------|
| Total Time | 7903 ms |
| Avg Execution | 1317 ms |
| Min Execution | 654 ms |
| Max Execution | 1846 ms |
| Avg SQL Generation | 1312 ms |

## Results by Tag

| Tag | Passed | Failed | Errors | Skipped |
|-----|--------|--------|--------|---------|
| aggregation | 0 | 0 | 0 | 0 |
| average | 0 | 0 | 0 | 0 |
| basic | 0 | 0 | 0 | 0 |
| complex | 0 | 0 | 0 | 0 |
| count | 0 | 0 | 0 | 0 |
| distinct | 0 | 0 | 0 | 0 |
| filter | 0 | 0 | 0 | 0 |
| groupby | 0 | 0 | 0 | 0 |
| limit | 0 | 0 | 0 | 0 |
| ranking | 0 | 0 | 0 | 0 |
| recent | 0 | 0 | 0 | 0 |
| status | 0 | 0 | 0 | 0 |
| temporal | 0 | 0 | 0 | 0 |

## SQL Errors by Type

### Unknown Error (6 tests)

- basic_001
- basic_002
- aggregation_001
- temporal_001
- filter_001
- complex_001

## Failed Tests Details

### basic_001

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** basic, count, aggregation

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select count(*) as record_count from information_schema.tables limit 100
```

**Expected SQL:**
```sql
SELECT COUNT(*) FROM entity_table
```

**Notes:** Row count mismatch: got 0, expected 1

### basic_002

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** basic, distinct

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select distinct category from your_table_name limit 100
```

**Expected SQL:**
```sql
SELECT DISTINCT category FROM entity_table
```

**Notes:** Row count mismatch: got 0, expected ; Query executed but returned no rows

### aggregation_001

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** aggregation, groupby, average

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select 'Insufficient data' as error
```

**Expected SQL:**
```sql
SELECT category, AVG(value) FROM measurement_table GROUP BY category
```

**Notes:** Row count mismatch: got 0, expected ; Query executed but returned no rows

### temporal_001

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** temporal, filter, recent

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select 'Insufficient data' as error
```

**Expected SQL:**
```sql
SELECT * FROM entity_table WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
```

**Notes:** Row count mismatch: got 0, expected ; Query executed but returned no rows

### filter_001

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** filter, status, basic

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select 'Insufficient data' as error
```

**Expected SQL:**
```sql
SELECT * FROM entity_table WHERE is_active = true AND is_deleted = false
```

**Notes:** Row count mismatch: got 0, expected ; Query executed but returned no rows

### complex_001

**Status:** error
**Category:** general
**Complexity:** medium
**Tags:** complex, ranking, limit

**Error:**
```
(duckdb.duckdb.IOException) IO Error: Cannot open database "/Users/adityanbhatt/Documents/Data-inisights-copilot/backend-modmono/data/test.db" in read-only mode: database does not exist
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

**Generated SQL:**
```sql
select category, count(*) as record_count from your_table_name group by category order by record_count desc limit 5
```

**Expected SQL:**
```sql
SELECT category, COUNT(*) as count FROM entity_table GROUP BY category ORDER BY count DESC LIMIT 5
```

**Notes:** Row count mismatch: got 0, expected 5
