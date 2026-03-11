# eval/pipeline/run_e2e_eval.py
import argparse
import json
import asyncio
from pathlib import Path

import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger
from eval.pipeline.e2e_evaluator import EndToEndEvaluator

async def async_main():
    parser = argparse.ArgumentParser(description="Run End-to-End Evaluation on Golden Dataset")
    parser.add_argument("--dataset", type=str, required=True, help="Path to golden dataset JSON")
    parser.add_argument("--output", type=str, default="eval/reports/e2e_results.json")
    parser.add_argument("--mock", action="store_true", help="Use mock agent response (fast testing)")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        golden_data = json.load(f)

    # Pick a small subset of queries for E2E eval to avoid long runtimes
    # e.g., First 2 SQL, First 2 Vector, First 2 Hybrid
    entries = golden_data["entries"]
    sample_queries = []
    
    seen_intents = {"A": 0, "B": 0, "C": 0}
    for e in entries:
        if seen_intents.get(e["intent"], 0) < 2:
            sample_queries.append(e)
            seen_intents[e["intent"]] += 1

    queries = [e["query"] for e in sample_queries]
    expected_answers = [e.get("ground_truth_hint", "") for e in sample_queries]

    if args.mock:
        logger.info("Using MOCK AgentService to simulate E2E testing...")
        class MockAgent:
            async def process_query(self, query, session_id=None):
                await asyncio.sleep(0.5) # Simulate API latency
                # Provide a mocked string that partially matches ground truth for ROUGE score testing
                mock_ans = f"This is a simulated agent response addressing: {query}. It contains partial truth."
                return {"answer": mock_ans, "trace_id": "mock_trace_123"}
                
        agent_service = MockAgent()
    else:
        logger.info("Initializing REAL AgentService (will require DB and Vector Store connections)")
        try:
            from backend.services.agent_service import AgentService
            agent_service = AgentService()
        except Exception as e:
            logger.error(f"Failed to initialize AgentService: {e}")
            logger.info("Run with --mock flag to test evaluation runner without a full backend setup.")
            return

    evaluator = EndToEndEvaluator(agent_service)
    
    logger.info(f"Running E2E pipeline for {len(queries)} sample queries...")
    metrics = await evaluator.evaluate_batch(queries, expected_answers)
    
    logger.info("--- E2E Pipeline Metrics ---")
    logger.info(f"Average ROUGE-L (F1): {metrics['avg_rouge_l']:.4f}")
    logger.info(f"Average Latency: {metrics['avg_latency_ms']:.2f} ms")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    logger.info(f"E2E evaluation saved to {output_path}")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
