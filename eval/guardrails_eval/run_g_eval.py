# eval/guardrails_eval/run_g_eval.py
import argparse
import json
import logging
from pathlib import Path
import asyncio

import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger
from eval.guardrails_eval.g_evaluator import GEvaluator

async def async_main():
    parser = argparse.ArgumentParser(description="Run G-Eval Clinical Guardrails Evaluation")
    parser.add_argument("--dataset", type=str, required=True, help="Path to golden dataset JSON")
    parser.add_argument("--output", type=str, default="eval/reports/guardrail_results.json")
    parser.add_argument("--mock", action="store_true", help="Use mock evaluation (no API calls)")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        golden_data = json.load(f)

    # We only care about Hybrid and Vector routes for clinical safety,
    # as SQL usually just returns numeric aggregations.
    rag_entries = [entry for entry in golden_data["entries"] if entry["intent"] in ["B", "C"]]
    
    # Pick a few to evaluate
    sample_queries = rag_entries[:5]
    queries = [e["query"] for e in sample_queries]
    
    if args.mock:
        logger.info("Using MOCK Agent Responses for G-Eval...")
        answers = [
            f"Based on the notes, the patient has hypertension. (Simulated answer for: {q})" 
            for q in queries
        ]
        # Inject one explicitly unsafe answer to test the evaluator
        if len(answers) > 1:
            answers[1] = "You have high blood pressure. You should immediately start taking 10mg of Amlodipine daily and stop eating salt."
    else:
        logger.info("Fetching real Agent Responses...")
        try:
            from backend.services.agent_service import AgentService
            agent = AgentService()
            answers = []
            for q in queries:
                res = await agent.process_query(q)
                answers.append(res.get("answer", ""))
        except Exception as e:
            logger.error(f"Failed to run real AgentService: {e}")
            logger.info("Run with --mock to test evaluator logic independently.")
            return

    evaluator = GEvaluator(use_mock=args.mock)
    
    logger.info(f"Running Clinical Safety G-Eval on {len(queries)} agent responses...")
    metrics = evaluator.evaluate_batch(queries, answers)
    
    logger.info("--- Clinical Safety Metrics ---")
    logger.info(f"Average Safety Score (1-5): {metrics['avg_safety_score']:.2f}")
    logger.info(f"Compliance Pass Rate: {metrics['pass_rate']:.2%}")
    logger.info(f"Total Violations: {metrics['violations']}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    logger.info(f"Guardrail evaluation saved to {output_path}")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
