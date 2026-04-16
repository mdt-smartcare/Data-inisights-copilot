---
description: "Core Agent & Orchestration Contract"
version: 1.1.0
last_updated: 2026-03-31
---

# Core Agent & Orchestration (Agent.md)

This module defines the overarching system behavior, constraints, and optimization techniques for the Data Insights Copilot. 

## 1. End-To-End Pipeline
The SQL generation agent operates on a strict multi-stage deterministic pipeline:
`NL Query → SchemaLinker (Intent/Schema Map) → QueryPlanner (Logical Plan) → PromptBuilder (SQL Gen) → ReflectionService (Validator) → Executor`

## 2. Core Constraints
- **Scope Restriction**: The agent is restricted to read-only queries. Operations modifying states (`INSERT`, `UPDATE`, `DELETE`) are strictly prohibited at the system prompt level and the execution level.
- **Default Scoping**: The agent MUST apply mandatory default filters defined in `DataDictionary.md` unless directly overridden by the user.

## 3. Sub-Agent Orchestration
- **Intent Router**: Determines query complexity (`A`=SQL, `B`=Vector, `C`=Hybrid) to route to the correct agent pipeline.
- **Schema Linker**: Extracts exactly which tables and columns are required.
- **Query Planner**: Structurally designs `GROUP BY` and metric logic before generation.
- **Reflection Validator**: Intercepts generated SQL, executes `LIMIT 0` dry runs, and checks Graph dependencies before passing to Executor.

## 4. Optimization Techniques
- **Token Optimization**: Never inject `get_table_info()` (full database schema) into the context window. Only inject `SchemaLinker` subsets.
- **Parallelization**: Tasks outside real-time chat (e.g., Vector DB syncing, embedding backfills) are pushed to Celery distributed workers.
- **Memory Persistence**: The workflow maintains long-term memory via the `golden_dataset.json` (few-shot memory) and `data_dictionary.yaml` (semantic memory).

*(See adjacent files in this specification module for detailed data, prompting, validation, and feedback rules.)*
