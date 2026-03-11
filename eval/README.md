# Data Insights Copilot — RAG Evaluation Framework

This folder contains a comprehensive evaluation suite for testing the health, maturity, and accuracy of the Data Insights Copilot's generation and retrieval pipelines.

## Prerequisites

All scripts should be executed from the **project root** inside the `fhir_rag_env` conda environment:

```bash
conda activate fhir_rag_env
pip install -r eval/requirements-eval.txt
```

⚠️ **Important:** The core `RAGAS` evaluation requires an OpenAI API key. Ensure `OPENAI_API_KEY` is present in the `.env` file at the project root before running RAGAS metrics.

## Data Sources
The evaluation runs entirely on local, seeded data to prevent mutating production environments. 
* **Evaluation Queries:** `eval/datasets/golden_dataset.json` (40 seeded Q&A pairs covering SQL, Vector, and Hybrid).
* **Test SQL Database:** `backend/data/clinical_data.db` (Local SQLite instances used to test DataFrame equivalence).
* **Test Vector Database:** Local ChromaDB or Qdrant collection configured in `backend/.env`.

## The Evaluation Pipelines

We evaluate the system across 4 distinct pillars:

### 1. Intent Router Evaluation (`eval/intent/run_intent_eval.py`)
Tests if queries are correctly routed to the SQL Agent (A), Vector RAG (B), or Hybrid Workflow (C).
- **Metrics:** Routing Accuracy (%), Latency per classification (ms), Confusion Matrix.
- **Costs:** Fast & Cheap (uses cached classification rules / cheap LLM calls).

### 2. Retrieval Evaluation (`eval/retrieval/run_retrieval_eval.py`)
Tests the vector database's capacity to find the right chunk without involving LLM generation.
- **Metrics:** Hit Rate@K, MRR@K (Mean Reciprocal Rank), Precision@K.
- **Costs:** Free (Vector similarity search only, no LLM calls).

### 3. RAGAS Evaluation (`eval/ragas_eval/run_ragas.py`)
Uses LLM-as-a-judge (via the `ragas` library) to evaluate the actual generative responses of the RAG pipeline.
- **Metrics:** Faithfulness (Anti-Hallucination), Answer Relevancy, Context Precision, Context Recall.
- **Costs:** High (requires multiple LLM calls per query to evaluate the generated output against context).

### 4. SQL Execution Equivalence (`eval/sql_eval/run_sql_eval.py`)
Tests Text-to-SQL logic by executing both the Generated SQL and the Ground Truth SQL against a test database and comparing their mathematical logic (`pandas.DataFrame.equals`).
- **Metrics:** SQL Generative Accuracy (% equivalent), Passed count, Failed count.
- **Costs:** Low (Local DB execution).

### 5. Custom G-Eval: Clinical Guardrails (`eval/guardrails_eval/run_g_eval.py`)
Uses LLM-as-a-judge with a custom strict rubric to ensure the agent is not hallucinating medical advice or prescribing treatments.
- **Metrics:** Average Safety Score (1-5), Compliance Pass Rate, Total Violations.
- **Costs:** High (Requires API Key).

### 6. End-to-End Evaluation (`eval/pipeline/run_e2e_eval.py`)
Runs the full Agent logic on a subset of the golden dataset.
- **Metrics:** Total pipeline latency, ROUGE-L similarity vs baseline expected answers.
- **Costs:** Moderate.

---

## How to Run

You can run individual evaluators as needed:

# 1. Run Retrieval Eval (Vector DB search only - no API costs)
python eval/retrieval/run_retrieval_eval.py --dataset eval/datasets/golden_dataset.json

# 2. Run Intent Eval (Uses actual OpenAI API for routing classification)
python eval/intent/run_intent_eval.py --dataset eval/datasets/golden_dataset.json

# 3. Run RAGAS (Uses actual OpenAI API to evaluate generative quality)
python eval/ragas_eval/run_ragas.py --dataset eval/datasets/golden_dataset.json

# 4. Run SQL Execution Equivalence (Requires a test DB connection string)
python eval/sql_eval/run_sql_eval.py --dataset eval/datasets/golden_dataset.json --mock

# 5. Run G-Eval Clinical Guardrails (Uses actual OpenAI API for grading safety)
python eval/guardrails_eval/run_g_eval.py --dataset eval/datasets/golden_dataset.json

# 6. Run E-to-E Agent Eval (Uses actual AgentService, DB, and LLM)
python eval/pipeline/run_e2e_eval.py --dataset eval/datasets/golden_dataset.json

# Note: You can pass `--mock` to any of the scripts (except retrieval) to run isolated tests without hitting your OpenAI API key or backend connections.

Generate the consolidated report (Requires outputs from above):
```bash
python eval/reports/generate_report.py
```
Open `eval/reports/latest_report.html` in your browser.

## CI/CD Pytest Integration

Mocked eval suites have been wrapped in `pytest` to ensure they can be executed during CI without API costs:

```bash
pytest backend/tests/eval/ -v
```

---

## Latest Evaluation Results (March 11, 2026)
Below are the baseline metrics captured across the test databases and the Golden Dataset:

- **1. Retrieval Performance:** 
  - **Hit Rate @ 5:** `80.0%`
  - **Mean Reciprocal Rank (MRR @ 5):** `0.44`
- **2. Intent Routing Accuracy:** `72.5%` (Avg Latency: ~155ms)
- **3. SQL Generative Accuracy:** `80.0%` (Execution Equivalence)
- **4. Clinical Safety Guardrails:** `100% Pass Rate` (Average Agent Safety Score: 4.5/5)
- **5. RAGAS Generative Quality:** *(Requires production OpenAI Key to evaluate)*
- **6. End-to-End Pipeline Performance:** 
  - **Total Latency:** `~501ms` 
  - **Response ROUGE-L:** `0.28`
