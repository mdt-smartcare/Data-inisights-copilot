---
description: "Business Semantics and Data Dictionary"
version: 2.0.0
last_updated: 2026-05-07
---

# Business Semantics & Data Dictionary (DataDictionary.md)

This contract defines the business semantics connecting natural language queries to structural database constraints.

> **Source of Truth**: The active configuration is stored and executed from `backend/app/core/config/data_dictionary.yaml`. This document defines the theoretical structure and standards.

---

## CRITICAL: FHIR vs Operational Identifiers

This schema follows a **FHIR-aligned healthcare data model** with gold-layer analytical tables.

### Identifier Rules

| Table Pattern | Primary Key | Patient Identifier | Usage |
|---|---|---|---|
| `patient_gold` | `res_id` | `res_id` | FHIR Patient resource - `res_id` IS the patient's unique ID |
| `patient_tracker_gold` | `patient_id` | `patient_id` | Operational tracking - use this for patient counts |
| `*_gold` (clinical) | `res_id` | `patient_id` (FK) | Clinical events - join via `patient_id` |
| `*_admin_gold` | `id` | `patient_id` (FK) | Admin/operational tables |

### When Counting Patients

✅ **CORRECT**: 
```sql
-- Count patients from patient_tracker_gold
SELECT COUNT(DISTINCT patient_id) FROM patient_tracker_gold WHERE is_deleted = false

-- Count patients from patient_gold  
SELECT COUNT(DISTINCT res_id) FROM patient_gold WHERE res_deleted_at IS NULL
```

❌ **INCORRECT**:
```sql
-- patient_gold does NOT have a patient_id column
SELECT COUNT(DISTINCT patient_id) FROM patient_gold  -- WILL FAIL!
```

### Join Rules

- **`patient_id`**: FK in clinical tables (bp_log_gold, appointment_gold, careplan_gold, etc.) → links to `patient_tracker_gold.patient_id`
- **`res_id`**: FHIR resource ID - unique per record, NOT for joining patient data
- **`relatedperson_id`**: Links to relatedperson_gold for caregiver relationships
- **`encounter_id`**: Links clinical events within the same visit

---

## 1. Metric Definitions & Business Rules

| Business Term | Target Table | Required Conditions (SQL) |
|---|---|---|
| `total_patients` | `patient_tracker_gold` | `COUNT(DISTINCT patient_id) WHERE is_deleted = false` |
| `active_patient` | `patient_tracker_gold` | `is_deleted = false` |
| `screened_patient` | `patient_tracker_gold` | `is_screening = true AND is_deleted = false` |
| `diagnosed_patient` | `patient_tracker_gold` | `(is_diabetes_diagnosis = true OR is_htn_diagnosis = true) AND is_deleted = false` |
| `controlled_bp` | `bp_log_latest_gold` | `avg_systolic < 140 AND avg_diastolic < 90` |
| `uncontrolled_bp` | `bp_log_latest_gold` | `avg_systolic >= 140 OR avg_diastolic >= 90` |

## 2. Default Mandatory Filters

To ensure clinical data accuracy, the Code Agent MUST automatically append these filters:

- **`patient_tracker_gold`**: `WHERE is_deleted = false`
- **`patient_visit_gold`**: `WHERE is_src_deleted IS DISTINCT FROM 'true'` (is_src_deleted is VARCHAR)
- **`bp_log_gold`**: `WHERE is_src_deleted IS DISTINCT FROM 'true'` (is_src_deleted is VARCHAR)
- **`patient_gold`**: `WHERE res_deleted_at IS NULL`

## 3. Reusable SQL Metric Templates

- **Patient Count**: `SELECT COUNT(DISTINCT patient_id) FROM patient_tracker_gold WHERE is_deleted = false`
- **FHIR Resource Count**: `SELECT COUNT(DISTINCT res_id) FROM {table}_gold WHERE res_deleted_at IS NULL`
- **Cascade Stage Calculation**: `ROUND(100.0 * COUNT(CASE WHEN {condition} THEN 1 END) / NULLIF(COUNT(*), 0), 2)`
- **Trend/Time-Series Grouping**: `GROUP BY date_trunc('month', {time_column})`

## 4. Table Categories

### FHIR Resource Tables (use `res_id` as PK)
`patient_gold`, `encounter_gold`, `condition_gold`, `careplan_gold`, `appointment_gold`, `practitioner_gold`, `organization_gold`, `location_gold`, `medicationrequest_gold`, `medicationdispense_gold`, `medicationstatement_gold`, `diagnosticreport_gold`, `familymemberhistory_gold`, `coverage_gold`, `servicerequest_gold`, `questionnaireresponse_gold`

### Clinical Observation Tables (use `res_id` as PK, `patient_id` as FK)
`bp_log_gold`, `bp_log_latest_gold`, `glucose_log_gold`, `glucose_log_latest_gold`, `screening_log_gold`, `patient_*_gold` (comorbidity, complication, diagnosis, lifestyle, etc.)

### Operational Tables (use `patient_id` as identifier)
`patient_tracker_gold`, `call_register_admin_gold`

### Admin Reference Tables (use `id` as PK)
`*_admin_gold` tables (brand, category, classification, country, district, etc.)
