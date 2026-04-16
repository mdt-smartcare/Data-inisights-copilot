---
description: "Evaluation Metrics & Benchmarking"
version: 1.0.0
last_updated: 2026-03-31
---

# System Evaluation & Benchmarking (Evaluation.md)

To prevent regression, the Code Agent and modifications must be evaluated against standard metrics defined in `eval/sql_eval/sql_evaluator.py`.

## 1. Evaluated Metrics

1. **Schema Compliance (Weight: 60%)**
   - *Table Accuracy*: Measures if the LLM selected the correct base tables.
   - *Join Correctness*: Measures if the `JOIN` syntax matches known `SchemaGraph` paths.
   - *Filter Compliance*: Measures whether business rules (e.g., `is_active = true`) were included.
   - *Aggregation Match*: Measures if the correct mathematical intent (`COUNT`, `ROUND`, etc.) was met.

2. **Execution Equivalence (Weight: 40%)**
   - Compares the `pd.DataFrame` output of the generated SQL against the `pd.DataFrame` of the `ground_truth_sql`.

## 2. Benchmark Datasets

The operational benchmark dataset lives at `eval/sql_eval/golden_dataset.json`. 
It contains curated NL → SQL pairs split by difficulty:
- **Easy**: Direct lookups, single table counts.
- **Medium**: Time-series (`date_trunc`), single-hop joins.
- **Hard**: Care cascades, multi-table hierarchical joins (e.g., `glucose_log` → `patient_tracker` → `site` → `organization`), complex case aggregations.

## 3. Acceptance Criteria

- Code changes modifying the generation pipeline must maintain a **>80% Overall Schema Compliance Score**.
- Agent updates must not increase latency (`generation_latency_ms`) beyond the p95 thresholds recorded in previous `eval/reports/sql_results.json` checkpoints.
