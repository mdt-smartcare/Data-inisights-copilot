import pytest
from eval.ragas_eval.ragas_evaluator import RagasEvaluator

class TestRagasMetrics:
    
    def test_mock_ragas_evaluation(self):
        """
        Test that RAGAS evaluator correctly processes a batch
        and returns metrics in the expected structure.
        Uses MOCK mode to avoid OpenAI API calls in CI.
        """
        evaluator = RagasEvaluator(use_mock=True)
        
        questions = ["What is the capital of France?", "Who wrote Hamlet?"]
        answers = ["The capital is Paris.", "William Shakespeare wrote Hamlet."]
        contexts = [
            ["Paris is the capital and most populous city of France."],
            ["Hamlet is a tragedy written by William Shakespeare."]
        ]
        ground_truths = ["Paris", "William Shakespeare"]
        
        results = evaluator.evaluate_batch(questions, answers, contexts, ground_truths)
        
        assert isinstance(results, dict)
        assert "faithfulness" in results
        assert "answer_relevancy" in results
        
        # In mock mode, we expect these specific stub values
        assert results["faithfulness"] == 0.85
        assert results["answer_relevancy"] == 0.90
        assert results["context_precision"] == 0.80
        assert results["context_recall"] == 0.75

    def test_mismatched_inputs(self):
        evaluator = RagasEvaluator(use_mock=True)
        
        with pytest.raises(ValueError):
            # 2 questions, 1 answer
            evaluator.evaluate_batch(
                ["Q1", "Q2"],
                ["A1"],
                [["C1"], ["C2"]],
                ["G1", "G2"]
            )
