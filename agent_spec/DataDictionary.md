---
description: "Business Semantics and Data Dictionary"
version: 1.0.0
last_updated: 2026-03-31
---

# Business Semantics & Data Dictionary (DataDictionary.md)

This contract defines the business semantics connecting natural language queries to structural database constraints.

> **Source of Truth**: The active configuration is stored and executed from `backend/config/data_dictionary.yaml`. This document defines the theoretical structure and standards.

## 1. Metric Definitions & Business Rules

| Business Term | Target Table | Required Conditions (SQL) |
|---|---|---|
| `active_patient` | `patient_tracker` | `is_active = true AND is_deleted = false` |
| `screened_patient` | `patient_tracker` | `is_screened = true` |
| `diagnosed_patient` | `patient_tracker` | `is_diabetes_diagnosed = true OR is_hypertension_diagnosed = true` |
| `treatment_patient`| `patient_tracker` | `is_on_treatment = true` |
| `controlled_bp` | `patient_tracker` | `is_bp_controlled = true` |

## 2. Default Mandatory Filters

To ensure clinical data accuracy, the Code Agent MUST automatically append these filters to any query touching the specified tables unless explicitly instructed otherwise:

- **`patient_tracker`**: `WHERE is_active = true AND is_deleted = false`
- **`patient_visit`**: `WHERE is_active = true AND is_deleted = false`
- **`bp_log`**: `WHERE is_active = true AND is_deleted = false`

## 3. Reusable SQL Metric Templates

- **Demographic Count**: `SELECT COUNT(DISTINCT patient_tracker_id) ...`
- **Cascade Stage Calculation (Percentage)**: `ROUND(100.0 * COUNT(CASE WHEN {condition} THEN 1 END) / NULLIF(COUNT(*), 0), 2)`
- **Trend/Time-Series Grouping**: `GROUP BY date_trunc('month', {time_column})`
