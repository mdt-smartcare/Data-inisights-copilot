# eval/sql_eval/sql_evaluator.py
import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger("eval.sql")

class SQLEvaluator:
    """
    Evaluates Text-to-SQL logic by executing the generated SQL against a test DB
    and comparing the resulting DataFrame to the execution result of the Ground Truth SQL.
    This provides a deterministic check for SQL accuracy, independent of string formatting.
    """
    def __init__(self, db_engine):
        """
        Initialize with a SQLAlchemy engine pointing to the test database.
        """
        self.engine = db_engine

    def evaluate_query(self, query: str, generated_sql: str, ground_truth_sql: str) -> Dict[str, Any]:
        """
        Execute both SQL statements and compare their DataFrames.
        """
        result = {
            "query": query,
            "generated_sql": generated_sql,
            "ground_truth_sql": ground_truth_sql,
            "is_equivalent": False,
            "error": None
        }

        if not ground_truth_sql:
            result["error"] = "Missing ground truth SQL"
            return result

        try:
            # Execute Ground Truth SQL
            df_gt = pd.read_sql_query(ground_truth_sql, self.engine)
            
            # Execute Generated SQL
            df_gen = pd.read_sql_query(generated_sql, self.engine)
            
            # Compare
            # We sort columns and index to handle cases where the column order or row order 
            # might technically differ but the data footprint is identical.
            try:
                pd.testing.assert_frame_equal(
                    df_gt.sort_index(axis=1).sort_values(by=df_gt.columns.tolist()).reset_index(drop=True),
                    df_gen.sort_index(axis=1).sort_values(by=df_gen.columns.tolist()).reset_index(drop=True),
                    check_dtype=False, # Often types return differently (e.g. Int64 vs float64) based on the query builder
                    check_exact=False,
                    check_names=False  # We don't care if the agent named the column aliases differently
                )
                result["is_equivalent"] = True
            except AssertionError as e:
                result["error"] = f"DataFrames do not match: {e}"
                
        except Exception as e:
            result["error"] = f"Execution error: {e}"

        return result
