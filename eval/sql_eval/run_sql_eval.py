# eval/sql_eval/run_sql_eval.py
"""
SQL Evaluation Runner — End-to-end evaluation of the schema-aware SQL pipeline.

Modes:
  --mode schema-only  : Offline schema-compliance scoring (no DB or LLM needed)
  --mode live         : Full pipeline: NL → SQL via SQLService → execution → evaluation
  --mode mock         : Simulated evaluation for CI/CD testing

Usage:
  python -m eval.sql_eval.run_sql_eval --dataset eval/sql_eval/golden_dataset.json --mode schema-only
  python -m eval.sql_eval.run_sql_eval --dataset eval/sql_eval/golden_dataset.json --mode live --db-url postgresql://...
"""
import argparse
import json
import sys
import time
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger, THRESHOLDS
from eval.sql_eval.sql_evaluator import SQLEvaluator


def load_golden_dataset(path: str) -> list:
    """Load and validate golden dataset entries."""
    dataset_path = Path(path)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        sys.exit(1)
    
    with open(dataset_path, "r") as f:
        data = json.load(f)
    
    entries = data.get("entries", [])
    logger.info(f"Loaded {len(entries)} entries from {dataset_path.name} (v{data.get('version', '?')})")
    return entries


def run_schema_only(entries: list, output_path: str):
    """
    Schema-compliance-only evaluation.
    
    Uses ground_truth_sql as both generated and expected SQL.
    This mode validates the golden dataset itself and the scoring logic.
    """
    evaluator = SQLEvaluator(db_engine=None)
    
    # Inject ground_truth_sql as generated_sql for self-scoring
    for entry in entries:
        entry["generated_sql"] = entry.get("ground_truth_sql", "")
    
    metrics = evaluator.evaluate_batch(entries)
    _report_and_save(metrics, output_path, mode="schema-only")


def run_live(entries: list, db_url: str, output_path: str):
    """
    Full live evaluation: NL question → SQLService → SQL → execute → compare.
    
    Requires:
    - Active database connection
    - Backend services initialized
    """
    from sqlalchemy import create_engine
    
    logger.info(f"Connecting to test DB: {db_url}")
    engine = create_engine(db_url)
    evaluator = SQLEvaluator(db_engine=engine)
    
    # Generate SQL for each entry using the live pipeline
    try:
        from backend.services.sql_service import SQLService
        sql_service = SQLService(database_url=db_url)
        logger.info("SQLService initialized for live evaluation")
    except Exception as e:
        logger.error(f"Failed to initialize SQLService: {e}")
        logger.info("Falling back to schema-only mode")
        run_schema_only(entries, output_path)
        return
    
    total_latency_ms = 0
    
    for i, entry in enumerate(entries):
        question = entry.get("query", "")
        logger.info(f"[{i+1}/{len(entries)}] Generating SQL for: {question[:60]}...")
        
        try:
            start = time.time()
            generated_sql = sql_service._generate_sql(question)
            latency_ms = (time.time() - start) * 1000
            total_latency_ms += latency_ms
            
            entry["generated_sql"] = generated_sql
            entry["generation_latency_ms"] = round(latency_ms, 2)
            
            logger.info(f"  SQL ({latency_ms:.0f}ms): {generated_sql[:100]}...")
        except Exception as e:
            logger.error(f"  Generation failed: {e}")
            entry["generated_sql"] = ""
            entry["generation_error"] = str(e)
    
    metrics = evaluator.evaluate_batch(entries)
    
    # Add latency metrics
    valid_latencies = [e.get("generation_latency_ms", 0) for e in entries if e.get("generated_sql")]
    if valid_latencies:
        metrics["latency"] = {
            "avg_ms": round(sum(valid_latencies) / len(valid_latencies), 2),
            "p50_ms": round(sorted(valid_latencies)[len(valid_latencies) // 2], 2),
            "p95_ms": round(sorted(valid_latencies)[int(len(valid_latencies) * 0.95)], 2),
            "total_ms": round(total_latency_ms, 2),
        }
    
    _report_and_save(metrics, output_path, mode="live")


def run_mock(entries: list, output_path: str):
    """
    Mock evaluation for CI/CD testing.
    Uses ground_truth_sql with minor modifications to simulate agent output.
    """
    evaluator = SQLEvaluator(db_engine=None)
    
    for entry in entries:
        gt_sql = entry.get("ground_truth_sql", "")
        # Simulate agent: use GT SQL but add harmless alias changes
        entry["generated_sql"] = gt_sql.replace("AS patient_count", "AS total")
    
    metrics = evaluator.evaluate_batch(entries)
    _report_and_save(metrics, output_path, mode="mock")


def _report_and_save(metrics: dict, output_path: str, mode: str):
    """Print summary and save detailed results."""
    logger.info("=" * 70)
    logger.info(f"SQL EVALUATION REPORT ({mode} mode)")
    logger.info("=" * 70)
    
    logger.info(f"Total Queries:             {metrics.get('total_queries', 0)}")
    logger.info(f"Execution Equivalence:     {metrics.get('execution_equivalence_rate', 0):.1%}")
    logger.info(f"Overall Score:             {metrics.get('avg_overall_score', 0):.1%}")
    
    sc = metrics.get("schema_compliance", {})
    logger.info(f"  Table Accuracy:          {sc.get('avg_table_accuracy', 0):.1%}")
    logger.info(f"  Join Correctness:        {sc.get('avg_join_correctness', 0):.1%}")
    logger.info(f"  Filter Compliance:       {sc.get('avg_filter_compliance', 0):.1%}")
    logger.info(f"  Aggregation Match:       {sc.get('avg_aggregation_match', 0):.1%}")
    
    by_diff = metrics.get("by_difficulty", {})
    if by_diff:
        logger.info("\n  By Difficulty:")
        for diff, data in by_diff.items():
            logger.info(f"    {diff:>8s}: {data['count']} queries, avg_score={data['avg_score']:.1%}")
    
    latency = metrics.get("latency")
    if latency:
        logger.info(f"\n  Latency: avg={latency['avg_ms']:.0f}ms, p50={latency['p50_ms']:.0f}ms, p95={latency['p95_ms']:.0f}ms")
    
    # Check thresholds
    threshold = THRESHOLDS.get("sql_answer_accuracy", 0.80)
    score = metrics.get("avg_overall_score", 0)
    if score >= threshold:
        logger.info(f"\n✅ PASS: Overall score {score:.1%} >= threshold {threshold:.1%}")
    else:
        logger.warning(f"\n❌ FAIL: Overall score {score:.1%} < threshold {threshold:.1%}")
    
    # Save results
    # Remove individual results from saved metrics to keep output clean
    save_metrics = {k: v for k, v in metrics.items() if k != "individual_results"}
    save_metrics["mode"] = mode
    
    # Save failures for debugging
    failures = [r for r in metrics.get("individual_results", []) if r.get("overall_score", 0) < 0.8]
    if failures:
        save_metrics["failures"] = [
            {
                "id": f.get("id"),
                "query": f.get("query"),
                "score": f.get("overall_score"),
                "issues": f.get("schema_compliance", {}).get("issues", []),
                "generated_sql": f.get("generated_sql", "")[:300],
            }
            for f in failures
        ]
    
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(save_metrics, f, indent=2, default=str)
    
    logger.info(f"\nDetailed results saved to {output}")


def main():
    parser = argparse.ArgumentParser(description="SQL Pipeline Evaluation")
    parser.add_argument("--dataset", type=str, default="eval/sql_eval/golden_dataset.json",
                        help="Path to golden dataset JSON")
    parser.add_argument("--db-url", type=str, default=None,
                        help="SQLAlchemy URL to the test database (required for --mode live)")
    parser.add_argument("--output", type=str, default="eval/reports/sql_results.json")
    parser.add_argument("--mode", type=str, choices=["schema-only", "live", "mock"],
                        default="schema-only",
                        help="Evaluation mode: schema-only (offline), live (full pipeline), mock (CI/CD)")
    args = parser.parse_args()

    entries = load_golden_dataset(args.dataset)
    
    if args.mode == "live":
        if not args.db_url:
            logger.error("--db-url is required for live mode")
            sys.exit(1)
        run_live(entries, args.db_url, args.output)
    elif args.mode == "mock":
        run_mock(entries, args.output)
    else:
        run_schema_only(entries, args.output)


if __name__ == "__main__":
    main()
