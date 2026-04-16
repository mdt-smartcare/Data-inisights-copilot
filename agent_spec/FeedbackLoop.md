---
description: "Continuous Learning & Feedback Loops"
version: 1.0.0
last_updated: 2026-03-31
---

# Continuous Learning & Feedback (FeedbackLoop.md)

This module operationalizes how the Copilot system learns from its mistakes over time. It establishes a closed-loop system where errors become prompt improvements.

## 1. Logging Infrastructure (Observability)

All SQL generation attempts are tracked via `Langfuse` and local logging protocols:
- **Captured State**:
  - Raw NL Query
  - Injected Schema Context
  - Initial Generated SQL
  - Validation Errors (if any syntax/logic checks trigger)
  - Final Corrected SQL (after Reflection loop)

## 2. The Learning Pipeline

When a query requires >1 `Reflection` iteration to fix, or fails database execution entirely:
1. **Identify the Failure Mode**: 
   - Was it a missing synonym? (e.g., user said "FBS" instead of "fasting blood sugar").
   - Was it a missing default filter?
   - Was it an invalid cross-table join?
2. **System Remediation Protocol**:
   - **Semantic Errors** → Manually append the new term to `backend/config/data_dictionary.yaml`.
   - **Join Errors** → Manually verify the foreign key constraints exist in the backend DB (this means the `SchemaGraph` is blind to it).
   - **Logic Structure Errors** → Create a new entry in `eval/sql_eval/golden_dataset.json` with the correct `ground_truth_sql` so `PromptBuilder` passes it as a Few-Shot example during runtime.

## 3. Code Agent Mandate

The Code Agent MUST utilize this feedback loop when implementing bug fixes or debugging failing RAG responses. If the user reports "The SQL returned active AND inactive patients", the agent MUST update `data_dictionary.yaml` rather than trying to hack the backend routing logic.
