# SQL Training Examples Documentation

This document provides detailed documentation for all SQL patterns in `sql_training_examples.json`. These examples serve as few-shot training data for the NL2SQL system and demonstrate DuckDB-compatible SQL patterns.

## Table of Contents

1. [Temporal Comparison Patterns](#temporal-comparison-patterns)
2. [Window Function Patterns](#window-function-patterns)
3. [Consecutive Streak Detection](#consecutive-streak-detection)
4. [Episode Detection](#episode-detection)
5. [Statistical Analysis](#statistical-analysis)
6. [Date Calculations](#date-calculations)
7. [Rolling Calculations](#rolling-calculations)
8. [State Transitions](#state-transitions)
9. [Comparisons](#comparisons)
10. [Deduplication](#deduplication)

---

## Temporal Comparison Patterns

### temporal_001: First vs Last Value Comparison

**Purpose:** Compare initial and latest measurement values for each entity.

**Pattern:** Uses dual `ROW_NUMBER()` window functions to identify first and last records, then self-joins to get both values in one row.

**Key Techniques:**
- `ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY date ASC)` for first record
- `ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY date DESC)` for last record
- Self-join on entity_id with rank filters

**Use Cases:**
- Track patient BP improvement (first vs last reading)
- Measure outcome changes over time
- Compare baseline to current status

**Example Output:**
| entity_id | initial_value | latest_value |
|-----------|---------------|--------------|
| P001      | 145           | 128          |
| P002      | 132           | 135          |

---

### temporal_002: First and Last Status with Dates

**Purpose:** Get both first and most recent status along with their timestamps.

**Pattern:** Similar to temporal_001 but includes date columns for tracking when transitions occurred.

**Key Techniques:**
- Dual ranking in single CTE
- Self-join pattern preserving dates
- Filtering on `asc_rank = 1` and `desc_rank = 1`

**Use Cases:**
- Audit trail analysis
- Status change tracking with timestamps
- Duration calculations between first and last

---

## Window Function Patterns

### window_001: LAG for Change Detection

**Purpose:** Find records where values increased from the previous entry.

**Critical Rule:** Window functions MUST be computed in a CTE, never used directly in WHERE clauses.

**Pattern:**
```sql
WITH ValueChanges AS (
    SELECT 
        entity_id,
        value,
        LAG(value) OVER (PARTITION BY entity_id ORDER BY date) AS prev_value
    FROM table
)
SELECT * FROM ValueChanges
WHERE prev_value IS NOT NULL AND value > prev_value;
```

**Why CTE is Required:**
- DuckDB (and most SQL engines) cannot filter on window function results directly
- The window function must be materialized first in a CTE or subquery

**Use Cases:**
- BP increase detection
- Worsening condition alerts
- Trend analysis

---

### window_002: LEAD for Forward Looking

**Purpose:** Identify entries that differ from the next scheduled entry.

**Pattern:** Uses `LEAD()` to look at the next row's values.

**Key Techniques:**
- `LEAD(column) OVER (PARTITION BY entity ORDER BY date)` to peek ahead
- CTE to compute LEAD, outer query to filter
- NULL handling for last records (no next value)

**Use Cases:**
- Schedule conflict detection
- Category change prediction
- Gap identification

---

## Consecutive Streak Detection

### streak_001: ROW_NUMBER Difference Technique

**Purpose:** Find consecutive periods where status remained the same.

**Pattern:** The classic "gaps and islands" solution using the difference between two row numbers.

**How It Works:**
1. Assign overall row number ordered by date
2. Assign row number within each status group
3. Subtract: `overall_rank - status_rank = streak_group`
4. Records with same streak_group are consecutive

**Visual Example:**
| date | status | overall_rank | status_rank | streak_group |
|------|--------|--------------|-------------|--------------|
| D1   | A      | 1            | 1           | 0            |
| D2   | A      | 2            | 2           | 0            |
| D3   | B      | 3            | 1           | 2            |
| D4   | A      | 4            | 3           | 1            |

**Use Cases:**
- Consecutive high BP readings
- Treatment adherence streaks
- Consistent attendance tracking

---

### streak_002: Date-Based Consecutive Days

**Purpose:** Count consecutive days with activity.

**Pattern:** Subtracts row number (as interval) from date to create a "streak base" that's identical for consecutive days.

**Key Formula:**
```sql
activity_date - INTERVAL '1 day' * ROW_NUMBER() OVER (...) AS streak_base
```

**How It Works:**
- Consecutive dates minus incrementing row numbers yield the same base date
- Non-consecutive dates yield different base dates
- Group by streak_base to find streaks

**Use Cases:**
- Daily medication adherence
- Consecutive visit tracking
- Activity streak gamification

---

## Episode Detection

### episode_001: Gap-Based Episode Grouping (30-day threshold)

**Purpose:** Group events into episodes where gaps > 30 days start new episodes.

**Pattern:** Three-step CTE approach:
1. Calculate gaps using LAG
2. Flag new episodes (gap > threshold or first record)
3. Running sum of flags = episode number

**Key Techniques:**
```sql
-- Step 1: Get gaps
LAG(event_date) OVER (PARTITION BY entity ORDER BY date) AS prev_date

-- Step 2: Flag new episodes  
CASE WHEN gap > 30 OR prev_date IS NULL THEN 1 ELSE 0 END AS is_new_episode

-- Step 3: Episode numbers via running sum
SUM(is_new_episode) OVER (PARTITION BY entity ORDER BY date) AS episode_num
```

**Use Cases:**
- Care episode identification
- Treatment course grouping
- Visit clustering

---

### episode_002: Episode Detection with DATEDIFF (90-day threshold)

**Purpose:** Same as episode_001 but uses `DATEDIFF` function.

**DuckDB DATEDIFF Syntax:**
```sql
DATEDIFF('day', start_date, end_date)  -- 3 arguments required!
```

**Common Mistake:** Using 2-argument DATEDIFF (MySQL style) won't work in DuckDB.

**Output Includes:**
- Episode ID
- Visit count per episode
- First and last visit dates
- Episode duration in days

---

## Statistical Analysis

### stats_001: Z-Score Outlier Detection

**Purpose:** Find outliers using z-score > 2 standard deviations.

**Pattern:** Calculate mean and stddev in one CTE, apply to all records via CROSS JOIN.

**Formula:**
```sql
z_score = (value - mean) / stddev
```

**Key Techniques:**
- Aggregate stats in separate CTE
- CROSS JOIN to apply stats to all rows
- Handle zero stddev with CASE or NULLIF
- Filter in outer query, not in window function

**Use Cases:**
- Outlier BP readings
- Data quality checks
- Anomaly detection

---

### stats_002: Percentile Ranking Within Groups

**Purpose:** Calculate percentile ranks for values within their groups.

**Key Function:**
```sql
PERCENT_RANK() OVER (PARTITION BY group ORDER BY score)
```

**Returns:** Value between 0 and 1 representing percentile position.

**Pattern:**
- Calculate group statistics in one CTE
- Add percentile ranks in second CTE
- Filter for top performers (e.g., >= 90th percentile)

**Use Cases:**
- Top performer identification
- Relative ranking within facilities
- Benchmark comparisons

---

## Date Calculations

### date_001: Recent Records Filter

**Purpose:** Find records from the last N days.

**DuckDB Syntax:**
```sql
WHERE record_date >= CURRENT_DATE - INTERVAL '90 days'
```

**Not Supported:**
- `DATE_SUB()` (MySQL)
- `DATEADD()` (SQL Server)

**Use Cases:**
- Recent activity reports
- Rolling time windows
- Fresh data filtering

---

### date_002: Duration Between Dates

**Purpose:** Calculate days between first and last event.

**Two Methods in DuckDB:**
```sql
-- Method 1: DATEDIFF (3 arguments)
DATEDIFF('day', first_date, last_date)

-- Method 2: Date subtraction
CAST(last_date AS DATE) - CAST(first_date AS DATE)
```

**Important:** Always cast to DATE if timestamps are involved to avoid time component issues.

---

## Rolling Calculations

### rolling_001: Trailing Average (Self-Join Method)

**Purpose:** Calculate 7-day trailing average.

**Pattern:** Self-join with date range condition.

```sql
LEFT JOIN table t2 
    ON t1.entity_id = t2.entity_id
    AND t2.date BETWEEN t1.date - INTERVAL '6 days' AND t1.date
```

**Advantages:**
- Works even with missing days
- Flexible window definition
- Can require minimum days in window

**Use Cases:**
- Moving average BP
- Trend smoothing
- Volatility reduction

---

### rolling_002: Rolling Sum (Window Frame Method)

**Purpose:** Compute 30-day moving sum.

**Pattern:** Window function with ROWS BETWEEN frame.

```sql
SUM(value) OVER (
    PARTITION BY entity 
    ORDER BY date 
    ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
)
```

**Note:** `29 PRECEDING` + current row = 30 rows total.

**Use Cases:**
- Cumulative activity counts
- Rolling revenue
- Usage tracking

---

## State Transitions

### transition_001: Category Change Detection

**Purpose:** Find entities whose category changed from first to last record.

**Pattern:** Same as temporal comparison but adds filter for different categories.

```sql
WHERE f.first_rank = 1 
  AND l.last_rank = 1
  AND f.category != l.category  -- Key filter
```

**Use Cases:**
- Risk level changes
- BMI category transitions
- Status improvements/deteriorations

---

### transition_002: Full Transition History

**Purpose:** Track all status transitions showing from/to states.

**Pattern:** LAG to get previous status, filter where status changed.

**Output Columns:**
- from_status
- to_status
- transition_from (date)
- transition_to (date)
- days_in_previous_status

**Use Cases:**
- Complete audit trail
- State machine analysis
- Process flow tracking

---

## Comparisons

### comparison_001: Sub-Group vs Parent Group

**Purpose:** Compare location averages to regional averages.

**Pattern:** Separate CTEs for each aggregation level, then JOIN.

```sql
WITH LocationAvg AS (...),
     RegionAvg AS (...)
SELECT 
    l.location_avg,
    r.region_avg,
    l.location_avg - r.region_avg AS difference
FROM LocationAvg l
JOIN RegionAvg r ON l.region_id = r.region_id
```

**Use Cases:**
- Facility vs county comparison
- Individual vs cohort benchmarking
- Performance variance analysis

---

### comparison_002: Comparison to Median

**Purpose:** Find entities performing above the overall median.

**Key Function:**
```sql
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY score) AS median_score
```

**Pattern:** Calculate overall median in CTE, CROSS JOIN to all entities, filter above median.

**Use Cases:**
- Above-average performer identification
- Median-based thresholds
- Distribution analysis

---

## Deduplication

### dedup_001: Latest Record with Tie-Breaking

**Purpose:** Get the most recent record for each entity with deterministic tie-breaking.

**Pattern:** ROW_NUMBER with multiple ORDER BY columns.

```sql
ROW_NUMBER() OVER (
    PARTITION BY entity_id 
    ORDER BY updated_at DESC, created_at DESC, record_id DESC
) AS rn
```

**Tie-Breaking Strategy:**
1. Most recent update time
2. Most recent creation time
3. Highest record ID (deterministic)

**Critical:** Always include a unique column (like ID) as final tie-breaker for deterministic results.

---

### dedup_002: Priority-Based Selection

**Purpose:** Select one representative record based on source priority.

**Pattern:** CASE expression in ORDER BY to define priority.

```sql
ORDER BY 
    CASE source 
        WHEN 'primary' THEN 1 
        WHEN 'secondary' THEN 2 
        ELSE 3 
    END,
    recorded_at DESC
```

**Use Cases:**
- Prefer verified over unverified data
- Primary source precedence
- Quality-ranked selection

---

## Best Practices Summary

### Always Use CTEs for Window Functions
```sql
-- CORRECT
WITH Computed AS (
    SELECT LAG(value) OVER (...) AS prev_value FROM t
)
SELECT * FROM Computed WHERE prev_value > 100;

-- WRONG (won't work)
SELECT * FROM t WHERE LAG(value) OVER (...) > 100;
```

### DuckDB Date Functions
```sql
-- Date arithmetic
CURRENT_DATE - INTERVAL '30 days'

-- Date difference (3 arguments!)
DATEDIFF('day', start_date, end_date)

-- Date casting
CAST(timestamp_col AS DATE)
```

### Case-Insensitive Matching
```sql
-- Use ILIKE for case-insensitive
WHERE category ILIKE '%diabetes%'

-- Not LIKE (case-sensitive)
```

### Boolean Comparisons
```sql
-- String booleans
WHERE is_active = 'true'
WHERE is_deleted = 'false'

-- Not boolean literals in some contexts
```

### Null Handling
```sql
-- Always handle potential NULLs
WHERE prev_value IS NOT NULL AND value > prev_value

-- Use COALESCE for defaults
COALESCE(value, 0)

-- Use NULLIF to avoid division by zero
value / NULLIF(divisor, 0)
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0     | 2024 | Initial 22 examples |

