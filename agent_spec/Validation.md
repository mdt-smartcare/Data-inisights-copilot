---
description: "Validation & Reliability Contract"
version: 1.0.0
last_updated: 2026-03-31
---

# Validation & Execution Reliability (Validation.md)

This module defines the required safeguards that intercept raw LLM outputs before they execute against databases. The `ReflectionService` handles these protocols.

## 1. Static Validation Checks

- **Table/Column Existence**: Parses the AST/Regex of the generated SQL and cross-references it against the active `SchemaGraph`. Outputs containing fictional tables fail immediately without LLM interaction.
- **Join Validity**: Cross-references the `JOIN ... ON` statements against known `SchemaGraph` Foreign Key linkages. 
- **Operation Safety**: Blocks all write-operations. Identifies and blocks subqueries attempting to mutate state via functions.

## 2. Logical Validation Checks

- **Aggregation Correctness**: Validates that any query containing an aggregate function (e.g., `COUNT`, `SUM`) also successfully outputs a `GROUP BY` clause containing all non-aggregated columns in the `SELECT` statement.
- **Filter Compliance Check**: Scans the `WHERE` clause to ensure `is_active` and `is_deleted` default parameters from the Data Dictionary were not omitted.

## 3. Execution Validation (Dry-Run)

Before passing SQL to the primary execution pool:
- The `ReflectionService` appends `LIMIT 0` to the query.
- It executes the query to validate database-level syntax and type-casting.
- If it fails, the database error message is captured, packaged into a constraint loop via `PromptBuilder.build_fix_prompt()`, and sent back to the LLM for self-correction.
