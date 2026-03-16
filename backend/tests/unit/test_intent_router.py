import pytest
from backend.services.intent_router import IntentClassifier, IntentClassification
from langchain_core.runnables import RunnableLambda

class DummyLLM:
    """Mock LLM to return a predefined IntentClassification."""
    def __init__(self, expected_response):
        self.expected_response = expected_response

    def with_structured_output(self, schema):
        # Return a LangChain Runnable that just emits our predefined response
        return RunnableLambda(lambda x: self.expected_response)

def test_rule_based_sql():
    classifier = IntentClassifier(llm=DummyLLM(None))
    result = classifier.classify("count the number of patients")
    assert result.intent == "A"
    assert result.confidence_score == 1.0

def test_rule_based_vector():
    classifier = IntentClassifier(llm=DummyLLM(None))
    result = classifier.classify("find patient notes about diabetes")
    assert result.intent == "B"
    assert result.confidence_score == 1.0

def test_llm_hybrid_low_confidence():
    # Mock LLM returning Intent C with low confidence
    mock_llm = DummyLLM(IntentClassification(
        intent="C", 
        sql_filter="SELECT id FROM patients", 
        confidence_score=0.4
    ))
    classifier = IntentClassifier(llm=mock_llm)
    # Give a query that doesn't trigger keyword rules
    result = classifier.classify("analyze complex medical situation over 90 days")
    
    assert result.intent == "C"
    assert result.confidence_score == 0.4
    assert result.sql_filter == "SELECT id FROM patients"

def test_llm_sql_high_confidence():
    mock_llm = DummyLLM(IntentClassification(
        intent="A", 
        sql_filter=None, 
        confidence_score=0.95
    ))
    classifier = IntentClassifier(llm=mock_llm)
    result = classifier.classify("aggregate demographics without keyword match")
    
    assert result.intent == "A"
    assert result.confidence_score == 0.95

