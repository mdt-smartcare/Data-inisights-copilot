"""
File SQL Service — Text-to-SQL engine for uploaded CSV/Excel files.

This is the PRIMARY retrieval mechanism for structured file data (6.5M+ rows).
RAG is inefficient for aggregations; SQL is designed for exactly this.

Architecture:
1. Schema Inference: DuckDB infers schema from CSV, stored in context
2. LLM Query Translation: Natural language → SQL via GPT
3. Execution: DuckDB executes SQL directly against virtualized CSV
4. Performance: 6.5M row aggregations in milliseconds, zero embedding cost
"""

import re
import time
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import OrderedDict

import duckdb
from langchain_openai import ChatOpenAI

from backend.config import get_settings, get_llm_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Storage directory (same as ingestion.py)
DATA_STORAGE_DIR = Path(__file__).parent.parent / "data" / "duckdb_files"


# =============================================================================
# Query Cache for File SQL
# =============================================================================
class FileQueryCache:
    """LRU cache for file SQL query results."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def _hash_key(self, user_id: int, question: str) -> str:
        normalized = f"{user_id}:{question.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get(self, user_id: int, question: str) -> Optional[Dict]:
        key = self._hash_key(user_id, question)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                self.cache.move_to_end(key)
                logger.info("File SQL cache HIT")
                return result
            del self.cache[key]
        return None
    
    def set(self, user_id: int, question: str, result: Dict) -> None:
        key = self._hash_key(user_id, question)
        self.cache[key] = (result, time.time())
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)


_file_query_cache = FileQueryCache()


# =============================================================================
# File SQL Service
# =============================================================================
class FileSQLService:
    """
    Text-to-SQL service for uploaded file data stored in DuckDB.
    
    This is optimized for analytical queries on large datasets (millions of rows).
    DuckDB queries CSV files directly from disk without loading into RAM.
    """
    
    def __init__(self, user_id: int):
        """
        Initialize File SQL service for a specific user.
        
        Args:
            user_id: User ID whose uploaded files to query
        """
        self.user_id = user_id
        self.db_path = DATA_STORAGE_DIR / f"user_{user_id}" / "database.duckdb"
        
        if not self.db_path.exists():
            raise ValueError(f"No uploaded files found for user {user_id}")
        
        # Get LLM settings
        llm_settings = get_llm_settings()
        
        # Fast model for SQL generation
        self.llm_fast = ChatOpenAI(
            temperature=0,
            model_name="gpt-3.5-turbo",
            api_key=settings.openai_api_key,
        )
        
        # Primary model for complex reasoning
        self.llm = ChatOpenAI(
            temperature=llm_settings.get('temperature', 0.0),
            model_name=llm_settings.get('model_name', 'gpt-4o'),
            api_key=settings.openai_api_key,
        )
        
        # Cache schema on init
        self._schema_cache: Optional[Dict] = None
        self._cache_schema()
        
        logger.info(f"FileSQLService initialized for user {user_id}")
    
    def _get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        """Get a DuckDB connection."""
        return duckdb.connect(str(self.db_path), read_only=read_only)
    
    def _cache_schema(self) -> None:
        """Cache the schema information for all user tables."""
        try:
            conn = self._get_connection()
            
            # Check if metadata table exists
            tables_exist = conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = '_file_metadata'
            """).fetchone()[0]
            
            if not tables_exist:
                conn.close()
                self._schema_cache = {"tables": [], "schema_text": ""}
                return
            
            # Get all tables
            tables = conn.execute("""
                SELECT table_name, original_filename, row_count, columns
                FROM _file_metadata
            """).fetchall()
            
            schema_parts = []
            table_info = []
            
            for table_name, orig_file, row_count, columns_json in tables:
                columns = json.loads(columns_json) if columns_json else []
                
                # Get column types from DuckDB
                col_types = conn.execute(f"DESCRIBE SELECT * FROM {table_name}").fetchall()
                col_type_map = {row[0]: row[1] for row in col_types}
                
                # Build schema text
                col_descriptions = []
                for col in columns:
                    col_type = col_type_map.get(col, 'VARCHAR')
                    col_descriptions.append(f"  - {col} ({col_type})")
                
                schema_text = f"""TABLE: {table_name}
Source File: {orig_file}
Row Count: {row_count:,}
Columns:
{chr(10).join(col_descriptions)}"""
                
                schema_parts.append(schema_text)
                table_info.append({
                    "name": table_name,
                    "original_file": orig_file,
                    "row_count": row_count,
                    "columns": columns,
                    "column_types": col_type_map,
                })
            
            conn.close()
            
            self._schema_cache = {
                "tables": table_info,
                "schema_text": "\n\n".join(schema_parts),
            }
            
            logger.info(f"Cached schema for {len(table_info)} tables")
            
        except Exception as e:
            logger.error(f"Failed to cache schema: {e}")
            self._schema_cache = {"tables": [], "schema_text": ""}
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the cached schema information."""
        if not self._schema_cache:
            self._cache_schema()
        return self._schema_cache
    
    def get_schema_for_prompt(self) -> str:
        """Get schema formatted for LLM prompt context."""
        schema = self.get_schema()
        if not schema["tables"]:
            return "No tables available."
        return schema["schema_text"]
    
    def _generate_sql(self, question: str) -> str:
        """Generate SQL from natural language question."""
        schema_text = self.get_schema_for_prompt()
        
        # Get sample data for context
        sample_data = self._get_sample_data()
        
        prompt = f"""You are a DuckDB SQL expert. Generate ONLY a SQL query to answer the question.

AVAILABLE TABLES AND SCHEMA:
{schema_text}

SAMPLE DATA (first 3 rows from each table):
{sample_data}

IMPORTANT RULES:
1. Use ONLY the exact column and table names shown above
2. DuckDB uses standard SQL syntax
3. For string comparisons, use ILIKE for case-insensitive matching
4. Use appropriate aggregation functions: COUNT, AVG, SUM, MIN, MAX
5. Always include meaningful column aliases for aggregations
6. For date columns, use standard SQL date functions
7. NULL handling: Use COALESCE or IS NOT NULL as needed

QUESTION: {question}

Return ONLY the SQL query. No markdown, no explanation, no comments.

SQL:"""

        response = self.llm_fast.invoke(prompt)
        sql = response.content.strip()
        
        # Clean up any markdown formatting
        sql = re.sub(r'```sql\n?', '', sql)
        sql = re.sub(r'```\n?', '', sql)
        sql = sql.strip()
        
        logger.info(f"Generated SQL: {sql[:200]}...")
        return sql
    
    def _get_sample_data(self, limit: int = 3) -> str:
        """Get sample rows from each table for LLM context."""
        schema = self.get_schema()
        if not schema["tables"]:
            return "No data available."
        
        samples = []
        conn = self._get_connection()
        
        try:
            for table in schema["tables"]:
                table_name = table["name"]
                try:
                    rows = conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchall()
                    cols = table["columns"]
                    
                    if rows:
                        sample_text = f"Table: {table_name}\n"
                        sample_text += " | ".join(cols) + "\n"
                        for row in rows:
                            sample_text += " | ".join(str(v)[:30] if v else "NULL" for v in row) + "\n"
                        samples.append(sample_text)
                except Exception as e:
                    logger.warning(f"Could not get sample from {table_name}: {e}")
        finally:
            conn.close()
        
        return "\n".join(samples) if samples else "No sample data available."
    
    def _validate_sql(self, sql: str) -> bool:
        """Validate SQL query for safety."""
        sql_lower = sql.lower().strip()
        
        # Must be SELECT query
        if not sql_lower.startswith('select') and not sql_lower.startswith('with'):
            logger.warning("Query must start with SELECT or WITH")
            return False
        
        # Check for dangerous keywords
        dangerous = ['drop', 'delete', 'truncate', 'alter', 'create', 'insert', 'update']
        for keyword in dangerous:
            if re.search(rf'\b{keyword}\b', sql_lower):
                logger.warning(f"Query contains dangerous keyword: {keyword}")
                return False
        
        return True
    
    def _execute_sql(self, sql: str) -> Tuple[List[str], List[Dict], float]:
        """
        Execute SQL and return results.
        
        Returns:
            Tuple of (column_names, rows_as_dicts, execution_time_ms)
        """
        start_time = time.time()
        
        conn = self._get_connection()
        try:
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows_raw = result.fetchmany(10000)  # Limit results
            
            # Convert to list of dicts
            rows = []
            for row in rows_raw:
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if val is None:
                        row_dict[col] = None
                    elif isinstance(val, (int, float, str, bool)):
                        row_dict[col] = val
                    else:
                        row_dict[col] = str(val)
                rows.append(row_dict)
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.info(f"SQL executed in {execution_time_ms:.2f}ms, {len(rows)} rows returned")
            
            return columns, rows, execution_time_ms
            
        finally:
            conn.close()
    
    def _format_response(self, question: str, sql: str, columns: List[str], 
                         rows: List[Dict], execution_time_ms: float) -> str:
        """Format SQL results into natural language response."""
        
        # For simple results, format directly
        if len(rows) == 0:
            return "No results found for your query."
        
        if len(rows) == 1 and len(columns) == 1:
            # Single value result (e.g., COUNT, AVG)
            value = rows[0][columns[0]]
            return f"The answer is: **{value:,}**" if isinstance(value, (int, float)) else f"The answer is: {value}"
        
        # For more complex results, use LLM to format
        result_preview = json.dumps(rows[:10], indent=2, default=str)
        
        prompt = f"""Convert this SQL query result into a clear, natural language answer.

Question: {question}
SQL Query: {sql}
Execution Time: {execution_time_ms:.2f}ms
Total Rows: {len(rows)}

Results (first 10 rows):
{result_preview}

Provide a concise, informative answer. If the data is suitable for visualization, suggest what type of chart would work best.

Answer:"""

        response = self.llm_fast.invoke(prompt)
        return response.content.strip()
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Main entry point: Natural language question → SQL → Results.
        
        This is the Text-to-SQL engine for uploaded files.
        For 6.5M rows, this executes in milliseconds with zero embedding cost.
        
        Args:
            question: Natural language question
            
        Returns:
            Dict with keys: answer, sql, columns, rows, execution_time_ms, row_count
        """
        logger.info(f"FileSQLService query: {question[:100]}...")
        
        # Check cache
        cached = _file_query_cache.get(self.user_id, question)
        if cached:
            return cached
        
        try:
            # Step 1: Generate SQL from natural language
            sql = self._generate_sql(question)
            
            # Step 2: Validate SQL
            if not self._validate_sql(sql):
                return {
                    "status": "error",
                    "error": "Generated SQL failed validation. Please rephrase your question.",
                    "sql": sql,
                }
            
            # Step 3: Execute against DuckDB (fast - direct from disk)
            columns, rows, execution_time_ms = self._execute_sql(sql)
            
            # Step 4: Format response
            answer = self._format_response(question, sql, columns, rows, execution_time_ms)
            
            result = {
                "status": "success",
                "answer": answer,
                "sql": sql,
                "columns": columns,
                "rows": rows[:100],  # Limit rows in response
                "total_rows": len(rows),
                "execution_time_ms": round(execution_time_ms, 2),
            }
            
            # Cache result
            _file_query_cache.set(self.user_id, question, result)
            
            logger.info(f"Query completed in {execution_time_ms:.2f}ms")
            return result
            
        except duckdb.Error as e:
            logger.error(f"DuckDB error: {e}")
            return {
                "status": "error",
                "error": f"SQL execution error: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {
                "status": "error", 
                "error": str(e),
            }
    
    def query_raw(self, sql: str) -> Dict[str, Any]:
        """
        Execute raw SQL directly (for advanced users/debugging).
        
        Args:
            sql: Raw SQL query
            
        Returns:
            Dict with query results
        """
        if not self._validate_sql(sql):
            return {
                "status": "error",
                "error": "SQL validation failed. Only SELECT queries are allowed.",
            }
        
        try:
            columns, rows, execution_time_ms = self._execute_sql(sql)
            
            return {
                "status": "success",
                "sql": sql,
                "columns": columns,
                "rows": rows[:100],
                "total_rows": len(rows),
                "execution_time_ms": round(execution_time_ms, 2),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }


def get_file_sql_service(user_id: int) -> FileSQLService:
    """Get FileSQLService instance for a user."""
    return FileSQLService(user_id)
