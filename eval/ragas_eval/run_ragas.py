# eval/ragas_eval/run_ragas.py
import argparse
import json
import asyncio
from pathlib import Path

# Add project root to sys path
import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger
from eval.ragas_eval.ragas_evaluator import RagasEvaluator

def main():
    parser = argparse.ArgumentParser(description="Run RAGAS Evaluation on Golden Dataset")
    parser.add_argument("--dataset", type=str, required=True, help="Path to golden dataset JSON")
    parser.add_argument("--output", type=str, default="eval/reports/ragas_results.json")
    parser.add_argument("--mock", action="store_true", help="Use mock evaluation (no API calls)")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        golden_data = json.load(f)

    # We only run RAGAS on Intent B (Vector RAG) and Intent C (Hybrid)
    # Intent A (SQL) does not use unstructured context retrieval, so RAGAS is not applicable.
    rag_entries = [entry for entry in golden_data["entries"] if entry["intent"] in ["B", "C"]]
    
    logger.info(f"Found {len(rag_entries)} RAG/Hybrid entries in dataset.")
    
    # In a real run, we would call the RAG pipeline here to get `answers` and `contexts`.
    # For now, we mock the retrieval outputs to demonstrate the execution pattern.
    logger.info("Fetching answers and contexts from RAG pipeline... (Mocked for demonstration)")
    
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    
    for entry in rag_entries:
        questions.append(entry["query"])
        # Mocking the pipeline output
        answers.append(f"Mocked answer for: {entry['query']} based on {entry.get('expected_answer_contains', [''])[0]}")
        contexts.append(["Mock context document 1 related to query.", "Mock context document 2 providing details."])
        ground_truths.append(entry.get("ground_truth_hint", ""))

    if not questions:
        logger.warning("No Intent B/C entries found to evaluate.")
        return

    evaluator = RagasEvaluator(use_mock=args.mock)
    
    try:
        results = evaluator.evaluate_batch(
            questions=questions,
            answers=answers,
            contexts=contexts,
            ground_truths=ground_truths
        )
        
        # Convert Ragas Dataset output to dictionary for JSON serialization
        results_dict = dict(results) if not args.mock else results
        
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(results_dict, f, indent=2)
            
        logger.info(f"Evaluations saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to run RAGAS: {e}")

if __name__ == "__main__":
    main()
