"""
SQL service for structured database queries.
Wraps LangChain SQL agent for database interactions.
"""
from functools import lru_cache
from typing import Optional
import re

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class SQLService:
    """Service for SQL database operations."""
    
    def __init__(self):
        """Initialize SQL database connection and agent."""
        logger.info(f"Connecting to database at {settings.database_url}")
        
        try:
            # Initialize database connection
            self.db = SQLDatabase.from_uri(settings.database_url)
            logger.info("Database connection established")
            
            # Cache table names and schema on initialization
            self._cache_schema()
            
            # Initialize LLM with verbose mode
            self.llm = ChatOpenAI(
                temperature=settings.openai_temperature,
                model_name=settings.openai_model,
                api_key=settings.openai_api_key,
                verbose=True  # Enable verbose mode to see LLM calls
            )
            
            # Create optimized SQL agent with pre-included context
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=self.db,
                agent_type="openai-tools",
                verbose=True,
                handle_parsing_errors=True,
                # Reduce max iterations to prevent excessive calls
                max_iterations=8,
                # Include table info in prompt to reduce lookups
                include_tables=self.relevant_tables
            )
            logger.info(f"SQL agent initialized successfully with {len(self.relevant_tables)} cached tables")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQL service: {e}", exc_info=True)
            raise
    
    def _cache_schema(self):
        """Cache database schema to avoid repeated lookups."""
        try:
            # Get all table names
            all_tables = self.db.get_usable_table_names()
            
            # Filter to most relevant tables for patient data
            self.relevant_tables = [
                table for table in all_tables 
                if any(keyword in table.lower() for keyword in [
                    'patient', 'visit', 'tracker', 'diagnosis', 'medication',
                    'lab_test', 'assessment', 'vital', 'bp_log', 'glucose',
                    'screening', 'enrollment', 'medical', 'notes'
                ])
            ]
            
            # Cache full schema for relevant tables
            self.cached_schema = self.db.get_table_info(table_names=self.relevant_tables)
            
            logger.info(f"Cached schema for {len(self.relevant_tables)} relevant tables out of {len(all_tables)} total")
            logger.info(f"Relevant tables: {', '.join(self.relevant_tables[:10])}...")
            
        except Exception as e:
            logger.warning(f"Could not cache schema: {e}. Will use default behavior.")
            self.relevant_tables = None
            self.cached_schema = None
    
    def _is_simple_query(self, question: str) -> bool:
        """
        Detect if query is simple enough for direct execution.
        Handles both natural language and pre-generated SQL.
        """
        question_lower = question.lower().strip()
        
        # Check if it's already SQL - be more strict about accepting it
        if question_lower.startswith('select'):
            logger.info(" Analyzing pre-generated SQL query")
            
            # IMPORTANT: Pre-generated SQL might have wrong column names
            # Only accept it if we can validate the columns exist
            try:
                # Try to extract table name and check if it's valid
                # But DON'T trust column names from external sources
                logger.info("  Pre-generated SQL detected, but will regenerate for safety")
                # Treat it as natural language instead
                return False  # Force regeneration with our cached schema
            except Exception:
                return False
        
        # Natural language patterns
        logger.info(" Analyzing natural language query")
        
        simple_patterns = [
            r'\bcount\b.*\bpatients?\b',
            r'\bhow many\b.*\bpatients?\b',
            r'\btotal\b.*\bnumber\b',
            r'\baverage\b.*\b(bmi|age|glucose|systolic|diastolic|bp|blood pressure)\b',
            r'\bmean\b.*\b(bmi|age|glucose)\b',
            r'\bsum\b.*\b(patients?|visits?)\b',
            r'number of (patients?|visits?)',
        ]
        
        has_simple_pattern = any(re.search(pattern, question_lower) for pattern in simple_patterns)
        
        # Complex indicators
        complex_indicators = [
            'compare', 'versus', 'vs', 'compared to',
            'trend', 'over time', 'by month', 'by year',
            'group by', 'breakdown', 'categorize',
            'join', 'combine', 'merge',
            'correlation', 'relationship',
            'most', 'least', 'top', 'bottom',
            'rank', 'order by', 'distribution',
            'each', 'per', 'by site', 'by region'
        ]
        
        has_complexity = any(indicator in question_lower for indicator in complex_indicators)
        
        # Check for multiple table references in natural language
        table_references = sum(1 for table in (self.relevant_tables or []) if table.lower() in question_lower)
        references_multiple_tables = table_references > 1
        
        is_simple = has_simple_pattern and not has_complexity and not references_multiple_tables
        
        if is_simple:
            logger.info(f" Query classified as SIMPLE (natural language)")
        else:
            logger.info(f" Query classified as COMPLEX (pattern={has_simple_pattern}, complexity={has_complexity}, multi_table={references_multiple_tables})")
        
        return is_simple
    
    def query(self, question: str) -> str:
        """
        Execute a natural language query against the database.
        Uses optimized path for simple queries.
        
        Args:
            question: Natural language question or SQL query
        
        Returns:
            SQL agent response as string
        """
        logger.info(f"Executing SQL query for: '{question[:100]}...'")
        
        # Check if it's a simple query
        if self._is_simple_query(question):
            logger.info(" Detected simple query - using optimized execution path")
            return self._execute_optimized(question)
        else:
            logger.info(" Complex query detected - using full agent")
            return self._execute_with_agent(question)
    
    def _execute_optimized(self, question: str) -> str:
        """
        Optimized execution for simple queries.
        Handles both natural language and pre-generated SQL.
        Reduces from 7 API calls to 1-2 calls.
        """
        logger.info("=" * 80)
        logger.info("⚡ OPTIMIZED SQL EXECUTION:")
        logger.info("=" * 80)
        
        try:
            sql_query = None
            api_call_count = 0
            
            # Check if question is already SQL
            if question.strip().lower().startswith('select'):
                logger.info(" Input is already SQL format, using directly")
                sql_query = question.strip()
                # Remove any trailing comments or explanation
                sql_query = sql_query.split('--')[0].strip()
                sql_query = sql_query.rstrip(';') + ';'
            else:
                # Generate SQL from natural language
                logger.info(" API Call 1: Generate SQL query with pre-cached schema")
                api_call_count += 1
                
                prompt = f"""You are a PostgreSQL expert. Generate ONLY a SQL query to answer the question.

DATABASE SCHEMA:
{self.cached_schema}

IMPORTANT RULES:
1. Use ONLY the exact column names shown in the schema above
2. Use ONLY the exact table names shown in the schema above
3. Study the sample rows to understand the data
4. For patient visit data, use the 'patient_visit' table
5. The patient_visit table links to patient_tracker via 'patient_track_id' (NOT patient_id)
6. For counting visits, use COUNT(*) or COUNT(id) from patient_visit
7. For counting unique patients from visits, use COUNT(DISTINCT patient_track_id)
8. Use proper date filtering: WHERE visit_date >= '2024-01-01' AND visit_date <= '2024-12-31'

QUESTION: {question}

Return ONLY the SQL query, no markdown, no explanation, no comments.

SQL Query:"""

                response = self.llm.invoke(prompt)
                sql_query = response.content.strip()
                
                # Clean up SQL (remove markdown code blocks if present)
                sql_query = re.sub(r'```sql\n?', '', sql_query)
                sql_query = re.sub(r'```\n?', '', sql_query)
                sql_query = sql_query.strip()
            
            logger.info(f" SQL to execute: {sql_query[:200]}...")
            
            # Basic validation
            if not self._validate_sql_query(sql_query):
                logger.warning("⚠️  SQL validation failed, falling back to agent")
                return self._execute_with_agent(question)
            
            # Execute the query directly
            logger.info(" Executing query against database (no API call)")
            result = self.db.run(sql_query)
            logger.info(f" Query result: {result}")
            
            # Format the result
            logger.info(f" API Call {api_call_count + 1}: Format natural language response")
            api_call_count += 1
            
            format_prompt = f"""Convert this database result into a clear, natural language answer.

SQL Query: {sql_query}
Result: {result}

Original question: {question}

Provide a concise, natural language answer."""

            formatted_response = self.llm.invoke(format_prompt)
            output = formatted_response.content.strip()
            
            logger.info("=" * 80)
            logger.info(f" Optimized execution completed with {api_call_count} API call(s) (vs 7 with agent)")
            logger.info(f" Final Answer: {output[:300]}...")
            logger.info("=" * 80)
            
            return output
            
        except Exception as e:
            logger.warning(f"  Optimized execution failed: {e}. Falling back to full agent.")
            logger.error(f"Error details: {str(e)}", exc_info=True)
            return self._execute_with_agent(question)
    
    def _validate_sql_query(self, sql_query: str) -> bool:
        """
        Basic validation of SQL query for safety and correctness.
        """
        sql_lower = sql_query.lower().strip()
        
        # Must start with SELECT
        if not sql_lower.startswith('select'):
            logger.warning("Query doesn't start with SELECT")
            return False
        
        # Check for dangerous operations
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter', 'create', 'insert', 'update', 'exec']
        if any(keyword in sql_lower for keyword in dangerous_keywords):
            logger.warning(f"Query contains dangerous keyword")
            return False
        
        # Check if query references known tables (if we have them)
        if self.relevant_tables:
            has_known_table = any(table.lower() in sql_lower for table in self.relevant_tables)
            if not has_known_table:
                logger.warning("Query doesn't reference any known tables")
                return False
        
        # Basic syntax check
        if 'from' not in sql_lower:
            logger.warning("Query missing FROM clause")
            return False
        
        return True
    
    def _execute_with_agent(self, question: str) -> str:
        """
        Full agent execution for complex queries.
        Still optimized with cached schema.
        """
        logger.info("=" * 80)
        logger.info(" SQL AGENT EXECUTION TRACE:")
        logger.info("=" * 80)
        
        try:
            # The agent already has schema pre-loaded via include_tables
            result = self.sql_agent.invoke({"input": question})
            
            # Extract output from agent result
            if isinstance(result, dict):
                output = result.get("output", str(result))
                
                # Log intermediate steps if available
                if "intermediate_steps" in result:
                    logger.info("\n Agent Intermediate Steps:")
                    for i, step in enumerate(result["intermediate_steps"], 1):
                        action = step[0] if len(step) > 0 else None
                        observation = step[1] if len(step) > 1 else None
                        
                        logger.info(f"\n  Step {i}:")
                        if action:
                            logger.info(f"     Action: {action}")
                        if observation:
                            obs_preview = str(observation)[:300]
                            logger.info(f"      Observation: {obs_preview}...")
            else:
                output = str(result)
            
            logger.info("=" * 80)
            logger.info(f" SQL query completed. Result length: {len(output)} chars")
            output_preview = output[:300] if len(output) > 300 else output
            logger.info(f" Final Answer: {output_preview}...")
            logger.info("=" * 80)
            
            return output
            
        except Exception as e:
            logger.error(f" SQL query failed: {e}", exc_info=True)
            raise
    
    def health_check(self) -> bool:
        """
        Check if database is accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Execute a simple query
            result = self.db.run("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_table_info(self) -> str:
        """
        Get database schema information.
        
        Returns:
            Table information as string
        """
        try:
            return self.db.get_table_info()
        except Exception as e:
            logger.error(f"Failed to get table info: {e}", exc_info=True)
            return "Error retrieving table information"


@lru_cache()
def get_sql_service() -> SQLService:
    """
    Get cached SQL service instance.
    Singleton pattern to reuse database connections.
    
    Returns:
        Cached SQL service
    """
    return SQLService()
