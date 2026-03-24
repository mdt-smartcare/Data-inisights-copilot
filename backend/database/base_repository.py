"""
Base repository class with common database operations.

This module provides reusable methods for:
- Executing queries
- Fetching results (one, many, all)
- Transaction management
- Parameter handling

Reduces boilerplate code across DatabaseService methods.
"""
from typing import Optional, Dict, Any, List, Tuple
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

from backend.core.logging import get_logger

logger = get_logger(__name__)


class BaseRepository:
    """Base class for database operations with common query execution patterns."""
    
    def __init__(self, get_connection_func):
        """
        Initialize repository with a connection function.
        
        Args:
            get_connection_func: Function that returns a database connection
        """
        self.get_connection = get_connection_func
    
    def execute_query(
        self, 
        query: str, 
        params: Optional[Tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = True
    ) -> Optional[Any]:
        """
        Execute a query with common error handling and fetch patterns.
        
        Args:
            query: SQL query string with %s placeholders
            params: Query parameters as tuple
            fetch_one: If True, fetch and return one result
            fetch_all: If True, fetch and return all results
            commit: If True, commit the transaction
            
        Returns:
            Query results based on fetch flags, or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params or ())
            
            if fetch_one:
                row = cursor.fetchone()
                result = dict(row) if row else None
            elif fetch_all:
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            else:
                result = None
            
            if commit:
                conn.commit()
            
            return result
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Database query error: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def execute_returning(
        self, 
        query: str, 
        params: Optional[Tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute an INSERT/UPDATE with RETURNING clause.
        
        Args:
            query: SQL query with RETURNING clause
            params: Query parameters as tuple
            
        Returns:
            Dict of returned row, or None
        """
        return self.execute_query(query, params, fetch_one=True, commit=True)
    
    def fetch_one(
        self, 
        query: str, 
        params: Optional[Tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row from query.
        
        Args:
            query: SQL SELECT query
            params: Query parameters as tuple
            
        Returns:
            Dict of row data, or None if not found
        """
        return self.execute_query(query, params, fetch_one=True, commit=False)
    
    def fetch_all(
        self, 
        query: str, 
        params: Optional[Tuple] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows from query.
        
        Args:
            query: SQL SELECT query
            params: Query parameters as tuple
            
        Returns:
            List of row dicts
        """
        result = self.execute_query(query, params, fetch_all=True, commit=False)
        return result if result is not None else []
    
    def execute_write(
        self, 
        query: str, 
        params: Optional[Tuple] = None
    ) -> int:
        """
        Execute an INSERT/UPDATE/DELETE and return affected row count.
        
        Args:
            query: SQL write query
            params: Query parameters as tuple
            
        Returns:
            Number of affected rows
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params or ())
            conn.commit()
            affected = cursor.rowcount
            return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"Database write error: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def execute_batch(
        self, 
        queries_with_params: List[Tuple[str, Optional[Tuple]]]
    ) -> bool:
        """
        Execute multiple queries in a single transaction.
        
        Args:
            queries_with_params: List of (query, params) tuples
            
        Returns:
            True if all queries succeeded, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            for query, params in queries_with_params:
                cursor.execute(query, params or ())
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Batch execution error: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    @contextmanager
    def transaction(self):
        """
        Context manager for explicit transaction control.
        
        Usage:
            with repo.transaction() as (conn, cursor):
                cursor.execute(query1, params1)
                cursor.execute(query2, params2)
                # Auto-commits on exit, rolls back on exception
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            yield conn, cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction error: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def parse_datetime(self, value) -> Optional[Any]:
        """
        Parse datetime from database - handles both datetime objects (PostgreSQL) and strings (SQLite).
        
        PostgreSQL returns datetime objects directly, while SQLite returns strings.
        This helper ensures consistent datetime handling across both databases.
        
        Args:
            value: datetime object, string, or None
            
        Returns:
            datetime object with timezone info, or None
        """
        from datetime import datetime, timezone
        
        if not value:
            return None
        
        # Already a datetime object (PostgreSQL)
        if isinstance(value, datetime):
            # Ensure it has timezone info
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        
        # String (SQLite or serialized)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except Exception as e:
                logger.warning(f"Failed to parse datetime string '{value}': {e}")
                return None
        
        return None
    
    def build_in_clause_placeholders(self, count: int) -> str:
        """
        Build placeholders for IN clause queries.
        
        Args:
            count: Number of items in IN clause
            
        Returns:
            String of comma-separated %s placeholders
            
        Example:
            >>> build_in_clause_placeholders(3)
            '%s,%s,%s'
        """
        return ','.join(['%s'] * count)
    
    def get_last_insert_id(self, conn, cursor) -> Optional[int]:
        """
        Get the ID of the last inserted row.
        
        Note: In PostgreSQL, use RETURNING id clause instead.
        This method is provided for compatibility but RETURNING is preferred.
        
        Args:
            conn: Database connection
            cursor: Database cursor
            
        Returns:
            Last inserted ID, or None
        """
        logger.warning("Using get_last_insert_id is discouraged. Use RETURNING id clause instead.")
        cursor.execute("SELECT lastval()")
        result = cursor.fetchone()
        return result[0] if result else None
