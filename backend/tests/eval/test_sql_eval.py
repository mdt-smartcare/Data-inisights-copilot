import pytest
import pandas as pd
from eval.sql_eval.sql_evaluator import SQLEvaluator
from sqlalchemy import create_engine

@pytest.fixture
def mock_db_engine():
    # Create an in-memory SQLite database for testing equivalence logic
    engine = create_engine("sqlite:///:memory:")
    df = pd.DataFrame({
        "patient_id": [1, 2, 3],
        "age": [45, 60, 35],
        "diagnosis": ["Hypertension", "Diabetes", "Healthy"]
    })
    df.to_sql("patients", engine, index=False)
    return engine

def test_sql_equivalence_match(mock_db_engine):
    evaluator = SQLEvaluator(mock_db_engine)
    
    gt_sql = "SELECT patient_id, age FROM patients WHERE age > 40"
    gen_sql = "SELECT age, patient_id FROM patients WHERE age > 40" # Different column order
    
    result = evaluator.evaluate_query("Find older patients", gen_sql, gt_sql)
    
    assert result["error"] is None
    assert result["is_equivalent"] is True

def test_sql_equivalence_mismatch(mock_db_engine):
    evaluator = SQLEvaluator(mock_db_engine)
    
    gt_sql = "SELECT patient_id FROM patients WHERE diagnosis = 'Diabetes'"
    gen_sql = "SELECT patient_id FROM patients" # Missing WHERE clause
    
    result = evaluator.evaluate_query("Find diabetic patients", gen_sql, gt_sql)

    assert result["is_equivalent"] is False
    assert "DataFrames do not match" in result["error"]

def test_sql_equivalence_syntax_error(mock_db_engine):
    evaluator = SQLEvaluator(mock_db_engine)
    
    gt_sql = "SELECT * FROM patients"
    gen_sql = "SELECT * FRO patients" # Typo
    
    result = evaluator.evaluate_query("Get all", gen_sql, gt_sql)

    assert result["is_equivalent"] is False
    assert "Execution error" in result["error"]
