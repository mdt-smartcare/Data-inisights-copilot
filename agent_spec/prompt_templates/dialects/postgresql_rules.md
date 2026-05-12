# PostgreSQL Dialect Rules

## PostgreSQL-Specific SQL Rules

Follow these rules when generating PostgreSQL queries:

### Date/Time Operations
- Use `DATE_TRUNC('month', date_col)` for date truncation
- Use `INTERVAL '90 days'` for date arithmetic
- Use `CURRENT_DATE` for current date
- Cast with `::date` or `::timestamp` syntax

### Window Functions
- Window functions work in SELECT and ORDER BY, NOT in WHERE
- Use CTE pattern to filter on window function results

### Type Casting
- Use `::` for type casting (e.g., `column::timestamp`)
- Use `CAST(column AS type)` as alternative

### String Operations
- String concatenation uses `||` operator
- Use `ILIKE` for case-insensitive pattern matching
- Use `LIKE` for case-sensitive pattern matching

### NULL Handling
- Use `COALESCE(col, default)` for NULL replacement
- Use `NULLIF(col, value)` to convert value to NULL

### Boolean Values
- Compare with `= true` or `= false`
- Can also use `IS TRUE` or `IS FALSE`

### Aggregation
- All non-aggregated columns must appear in GROUP BY
- Use `HAVING` to filter on aggregate results

### ROUND Function (CRITICAL)
- PostgreSQL's `ROUND(value, decimals)` only works with NUMERIC type, NOT double precision
- Always cast to `::numeric` before rounding:
  - WRONG: `ROUND(AVG(column), 2)`
  - CORRECT: `ROUND(AVG(column)::numeric, 2)`
  - CORRECT: `ROUND(CAST(value AS numeric), 2)`
- This applies to any floating-point aggregation result (AVG, SUM of decimals, etc.)

### Best Practices
- Use explicit JOIN syntax (INNER JOIN, LEFT JOIN) - never comma joins
- Include appropriate WHERE clauses for filtering
- Add meaningful column aliases for clarity
