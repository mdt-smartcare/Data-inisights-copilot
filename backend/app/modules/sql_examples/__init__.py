"""
SQL Examples module for storing and retrieving curated Q&A pairs.

Used for few-shot learning to improve NL2SQL accuracy.
"""
from app.modules.sql_examples.store import SQLExamplesStore, get_sql_examples_store

__all__ = ["SQLExamplesStore", "get_sql_examples_store"]
