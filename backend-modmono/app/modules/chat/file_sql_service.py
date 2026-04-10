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

from app.core.settings import get_settings
from app.core.utils.logging import get_logger
from app.modules.chat.query.prompt_builder import PromptBuilder
from app.modules.chat.query.schema_context_service import SchemaContextService, get_schema_context_service
from app.modules.chat.query.query_validation_layer import (
    QueryValidationLayer,
    SQLValidationResult,
    validate_and_execute_sql,
)
from app.modules.sql_examples.store import get_sql_examples_store, SQLExamplesStore

settings = get_settings()
logger = get_logger(__name__)

# Storage directory - use project root /data folder
DATA_STORAGE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "duckdb_files"


# =============================================================================
# DuckDB Constraints (Fallback)
# =============================================================================
DUCKDB_CONSTRAINTS_FALLBACK = """
CRITICAL DUCKDB RULES:
- Window functions (LAG, LEAD, ROW_NUMBER) CANNOT be in WHERE clause - use CTE
- Aggregates (AVG, STDDEV) CANNOT be in WHERE clause - use subquery/CTE
- Date difference: CAST(date2 AS DATE) - CAST(date1 AS DATE) or DATEDIFF('day', d1, d2)
- Date subtraction: CAST(date AS DATE) - INTERVAL '90 days' (not DATE_SUB)
- For first/last comparisons: use ROW_NUMBER() with CTE pattern
- Boolean values may be strings: use = 'true' or = 'false'
"""


# =============================================================================
# Query Cache for File SQL
# =============================================================================
class FileQueryCache:
    """LRU cache for file SQL query results."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def _hash_key(self, user_id: str, question: str) -> str:
        normalized = f"{user_id}:{question.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get(self, user_id: str, question: str) -> Optional[Dict]:
        key = self._hash_key(user_id, question)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                self.cache.move_to_end(key)
                logger.info("File SQL cache HIT")
                return result
            del self.cache[key]
        return None
    
    def set(self, user_id: str, question: str, result: Dict) -> None:
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
    
    def __init__(
        self, 
        user_id: str, 
        callbacks: list = None, 
        trace_id: str = None,
        allowed_tables: List[str] = None
    ):
        """
        Initialize File SQL service for a specific user.
        
        Args:
            user_id: User ID whose uploaded files to query
            callbacks: Optional list of LangChain callbacks (e.g., LangfuseCallbackHandler)
            trace_id: Optional trace ID to group all LLM calls under one trace
            allowed_tables: Optional list of table names to restrict queries to.
                           If None, all tables are available. Used to scope
                           queries to a specific agent's data source.
        """
        self.user_id = user_id
        self.db_path = DATA_STORAGE_DIR / f"user_{user_id}" / "database.duckdb"
        self.callbacks = callbacks or []
        self.trace_id = trace_id
        self.allowed_tables = allowed_tables
        
        if not self.db_path.exists():
            raise ValueError(f"No uploaded files found for user {user_id}")
        
        # Fast model for SQL generation
        self.llm_fast = ChatOpenAI(
            temperature=0,
            model_name="gpt-4o-mini",
            api_key=settings.openai_api_key,
        )
        
        # Primary model for complex reasoning
        self.llm = ChatOpenAI(
            temperature=0,
            model_name="gpt-4o",
            api_key=settings.openai_api_key,
        )
        
        # Cache schema on init
        self._schema_cache: Optional[Dict] = None
        self._cache_schema()
        
        # Initialize PromptBuilder for dynamic prompt construction (dialect=duckdb)
        self.prompt_builder = PromptBuilder()
        
        # Initialize SQL examples store for few-shot learning
        self._sql_examples_store: Optional[SQLExamplesStore] = None
        try:
            self._sql_examples_store = get_sql_examples_store()
            logger.info("SQL Examples Store initialized for FileSQLService")
        except Exception as e:
            logger.warning(f"Failed to initialize SQL examples store: {e}")
            self._sql_examples_store = None
        
        if allowed_tables:
            logger.info(f"FileSQLService initialized for user {user_id}, restricted to tables: {allowed_tables}")
        else:
            logger.info(f"FileSQLService initialized for user {user_id}")
    
    def _get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        """Get a DuckDB connection."""
        return duckdb.connect(str(self.db_path), read_only=read_only)
    
    def _cache_schema(self) -> None:
        """Cache the schema information for allowed user tables."""
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
                # Skip tables not in allowed_tables if filter is set
                if self.allowed_tables and table_name not in self.allowed_tables:
                    logger.debug(f"Skipping table {table_name} - not in allowed_tables")
                    continue
                    
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
            
            logger.info(f"Cached schema for {len(table_info)} tables" + 
                       (f" (filtered from allowed_tables)" if self.allowed_tables else ""))
            
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
    
    async def _get_few_shot_examples(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve similar SQL examples for few-shot prompting."""
        if not self._sql_examples_store:
            return []
        
        try:
            examples = await self._sql_examples_store.get_similar_examples(
                question=question,
                top_k=top_k,
                min_score=0.5
            )
            return examples
        except Exception as e:
            logger.error(f"Failed to retrieve few-shot examples: {e}")
            return []
    
    def _format_few_shot_examples(self, examples: List[Dict[str, Any]]) -> str:
        """Format few-shot examples as a string for prompt injection."""
        if not examples:
            return ""
        
        formatted_parts = ["SIMILAR SQL EXAMPLES (use these patterns as reference):", ""]
        
        for i, example in enumerate(examples, 1):
            score = example.get("score", 0)
            question = example.get("question", "")
            sql = example.get("sql", "")
            category = example.get("category", "general")
            
            formatted_parts.append(f"Example {i} (similarity: {score:.2f}, category: {category}):")
            formatted_parts.append(f"Q: {question}")
            formatted_parts.append("SQL:")
            formatted_parts.append(sql)
            formatted_parts.append("")
        
        return "\n".join(formatted_parts)
    
    def _generate_sql(self, question: str) -> str:
        """Generate SQL from natural language question using PromptBuilder."""
        schema_text = self.get_schema_for_prompt()
        sample_data = self._get_sample_data()
        
        # Get few-shot examples (sync wrapper)
        few_shot_examples = []
        try:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run, 
                            self._get_few_shot_examples(question)
                        )
                        few_shot_examples = future.result(timeout=10)
                else:
                    few_shot_examples = loop.run_until_complete(
                        self._get_few_shot_examples(question)
                    )
            except RuntimeError:
                few_shot_examples = asyncio.run(self._get_few_shot_examples(question))
        except Exception as e:
            logger.warning(f"Failed to get few-shot examples: {e}")
            few_shot_examples = []
        
        few_shot_context = self._format_few_shot_examples(few_shot_examples)
        
        # Use PromptBuilder for dynamic, schema-aware prompt construction
        # build_for_file_query sets dialect="duckdb" which includes DuckDB constraints
        prompt = self.prompt_builder.build_for_file_query(
            question=question,
            schema_context=schema_text,
            sample_data=sample_data
        )
        
        # Inject few-shot examples if available
        if few_shot_context:
            prompt = prompt.replace(
                "QUESTION:",
                f"{few_shot_context}\n\nQUESTION:"
            )
        
        # Ensure DuckDB constraints are always present (fallback if PromptBuilder injection fails)
        if "CRITICAL DUCKDB" not in prompt:
            logger.warning("DuckDB constraints not found in prompt, injecting fallback")
            prompt = prompt.replace(
                "QUESTION:",
                f"{DUCKDB_CONSTRAINTS_FALLBACK}\n\nQUESTION:"
            )
        
        # Use callbacks for tracing if available
        invoke_config = {"callbacks": self.callbacks} if self.callbacks else {}
        response = self.llm_fast.invoke(prompt, config=invoke_config)
        sql = response.content.strip()
        
        # Clean up any markdown formatting
        sql = re.sub(r'```sql\n?', '', sql)
        sql = re.sub(r'```\n?', '', sql)
        sql = sql.strip()
        
        logger.info(f"Generated SQL: {sql[:200]}...")
        return sql
    
    def _get_sample_data(self, limit: int = 3) -> str:
        """Get sample rows and distinct values from each table for LLM context."""
        schema = self.get_schema()
        if not schema["tables"]:
            return "No data available."
        
        samples = []
        conn = self._get_connection()
        
        try:
            for table in schema["tables"]:
                table_name = table["name"]
                col_types = table.get("column_types", {})
                
                try:
                    # Get sample rows
                    rows = conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchall()
                    cols = table["columns"]
                    
                    if rows:
                        sample_text = f"Table: {table_name}\n"
                        sample_text += " | ".join(cols) + "\n"
                        for row in rows:
                            sample_text += " | ".join(str(v)[:30] if v else "NULL" for v in row) + "\n"
                        
                        # Get distinct values for categorical columns
                        categorical_values = []
                        for col in cols:
                            col_type = col_types.get(col, "").upper()
                            if "VARCHAR" in col_type or "TEXT" in col_type or col_type == "":
                                try:
                                    count_result = conn.execute(f"""
                                        SELECT COUNT(DISTINCT "{col}") FROM {table_name}
                                    """).fetchone()[0]
                                    
                                    if count_result and count_result <= 20:
                                        distinct_vals = conn.execute(f"""
                                            SELECT DISTINCT "{col}" FROM {table_name} 
                                            WHERE "{col}" IS NOT NULL 
                                            ORDER BY "{col}" 
                                            LIMIT 20
                                        """).fetchall()
                                        
                                        if distinct_vals:
                                            vals = [str(v[0])[:50] for v in distinct_vals if v[0]]
                                            if vals:
                                                categorical_values.append(f"  {col}: {vals}")
                                except Exception:
                                    pass
                        
                        if categorical_values:
                            sample_text += "\nDISTINCT VALUES (use these exact values in queries):\n"
                            sample_text += "\n".join(categorical_values)
                        
                        samples.append(sample_text)
                except Exception as e:
                    logger.warning(f"Could not get sample from {table_name}: {e}")
        finally:
            conn.close()
        
        return "\n\n".join(samples) if samples else "No sample data available."
    
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
            rows_raw = result.fetchall()  # No limit - data analysts need all results
            
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
    
    def _format_response(
        self, 
        question: str, 
        sql: str, 
        columns: List[str],
        rows: List[Dict], 
        execution_time_ms: float
    ) -> str:
        """Format SQL results into natural language response with chart JSON."""
        
        if len(rows) == 0:
            return "No results found for your query."
        
        question_lower = question.lower()
        
        # Detect if this is a rate/percentage question
        is_rate_question = any(word in question_lower for word in [
            'rate', 'percentage', 'percent', '%', 'coverage', 'control rate',
            'achievement', 'target', 'goal', 'proportion'
        ])
        
        # Single value result handling
        if len(rows) == 1 and len(columns) == 1:
            value = rows[0][columns[0]]
            
            if is_rate_question and isinstance(value, (int, float)):
                display_value = value * 100 if value <= 1 else value
                return f"""The answer is: **{display_value:.1f}%**

```json
{{
    "chart_json": {{
        "title": "{columns[0].replace('_', ' ').title()}",
        "type": "gauge",
        "value": {display_value:.1f},
        "min": 0,
        "max": 100,
        "target": 80,
        "thresholds": [
            {{"value": 80, "color": "#10b981", "label": "Good (≥80%)"}},
            {{"value": 60, "color": "#f59e0b", "label": "Fair (60-79%)"}},
            {{"value": 0, "color": "#ef4444", "label": "Poor (<60%)"}}
        ]
    }}
}}
```"""
            
            formatted_value = f"{value:,.2f}" if isinstance(value, float) else (f"{value:,}" if isinstance(value, int) else str(value))
            return f"""The answer is: **{formatted_value}**

```json
{{
    "chart_json": {{
        "title": "Result",
        "type": "scorecard",
        "data": {{
            "labels": ["{columns[0]}"],
            "values": [{value if isinstance(value, (int, float)) else f'"{value}"'}]
        }}
    }}
}}
```"""
        
        # For more complex results, use LLM to format with chart
        result_preview = json.dumps(rows[:15], indent=2, default=str)
        
        chart_hint = ""
        if any(word in question_lower for word in ['cascade', 'funnel', 'journey', 'stages', 'flow']):
            chart_hint = "USE type='funnel' - This is a care cascade/patient journey question."
        elif any(word in question_lower for word in ['vs target', 'versus target', 'against target', 'compare', 'performance']):
            chart_hint = "USE type='bullet' - This compares actual values against targets."
        elif any(word in question_lower for word in ['highest', 'lowest', 'top', 'bottom', 'rank', 'most', 'least']):
            chart_hint = "USE type='horizontal_bar' - This is a ranking question. Show top 10."
        elif any(word in question_lower for word in ['by region', 'by district', 'by location', 'distribution by', 'regional']):
            chart_hint = "USE type='treemap' - This is a regional/hierarchical distribution."
        elif any(word in question_lower for word in ['trend', 'over time', 'monthly', 'yearly', 'by month', 'by year']):
            chart_hint = "USE type='line' - This is a time series trend."
        elif any(word in question_lower for word in ['breakdown', 'by age', 'by gender', 'by category', 'by type']):
            chart_hint = "USE type='bar' - This is a categorical breakdown."
        elif any(word in question_lower for word in ['male', 'female', 'gender', 'proportion', 'percentage of']):
            chart_hint = "USE type='pie' - This shows proportions/distributions."
        
        prompt = f"""Convert this SQL query result into a clear, natural language answer.
Also, generate a JSON chart specification for visualization.

Question: {question}
SQL Query: {sql}
Execution Time: {execution_time_ms:.2f}ms
Total Rows: {len(rows)}

Results (first 15 rows):
{result_preview}

{f"IMPORTANT: {chart_hint}" if chart_hint else ""}

RESPOND WITH A CHART JSON:
1. First, provide a concise natural language answer explaining the data.
2. Then, you MUST append a JSON code block with chart data.

Format:
```json
{{
    "chart_json": {{
        "title": "Descriptive Chart Title",
        "type": "<chart_type>",
        "data": {{
            "labels": ["label1", "label2", ...],
            "values": [value1, value2, ...]
        }}
    }}
}}
```

Response:"""

        invoke_config = {"callbacks": self.callbacks} if self.callbacks else {}
        response = self.llm_fast.invoke(prompt, config=invoke_config)
        return response.content.strip()
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Main entry point: Natural language question → SQL → Results.
        
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
            
            # Step 3: Execute against DuckDB
            columns, rows, execution_time_ms = self._execute_sql(sql)
            
            # Step 4: Format response
            answer = self._format_response(question, sql, columns, rows, execution_time_ms)
            
            result = {
                "status": "success",
                "answer": answer,
                "sql": sql,
                "columns": columns,
                "rows": rows,  # Return all rows - no artificial limit
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
                "rows": rows,  # Return all rows - no artificial limit
                "total_rows": len(rows),
                "execution_time_ms": round(execution_time_ms, 2),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }


def get_file_sql_service(user_id: str, allowed_tables: List[str] = None) -> FileSQLService:
    """Get FileSQLService instance for a user."""
    return FileSQLService(user_id, allowed_tables=allowed_tables)


    async def query_with_retry(self, question: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Query with automatic retry using QueryValidationLayer.
        
        This method generates SQL and uses the QueryValidationLayer to automatically
        retry on execution errors, using LLM-based query fixing.
        
        Args:
            question: Natural language question
            max_retries: Maximum number of retry attempts (default 3)
            
        Returns:
            Dict with keys: answer, sql, columns, rows, execution_time_ms, row_count, retries
        """
        import asyncio
        
        logger.info(f"FileSQLService query_with_retry: {question[:100]}...")
        
        # Check cache
        cached = _file_query_cache.get(self.user_id, question)
        if cached:
            return cached
        
        try:
            # Step 1: Generate SQL from natural language
            sql = self._generate_sql(question)
            
            # Step 2: Validate SQL (basic safety check)
            if not self._validate_sql(sql):
                return {
                    "status": "error",
                    "error": "Generated SQL failed validation. Please rephrase your question.",
                    "sql": sql,
                }
            
            # Step 3: Execute with automatic retry using QueryValidationLayer
            schema_text = self.get_schema_for_prompt()
            sample_data = self._get_sample_data()
            
            # Create executor function for QueryValidationLayer
            def execute_fn(query: str) -> Tuple[List[Dict], int]:
                columns, rows, _ = self._execute_sql(query)
                # Convert to format expected by QueryValidationLayer
                return rows, len(rows)
            
            # Use QueryValidationLayer for automatic retry
            validation_result = await validate_and_execute_sql(
                sql=sql,
                question=question,
                execute_fn=execute_fn,
                schema_context=schema_text,
                dialect="duckdb",
                max_retries=max_retries,
                sample_data=sample_data,
            )
            
            if not validation_result.success:
                return {
                    "status": "error",
                    "error": f"SQL execution failed after {validation_result.attempt_number} attempts: {validation_result.error}",
                    "sql": validation_result.sql,
                    "error_type": validation_result.error_type.value if validation_result.error_type else "unknown",
                    "attempts": validation_result.attempt_number,
                }
            
            # Extract results
            rows = validation_result.result.get("rows", [])
            count = validation_result.result.get("count", 0)
            
            # Get columns from first row
            columns = list(rows[0].keys()) if rows else []
            
            # Step 4: Format response
            answer = self._format_response(
                question, 
                validation_result.sql, 
                columns, 
                rows, 
                validation_result.execution_time_ms
            )
            
            result = {
                "status": "success",
                "answer": answer,
                "sql": validation_result.sql,
                "columns": columns,
                "rows": rows,  # Return all rows - no artificial limit
                "total_rows": count,
                "execution_time_ms": round(validation_result.execution_time_ms, 2),
                "attempts": validation_result.attempt_number,
                "fix_applied": validation_result.fix_applied,
            }
            
            # Cache result
            _file_query_cache.set(self.user_id, question, result)
            
            logger.info(
                f"Query completed in {validation_result.execution_time_ms:.2f}ms "
                f"(attempts: {validation_result.attempt_number})"
            )
            return result
            
        except Exception as e:
            logger.error(f"Query with retry failed: {e}")
            return {
                "status": "error", 
                "error": str(e),
            }
    
    def query_with_retry_sync(self, question: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Synchronous wrapper for query_with_retry.
        
        Args:
            question: Natural language question
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dict with query results
        """
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.query_with_retry(question, max_retries)
                    )
                    return future.result(timeout=120)
            else:
                return loop.run_until_complete(
                    self.query_with_retry(question, max_retries)
                )
        except RuntimeError:
            return asyncio.run(self.query_with_retry(question, max_retries))
