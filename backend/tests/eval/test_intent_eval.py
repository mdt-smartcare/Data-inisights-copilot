import pytest
from eval.intent.intent_evaluator import IntentEvaluator
from backend.services.intent_router import IntentClassifier, IntentClassification

class MockClassifierForTest:
    def classify(self, query: str, schema_context: str = "") -> IntentClassification:
        q_lower = query.lower()
        if "summary" in q_lower or "notes" in q_lower:
            return IntentClassification(intent="B", sql_filter=None)
        
        if "hybrid" in q_lower:
            return IntentClassification(intent="C", sql_filter="SELECT 1")
            
        return IntentClassification(intent="A", sql_filter=None)

class TestIntentEvaluator:
    
    def test_evaluator_accuracy(self):
        mock_classifier = MockClassifierForTest()
        evaluator = IntentEvaluator(mock_classifier)
        
        queries = [
            "How many patients?",          # -> A
            "Show me summary notes",       # -> B
            "Give me a hybrid analysis",   # -> C
            "This will route to A",        # -> A (misclassified, expected B)
        ]
        
        expected = [
            "A",  # Correct
            "B",  # Correct
            "C",  # Correct
            "B",  # Incorrect
        ]
        
        metrics = evaluator.evaluate_batch(queries, expected)
        
        assert metrics["accuracy"] == 0.75  # 3 out of 4 correct
        
        cm = metrics["confusion_matrix"]
        assert cm["A"]["A"] == 1
        assert cm["B"]["B"] == 1
        assert cm["C"]["C"] == 1
        assert cm["B"]["A"] == 1  # Expected B, got A
        
    def test_evaluator_latency(self):
        mock_classifier = MockClassifierForTest()
        evaluator = IntentEvaluator(mock_classifier)
        
        queries = ["q1", "q2"]
        expected = ["A", "A"]
        
        metrics = evaluator.evaluate_batch(queries, expected)
        
        assert "avg_latency_ms" in metrics
        assert metrics["avg_latency_ms"] >= 0
