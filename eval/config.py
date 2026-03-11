"""
Shared configuration for the RAG Evaluation Framework.
Loads .env from project root and sets thresholds per metric.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────
# Path setup — ensure project root is on PYTHONPATH
# ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"

# Make sure backend imports work when running eval scripts standalone
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")

# ──────────────────────────────────────────────────────────
# Dataset paths
# ──────────────────────────────────────────────────────────
DATASETS_DIR = EVAL_DIR / "datasets"
GOLDEN_DATASET_PATH = DATASETS_DIR / "golden_dataset.json"
REPORTS_DIR = EVAL_DIR / "reports"

# ──────────────────────────────────────────────────────────
# LLM Provider for RAGAS evaluation
# ──────────────────────────────────────────────────────────
EVAL_LLM_MODEL = os.getenv("EVAL_LLM_MODEL", "gpt-4o-mini")   # cheaper for eval
EVAL_EMBEDDING_MODEL = os.getenv("EVAL_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ──────────────────────────────────────────────────────────
# Quality Thresholds (used by pytest pass/fail assertions)
# ──────────────────────────────────────────────────────────
THRESHOLDS = {
    # RAGAS metrics (scale: 0.0 – 1.0)
    "faithfulness":         0.75,   # Hallucination guard — LLM answers grounded in context
    "answer_relevancy":     0.70,   # How relevant is the answer to the question
    "context_precision":    0.65,   # Signal-to-noise in retrieved context
    "context_recall":       0.65,   # Did we retrieve all relevant info?

    # Retrieval metrics
    "hit_rate_at_5":        0.70,   # 70 % of queries find a relevant doc in top-5
    "mrr":                  0.60,   # Mean Reciprocal Rank
    "ndcg_at_5":            0.60,   # Normalized Discounted Cumulative Gain
    "precision_at_5":       0.50,   # Precision@5

    # Intent router
    "intent_accuracy":      0.90,   # 90 % routing accuracy expected
    "intent_latency_ms":    200,    # Max 200 ms per classification

    # SQL agent
    "sql_answer_accuracy":  0.80,   # % of SQL answers that are correct/expected
    "sql_latency_ms":       3000,   # Max 3s for SQL path

    # E2E pipeline (ROUGE-L)
    "rouge_l":              0.30,   # Minimum ROUGE-L vs ground truth answer
    "e2e_latency_ms":       8000,   # Max 8s end-to-end
}

# ──────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("eval")
