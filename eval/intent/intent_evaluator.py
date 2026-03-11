# eval/intent/intent_evaluator.py
import time
import logging
from typing import List, Dict

logger = logging.getLogger("eval.intent")

class IntentEvaluator:
    """
    Evaluates the IntentClassifier routing logic (Intent A vs B vs C).
    Matches expected intents from dataset against actual classifications.
    Also measures latency per classification.
    """
    def __init__(self, classifier_instance):
        """Pass an instance of backend.services.intent_router.IntentClassifier"""
        self.classifier = classifier_instance

    def evaluate_batch(self, queries: List[str], expected_intents: List[str]) -> Dict[str, float]:
        """
        Run IntentClassifier on a batch of queries and measure accuracy.
        """
        if len(queries) != len(expected_intents):
            raise ValueError("Query and expected_intent lists must have same length")

        correct = 0
        total_latency_ms = 0.0
        
        # Confusion matrix for intent routing (A, B, C)
        confusion_matrix = {
            "A": {"A": 0, "B": 0, "C": 0},
            "B": {"A": 0, "B": 0, "C": 0},
            "C": {"A": 0, "B": 0, "C": 0},
        }

        for query, expected in zip(queries, expected_intents):
            start = time.time()
            try:
                # Classify query
                result = self.classifier.classify(query=query, schema_context="")
                actual = result.intent
                
                # Check accuracy
                if actual == expected:
                    correct += 1
                else:
                    logger.warning(f"Routing Error: Query='{query[:40]}...' Expected={expected}, Got={actual}")
                
                # Record confusion matrix
                if expected in confusion_matrix and actual in confusion_matrix[expected]:
                    confusion_matrix[expected][actual] += 1
                    
            except Exception as e:
                logger.error(f"Classification failed for '{query[:40]}...': {e}")
                
            finally:
                latency = (time.time() - start) * 1000
                total_latency_ms += latency

        total_queries = len(queries)
        accuracy = correct / total_queries if total_queries > 0 else 0.0
        avg_latency = total_latency_ms / total_queries if total_queries > 0 else 0.0

        return {
            "accuracy": accuracy,
            "avg_latency_ms": avg_latency,
            "confusion_matrix": confusion_matrix
        }
