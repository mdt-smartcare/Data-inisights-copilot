# RAG Evaluation Framework Guide

The **Data Insights Copilot** includes a standalone evaluation suite located in the `eval/` directory. It evaluates the generative and retrieval capabilities of the hybrid pipeline across SQL and Vector data paths.

## Architecture

The framework consists of four main evaluation pillars:

1. **RAGAS Evaluator (`eval/ragas_eval/`)**
   - **What it does:** Uses LLM-as-a-judge (via OpenAI) to score the generative text output.
   - **Metrics:** Faithfulness, Answer Relevancy, Context Precision, Context Recall.
   - **Cost:** High (Requires API Key).

2. **Retrieval Evaluator (`eval/retrieval/`)**
   - **What it does:** Scores the underlying Vector DB (Chroma/Qdrant) searching capabilities.
   - **Metrics:** Hit Rate@K, MRR@K, Precision@K.
   - **Cost:** Free (Pure DB search).

3. **Intent Evaluator (`eval/intent/`)**
   - **What it does:** Scores the accuracy of the Pydantic structured intent classifier (A/B/C routing).
   - **Metrics:** Accuracy %, Latency ms, Confusion Matrix.
   - **Cost:** Low.

4. **SQL Execution Equivalence Evaluator (`eval/sql_eval/`)**
   - **What it does:** Tests text-to-SQL intent accuracy by executing generated SQL strings against a database and asserting equivalence of the output `pandas.DataFrames`. This bypasses strict string matching logic (e.g. "150 patients" vs "count is 150").
   - **Metrics:** SQL Generative Accuracy, Equivalent Count.
   - **Cost:** Free (Local DB queries).

5. **G-Eval Clinical Guardrails (`eval/guardrails_eval/`)**
   - **What it does:** Uses LLM-as-a-judge with a structured grading rubric to evaluate if the agent is hallucinating dangerous medical advice versus safely summarizing context.
   - **Metrics:** Average Safety Score (1-5), Compliance Pass Rate.
   - **Cost:** High (Requires API Key).

6. **End-to-End Pipeline Evaluator (`eval/pipeline/`)**
   - **What it does:** Evaluates the `AgentService` response logic end-to-end using ROUGE-L similarity against expected baseline answers.
   - **Metrics:** ROUGE-L, Total Latency.
   - **Cost:** Moderate.

## Data Sources & The Golden Dataset

Evaluations are powered by the **Golden Dataset** (`eval/datasets/golden_dataset.json`). 

It contains 40 realistic Q&A pairs categorized by intent:
- **Intent A (SQL):** Aggregations, counts, statistical queries.
- **Intent B (Vector):** Clinical note lookups, narrative summaries.
- **Intent C (Hybrid):** SQL filtering combined with Vector semantic search.

This dataset runs against your local environments:
- **Test Relational DB:** `backend/data/clinical_data.db` (For SQL Equivalence checks).
- **Test Vector DB:** Your local ChromaDB or Qdrant index (For Retrieval hit rates).

*Tip: Before running retrieval metrics on actual data, ensure the `relevant_doc_ids` in the golden dataset match actual keys in your Chroma/Qdrant instance.*

## Using the Framework

Run evaluations from the project root inside the Conda environment.

```bash
# Activate Environment
conda activate fhir_rag_env
pip install -r eval/requirements-eval.txt

# Run an evaluator with the actual OpenAI API (Real execution)
python eval/intent/run_intent_eval.py --dataset eval/datasets/golden_dataset.json
python eval/ragas_eval/run_ragas.py --dataset eval/datasets/golden_dataset.json

# Note: You can pass `--mock` to run isolated logic tests without hitting backend APIs or incurring costs
python eval/pipeline/run_e2e_eval.py --dataset eval/datasets/golden_dataset.json --mock

# Generate the consolidated HTML Dashboard
python eval/reports/generate_report.py
```

## Continuous Integration (pytest)

The evaluation math and runner logic is integration-tested using pytest (with mocked LLMs). Run checks using:

```bash
pytest backend/tests/eval/ -v
```

Thresholds (e.g., minimum 0.70 Hit Rate) are configured centrally in `eval/config.py`.
