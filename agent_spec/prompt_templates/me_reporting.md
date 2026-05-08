# M&E (Monitoring & Evaluation) Reporting SQL Patterns

You are generating SQL for **M&E (Monitoring & Evaluation) reporting** in a healthcare analytics system. M&E queries typically require enriching clinical data with geographic hierarchy and program information.

## When to Apply These Patterns

Use M&E patterns when the user asks about:
- Data **by facility, county, subcounty, or country**
- Data **by program** or program-level aggregations
- **Geographic breakdowns** of clinical metrics
- **Facility-level** performance or volumes
- **Dashboard exports** with location context

## Core M&E CTEs (Common Table Expressions)

### 1. Facility Hierarchy CTE

Builds the complete geographic hierarchy: **Country → District/County → Chiefdom/Subcounty**

```sql
WITH facilities AS (
    SELECT
        hf.id AS facility_id,
        hf.name AS facility_name,
        CAST(hf.fhir_id AS BIGINT) AS organization_id,  -- CRITICAL: Cast for join
        co.id AS country_id,
        co.name AS country,
        dis.id AS county_id,
        dis.name AS county_name,
        chif.id AS subcounty_id,
        chif.name AS subcounty_name
    FROM health_facility_admin_gold hf
    LEFT JOIN country_admin_gold co ON hf.country_id = co.id
    LEFT JOIN district_admin_gold dis ON hf.district_id = dis.id
    LEFT JOIN chiefdom_admin_gold chif ON hf.chiefdom_id = chif.id
    WHERE hf.is_deleted = FALSE
)
```

**Key Points:**
- `CAST(hf.fhir_id AS BIGINT)` is **required** - fhir_id is VARCHAR, organization_id is BIGINT
- Always filter `hf.is_deleted = FALSE`
- Use `LEFT JOIN` to preserve facilities without all hierarchy levels

### 2. Program Assignment CTE

Maps facilities to their NCD programs:

```sql
facility_programs AS (
    SELECT
        hfp.health_facility_id AS facility_id,
        COALESCE(MAX(pg.name), 'Unassigned') AS program_name
    FROM health_facility_program_admin_gold hfp
    LEFT JOIN program_admin_gold pg ON pg.id = hfp.program_id
    GROUP BY hfp.health_facility_id
)
```

**Key Points:**
- `MAX(pg.name)` handles facilities with multiple programs
- `COALESCE(..., 'Unassigned')` for facilities without program assignment

## Join Patterns

### Clinical Data → Facility Hierarchy

Join clinical tables to facility CTE via `organization_id`:

```sql
FROM bp_log_gold bl
LEFT JOIN facilities f ON f.organization_id = bl.organization_id
LEFT JOIN facility_programs fp ON fp.facility_id = f.facility_id
```

### Patient Tracker → Facility Hierarchy

Patient tracker uses `site_id` instead of `organization_id`:

```sql
FROM patient_tracker_gold pt
LEFT JOIN facilities f ON f.organization_id = pt.site_id
LEFT JOIN facility_programs fp ON fp.facility_id = f.facility_id
WHERE pt.is_deleted = FALSE
```

## Complete M&E Query Template

```sql
WITH facilities AS (
    SELECT
        hf.id AS facility_id,
        hf.name AS facility_name,
        CAST(hf.fhir_id AS BIGINT) AS organization_id,
        co.name AS country,
        dis.name AS county_name,
        chif.name AS subcounty_name
    FROM health_facility_admin_gold hf
    LEFT JOIN country_admin_gold co ON hf.country_id = co.id
    LEFT JOIN district_admin_gold dis ON hf.district_id = dis.id
    LEFT JOIN chiefdom_admin_gold chif ON hf.chiefdom_id = chif.id
    WHERE hf.is_deleted = FALSE
),
facility_programs AS (
    SELECT
        hfp.health_facility_id AS facility_id,
        COALESCE(MAX(pg.name), 'Unassigned') AS program_name
    FROM health_facility_program_admin_gold hfp
    LEFT JOIN program_admin_gold pg ON pg.id = hfp.program_id
    GROUP BY hfp.health_facility_id
)
SELECT
    -- Clinical data columns
    bl.patient_id,
    bl.avg_systolic,
    bl.avg_diastolic,
    bl.bp_taken_on,
    bl.cvd_risk_level,
    -- Facility hierarchy
    f.facility_name,
    f.country,
    f.county_name,
    f.subcounty_name,
    -- Program
    COALESCE(fp.program_name, 'Unassigned') AS program_name
FROM bp_log_gold bl
LEFT JOIN facilities f ON f.organization_id = bl.organization_id
LEFT JOIN facility_programs fp ON fp.facility_id = f.facility_id
WHERE bl.bp_taken_on IS NOT NULL
```

## Date Filtering for M&E Reports

Use `TRY_CAST` for safe date parsing (handles NULL gracefully):

```sql
WHERE TRY_CAST(bl.bp_taken_on AS DATE) >= DATE '2024-10-01'
  AND TRY_CAST(bl.bp_taken_on AS DATE) <= CURRENT_DATE
```

Or standard date comparison if column is already DATE type:

```sql
WHERE bl.ymd >= DATE '2024-10-01'
  AND bl.ymd <= CURRENT_DATE
```

## Common M&E Aggregations

### By Facility
```sql
GROUP BY f.facility_id, f.facility_name
```

### By County
```sql
GROUP BY f.county_id, f.county_name
```

### By Program and County
```sql
GROUP BY fp.program_name, f.county_name
```

### Monthly Trends by Facility
```sql
GROUP BY f.facility_name, DATE_TRUNC('month', bl.bp_taken_on)
ORDER BY DATE_TRUNC('month', bl.bp_taken_on), f.facility_name
```

## Glucose Log M&E Query Template

For glucose data, use `bg_taken_on` as the date field and `glucose_log_latest_gold`:

```sql
WITH facilities AS (
    SELECT
        hf.id AS facility_id,
        hf.name AS facility_name,
        CAST(hf.fhir_id AS BIGINT) AS organization_id,
        co.id AS country_id,
        co.name AS country,
        dis.id AS county_id,
        dis.name AS county_name,
        chif.id AS subcounty_id,
        chif.name AS subcounty_name
    FROM health_facility_admin_gold hf
    LEFT JOIN country_admin_gold co ON hf.country_id = co.id
    LEFT JOIN district_admin_gold dis ON hf.district_id = dis.id
    LEFT JOIN chiefdom_admin_gold chif ON hf.chiefdom_id = chif.id
    WHERE hf.is_deleted = FALSE
),
facility_programs AS (
    SELECT
        hfp.health_facility_id AS facility_id,
        COALESCE(MAX(pg.name), 'Unassigned') AS program_name
    FROM health_facility_program_admin_gold hfp
    LEFT JOIN program_admin_gold pg ON pg.id = hfp.program_id
    GROUP BY hfp.health_facility_id
)
SELECT
    gl.patient_id,
    gl.glucose_type,
    gl.glucose_value,
    gl.glucose_unit,
    gl.hba1c,
    gl.hba1c_unit,
    gl.last_meal_time,
    gl.is_latest,
    gl.encounter_type,
    date_format(TRY_CAST(gl.bg_taken_on AS DATE), '%Y-%m-%d') AS bg_taken_on,
    TRY_CAST(gl.bg_taken_on AS DATE) AS event_date,
    CAST(date_format(TRY_CAST(gl.bg_taken_on AS DATE), '%Y%m%d') AS INTEGER) AS ymd,
    f.facility_id,
    f.facility_name,
    f.country_id,
    f.country,
    f.county_id,
    f.county_name,
    f.subcounty_id,
    f.subcounty_name,
    COALESCE(fp.program_name, 'Unassigned') AS program_name
FROM glucose_log_latest_gold gl
LEFT JOIN facilities f ON f.organization_id = gl.organization_id
LEFT JOIN facility_programs fp ON fp.facility_id = f.facility_id
WHERE TRY_CAST(gl.bg_taken_on AS DATE) >= DATE '2024-10-01'
  AND TRY_CAST(gl.bg_taken_on AS DATE) <= CURRENT_DATE
```

### Glucose-Specific Columns

| Column | Description |
|--------|-------------|
| `glucose_type` | Type of glucose measurement |
| `glucose_value` | Glucose reading value |
| `glucose_unit` | Unit of measurement |
| `hba1c` | HbA1c value |
| `hba1c_unit` | HbA1c unit |
| `last_meal_time` | Time of last meal |
| `is_latest` | Flag for most recent record |
| `bg_taken_on` | Date glucose was taken |

### Date Formatting Pattern (Spark/DuckDB Compatible)

```sql
-- Format date as string
date_format(TRY_CAST(gl.bg_taken_on AS DATE), '%Y-%m-%d') AS bg_taken_on

-- Create integer YMD for partitioning
CAST(date_format(TRY_CAST(gl.bg_taken_on AS DATE), '%Y%m%d') AS INTEGER) AS ymd

-- Cast to DATE for comparisons
TRY_CAST(gl.bg_taken_on AS DATE) AS event_date
```

## Table Reference

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `health_facility_admin_gold` | Facility registry | `id`, `name`, `fhir_id`, `country_id`, `district_id`, `chiefdom_id` |
| `country_admin_gold` | Countries | `id`, `name` |
| `district_admin_gold` | Districts/Counties | `id`, `name`, `country_id` |
| `chiefdom_admin_gold` | Chiefdoms/Subcounties | `id`, `name`, `district_id` |
| `program_admin_gold` | NCD Programs | `id`, `name` |
| `health_facility_program_admin_gold` | Facility-Program mapping | `health_facility_id`, `program_id` |
| `glucose_log_latest_gold` | Latest glucose readings | `patient_id`, `glucose_type`, `glucose_value`, `hba1c`, `bg_taken_on`, `organization_id` |
| `bp_log_gold` | BP readings | `patient_id`, `avg_systolic`, `avg_diastolic`, `bp_taken_on`, `organization_id` |
| `screening_log_gold` | Screening records | `patient_id`, `bp_taken_on`, `organization_id` |

## Geographic Terminology

| Database Column | Alternative Names |
|-----------------|-------------------|
| `country_admin_gold.name` | Country, Nation |
| `district_admin_gold.name` | District, County, Region |
| `chiefdom_admin_gold.name` | Chiefdom, Subcounty, Ward |

When users ask for "county" data, use `district_admin_gold`.
When users ask for "subcounty" data, use `chiefdom_admin_gold`.
