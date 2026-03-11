# eval/intent/run_intent_eval.py
import argparse
import json
from pathlib import Path

import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger
from eval.intent.intent_evaluator import IntentEvaluator
from backend.services.intent_router import IntentClassifier
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

# Mock LLM for CI environments where we don't want to use real OpenAI calls
class MockIntentLLM(BaseChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        pass
        
    def invoke(self, input, config=None, **kwargs):
        return AIMessage(content='{"intent": "A", "sql_filter": null}')
        
    def with_structured_output(self, schema, **kwargs):
        # Return a lambda that returns a mock classification object
        class MockResult:
            def __init__(self, intent, sql_filter=None):
                self.intent = intent
                self.sql_filter = sql_filter
        
        # Simple heuristic mocker based on query keywords
        def mock_invoke(args):
            query = args.get("query", "").lower()
            if "notes" in query or "narrative" in query or "summary" in query:
                if ">" in query or "<" in query or "above" in query or "below" in query:
                     return MockResult("C", "SELECT id FROM test")
                return MockResult("B")
            return MockResult("A")
            
        return mock_invoke
    
    @property
    def _llm_type(self) -> str:
        return "mock"

def main():
    parser = argparse.ArgumentParser(description="Run Intent Router Evaluation on Golden Dataset")
    parser.add_argument("--dataset", type=str, required=True, help="Path to golden dataset JSON")
    parser.add_argument("--output", type=str, default="eval/reports/intent_results.json")
    parser.add_argument("--mock", action="store_true", help="Use heuristic mock instead of real LLM to test runner logic")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        golden_data = json.load(f)

    entries = golden_data["entries"]
    logger.info(f"Found {len(entries)} total queries for intent evaluation.")
    
    queries = [e["query"] for e in entries]
    expected_intents = [e["intent"] for e in entries]
    
    # Initialize the real or mock classifier
    if args.mock:
        logger.info("Using MOCK IntentClassifier for fast offline evaluation")
        classifier = IntentClassifier(llm=MockIntentLLM())
    else:
        logger.info("Using REAL IntentClassifier (requires API Key)")
        classifier = IntentClassifier()
        
    evaluator = IntentEvaluator(classifier_instance=classifier)
    metrics = evaluator.evaluate_batch(queries, expected_intents)
    
    logger.info("--- Intent Routing Metrics ---")
    logger.info(f"Accuracy: {metrics['accuracy']:.2%}")
    logger.info(f"Avg Latency: {metrics['avg_latency_ms']:.2f} ms")
    logger.info(f"Confusion Matrix (Expected row, Actual col):")
    for k, v in metrics['confusion_matrix'].items():
        logger.info(f"  Expected {k}: A={v['A']}, B={v['B']}, C={v['C']}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    logger.info(f"Intent evaluation saved to {output_path}")

if __name__ == "__main__":
    main()
