from contextvars import ContextVar
from typing import Optional

class SQLCapture:
    """Mutable container for capturing generated SQL queries across task boundaries."""
    def __init__(self, query: Optional[str] = None):
        self.query = query

# Global context var to store SQL capture container for the current request
current_sql_capture: ContextVar[Optional[SQLCapture]] = ContextVar("current_sql_capture", default=None)
