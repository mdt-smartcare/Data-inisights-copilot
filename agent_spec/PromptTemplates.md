---
description: "Prompting & Context Engineering Rules"
version: 1.0.0
last_updated: 2026-03-31
---

# Prompt Templates & Context Policy (PromptTemplates.md)

This document standardizes how prompts are programmatically assembled via `PromptBuilder.py` to ensure token-efficient and reproducible SQL generation.

## 1. Modular Prompt Assembly

Prompts are never static. They are dynamically concatenated blocks:
1. **Instruction Block**: Dialect assignment (`PostgreSQL` vs `DuckDB`) and strict constraints.
2. **Schema Block**: Targeted injection of tables/columns matched by `SchemaLinker`.
3. **Plan Block**: The structured `QueryPlan` generated in the preliminary stage.
4. **Dictionary Block**: Default filters and term resolutions from `DataDictionary.yaml`.
5. **Few-Shot Examples Block**: Query-type matched examples from the `golden_dataset.json`.

## 2. Context Retrieval Strategies (Token Optimization)

- **Do NOT** embed raw `CREATE TABLE` statements for the entire database.
- **Top-K Retrieval**: The Agent matches the NL question to entities, restricting the injected schema to only those tables + 1 hop across foreign keys.
- **Semantic Limits**: Irrelevant columns (e.g., auditing timestamps, sync hashes) should be stripped from the prompt schema output unless explicitly requested.

## 3. Dynamic Prompt Rules

- **PostgreSQL**: Instruct the LLM to use `ILIKE` for case-insensitive matches and `date_trunc()` for time grouping.
- **DuckDB**: Instruct the LLM to use DuckDB-specific JSON extraction methods or exact CSV parsing syntax.
- **Zero-Hallucination Mandate**: The prompt absolutely mandates `"DO NOT USE TABLES OR COLUMNS NOT LISTED IN THE SCHEMA BLOCK."`
