"""
SQL service for structured database queries.
Wraps LangChain SQL agent for database interactions.

OPTIMIZED: Added query result caching and reduced agent iterations.
"""
from functools import lru_cache
from typing import Optional, Tuple, List, Dict, Any
from collections import OrderedDict
import re
import time
import hashlib
import json
import redis
from datetime import timedelta

from sqlalchemy import inspect
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

# Langfuse imports for tracing
from langfuse import observe
try:
    from langfuse import langfuse_context
except ImportError:
    langfuse_context = None

from backend.config import get_settings, get_llm_settings
from backend.core.logging import get_logger
from backend.services.reflection_service import get_critique_service


settings = get_settings()
logger = get_logger(__name__)


# =============================================================================
# REDIS SQL QUERY RESULT CACHE
# =============================================================================

# Initialize Redis client using settings
try:
    _redis_client = redis.from_url(settings.celery_result_backend, decode_responses=True)
    # Test connection
    _redis_client.ping()
    logger.info("Successfully connected to Redis for SQL caching")
except Exception as e:
    logger.warning(f"Failed to connect to Redis for SQL caching: {e}. Falling back to disabled cache.")
    _redis_client = None

def _hash_sql(sql_query: str) -> str:
    """Create a SHA256 hash from normalized SQL to use as cache key."""
    # Normalize: lowercase and remove extra whitespace/newlines
    normalized = " ".join(sql_query.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

def _determine_ttl(sql_query: str) -> int:
    """
    Determine TTL based on query volatility:
    - High-volatility metrics (live counts): 5 minutes
    - Historical aggregations: 1 hour
    """
    sql_lower = sql_query.lower()
    
    historical_indicators = [
        'group by month', 'group by year', 'group by quarter',
        'extract(year', 'extract(month', 'date_trunc',
        '< 202', '<= 202', '< 201' # explicit past years
    ]
    
    if any(indicator in sql_lower for indicator in historical_indicators):
        return 3600 # 1 hour
    
    return 300 # 5 minutes default

def invalidate_sql_cache():
    """Clear all SQL query results from Redis cache."""
    if not _redis_client:
        return
        
    try:
        # We prefix all sql cache keys with 'sql_cache:'
        keys = _redis_client.keys('sql_cache:*')
        if keys:
            _redis_client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} SQL cache entries")
    except Exception as e:
        logger.error(f"Failed to invalidate SQL cache: {e}")

class CachedSQLDatabase(SQLDatabase):
    """
    Extension of LangChain's SQLDatabase that intercepts .run()
    to inject Redis query result caching. This ensures both optimized
    and Agent executions benefit from the same cache.
    """
    def run(self, command: str, fetch: str = "all", include_columns: bool = False) -> str:
        # 1. Skip caching for non-SELECT commands (though Langchain agent should only SELECT)
        if not command.strip().lower().startswith('select') or not _redis_client:
            return super().run(command, fetch, include_columns)
        
        # 2. Key Structure 
        # Adding fetch & include_columns to hash just in case, though they are usually default
        cache_key = f"sql_cache:{_hash_sql(command)}_{fetch}_{include_columns}"
        
        try:
            cached_result = _redis_client.get(cache_key)
            if cached_result:
                logger.info(" Cache HIT in Redis from CachedSQLDatabase wrapper")
                return cached_result
        except Exception as e:
            logger.warning(f" Redis GET failed in CachedSQLDatabase: {e}")
            
        # 3. Cache MISS, execute DB
        logger.info(" Cache MISS in CachedSQLDatabase, executing DB run")
        run_start = time.time()
        result = super().run(command, fetch, include_columns)
        logger.info(f"  DB Execution Time: {(time.time() - run_start)*1000:.0f}ms")
        
        # 4. Save to Cache
        if _redis_client and result:
             try:
                 ttl = _determine_ttl(command)
                 _redis_client.setex(cache_key, ttl, str(result))
             except Exception as e:
                 logger.warning(f" Redis SET failed in CachedSQLDatabase: {e}")
                 
        return str(result)




def _get_active_database_url(agent_id: Optional[int] = None, connection_id: Optional[int] = None) -> Optional[str]:
    """
    Get the database URL from the active published config.
    
    Clinical database connections are managed via the `db_connections` table
    and assigned to agents. There is no hardcoded fallback - a connection
    must be configured via the frontend.
    
    Args:
        agent_id: Optional agent ID to get agent-specific config.
        connection_id: Optional direct connection ID to use (bypasses config lookup).
    
    Returns:
        Database URI string, or None if no connection is configured.
    """
    try:
        from backend.sqliteDb.db import get_db_service
        db_service = get_db_service()
        
        # If direct connection_id provided, use it
        if connection_id:
            connection = db_service.get_db_connection_by_id(connection_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection by ID: {connection.get('name')} (ID: {connection_id})")
                return connection['uri']
        
        # Try to get active config for specific agent first
        if agent_id:
            active_config = db_service.get_active_config(agent_id=agent_id)
            if active_config and active_config.get('connection_id'):
                conn_id = active_config['connection_id']
                connection = db_service.get_db_connection_by_id(conn_id)
                if connection and connection.get('uri'):
                    logger.info(f"Using database connection from agent {agent_id} config: {connection.get('name')} (ID: {conn_id})")
                    return connection['uri']
        
        # Try global config (no agent_id)
        active_config = db_service.get_active_config()
        if active_config and active_config.get('connection_id'):
            connection_id = active_config['connection_id']
            connection = db_service.get_db_connection_by_id(connection_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection from global config: {connection.get('name')} (ID: {connection_id})")
                return connection['uri']
        
        # Fallback: Check if ANY agent has a published config with a connection
        # This handles the case where only agent-specific configs exist
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pc.connection_id, sp.agent_id
            FROM system_prompts sp
            JOIN prompt_configs pc ON sp.id = pc.prompt_id
            WHERE sp.is_active = 1 AND pc.connection_id IS NOT NULL
            ORDER BY sp.created_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            fallback_conn_id = row[0]
            fallback_agent_id = row[1]
            connection = db_service.get_db_connection_by_id(fallback_conn_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection from agent {fallback_agent_id} config (fallback): {connection.get('name')} (ID: {fallback_conn_id})")
                return connection['uri']
        
        logger.warning("No active database connection configured. Please configure a connection via the frontend.")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get active database URL: {e}")
        return None


class SQLService:
    """Service for SQL database operations."""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize SQL service with a database connection.
        
        Args:
            database_url: Optional database URI. If not provided, will attempt
                         to get from active config in db_connections table.
                         
        Raises:
            ValueError: If no database connection is available.
        """
        # Use provided URL, or get from active config
        if database_url:
            self._database_url = database_url
        else:
            self._database_url = _get_active_database_url()
        
        if not self._database_url:
            raise ValueError(
                "No database connection configured. "
                "Please add a database connection via Settings > Database Connections "
                "and publish a RAG configuration that uses it."
            )
            
        logger.info("Connecting to database...")
        
        try:
            # Initialize critique service
            self.critique_service = get_critique_service()

            # WORKAROUND for PostgreSQL permission issues:
            # Some PostgreSQL instances don't grant access to pg_collation system table.
            # SQLAlchemy's full metadata reflection tries to load domains which requires pg_collation.
            # Solution: First get table names via a lightweight query, then use include_tables
            # to limit reflection to only those tables (avoids domain inspection).
            
            from backend.core.db_pool import get_cached_engine
            from sqlalchemy import text
            
            # Extract engine using connection pooling wrapper
            engine = get_cached_engine(
                self._database_url,
                pool_size=5, 
                max_overflow=10
            )
            
            all_table_names = []
            detected_schema = 'public'
            
            # Get table names without triggering full reflection
            with engine.connect() as conn:
                # First, try to get tables from ALL accessible schemas (not just public)
                try:
                    # Query for regular tables across all schemas the user can access
                    tables_result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.tables 
                        WHERE table_type = 'BASE TABLE'
                        AND table_schema NOT IN ('pg_catalog', 'information_schema')
                        ORDER BY table_schema, table_name
                    """))
                    tables_with_schema = [(row[0], row[1]) for row in tables_result]
                    
                    # Query for views across all schemas
                    views_result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.views 
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                        ORDER BY table_schema, table_name
                    """))
                    views_with_schema = [(row[0], row[1]) for row in views_result]
                    
                    # Combine and determine the primary schema
                    all_objects = tables_with_schema + views_with_schema
                    
                    if all_objects:
                        # Use the schema that has the most tables
                        from collections import Counter
                        schema_counts = Counter(obj[0] for obj in all_objects)
                        detected_schema = schema_counts.most_common(1)[0][0]
                        logger.info(f"Detected primary schema: {detected_schema}")
                        
                        # Get table names from the primary schema
                        all_table_names = [obj[1] for obj in all_objects if obj[0] == detected_schema]
                        logger.info(f"Found {len(all_table_names)} tables/views in schema '{detected_schema}'")
                    
                except Exception as e:
                    logger.warning(f"information_schema query failed: {e}")
                
                # Fallback: If information_schema didn't work, try pg_class directly
                if not all_table_names:
                    try:
                        logger.info("Trying pg_class fallback for table discovery...")
                        result = conn.execute(text("""
                            SELECT c.relname 
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relkind IN ('r', 'v')  -- r=table, v=view
                            AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                            AND has_table_privilege(c.oid, 'SELECT')
                            ORDER BY c.relname
                        """))
                        all_table_names = [row[0] for row in result]
                        logger.info(f"pg_class fallback found {len(all_table_names)} accessible tables/views")
                    except Exception as e2:
                        logger.warning(f"pg_class fallback also failed: {e2}")
            
            # engine.dispose() # DO NOT DISPOSE cached engine
            
            logger.info(f"Discovered {len(all_table_names)} tables/views total")
            
            # Determine tables to ignore (demo tables that shouldn't be used)
            ignore_tables = []
            if 'patient_tracker' in all_table_names and 'patient' in all_table_names:
                ignore_tables.append('patient')
                logger.info("Will ignore demo 'patient' table - using 'patient_tracker' for patient data")
            
            # Filter out ignored tables
            include_tables = [t for t in all_table_names if t not in ignore_tables]

            # CRITICAL: If no tables found, we cannot use include_tables=[] 
            # as SQLAlchemy will still try full reflection. Instead, raise a clear error.
            if not include_tables:
                raise ValueError(
                    "No accessible tables found in the database. "
                    "Please ensure the database user has SELECT permission on at least one table. "
                    "Check that tables exist and are not in system schemas."
                )

            # Initialize database connection with explicit include_tables
            # This avoids full metadata reflection that requires pg_collation access
            db_kwargs = {
                'view_support': True,
                'include_tables': include_tables,
                'engine_args': {'pool_size': 20, 'max_overflow': 50, 'pool_timeout': 60}
            }
            
            # If we detected a non-public schema, we need to set it
            if detected_schema != 'public':
                db_kwargs['schema'] = detected_schema
                logger.info(f"Using schema: {detected_schema}")
            
            # Use our custom CachedSQLDatabase wrapper
            self.db = CachedSQLDatabase(engine=engine, **db_kwargs)
            logger.info("Database connection established with view support and Redis caching")
            
            self._cache_schema()
            
            # Get LLM settings from database (runtime configurable)
            llm_settings = get_llm_settings()
            llm_model = llm_settings.get('model_name', 'gpt-4o')
            llm_temperature = llm_settings.get('temperature', 0.0)
            
            self.llm_fast = ChatOpenAI(
                temperature=0,
                model_name="gpt-3.5-turbo",
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.llm = ChatOpenAI(
                temperature=llm_temperature,
                model_name=llm_model,
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=self.db,
                agent_type="openai-tools",
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=5,  # Reduced from 8 for faster execution
                include_tables=self.relevant_tables
            )
            logger.info(f"SQL agent initialized successfully with {len(self.relevant_tables)} cached tables")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQL service: {e}", exc_info=True)
            raise
    
    def reinitialize(self, database_url: Optional[str] = None):
        """
        Reinitialize the SQLService with a new database connection.
        """
        logger.info("Reinitializing SQLService with new database connection")
        self.__init__(database_url=database_url)

    def _cache_schema(self):
        try:
            all_tables = self.db.get_usable_table_names()
            
            # Use all discovered tables without domain-specific filtering
            # Schema relevance is now determined dynamically by the LLM
            self.relevant_tables = list(all_tables)
            
            # IMPORTANT: Exclude the demo 'patient' table if patient_tracker exists
            # The 'patient' table is a simple demo table with only 3 rows
            # patient_tracker is the real patient data table with actual data
            if 'patient_tracker' in self.relevant_tables and 'patient' in self.relevant_tables:
                self.relevant_tables.remove('patient')
                logger.info("Excluded demo 'patient' table from schema - using 'patient_tracker' for patient data")
            
            base_schema = self.db.get_table_info(table_names=self.relevant_tables)
            
            # Schema context is provided dynamically via system prompt configuration
            # Domain-specific rules should be defined in the data dictionary
            schema_enhancements = ""
            
            self.cached_schema = base_schema + schema_enhancements
            
            logger.info(f"Cached schema for {len(self.relevant_tables)} relevant tables out of {len(all_tables)} total")
            logger.info(f"Relevant tables: {', '.join(self.relevant_tables[:10])}...")
            
        except Exception as e:
            logger.warning(f"Could not cache schema: {e}. Will use default behavior.")
            self.relevant_tables = None
            self.cached_schema = None
    
    def _get_relevant_schema(self, question: str) -> str:
        try:
            question_lower = question.lower()
            
            relevant_tables = [
                table for table in (self.relevant_tables or [])
                if table.lower() in question_lower
            ]
            
            # Dynamic table matching: look for tables whose names appear in the question
            # No hardcoded keyword mappings - schema understanding comes from data dictionary
            for table in (self.relevant_tables or []):
                # Match if table name (or parts of it) appear in the question
                table_words = table.lower().replace('_', ' ').split()
                if any(word in question_lower for word in table_words if len(word) > 2):
                    if table not in relevant_tables:
                        relevant_tables.append(table)
            
            if not relevant_tables:
                logger.info("No specific tables matched in question. Using full cached schema.")
                return self.cached_schema
            
            # IMPORTANT: Exclude the demo 'patient' table if patient_tracker exists
            # patient_tracker is the real patient data table
            if 'patient_tracker' in relevant_tables and 'patient' in relevant_tables:
                relevant_tables.remove('patient')
                logger.info("Removed demo 'patient' table - using 'patient_tracker' instead")
            
            relevant_tables = list(dict.fromkeys(relevant_tables))
            logger.info(f"Selected relevant tables for query: {', '.join(relevant_tables)}")
            
            base_schema = self.db.get_table_info(table_names=relevant_tables)
            
            # Join patterns are discovered from schema foreign keys or data dictionary
            schema_enhancements = ""
            
            return base_schema + schema_enhancements
            
        except Exception as e:
            logger.warning(f"Failed to get relevant schema: {e}. Falling back to full schema.")
            return self.cached_schema

    def _get_active_system_prompt_rules(self) -> str:
        """
        Fetch active system prompt rules for domain-specific SQL generation.
        Extracts key rules from the published system prompt.
        """
        try:
            from backend.sqliteDb.db import get_db_service
            db_service = get_db_service()
            
            # Get the active system prompt
            prompt_text = db_service.get_latest_active_prompt()
            
            if not prompt_text:
                logger.warning("No active system prompt found")
                return ""
            
            # Extract important rules section from the prompt
            # Look for TABLE CLARIFICATIONS or RULES sections
            rules_section = ""
            
            # Extract IMPORTANT TABLE CLARIFICATIONS if present
            if "IMPORTANT TABLE CLARIFICATIONS:" in prompt_text:
                start = prompt_text.find("IMPORTANT TABLE CLARIFICATIONS:")
                end = prompt_text.find("RULES FOR SQL GENERATION:", start)
                if end == -1:
                    end = len(prompt_text)
                rules_section += prompt_text[start:end].strip() + "\n\n"
            
            # Extract RULES FOR SQL GENERATION if present
            if "RULES FOR SQL GENERATION:" in prompt_text:
                start = prompt_text.find("RULES FOR SQL GENERATION:")
                # Find next major section or end of prompt
                end = len(prompt_text)
                rules_section += prompt_text[start:end].strip()
            
            # If no specific sections found, look for KEY TABLES section
            if not rules_section and "KEY TABLES AND COLUMNS:" in prompt_text:
                start = prompt_text.find("KEY TABLES AND COLUMNS:")
                end = prompt_text.find("RULES FOR SQL", start)
                if end == -1:
                    end = min(start + 2000, len(prompt_text))  # Limit to 2000 chars
                rules_section = prompt_text[start:end].strip()
            
            if rules_section:
                logger.info(f"Loaded {len(rules_section)} chars of system prompt rules for SQL generation")
                return f"DOMAIN-SPECIFIC RULES FROM SYSTEM PROMPT:\n{rules_section}"
            
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to fetch system prompt rules: {e}")
            return ""

    def _is_simple_query(self, question: str) -> bool:
        question_lower = question.lower().strip()
        
        if question_lower.startswith('select'):
            logger.info(" Analyzing pre-generated SQL query")
            
            try:
                logger.info("  Pre-generated SQL detected, but will regenerate for safety")
                return False
            except Exception:
                return False
        
        logger.info("Analyzing natural language query")
        
        simple_patterns = [
            r'\bcount\b',
            r'\bhow many\b',
            r'\btotal\b.*\bnumber\b',
            r'\baverage\b',
            r'\bmean\b',
            r'\bsum\b',
            r'number of',
            r'distribution of',
        ]
        
        has_simple_pattern = any(re.search(pattern, question_lower) for pattern in simple_patterns)
        
        complex_indicators = [
            'compare', 'versus', 'vs', 'compared to',
            'trend', 'over time', 'by month', 'by year', 'by quarter',
            'breakdown by site', 'breakdown by region',
            'categorize',
            'correlation', 'relationship',
            'most', 'least', 'top', 'bottom',
            'rank', 'order by',
            'each', 'per', 'by site', 'by region',
            'percentage', 'proportion', 'ratio'
        ]
        
        has_complexity = any(indicator in question_lower for indicator in complex_indicators)
        
        table_references = sum(1 for table in (self.relevant_tables or []) if table.lower() in question_lower)
        
        targets_analytics_view = 'v_analytics' in question_lower
        if targets_analytics_view:
            logger.info("Query targets analytics view - treating as single source")
            references_multiple_tables = False
        else:
            references_multiple_tables = table_references > 1
        
        is_simple = has_simple_pattern and not has_complexity and not references_multiple_tables
        
        if is_simple:
            logger.info("Query classified as SIMPLE (natural language)")
        else:
            logger.info(f" Query classified as COMPLEX (pattern={has_simple_pattern}, complexity={has_complexity}, multi_table={references_multiple_tables})")
        
        return is_simple
    
    @observe
    def query(self, question: str) -> str:
        logger.info(f"Executing SQL query for: '{question[:100]}...'")
        
        # We removed the NLP question-level cache in favor of the lower-level Redis SQL-execution cache
        
        if self._is_simple_query(question):
            logger.info(" Detected simple query - using optimized execution path")
            result = self._execute_optimized(question)
        else:
            logger.info(" Complex query detected - using full agent")
            result = self._execute_with_agent(question)
        
        return result
    

    @observe(as_type="span")
    def _execute_optimized(self, question: str) -> str:
        logger.info("=" * 80)
        logger.info("OPTIMIZED SQL EXECUTION:")
        logger.info("=" * 80)
        
        # Track start time for SQL execution
        start_time = time.time()
        
        try:
            sql_query = None
            api_call_count = 0
            
            if question.strip().lower().startswith('select'):
                logger.info(" Input is already SQL format, using directly")
                sql_query = question.strip()
                sql_query = sql_query.split('--')[0].strip()
                sql_query = sql_query.rstrip(';') + ';'
            else:
                sql_query = self._generate_sql(question)
                api_call_count += 1
            
            # Update Langfuse trace with generated SQL
            if langfuse_context:
                try:
                    langfuse_context.update_current_observation(
                        input=question,
                        metadata={
                            "generated_sql": sql_query[:500],
                            "execution_type": "optimized"
                        }
                    )
                except Exception:
                    pass
            
            # Validate SQL with reflection loop
            sql_query, validation_retries = self._validate_and_fix_sql(question, sql_query)
            api_call_count += validation_retries
            
            logger.info(f" SQL to execute: {sql_query[:200]}...")
            
            # Still run the regex safety check as a final fail-safe
            if not self._validate_sql_query(sql_query):
                logger.warning("  Final SQL validation failed, falling back to agent")
                return self._execute_with_agent(question)
            
            # Execute SQL (CachedSQLDatabase will intercept and cache this transparently)
            logger.info(" Executing SQL query via CachedSQLDatabase")
            sql_start = time.time()
            result_raw = self.db.run(sql_query)
            result = str(result_raw)
            sql_duration_ms = (time.time() - sql_start) * 1000
            
            logger.info(f" Query result: {result[:500]}...")
            
            # Update Langfuse with SQL execution metrics
            if langfuse_context:
                try:
                    langfuse_context.update_current_observation(
                        metadata={
                            "sql_execution_time_ms": sql_duration_ms,
                            "result_length": len(str(result)),
                            "final_sql": sql_query
                        }
                    )
                except Exception:
                    pass
            
            # Format response using FAST model
            output = self._format_response(question, sql_query, result)
            api_call_count += 1
            
            total_duration_ms = (time.time() - start_time) * 1000
            logger.info("=" * 80)
            logger.info(f" Optimized execution completed with {api_call_count} API call(s)")
            logger.info(f" Total duration: {total_duration_ms:.0f}ms, SQL execution: {sql_duration_ms:.0f}ms")
            logger.info(f" Final Answer: {output[:300]}...")
            logger.info("=" * 80)
            
            # Final Langfuse update
            if langfuse_context:
                try:
                    langfuse_context.update_current_observation(
                        output=output[:500],
                        metadata={
                            "total_duration_ms": total_duration_ms,
                            "api_calls": api_call_count
                        }
                    )
                except Exception:
                    pass
            
            return output
            
        except Exception as e:
            logger.warning(f"  Optimized execution failed: {e}. Falling back to full agent.")
            logger.error(f"Error details: {str(e)}", exc_info=True)
            return self._execute_with_agent(question)

    @observe(as_type="span", name="generate_sql")
    def _generate_sql(self, question: str) -> str:
        """Generate SQL query from natural language question using fast model."""
        logger.info(" API Call: Generate SQL query with targeted schema")
        
        relevant_schema = self._get_relevant_schema(question)
        system_prompt_rules = self._get_active_system_prompt_rules()
        
        prompt = f"""You are a PostgreSQL expert. Generate ONLY a SQL query to answer the question.

{system_prompt_rules}

DATABASE SCHEMA:
{relevant_schema}

IMPORTANT RULES:
1. Use ONLY the exact column names shown in the schema above
2. Use ONLY the exact table names shown in the schema above
3. Study the sample rows to understand the data
4. Identify primary and foreign key relationships from column names
5. Use proper date filtering: WHERE date_column >= 'YYYY-MM-DD' AND date_column <= 'YYYY-MM-DD'
6. ALWAYS filter by is_active = true AND is_deleted = false unless explicitly asked otherwise

QUESTION: {question}

Return ONLY the SQL query, no markdown, no explanation, no comments.

SQL Query:"""

        response = self.llm_fast.invoke(prompt)
        sql_query = response.content.strip()
        sql_query = re.sub(r'```sql\n?', '', sql_query)
        sql_query = re.sub(r'```\n?', '', sql_query)
        return sql_query.strip()

    @observe(as_type="span", name="validate_sql")
    def _validate_and_fix_sql(self, question: str, sql_query: str) -> tuple:
        """Validate SQL and fix if needed. Returns (sql_query, retry_count)."""
        logger.info(f"Initial SQL generated: {sql_query[:100]}...")
        
        relevant_schema = self._get_relevant_schema(question)
        max_retries = 2
        current_try = 0
        retry_count = 0
        critique_feedback = ""  # Initialize before the loop
        
        while current_try <= max_retries:
            if current_try > 0:
                logger.warning(f"Retry attempt {current_try}/{max_retries}")
                retry_count += 1
                
                # Fix SQL based on critique
                fix_prompt = f"""The previous SQL query was invalid. Fix it based on the critique.

DATABASE SCHEMA:
{relevant_schema}

CRITIQUE:
{critique_feedback}

ORIGINAL QUESTION: {question}

PREVIOUS SQL: {sql_query}

Return ONLY the corrected SQL query."""
                
                response = self.llm_fast.invoke(fix_prompt)
                sql_query = response.content.strip()
                sql_query = re.sub(r'```sql\n?', '', sql_query)
                sql_query = re.sub(r'```\n?', '', sql_query)
                sql_query = sql_query.strip()
                logger.info(f"Fixed SQL: {sql_query[:100]}...")

            # Validate with Critique Service
            critique = self.critique_service.critique_sql(
                question=question,
                sql_query=sql_query,
                schema_context=relevant_schema
            )
            
            if critique.is_valid:
                logger.info("SQL validated successfully via reflection")
                return sql_query, retry_count
            else:
                critique_feedback = "; ".join(critique.issues)
                current_try += 1
        
        logger.warning("SQL failed validation after retries. Proceeding with safety check.")
        return sql_query, retry_count

    @observe(as_type="span", name="format_response")
    def _format_response(self, question: str, sql_query: str, result: str) -> str:
        """Format SQL result into natural language response with chart. Uses FAST model."""
        logger.info(" API Call: Format natural language response (using gpt-3.5-turbo)")
        
        format_prompt = f"""Convert this database result into a clear, natural language answer.
Also, generate a JSON chart specification for visualization.

SQL Query: {sql_query}
Result: {result}

Original question: {question}

RESPOND WITH A CHART JSON:
1. First, provide a concise natural language answer explaining the data.
2. Then, you MUST append a JSON code block with chart data.
   - NEVER skip this step if you have data.

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

CHART TYPE SELECTION GUIDE (choose the most appropriate):

1. **"gauge"** - For percentage/rate metrics against targets:
   - Coverage rates, control rates, achievement percentages
   - Example: "What is the diabetes control rate?" → gauge with value, target
   - Extra fields: "value": 75, "target": 80, "min": 0, "max": 100

2. **"funnel"** - For care cascades and sequential dropoff:
   - Patient journey stages, screening → diagnosis → treatment → controlled
   - Example: "Show the NCD care cascade" → funnel
   - Data should be ordered from largest to smallest stage

3. **"bullet"** - For multiple KPIs vs targets:
   - Facility performance comparisons, multiple metrics vs goals
   - Example: "Compare facility screening rates vs targets"
   - Extra fields: "target": 80, "ranges": [30, 70, 100]

4. **"horizontal_bar"** - For rankings and comparisons:
   - Top/bottom performers, district rankings
   - Example: "Which districts have highest cases?" → horizontal_bar

5. **"bar"** - For categorical comparisons:
   - Breakdowns by age group, gender, category
   - Example: "Breakdown by age group" → bar

6. **"pie"** - For proportions/distributions:
   - Gender distribution, percentage breakdowns
   - Example: "What percentage are male vs female?" → pie

7. **"line"** - For trends over time:
   - Monthly/yearly trends, time series
   - Example: "Show monthly trend of screenings" → line

8. **"scorecard"** - For single KPI values:
   - Total counts, single metrics
   - Example: "Total number of patients" → scorecard

9. **"treemap"** - For hierarchical/regional breakdowns:
   - Regional distributions, nested categories
   - Example: "Distribution by region and district" → treemap

Response:"""

        # OPTIMIZATION: Use fast model (gpt-3.5-turbo) for response formatting
        formatted_response = self.llm_fast.invoke(format_prompt)
        return formatted_response.content.strip()

    def _validate_sql_query(self, sql_query: str) -> bool:
        sql_lower = sql_query.lower().strip()
        
        if not sql_lower.startswith('select'):
            logger.warning("Query doesn't start with SELECT")
            return False
        
        # Check for dangerous keywords as WHOLE WORDS only (not substrings)
        # This prevents false positives like 'is_deleted' triggering on 'delete'
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter', 'create', 'insert', 'update', 'exec']
        for keyword in dangerous_keywords:
            # Match keyword as a whole word using word boundaries
            if re.search(rf'\b{keyword}\b', sql_lower):
                # Exception: 'is_deleted' column is safe
                if keyword == 'delete' and 'is_deleted' in sql_lower:
                    continue
                logger.warning(f"Query contains dangerous keyword: {keyword}")
                return False
        
        if self.relevant_tables:
            has_known_table = any(table.lower() in sql_lower for table in self.relevant_tables)
            if not has_known_table:
                logger.warning("Query doesn't reference any known tables")
                return False
        
        if 'from' not in sql_lower:
            logger.warning("Query missing FROM clause")
            return False
        
        return True
    
    @observe
    def _execute_with_agent(self, question: str) -> str:
        logger.info("=" * 80)
        logger.info(" SQL AGENT EXECUTION TRACE:")
        logger.info("=" * 80)
        
        try:
            result = self.sql_agent.invoke({"input": question})
            
            if isinstance(result, dict):
                output = result.get("output", str(result))
                
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
        try:
            self.db.run("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_table_info(self) -> str:
        try:
            return self.db.get_table_info()
        except Exception as e:
            logger.error(f"Failed to get table info: {e}")
            return "Error retrieving table information"

    def get_schema_info_for_connection(self, uri: str, table_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Connect to a database URI and retrieve its schema (tables and columns).
        Used for the frontend Schema Explorer and Embedding Generator.
        
        Args:
            uri: Database connection URI
            table_names: Optional list of tables to inspect. If None, fetches all.
        """
        try:
            from backend.core.db_pool import get_cached_engine
            from sqlalchemy import text
            
            # Extract engine using connection pooling wrapper
            engine = get_cached_engine(
                uri,
                pool_size=5, 
                max_overflow=10
            )
            
            all_table_names = []
            
            # Get table names without triggering full reflection
            with engine.connect() as conn:
                # Query for tables across all accessible schemas
                try:
                    tables_result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.tables 
                        WHERE table_type = 'BASE TABLE'
                        AND table_schema NOT IN ('pg_catalog', 'information_schema')
                        ORDER BY table_schema, table_name
                    """))
                    tables_with_schema = [(row[0], row[1]) for row in tables_result]
                    
                    views_result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.views 
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                        ORDER BY table_schema, table_name
                    """))
                    views_with_schema = [(row[0], row[1]) for row in views_result]
                    
                    all_objects = tables_with_schema + views_with_schema
                    all_table_names = [obj[1] for obj in all_objects]
                    
                except Exception as e:
                    logger.warning(f"information_schema query failed: {e}")
                
                # Fallback to pg_class if information_schema didn't work
                if not all_table_names:
                    try:
                        result = conn.execute(text("""
                            SELECT c.relname 
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relkind IN ('r', 'v')
                            AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                            AND has_table_privilege(c.oid, 'SELECT')
                            ORDER BY c.relname
                        """))
                        all_table_names = [row[0] for row in result]
                    except Exception as e2:
                        logger.warning(f"pg_class fallback also failed: {e2}")
            
            # If explicit tables requested, filter to only those that exist
            if table_names:
                target_tables = [t for t in table_names if t in all_table_names]
            else:
                target_tables = all_table_names
            
            schema_info = {}
            inspector = inspect(engine)
            
            for table in target_tables:
                try:
                    # Get column info
                    columns = inspector.get_columns(table)
                    
                    column_details = []
                    for col in columns:
                        column_details.append({
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True)
                        })
                    
                    schema_info[table] = column_details
                except Exception as e:
                    logger.warning(f"Could not get columns for table {table}: {e}")
                    schema_info[table] = []
            
            # engine.dispose() # DO NOT DISPOSE CACHED ENGINE
            return {"tables": target_tables, "details": schema_info}
            
        except Exception as e:
            logger.error(f"Failed to inspect schema for URI {uri}: {e}")
            raise ValueError(f"Could not connect or inspect database: {str(e)}")

@lru_cache()
def get_sql_service() -> SQLService:
    return SQLService()

