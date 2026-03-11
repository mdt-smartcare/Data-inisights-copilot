# eval/retrieval/run_retrieval_eval.py
import argparse
import json
from pathlib import Path

import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger
from eval.retrieval.retrieval_evaluator import RetrievalEvaluator

def main():
    parser = argparse.ArgumentParser(description="Run Retrieval Evaluation on Golden Dataset")
    parser.add_argument("--dataset", type=str, required=True, help="Path to golden dataset JSON")
    parser.add_argument("--output", type=str, default="eval/reports/retrieval_results.json")
    parser.add_argument("--k", type=int, default=5, help="Top-K cutoff for metrics (Hit Rate, Precision)")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        golden_data = json.load(f)

    # We only run Retrieval on Intent B (Vector RAG)
    rag_entries = [entry for entry in golden_data["entries"] if entry["intent"] == "B"]
    
    logger.info(f"Found {len(rag_entries)} Intent B (Vector RAG) entries in dataset.")
    
    # In a real scenario, run the `AdvancedRAGRetriever` here to get returned doc IDs
    # For now, we mock the results to demonstrate evaluation flow
    logger.info("Fetching retrieved document IDs from vector store... (Mocked for demonstration)")
    
    expected_docs = []
    retrieved_docs_mock = []
    
    for entry in rag_entries:
        expected = entry.get("relevant_doc_ids", [])
        expected_docs.append(expected)
        
        # Mocking retrieval: randomly deciding if we "hit" the expected doc
        if len(expected) > 0:
            import random
            # 70% chance to put the first expected doc in the top 3 results
            hit = random.random() < 0.7
            if hit:
                # Insert expected doc at a random rank between 0 and 2
                rank = random.randint(0, min(2, args.k-1))
                mock_res = [f"irrelevant_doc_{i}" for i in range(args.k)]
                mock_res[rank] = expected[0]
                retrieved_docs_mock.append(mock_res)
            else:
                retrieved_docs_mock.append([f"missed_doc_{i}" for i in range(args.k)])
        else:
            retrieved_docs_mock.append([])
    
    evaluator = RetrievalEvaluator()
    metrics = evaluator.evaluate(retrieved_docs_mock, expected_docs, k=args.k)
    
    logger.info("--- Retrieval Metrics ---")
    for k, v in metrics.items():
        logger.info(f"{k}: {v:.4f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    logger.info(f"Retrieval evaluation saved to {output_path}")

if __name__ == "__main__":
    main()
