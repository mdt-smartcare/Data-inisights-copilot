"""
File Query Service - Unified query interface for uploaded file data.

Integrates Intent Router, Text-to-SQL, and RAG for optimal query handling on 6.5M+ row datasets.

Query Flow:
1. Intent Router classifies query (SQL vs RAG vs Hybrid)
2. SQL Engine: DuckDB for structured queries (milliseconds)
3. RAG Engine: Vector search for semantic queries on text columns
4. **Agentic Hybrid**: RAG finds IDs -> SQL aggregates on those IDs -> LLM synthesizes

The Agentic Hybrid Workflow (Gold Standard):
===============================================
User: "Find the average heart rate of patients with clinical notes mentioning 'severe chronic migraines'"

Step 1 (RAG): Search ChromaDB for "severe chronic migraines" -> Returns 500 Patient_IDs
Step 2 (SQL): Generate SQL with those IDs:
              SELECT Patient_ID, AVG(Heart_Rate) FROM patients 
              WHERE Patient_ID IN (1, 2, 3...) GROUP BY Patient_ID
Step 3 (Synthesis): DuckDB executes instantly, LLM formats final response
"""

import asyncio
import logging
import time
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from backend.pipeline.ingestion.intent_router import (
    QueryIntent,
    get_intent_router,
)
from backend.services.file_sql_service import FileSQLService, get_file_sql_service

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Unified result from file query service."""
    status: str
    query_type: str  # 'sql', 'rag', 'hybrid', 'agentic_hybrid'
    intent: str
    confidence: float
    
    # SQL results
    sql_answer: Optional[str] = None
    sql_query: Optional[str] = None
    sql_rows: Optional[List[Dict]] = None
    sql_execution_ms: Optional[float] = None
    
    # RAG results
    rag_answer: Optional[str] = None
    rag_documents: Optional[List[Dict]] = None
    rag_sources: Optional[List[str]] = None
    rag_matched_ids: Optional[List[str]] = None  # IDs from RAG for agentic workflow
    
    # Combined answer for hybrid
    final_answer: Optional[str] = None
    
    # Agentic workflow metadata
    workflow_steps: Optional[List[Dict[str, Any]]] = None
    total_execution_ms: Optional[float] = None
    
    # Metadata
    routing_reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AgenticWorkflowStep:
    """A single step in the agentic hybrid workflow."""
    step_number: int
    step_type: str  # 'rag_search', 'sql_generation', 'sql_execution', 'synthesis'
    description: str
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    execution_ms: float = 0.0
    status: str = "pending"


class FileQueryService:
    """
    Unified query service for uploaded file data.
    
    Automatically routes queries to the optimal engine:
    - "How many patients have diabetes?" -> SQL (COUNT, instant)
    - "Find patients with chronic migraine symptoms" -> RAG (semantic search)
    - "Average age of patients mentioning chest pain" -> **Agentic Hybrid** (RAG -> SQL -> Synthesis)
    
    The Agentic Hybrid is the GOLD STANDARD for complex queries on 6.5M+ rows.
    """
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.intent_router = get_intent_router()
        self._sql_service: Optional[FileSQLService] = None
        self._rag_pipeline = None
        self._rag_tables: Optional[List[str]] = None
        self._rag_config: Optional[Dict[str, Any]] = None
    
    @property
    def sql_service(self) -> FileSQLService:
        """Lazy initialization of SQL service."""
        if self._sql_service is None:
            self._sql_service = get_file_sql_service(self.user_id)
        return self._sql_service
    
    @property
    def rag_pipeline(self):
        """Lazy initialization of RAG pipeline."""
        if self._rag_pipeline is None:
            from backend.pipeline.file_rag_pipeline import get_file_rag_pipeline
            self._rag_pipeline = get_file_rag_pipeline(self.user_id)
        return self._rag_pipeline
    
    def _get_schema_context(self) -> str:
        """Get schema context for intent routing."""
        try:
            schema = self.sql_service.get_schema()
            return schema.get("schema_text", "")
        except Exception:
            return ""
    
    def _get_rag_config(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get RAG configuration for a table (cached)."""
        try:
            import duckdb
            from backend.api.routes.ingestion import _get_user_duckdb_path
            
            db_path = _get_user_duckdb_path(self.user_id)
            if not db_path.exists():
                return None
            
            conn = duckdb.connect(str(db_path), read_only=True)
            result = conn.execute("""
                SELECT text_columns, id_column, status
                FROM _rag_config WHERE table_name = ?
            """, [table_name]).fetchone()
            conn.close()
            
            if result and result[2] == "ready":
                import json
                return {
                    "text_columns": json.loads(result[0]) if result[0] else [],
                    "id_column": result[1],
                    "status": result[2],
                }
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get RAG config for {table_name}: {e}")
            return None
    
    def _get_rag_enabled_tables(self) -> List[str]:
        """Get list of tables that have RAG embeddings."""
        if self._rag_tables is not None:
            return self._rag_tables
        
        try:
            from backend.api.routes.ingestion import _get_user_data_dir
            import chromadb
            from chromadb.config import Settings
            
            user_dir = _get_user_data_dir(self.user_id)
            chroma_path = user_dir / "chroma_db"
            
            if not chroma_path.exists():
                self._rag_tables = []
                return []
            
            chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
            
            collections = chroma_client.list_collections()
            self._rag_tables = [
                c.name.replace("file_rag_", "") 
                for c in collections 
                if c.name.startswith("file_rag_")
            ]
            
            return self._rag_tables
            
        except Exception as e:
            logger.warning(f"Failed to get RAG-enabled tables: {e}")
            self._rag_tables = []
            return []

    # =========================================================================
    # AGENTIC HYBRID WORKFLOW - The Gold Standard
    # =========================================================================
    
    def _execute_agentic_hybrid(
        self,
        question: str,
        sql_hints: List[str],
        rag_hints: List[str],
    ) -> Dict[str, Any]:
        """
        Execute the Agentic Hybrid Workflow (Gold Standard for 6.5M+ rows).
        
        Workflow:
        1. RAG Search: Find IDs matching semantic criteria in text columns
        2. SQL Generation: Build query using those IDs with aggregations
        3. SQL Execution: DuckDB executes instantly on filtered subset
        4. LLM Synthesis: Format final answer with both contexts
        """
        workflow_steps = []
        start_time = time.time()
        
        # STEP 1: RAG Search - Find matching IDs from semantic search
        step1_start = time.time()
        step1 = AgenticWorkflowStep(
            step_number=1,
            step_type="rag_search",
            description="Searching clinical notes for semantic matches",
        )
        
        rag_tables = self._get_rag_enabled_tables()
        if not rag_tables:
            return {
                "status": "rag_not_configured",
                "error": "No RAG embeddings configured. Enable RAG on text columns first.",
                "workflow_steps": [],
            }
        
        semantic_query = self._extract_semantic_query(question, rag_hints)
        
        matched_ids = []
        rag_documents = []
        id_column = "patient_id"
        primary_table = None
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for table_name in rag_tables:
                try:
                    rag_config = self._get_rag_config(table_name)
                    if rag_config:
                        id_column = rag_config.get("id_column", "patient_id")
                        primary_table = table_name
                    
                    results = loop.run_until_complete(
                        self.rag_pipeline.semantic_search(
                            query=semantic_query,
                            table_name=table_name,
                            top_k=500,
                            return_parents=True,
                        )
                    )
                    
                    for r in results:
                        r["source_table"] = table_name
                        row_id = r.get("source_row_id")
                        if row_id and row_id not in matched_ids:
                            matched_ids.append(row_id)
                    
                    rag_documents.extend(results)
                    
                except Exception as e:
                    logger.warning(f"RAG search failed for {table_name}: {e}")
                    continue
        finally:
            loop.close()
        
        step1.execution_ms = (time.time() - step1_start) * 1000
        step1.status = "success" if matched_ids else "no_matches"
        step1.output_data = {
            "matched_ids_count": len(matched_ids),
            "semantic_query": semantic_query,
            "tables_searched": rag_tables,
            "sample_ids": matched_ids[:10],
        }
        workflow_steps.append(step1.__dict__)
        
        if not matched_ids:
            return {
                "status": "no_semantic_matches",
                "final_answer": f"No clinical notes found matching '{semantic_query}'.",
                "workflow_steps": workflow_steps,
                "rag_documents": [],
                "matched_ids": [],
            }
        
        logger.info(f"Agentic Step 1: RAG found {len(matched_ids)} matching IDs")
        
        # STEP 2: SQL Generation - Build query with matched IDs
        step2_start = time.time()
        step2 = AgenticWorkflowStep(
            step_number=2,
            step_type="sql_generation",
            description=f"Generating SQL query filtered to {len(matched_ids)} matched IDs",
        )
        
        sql_query = self._generate_filtered_sql(
            question=question,
            matched_ids=matched_ids,
            id_column=id_column,
            table_name=primary_table or rag_tables[0],
            sql_hints=sql_hints,
        )
        
        step2.execution_ms = (time.time() - step2_start) * 1000
        step2.status = "success" if sql_query else "failed"
        step2.input_data = {"matched_ids_count": len(matched_ids), "id_column": id_column}
        step2.output_data = {"generated_sql": sql_query}
        workflow_steps.append(step2.__dict__)
        
        if not sql_query:
            return {
                "status": "partial_success",
                "final_answer": self._format_rag_answer(question, rag_documents[:10]),
                "workflow_steps": workflow_steps,
                "rag_documents": rag_documents[:10],
                "matched_ids": matched_ids,
            }
        
        logger.info(f"Agentic Step 2: Generated SQL: {sql_query[:200]}...")
        
        # STEP 3: SQL Execution - DuckDB executes filtered query
        step3_start = time.time()
        step3 = AgenticWorkflowStep(
            step_number=3,
            step_type="sql_execution",
            description="Executing SQL on DuckDB (filtered to RAG matches)",
        )
        
        sql_result = self._execute_raw_sql(sql_query)
        
        step3.execution_ms = (time.time() - step3_start) * 1000
        step3.status = sql_result.get("status", "error")
        step3.output_data = {
            "row_count": len(sql_result.get("rows", [])),
            "columns": sql_result.get("columns", []),
        }
        workflow_steps.append(step3.__dict__)
        
        logger.info(f"Agentic Step 3: SQL returned {len(sql_result.get('rows', []))} rows")
        
        # STEP 4: LLM Synthesis - Combine RAG context + SQL results
        step4_start = time.time()
        step4 = AgenticWorkflowStep(
            step_number=4,
            step_type="synthesis",
            description="Synthesizing final answer from RAG and SQL results",
        )
        
        final_answer = self._synthesize_agentic_answer(
            question=question,
            semantic_query=semantic_query,
            matched_ids=matched_ids,
            rag_documents=rag_documents[:5],
            sql_result=sql_result,
        )
        
        step4.execution_ms = (time.time() - step4_start) * 1000
        step4.status = "success"
        workflow_steps.append(step4.__dict__)
        
        total_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "success",
            "query_type": "agentic_hybrid",
            "final_answer": final_answer,
            "sql_query": sql_query,
            "sql_rows": sql_result.get("rows", []),
            "sql_columns": sql_result.get("columns", []),
            "rag_documents": rag_documents[:10],
            "matched_ids": matched_ids,
            "matched_ids_count": len(matched_ids),
            "workflow_steps": workflow_steps,
            "total_execution_ms": round(total_ms, 2),
        }
    
    def _extract_semantic_query(self, question: str, rag_hints: List[str]) -> str:
        """Extract the semantic search component from a hybrid question."""
        # Look for quoted phrases first
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", question)
        if quoted:
            return " ".join(quoted)
        
        # Look for common semantic patterns
        semantic_patterns = [
            r"mentioning\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"with notes about\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"clinical notes?\s+(?:about|mentioning|containing)\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"notes?\s+(?:about|mentioning|containing)\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"history of\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"symptoms?\s+(?:of|like|including)\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"diagnosed with\s+(.+?)(?:\s+and|\s+or|\s*$)",
            r"suffering from\s+(.+?)(?:\s+and|\s+or|\s*$)",
        ]
        
        for pattern in semantic_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        if rag_hints:
            return " ".join(rag_hints)
        
        return question
    
    def _generate_filtered_sql(
        self,
        question: str,
        matched_ids: List[str],
        id_column: str,
        table_name: str,
        sql_hints: List[str],
    ) -> Optional[str]:
        """Generate SQL query filtered to RAG-matched IDs."""
        try:
            from langchain_openai import ChatOpenAI
            from backend.config import get_settings
            
            settings = get_settings()
            
            if not settings.openai_api_key:
                return self._generate_fallback_sql(
                    matched_ids, id_column, table_name, sql_hints
                )
            
            llm = ChatOpenAI(
                temperature=0,
                model_name="gpt-4o-mini",
                api_key=settings.openai_api_key,
            )
            
            schema_context = self._get_schema_context()
            
            max_ids = 1000
            ids_for_sql = matched_ids[:max_ids]
            ids_str = ", ".join(f"'{id}'" for id in ids_for_sql)
            
            prompt = f"""Generate a SQL query for DuckDB based on this question.

IMPORTANT: The semantic search has already identified {len(matched_ids)} matching records.
You MUST filter using: WHERE {id_column} IN ({ids_str[:500]}{'...' if len(ids_str) > 500 else ''})

User Question: {question}

Database Schema:
{schema_context}

Requirements:
1. MUST include the WHERE {id_column} IN (...) clause with the provided IDs
2. Focus on the aggregation/calculation part of the question (AVG, COUNT, SUM, etc.)
3. Return only the SQL query, no explanations
4. Use table name: {table_name}

SQL Query:"""

            response = llm.invoke(prompt)
            sql = response.content.strip()
            sql = sql.replace("```sql", "").replace("```", "").strip()
            
            # Ensure ID filter is present
            if id_column.upper() not in sql.upper() or "IN" not in sql.upper():
                if "WHERE" in sql.upper():
                    sql = sql.replace("WHERE", f"WHERE {id_column} IN ({ids_str}) AND", 1)
                else:
                    for keyword in ["GROUP BY", "ORDER BY", "LIMIT"]:
                        if keyword in sql.upper():
                            idx = sql.upper().index(keyword)
                            sql = sql[:idx] + f" WHERE {id_column} IN ({ids_str}) " + sql[idx:]
                            break
                    else:
                        sql = sql.rstrip(";") + f" WHERE {id_column} IN ({ids_str})"
            
            return sql
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return self._generate_fallback_sql(matched_ids, id_column, table_name, sql_hints)
    
    def _generate_fallback_sql(
        self,
        matched_ids: List[str],
        id_column: str,
        table_name: str,
        sql_hints: List[str],
    ) -> str:
        """Generate a simple fallback SQL without LLM."""
        ids_str = ", ".join(f"'{id}'" for id in matched_ids[:1000])
        
        if any(hint in ["average", "avg", "mean"] for hint in sql_hints):
            return f"SELECT {id_column}, AVG(*) FROM {table_name} WHERE {id_column} IN ({ids_str}) GROUP BY {id_column}"
        elif any(hint in ["count", "total", "number"] for hint in sql_hints):
            return f"SELECT COUNT(*) as count FROM {table_name} WHERE {id_column} IN ({ids_str})"
        else:
            return f"SELECT * FROM {table_name} WHERE {id_column} IN ({ids_str}) LIMIT 100"
    
    def _execute_raw_sql(self, sql: str) -> Dict[str, Any]:
        """Execute raw SQL query using DuckDB."""
        try:
            import duckdb
            from backend.api.routes.ingestion import _get_user_duckdb_path
            
            db_path = _get_user_duckdb_path(self.user_id)
            conn = duckdb.connect(str(db_path), read_only=True)
            
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows_data = result.fetchmany(10000)
            conn.close()
            
            rows = []
            for row in rows_data:
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
            
            return {"status": "success", "columns": columns, "rows": rows}
            
        except Exception as e:
            logger.error(f"Raw SQL execution failed: {e}")
            return {"status": "error", "error": str(e), "columns": [], "rows": []}
    
    def _synthesize_agentic_answer(
        self,
        question: str,
        semantic_query: str,
        matched_ids: List[str],
        rag_documents: List[Dict],
        sql_result: Dict[str, Any],
    ) -> str:
        """Synthesize final answer combining RAG context and SQL results."""
        try:
            from langchain_openai import ChatOpenAI
            from backend.config import get_settings
            
            settings = get_settings()
            
            if not settings.openai_api_key:
                return self._format_fallback_answer(
                    semantic_query, matched_ids, rag_documents, sql_result
                )
            
            llm = ChatOpenAI(
                temperature=0.3,
                model_name="gpt-4o-mini",
                api_key=settings.openai_api_key,
            )
            
            rag_context = ""
            if rag_documents:
                rag_parts = []
                for i, doc in enumerate(rag_documents[:3], 1):
                    content = doc.get("parent_content") or doc.get("child_content", "")
                    row_id = doc.get("source_row_id", "?")
                    rag_parts.append(f"[Patient {row_id}]: {content[:300]}...")
                rag_context = "\n".join(rag_parts)
            
            sql_context = ""
            if sql_result.get("status") == "success":
                rows = sql_result.get("rows", [])
                if rows:
                    sql_context = f"SQL Results ({len(rows)} rows):\n"
                    for row in rows[:10]:
                        sql_context += f"  {row}\n"
                    if len(rows) > 10:
                        sql_context += f"  ... and {len(rows) - 10} more rows"
            
            prompt = f"""Synthesize a comprehensive answer to the user's question based on the analysis results.

User Question: {question}

ANALYSIS RESULTS:

1. Semantic Search (found {len(matched_ids)} patients with "{semantic_query}"):
{rag_context if rag_context else "No document excerpts available."}

2. SQL Aggregation Results:
{sql_context if sql_context else "No SQL results available."}

Instructions:
- Provide a clear, direct answer to the question
- Include specific numbers/statistics from the SQL results
- Reference the clinical notes context where relevant
- Be concise but comprehensive

Answer:"""

            response = llm.invoke(prompt)
            return response.content
            
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}")
            return self._format_fallback_answer(
                semantic_query, matched_ids, rag_documents, sql_result
            )
    
    def _format_fallback_answer(
        self,
        semantic_query: str,
        matched_ids: List[str],
        rag_documents: List[Dict],
        sql_result: Dict[str, Any],
    ) -> str:
        """Format answer without LLM (fallback)."""
        parts = [f"**Analysis Results for '{semantic_query}'**\n"]
        parts.append(f"Found {len(matched_ids)} patients with matching clinical notes.\n")
        
        if sql_result.get("status") == "success":
            rows = sql_result.get("rows", [])
            if rows:
                parts.append(f"\n**SQL Results** ({len(rows)} rows):")
                for row in rows[:5]:
                    parts.append(f"  - {row}")
                if len(rows) > 5:
                    parts.append(f"  ... and {len(rows) - 5} more")
        
        if rag_documents:
            parts.append(f"\n**Sample Clinical Notes:**")
            for doc in rag_documents[:2]:
                content = doc.get("parent_content") or doc.get("child_content", "")
                row_id = doc.get("source_row_id", "?")
                parts.append(f"  [Patient {row_id}]: {content[:200]}...")
        
        return "\n".join(parts)

    # =========================================================================
    # STANDARD QUERY METHODS
    # =========================================================================
    
    def _execute_sql_query(self, question: str, hints: List[str]) -> Dict[str, Any]:
        """Execute SQL query using FileSQLService."""
        try:
            result = self.sql_service.query(question)
            return {
                "status": result.get("status", "error"),
                "answer": result.get("answer"),
                "sql": result.get("sql"),
                "rows": result.get("rows", []),
                "execution_ms": result.get("execution_time_ms"),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.error(f"SQL query failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _execute_rag_query(self, question: str, hints: List[str]) -> Dict[str, Any]:
        """Execute RAG semantic search against embedded text columns."""
        try:
            rag_tables = self._get_rag_enabled_tables()
            
            if not rag_tables:
                return {
                    "status": "not_configured",
                    "answer": "No text columns configured for semantic search.",
                    "documents": [],
                    "sources": [],
                }
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                all_results = []
                
                for table_name in rag_tables:
                    try:
                        results = loop.run_until_complete(
                            self.rag_pipeline.semantic_search(
                                query=question,
                                table_name=table_name,
                                top_k=10,
                                return_parents=True,
                            )
                        )
                        
                        for r in results:
                            r["source_table"] = table_name
                        all_results.extend(results)
                        
                    except Exception as e:
                        logger.warning(f"RAG search failed for {table_name}: {e}")
                        continue
                
                if not all_results:
                    return {
                        "status": "no_results",
                        "answer": "No relevant documents found.",
                        "documents": [],
                        "sources": [],
                    }
                
                all_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                top_results = all_results[:10]
                
                answer = self._format_rag_answer(question, top_results)
                sources = list(set(
                    f"{r.get('source_table')}.{r.get('source_column')} (row {r.get('source_row_id')})"
                    for r in top_results
                ))
                
                return {
                    "status": "success",
                    "answer": answer,
                    "documents": top_results,
                    "sources": sources,
                }
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            return {"status": "error", "error": str(e), "documents": [], "sources": []}
    
    def _format_rag_answer(self, question: str, results: List[Dict]) -> str:
        """Format RAG search results into a readable answer."""
        if not results:
            return "No relevant documents found."
        
        try:
            from langchain_openai import ChatOpenAI
            from backend.config import get_settings
            
            settings = get_settings()
            
            if settings.openai_api_key:
                llm = ChatOpenAI(
                    temperature=0,
                    model_name="gpt-3.5-turbo",
                    api_key=settings.openai_api_key,
                )
                
                context_parts = []
                for i, r in enumerate(results[:5], 1):
                    content = r.get("parent_content") or r.get("child_content", "")
                    row_id = r.get("source_row_id", "unknown")
                    score = r.get("similarity_score", 0)
                    context_parts.append(
                        f"[Document {i}] (Row: {row_id}, Relevance: {score:.2%})\n{content[:500]}"
                    )
                
                context = "\n\n".join(context_parts)
                
                prompt = f"""Based on the following clinical notes, answer the user's question.
Include specific details and cite which document/row the information comes from.

Question: {question}

Clinical Notes:
{context}

Answer:"""
                
                response = llm.invoke(prompt)
                return response.content
                
        except Exception as e:
            logger.warning(f"LLM answer synthesis failed: {e}")
        
        # Fallback
        answer_parts = [f"Found {len(results)} relevant clinical notes:\n"]
        for i, r in enumerate(results[:5], 1):
            content = r.get("parent_content") or r.get("child_content", "")
            row_id = r.get("source_row_id", "unknown")
            score = r.get("similarity_score", 0)
            if len(content) > 300:
                content = content[:300] + "..."
            answer_parts.append(f"\n**Result {i}** (Row {row_id}, {score:.0%} match):\n{content}")
        
        return "\n".join(answer_parts)
    
    def _execute_hybrid_query(
        self, 
        question: str, 
        sql_hints: List[str],
        rag_hints: List[str]
    ) -> Dict[str, Any]:
        """Execute hybrid query - NOW USES AGENTIC WORKFLOW."""
        return self._execute_agentic_hybrid(question, sql_hints, rag_hints)
    
    def query(self, question: str, use_llm_routing: bool = True) -> QueryResult:
        """Execute a query against uploaded file data."""
        question = question.strip()
        if not question:
            return QueryResult(
                status="error",
                query_type="none",
                intent="unknown",
                confidence=0.0,
                error="Empty question"
            )
        
        start_time = time.time()
        schema_context = self._get_schema_context()
        
        routing = self.intent_router.route(
            question, 
            schema_context=schema_context,
            use_llm=use_llm_routing
        )
        
        logger.info(
            f"Query routed: intent={routing.primary_intent.value}, "
            f"sql={routing.use_sql}, rag={routing.use_rag}"
        )
        
        # Execute based on routing decision
        if routing.primary_intent == QueryIntent.HYBRID or (routing.use_sql and routing.use_rag):
            # AGENTIC HYBRID - The Gold Standard
            result = self._execute_agentic_hybrid(
                question, 
                routing.sql_hints, 
                routing.rag_hints
            )
            
            total_ms = (time.time() - start_time) * 1000
            
            return QueryResult(
                status=result.get("status", "error"),
                query_type="agentic_hybrid",
                intent=routing.primary_intent.value,
                confidence=routing.confidence,
                sql_query=result.get("sql_query"),
                sql_rows=result.get("sql_rows"),
                sql_execution_ms=result.get("total_execution_ms"),
                rag_documents=result.get("rag_documents"),
                rag_matched_ids=result.get("matched_ids"),
                final_answer=result.get("final_answer"),
                workflow_steps=result.get("workflow_steps"),
                total_execution_ms=round(total_ms, 2),
                routing_reason=routing.reason,
                error=result.get("error"),
            )
        
        elif routing.use_sql:
            sql_result = self._execute_sql_query(question, routing.sql_hints)
            total_ms = (time.time() - start_time) * 1000
            
            return QueryResult(
                status=sql_result.get("status", "error"),
                query_type="sql",
                intent=routing.primary_intent.value,
                confidence=routing.confidence,
                sql_answer=sql_result.get("answer"),
                sql_query=sql_result.get("sql"),
                sql_rows=sql_result.get("rows"),
                sql_execution_ms=sql_result.get("execution_ms"),
                final_answer=sql_result.get("answer"),
                total_execution_ms=round(total_ms, 2),
                routing_reason=routing.reason,
                error=sql_result.get("error"),
            )
        
        elif routing.use_rag:
            rag_result = self._execute_rag_query(question, routing.rag_hints)
            total_ms = (time.time() - start_time) * 1000
            
            return QueryResult(
                status=rag_result.get("status", "error"),
                query_type="rag",
                intent=routing.primary_intent.value,
                confidence=routing.confidence,
                rag_answer=rag_result.get("answer"),
                rag_documents=rag_result.get("documents"),
                rag_sources=rag_result.get("sources"),
                final_answer=rag_result.get("answer"),
                total_execution_ms=round(total_ms, 2),
                routing_reason=routing.reason,
                error=rag_result.get("error"),
            )
        
        else:
            sql_result = self._execute_sql_query(question, [])
            total_ms = (time.time() - start_time) * 1000
            
            return QueryResult(
                status=sql_result.get("status", "error"),
                query_type="sql_fallback",
                intent="unknown",
                confidence=routing.confidence,
                sql_answer=sql_result.get("answer"),
                sql_query=sql_result.get("sql"),
                sql_rows=sql_result.get("rows"),
                sql_execution_ms=sql_result.get("execution_ms"),
                final_answer=sql_result.get("answer"),
                total_execution_ms=round(total_ms, 2),
                routing_reason="Fallback to SQL due to unknown intent",
                error=sql_result.get("error"),
            )
    
    def get_routing_preview(self, question: str) -> Dict[str, Any]:
        """Preview how a query would be routed without executing."""
        schema_context = self._get_schema_context()
        routing = self.intent_router.route(question, schema_context=schema_context, use_llm=False)
        rag_tables = self._get_rag_enabled_tables()
        
        would_use_agentic = (
            routing.primary_intent == QueryIntent.HYBRID or 
            (routing.use_sql and routing.use_rag)
        )
        
        return {
            "question": question,
            "intent": routing.primary_intent.value,
            "confidence": routing.confidence,
            "use_sql": routing.use_sql,
            "use_rag": routing.use_rag,
            "sql_hints": routing.sql_hints,
            "rag_hints": routing.rag_hints,
            "reason": routing.reason,
            "engine": "agentic_hybrid" if would_use_agentic
                     else "sql" if routing.use_sql 
                     else "rag" if routing.use_rag 
                     else "unknown",
            "rag_enabled_tables": rag_tables,
            "rag_available": len(rag_tables) > 0,
            "workflow_description": (
                "RAG -> SQL -> Synthesis (Gold Standard)" if would_use_agentic
                else "Direct SQL query" if routing.use_sql
                else "Semantic vector search" if routing.use_rag
                else "Unknown routing"
            ),
        }


def get_file_query_service(user_id: int) -> FileQueryService:
    """Get a FileQueryService instance for a user."""
    return FileQueryService(user_id)
