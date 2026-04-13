# SQL Query Fix Template

You are a {dialect} SQL expert. Fix the failed SQL query based on the error.

## ORIGINAL QUESTION
{question}

## DATABASE SCHEMA
{schema_context}

## SAMPLE DATA
{sample_data}

## FAILED SQL
```sql
{failed_sql}
```

## ERROR ({error_type})
{error_message}

## FIX HINTS
{fix_hints}

## COMMON FIX PATTERNS

### Window Functions (DuckDB)
Window functions CANNOT be in WHERE or GROUP BY. Use CTE:
```sql
WITH computed AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY date) AS rn
    FROM table
)
SELECT * FROM computed WHERE rn = 1
```

### Aggregates in WHERE
Use HAVING or subquery instead:
```sql
-- Wrong: WHERE col > AVG(col)
-- Correct:
WITH stats AS (SELECT AVG(col) AS avg_val FROM table)
SELECT * FROM table, stats WHERE col > stats.avg_val
```

### Date Functions (DuckDB)
- DATEDIFF requires 3 args: `DATEDIFF('day', start_date, end_date)`
- Date subtraction: `date_col - INTERVAL '90 days'`
- Cast strings: `CAST(varchar_col AS TIMESTAMP)`

### Ambiguous Columns
Always use table aliases: `t.column_name` not just `column_name`

## INSTRUCTIONS
1. Analyze the error message carefully
2. Apply the relevant fix pattern
3. Use ONLY tables and columns from the schema above
4. Return ONLY the corrected SQL query, no explanation

## CORRECTED SQL
