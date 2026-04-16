---
description: "Machine-Readable Schema Abstraction"
version: 1.0.0
last_updated: 2026-03-31
---

# Schema Definition & Abstraction (Schema.md)

This document provides a machine-readable abstraction of the core clinical database used by the Copilot. It ensures the Agent never hallucinates table structures or foreign key connections.

## Core Schema Structure

```yaml
tables:
  patient_tracker:
    description: "Core demographic and enrollment table for all patients."
    primary_key: "id"
    columns:
      id: int
      national_id: varchar
      name: varchar
      gender: varchar
      age: int
      site_id: int
      cvd_risk_level: varchar
      is_active: boolean
      is_deleted: boolean
      is_screened: boolean
      is_diabetes_diagnosed: boolean
      is_hypertension_diagnosed: boolean
      is_on_treatment: boolean
      is_bp_controlled: boolean

  site:
    description: "Healthcare facility location."
    primary_key: "id"
    columns:
      id: int
      name: varchar
      organization_id: int

  patient_visit:
    description: "Log of patient encounters and visits."
    primary_key: "id"
    columns:
      id: int
      patient_tracker_id: int
      visit_date: timestamp

  bp_log:
    description: "Blood pressure telemetric/visit logs."
    primary_key: "id"
    columns:
      id: int
      patient_tracker_id: int
      systolic: int
      diastolic: int
      bp_taken_at: timestamp

  screening_log:
    description: "Pre-diagnosis screening events."
    primary_key: "id"
    columns:
      id: int
      patient_tracker_id: int
      created_at: timestamp
```

## Validated Join Paths

The `SchemaGraph` service generates and validates these explicit paths. The Agent MUST NOT invent alternative join linkages.

- `patient_tracker` ↔ `site` : `patient_tracker.site_id = site.id`
- `patient_tracker` ↔ `patient_visit` : `patient_visit.patient_tracker_id = patient_tracker.id`
- `patient_tracker` ↔ `bp_log` : `bp_log.patient_tracker_id = patient_tracker.id`
- `patient_tracker` ↔ `screening_log` : `screening_log.patient_tracker_id = patient_tracker.id`
