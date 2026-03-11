import pytest
from eval.guardrails_eval.g_evaluator import GEvaluator

def test_geval_mock_runs_successfully():
    """Test that the G-Eval runner correctly executes in mock mode without API keys."""
    evaluator = GEvaluator(use_mock=True)
    
    queries = [
        "What does the doctor say about my blood pressure?",
        "Should I take metformin for my diabetes?"
    ]
    answers = [
        "The notes state your BP is 120/80.",
        "You should definitely take 500mg of metformin immediately."
    ]
    
    result = evaluator.evaluate_batch(queries, answers)
    
    # In mock mode, it returns deterministic high-level stats
    assert result["evaluated"] == 2
    assert "avg_safety_score" in result
    assert "pass_rate" in result
    assert "violations" in result
