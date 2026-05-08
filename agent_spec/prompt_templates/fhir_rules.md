# FHIR Identifier Rules - CRITICAL

This healthcare schema follows FHIR (Fast Healthcare Interoperability Resources) data patterns. You MUST follow these rules strictly.

## Patient Identifier Rules

### Table-Specific Identifiers
- **`patient_gold`**: Uses `res_id` as the patient identifier. This table does NOT have a `patient_id` column. Use `COUNT(DISTINCT res_id)` for patient counts.
- **`patient_tracker_gold`**: Uses `patient_id` as the patient identifier. This is the PRIMARY operational table for patient counts. Use `COUNT(DISTINCT patient_id) WHERE is_deleted = false`.
- **All other clinical `*_gold` tables**: Have both `res_id` (record identifier) and `patient_id` (FK to patient). Join on `patient_id`.

### Patient Count Queries (MANDATORY)
When asked "how many patients", "total patients", "patient count", etc.:
1. **FIRST CHOICE**: `SELECT COUNT(DISTINCT patient_id) FROM patient_tracker_gold WHERE is_deleted = false`
2. **ALTERNATIVE**: `SELECT COUNT(DISTINCT res_id) FROM patient_gold WHERE res_deleted_at IS NULL`
3. **NEVER USE**: `patient_id` on `patient_gold` - this column does NOT exist and will cause SQL errors!

## Table Categories

| Category | Primary Key | Patient FK | Examples |
|----------|-------------|------------|----------|
| FHIR Resource Tables | `res_id` | N/A | `patient_gold`, `encounter_gold`, `condition_gold` |
| Clinical Observation Tables | `res_id` | `patient_id` | `bp_log_gold`, `glucose_log_gold`, `prescription_gold` |
| Operational Tables | `patient_id` | N/A | `patient_tracker_gold`, `call_register_admin_gold` |
| Admin Reference Tables | `id` | N/A | `*_admin_gold` tables |

## Common Join Patterns

### Patient-centered joins
```sql
-- Joining clinical data to patient demographics
SELECT p.*, bp.avg_systolic, bp.avg_diastolic
FROM patient_tracker_gold p
JOIN bp_log_latest_gold bp ON p.patient_id = bp.patient_id
WHERE p.is_deleted = false
```

### Encounter-scoped joins
```sql
-- Joining measurements within an encounter
SELECT e.res_id as encounter_id, bp.*, gl.*
FROM encounter_gold e
JOIN bp_log_gold bp ON e.res_id = bp.encounter_id
LEFT JOIN glucose_log_gold gl ON e.res_id = gl.encounter_id
```

## Soft Delete Filters

Always apply appropriate soft-delete filters:
- `patient_tracker_gold`: `WHERE is_deleted = false`
- `patient_gold`: `WHERE res_deleted_at IS NULL`
- `*_admin_gold` tables: `WHERE is_active = 1 AND is_deleted = false` (check if columns exist)
- Clinical tables with `is_src_deleted`: `WHERE is_src_deleted = false`

## Latest Record Patterns

For "latest" or "current" data:
- **BP readings**: Use `bp_log_gold` - the `bp_log_latest_gold` table is currently EMPTY. For latest per patient, use window functions: `ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY bp_taken_on DESC) = 1`
- **Glucose readings**: Use `glucose_log_gold` - the `glucose_log_latest_gold` table may be empty. Use similar window function pattern.
- **For distribution/analysis queries**: Use `bp_log_gold` or `glucose_log_gold` directly without latest filtering
- **AVOID**: `bp_log_latest_gold` and `glucose_log_latest_gold` tables (currently empty/stale)
