"""
SQL service for structured database queries.
Wraps LangChain SQL agent for database interactions.
"""
from functools import lru_cache
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import re

from sqlalchemy import inspect
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.services.reflection_service import get_critique_service


settings = get_settings()
logger = get_logger(__name__)


def _get_active_database_url() -> str:
    """
    Get the database URL from the active published config.
    Falls back to settings.database_url if no active config or connection.
    """
    try:
        from backend.sqliteDb.db import get_db_service
        db_service = get_db_service()
        
        # Get active config
        active_config = db_service.get_active_config()
        if active_config and active_config.get('connection_id'):
            connection_id = active_config['connection_id']
            connection = db_service.get_db_connection_by_id(connection_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection from active config: {connection.get('name')} (ID: {connection_id})")
                return connection['uri']
        
        logger.info("No active config connection found, using default database URL")
        return settings.database_url
        
    except Exception as e:
        logger.warning(f"Failed to get active database URL: {e}. Using default.")
        return settings.database_url


class SQLService:
    """Service for SQL database operations."""
    
    def __init__(self, database_url: Optional[str] = None):
        # Use provided URL, or get from active config, or fall back to settings
        if database_url:
            self._database_url = database_url
        else:
            self._database_url = _get_active_database_url()
            
        logger.info(f"Connecting to database at {self._database_url}")
        
        try:
            # Initialize critique service
            self.critique_service = get_critique_service()

            # Check if patient_tracker exists to determine if we should ignore demo 'patient' table
            # First, create a temporary connection to check tables
            temp_db = SQLDatabase.from_uri(self._database_url, view_support=True)
            all_tables = temp_db.get_usable_table_names()
            
            # Determine tables to ignore (demo tables that shouldn't be used)
            ignore_tables = []
            if 'patient_tracker' in all_tables and 'patient' in all_tables:
                ignore_tables.append('patient')
                logger.info("Will ignore demo 'patient' table - using 'patient_tracker' for patient data")

            # Initialize database connection with dynamic table discovery
            # No hardcoded view names - uses whatever tables/views exist in the database
            self.db = SQLDatabase.from_uri(
                self._database_url,
                view_support=True,
                ignore_tables=ignore_tables if ignore_tables else None
            )
            logger.info("Database connection established with view support")
            
            self._cache_schema()
            
            self.llm_fast = ChatOpenAI(
                temperature=0,
                model_name="gpt-3.5-turbo",
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.llm = ChatOpenAI(
                temperature=settings.openai_temperature,
                model_name=settings.openai_model,
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=self.db,
                agent_type="openai-tools",
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=8,
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
    
    def query(self, question: str) -> str:
        logger.info(f"Executing SQL query for: '{question[:100]}...'")
        
        # KPI template matching disabled by domain-agnostic refactor
        # kpi_match = self._check_dashboard_kpi(question)
        # if kpi_match:
        #     sql_query, description = kpi_match
        #     logger.info(f"Using pre-defined KPI template for: {description}")
        #     return self._execute_kpi_template(sql_query, description, question)
        
        if self._is_simple_query(question):
            logger.info(" Detected simple query - using optimized execution path")
            return self._execute_optimized(question)
        else:
            logger.info(" Complex query detected - using full agent")
            return self._execute_with_agent(question)
    

    
    def _execute_optimized(self, question: str) -> str:
        logger.info("=" * 80)
        logger.info("OPTIMIZED SQL EXECUTION:")
        logger.info("=" * 80)
        
        try:
            sql_query = None
            api_call_count = 0
            
            if question.strip().lower().startswith('select'):
                logger.info(" Input is already SQL format, using directly")
                sql_query = question.strip()
                sql_query = sql_query.split('--')[0].strip()
                sql_query = sql_query.rstrip(';') + ';'
            else:
                logger.info(" API Call 1: Generate SQL query with targeted schema")
                api_call_count += 1
                
                relevant_schema = self._get_relevant_schema(question)
                
                # Fetch active system prompt for domain-specific rules
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
                
                sql_query = re.sub(r'```\n?', '', sql_query)
                sql_query = sql_query.strip()
            
            # =================================================================
            # REFLECTION LOOP: Validate and Fix SQL Algorithm
            # =================================================================
            logger.info(f"Initial SQL generated: {sql_query[:100]}...")
            
            max_retries = 2
            current_try = 0
            is_valid = False
            critique_feedback = ""
            
            while current_try <= max_retries:
                if current_try > 0:
                    logger.warning(f"Retry attempt {current_try}/{max_retries} due to critique: {critique_feedback}")
                    
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
                # We need the full schema context for critique, or at least the relevant part
                critique = self.critique_service.critique_sql(
                    question=question,
                    sql_query=sql_query,
                    schema_context=relevant_schema
                )
                
                if critique.is_valid:
                    logger.info("SQL validated successfully via reflection")
                    is_valid = True
                    break
                else:
                    critique_feedback = "; ".join(critique.issues)
                    current_try += 1
            
            if not is_valid:
                logger.warning("SQL failed validation after retries. Executing strict safety check fallback.")
            
            logger.info(f" SQL to execute: {sql_query[:200]}...")
            
            # Still run the regex safety check as a final fail-safe
            if not self._validate_sql_query(sql_query):
                logger.warning("  Final SQL validation failed, falling back to agent")
                return self._execute_with_agent(question)
            
            logger.info(" Executing query against database (no API call)")
            result = self.db.run(sql_query)
            logger.info(f" Query result: {result}")
            
            logger.info(f" API Call {api_call_count + 1}: Format natural language response")
            api_call_count += 1
            
            format_prompt = f"""Convert this database result into a clear, natural language answer.
Also, generate a JSON chart specification if the data is suitable for visualization.

SQL Query: {sql_query}
Result: {result}

Original question: {question}

RESPONSE FORMAT:
1. First, provide a concise natural language answer explaining the data.
2. Then, you MUST append a JSON code block with chart data if the result is a number, a count, an average, or a list of values.

Format:
```json
{{
    "chart_json": {{
        "title": "Descriptive Chart Title",
        "type": "pie|bar|line|scorecard",
        "data": {{
            "labels": ["Label1", "Label2"],
            "values": [100, 200]
        }},
        "metrics": [   // REQUIRED for 'scorecard' type, optional otherwise
            {{ "label": "Metric Name", "value": 123, "change": "+5% vs last month", "status": "up" }}
        ]
    }}
}}
```

Chart type guidelines:
- Use "pie" for: distributions, proportions, percentages (2-6 categories)
- Use "bar" for: comparisons, counts by category, rankings
- Use "line" for: trends over time
- Use "scorecard" for: single numeric values (counts, averages, sums) or highly aggregated KPIs. 
  For example, if the result is just [(8322,)], make a scorecard with label="Total Patients" and value=8322.

Response:"""

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
            # Create a temporary connection
            temp_db = SQLDatabase.from_uri(uri)
            
            # If explicit tables requested, use those. Otherwise discover all.
            if table_names:
                all_tables = temp_db.get_usable_table_names()
                # Filter to only those that actually exist
                target_tables = [t for t in table_names if t in all_tables]
            else:
                target_tables = temp_db.get_usable_table_names()
            
            schema_info = {}
            inspector = inspect(temp_db._engine)
            
            for table in target_tables:
                # Get column info
                columns = inspector.get_columns(table)
                
                column_details = []
                for col in columns:
                    column_details.append({
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True)
                    })
                
                # Get FK info if possible (useful for graph relationships)
                try:
                    fks = inspector.get_foreign_keys(table)
                    # Enrich column details with FK info? 
                    # For now just store columns as generator expects
                except:
                    pass
                
                schema_info[table] = column_details
                
            return {"tables": target_tables, "details": schema_info}
            
        except Exception as e:
            logger.error(f"Failed to inspect schema for URI {uri}: {e}")
            raise ValueError(f"Could not connect or inspect database: {str(e)}")

@lru_cache()
def get_sql_service() -> SQLService:
    return SQLService()

