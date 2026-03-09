"""
Agent service - Main RAG orchestration logic.
Coordinates SQL and vector search tools to answer user queries.
"""
import re
import json
import uuid
import asyncio
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

from backend.config import get_settings, get_llm_settings, get_embedding_settings
from backend.core.logging import get_logger
from backend.services.sql_service import get_sql_service, SQLService
from backend.services.vector_store import get_vector_store
from backend.services.embeddings import get_embedding_model
from backend.services.followup_service import FollowUpService
from backend.services.llm_registry import get_llm_registry
from backend.services.intent_router import IntentClassifier
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import (
    ChatResponse, ChartData, ReasoningStep, EmbeddingInfo
)

settings = get_settings()
logger = get_logger(__name__)



DEFAULT_SYSTEM_PROMPT = """You are a helpful Data Intelligence Agent.
Please contact the administrator to configure the active system prompt in the database.
"""
class AgentService:
    """Main RAG agent service for processing user queries."""
    
    def __init__(self, agent_config: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None, langfuse_trace: Optional[Any] = None):
        """Initialize the agent with tools and LLM."""
        logger.info(f"Initializing AgentService (Config: {agent_config.get('name') if agent_config else 'Default'})")
        
        # Initialize services
        self.db_service = get_db_service()
        self.agent_config = agent_config
        self.user_id = user_id
        self.langfuse_trace = langfuse_trace
        
        # Determine data source type from active config
        agent_id = agent_config.get('id') if agent_config else None
        active_config = self.db_service.get_active_config(agent_id=agent_id)
        self.data_source_type = active_config.get('data_source_type', 'database') if active_config else 'database'
        
        logger.info(f"Data source type for agent: {self.data_source_type}")
        
        # Fetch agent-specific system prompt from system_prompts table (NOT from agents table)
        # The agents.system_prompt column is deprecated - prompts are stored in system_prompts with agent_id
        if agent_id:
            self.fixed_system_prompt = self.db_service.get_latest_active_prompt(agent_id=agent_id)
            if self.fixed_system_prompt:
                logger.info(f"Loaded agent-specific system prompt for agent_id={agent_id}")
            else:
                logger.warning(f"No active system prompt found for agent_id={agent_id}")
        else:
            self.fixed_system_prompt = None
        
        # Initialize SQL service based on data source type
        if self.data_source_type == 'file':
            # Use FileSQLService (DuckDB) for Excel/CSV file-based agents
            from backend.services.file_sql_service import FileSQLService
            if user_id:
                try:
                    # Pass callbacks to FileSQLService for Langfuse tracing
                    callbacks = [langfuse_trace] if langfuse_trace else []
                    
                    # Extract allowed tables from active config to scope queries to this agent's data
                    allowed_tables = None
                    if active_config:
                        # Try to get table name from ingestion_file_name (e.g., "WDF BP assessment data.xlsx" -> "wdf_bp_assessment_data")
                        ingestion_file = active_config.get('ingestion_file_name')
                        if ingestion_file:
                            # Convert filename to table name (same logic as file upload)
                            import re
                            table_name = re.sub(r'\.[^.]+$', '', ingestion_file)  # Remove extension
                            table_name = re.sub(r'[^a-zA-Z0-9_]', '_', table_name)  # Replace special chars
                            table_name = table_name.lower().strip('_')
                            table_name = re.sub(r'_+', '_', table_name)  # Collapse multiple underscores
                            allowed_tables = [table_name]
                            logger.info(f"File agent restricted to table: {table_name} (from {ingestion_file})")
                        
                        # Also check schema_selection if available
                        if not allowed_tables:
                            schema_sel = active_config.get('schema_selection')
                            if schema_sel:
                                try:
                                    schema_data = json.loads(schema_sel) if isinstance(schema_sel, str) else schema_sel
                                    if isinstance(schema_data, dict):
                                        allowed_tables = list(schema_data.keys())
                                    elif isinstance(schema_data, list):
                                        allowed_tables = schema_data
                                    if allowed_tables:
                                        logger.info(f"File agent restricted to tables from schema_selection: {allowed_tables}")
                                except Exception as e:
                                    logger.warning(f"Failed to parse schema_selection: {e}")
                    
                    self._file_sql_service = FileSQLService(
                        user_id=user_id, 
                        callbacks=callbacks,
                        allowed_tables=allowed_tables
                    )
                    # Wrap FileSQLService.query to return string like SQLService
                    self.sql_service = self._create_file_sql_wrapper(self._file_sql_service)
                    logger.info(f"Using FileSQLService (DuckDB) for user {user_id}")
                except ValueError as e:
                    logger.warning(f"FileSQLService init failed: {e}. No uploaded files for user.")
                    self.sql_service = self._create_dummy_sql_service()
            else:
                logger.warning("File-based agent requires user_id for FileSQLService")
                self.sql_service = self._create_dummy_sql_service()
        elif agent_config and agent_config.get('db_connection_uri'):
            # Use SQLService with dedicated database connection
            logger.info(f"Connecting to dedicated agent database: {agent_config['db_connection_uri']}")
            self.sql_service = SQLService(database_url=agent_config['db_connection_uri'])
        else:
            # Use default SQLService (PostgreSQL)
            self.sql_service = get_sql_service()

        # Don't load vector store on init - lazy load it when needed!
        self._vector_store = None
        self.embedding_model = get_embedding_model()
        
        # In-memory conversation history store
        # Structure: {session_id: ChatMessageHistory}
        self.message_store: Dict[str, ChatMessageHistory] = {}
        # Track last access time for session expiry
        self.session_timestamps: Dict[str, datetime] = {}
        # Session expiry: 1 hour of inactivity
        self.SESSION_EXPIRY_SECONDS = 3600
        
        # Initialize LLM via registry (enables hot-swapping)
        self._llm_registry = get_llm_registry()
        base_provider = self._llm_registry.get_active_provider()
        self.llm = base_provider.get_langchain_llm()
        
        # Check active config for LLM overrides (temperature, max_tokens)
        if active_config and active_config.get('llm_config'):
            try:
                llm_conf = json.loads(active_config['llm_config'])
                overrides = {}
                if 'temperature' in llm_conf:
                    overrides['temperature'] = float(llm_conf['temperature'])
                if 'maxTokens' in llm_conf:
                    overrides['max_tokens'] = int(llm_conf['maxTokens'])
                    
                if overrides:
                    from backend.services.llm_providers import create_llm_provider
                    provider_config = base_provider.get_config()
                    provider_config.update(overrides)
                    custom_provider = create_llm_provider(base_provider.provider_name, provider_config)
                    self.llm = custom_provider.get_langchain_llm()
                    logger.info(f"Applied LLM config overrides for agent: {overrides}")
            except Exception as e:
                logger.error(f"Failed to apply LLM config overrides: {e}")
        
        # Create tools
        # SQL Agent tool accepts natural language questions and handles SQL generation internally.
        self.tools = [
            Tool(
                name="sql_query_tool",
                func=self.sql_service.query if self.sql_service else lambda x: "SQL service not available.",
                description="""**PRIMARY TOOL FOR STATISTICS - Pass NATURAL LANGUAGE questions only.**

This tool accepts natural language questions (NOT SQL queries) and automatically generates and executes SQL.

When to use:
- Counting: "How many entities...", "Total number of..."
- Averages: "Average value of...", "Mean of..."
- Aggregations: "Sum of...", "Distribution of..."
- Filtering: By attributes, date ranges, categories

Input format: Natural language question ONLY
Example: "Count records with status 'active' in 2024"
DO NOT generate SQL yourself - the tool handles that internally.

Available data: structured tables in the database."""
            ),
            # RAG tool for unstructured context - accepts natural language queries and returns relevant text snippets.
            Tool(
                name="rag_document_search_tool",
                func=self._rag_search,
                description="""**PRIMARY TOOL FOR UNSTRUCTURED CONTEXT.**
Use this to search unstructured text, notes, and semantic descriptions.
- Capabilities: Semantic search for concepts, logs, and specific records.
- Use for: "Find records related to...", "Show me details about..."."""
            ),
        ]
        
        # Create prompt template with chat history for conversation memory
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=settings.debug,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            max_iterations=5,  # Allow enough iterations for multi-tool queries (age + gender breakdown)
            max_execution_time=60,  # Maximum 60 seconds for agent execution
        )
        
        self.agent_with_history = RunnableWithMessageHistory(
            self.agent_executor,
            self.get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )
        
        # Initialize follow-up question service (shares LLM instance)
        self.followup_service = FollowUpService(llm=self.llm, langfuse_callback_handler=langfuse_trace)
        
        # Initialize Intent Router
        self.intent_router = IntentClassifier(llm=self.llm)
        
        self._initialized = True
        logger.info("AgentService initialized successfully")
    
    @property
    def vector_store(self):
        """Lazy load vector store only when needed."""
        if self._vector_store is None:
            agent_id = self.agent_config.get('id') if self.agent_config else None
            logger.info(f"⚡ Lazy loading vector store on first use (Agent ID: {agent_id})...")
            self._vector_store = get_vector_store(agent_id=agent_id)
            logger.info(f"✅ Vector store loaded for agent: {agent_id}")
        return self._vector_store
    
    def _rag_search(self, query: str, filter: Optional[Dict[str, Any]] = None) -> str:
        """
        RAG tool wrapper that returns string for agent.
        
        Note: Tracing is handled by the parent LangChain callback handler
        to ensure all operations are grouped under a single trace.
        """
        # Pass the filter down to the vector store search
        docs = self.vector_store.search(query, filter=filter)  # Uses lazy-loaded property
        if not docs:
            return "No relevant documents found."
        
        # Combine document contents
        combined = "\n\n".join([doc.page_content for doc in docs[:3]])
        return combined[:1000]  # Limit length
    
    def get_session_history(self, session_id: str, limit: int = 20) -> ChatMessageHistory:
        """
        Retrieve conversation history for a session with sliding window limit.
        Also handles session expiry and cleanup.
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to retain (default: 20)
            
        Returns:
            ChatMessageHistory with at most 'limit' recent messages
        """
        now = datetime.utcnow()
        
        # Cleanup expired sessions periodically (every 10th call)
        if len(self.message_store) > 0 and hash(session_id) % 10 == 0:
            self._cleanup_expired_sessions()
        
        # Check if session exists and is not expired
        if session_id in self.message_store:
            last_access = self.session_timestamps.get(session_id, now)
            if (now - last_access).total_seconds() > self.SESSION_EXPIRY_SECONDS:
                # Session expired, clear it
                logger.info(f"Session expired (idle > 1hr): {session_id}")
                del self.message_store[session_id]
                del self.session_timestamps[session_id]
        
        # Create new history if session doesn't exist
        if session_id not in self.message_store:
            self.message_store[session_id] = ChatMessageHistory()
            logger.info(f"Created new conversation history for session: {session_id}")
        
        # Update last access timestamp
        self.session_timestamps[session_id] = now
        
        history = self.message_store[session_id]
        
        # Enforce sliding window: keep only last N messages
        if len(history.messages) > limit:
            history.messages = history.messages[-limit:]
            logger.debug(f"Trimmed history to {limit} messages for session: {session_id}")
        
        return history
    
    def _cleanup_expired_sessions(self) -> None:
        """Remove sessions that have been idle for more than SESSION_EXPIRY_SECONDS."""
        now = datetime.utcnow()
        expired = [
            sid for sid, ts in self.session_timestamps.items()
            if (now - ts).total_seconds() > self.SESSION_EXPIRY_SECONDS
        ]
        for sid in expired:
            if sid in self.message_store:
                del self.message_store[sid]
            if sid in self.session_timestamps:
                del self.session_timestamps[sid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    async def _rewrite_query_with_context(self, query: str, session_id: Optional[str]) -> str:
        """
        Rewrite a query to resolve pronouns and references using conversation history.
        
        Examples:
        - "what is the patient's CVD risk?" + history about patient 49686742
          -> "what is the CVD risk for patient 49686742?"
        - "and what about the Cardiovascular Disease Risk?" + history about patient 49686742
          -> "what is the Cardiovascular Disease Risk for patient 49686742?"
        
        Args:
            query: The user's current query
            session_id: Session ID to retrieve conversation history
            
        Returns:
            Rewritten query with resolved references, or original query if no rewriting needed
        """
        if not session_id:
            return query
        
        # Get conversation history
        history = self.get_session_history(session_id)
        if not history.messages or len(history.messages) < 2:
            # No prior conversation to reference
            return query
        
        # Check if query contains references that need resolution
        # Include both explicit references AND conversational follow-up patterns
        reference_patterns = [
            # Explicit entity references
            r'\b(the patient|this patient|that patient)\b',
            r'\b(their|his|her|its)\b',
            r'\b(them|him|her|it)\b',
            r'\b(same|above|previous|mentioned)\b',
            r"patient's\b",
            # Conversational follow-up patterns (likely referring to previous context)
            r'^and\s+(what|how|show|get|tell)',  # "and what about...", "and how about..."
            r'^what about\b',  # "what about the..."
            r'^how about\b',  # "how about..."
            r'^also\s+(show|get|what|tell)',  # "also show me...", "also what is..."
            r'^now\s+(show|get|what|tell)',  # "now show me...", "now what is..."
            r'(for (the same|this|that))\b',  # "for the same patient"
            r'^(show|get|tell|give)\s+me\s+(the|their|his|her)',  # "show me the...", "tell me their..."
        ]
        
        needs_rewriting = any(re.search(pattern, query.lower()) for pattern in reference_patterns)
        
        if not needs_rewriting:
            return query
        
        logger.info(f"Query appears to need context rewriting: '{query[:50]}...'")
        
        # Build conversation context from last few exchanges
        recent_messages = history.messages[-6:]  # Last 3 exchanges (human + AI pairs)
        context_parts = []
        for msg in recent_messages:
            role = "User" if msg.type == "human" else "Assistant"
            # Truncate long messages
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            context_parts.append(f"{role}: {content}")
        
        conversation_context = "\n".join(context_parts)
        
        # Use LLM to rewrite the query
        rewrite_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a query rewriter. Your task is to rewrite the user's current query to make it self-contained by resolving any pronouns, references, or implicit context from the conversation history.

RULES:
1. If the query references "the patient", "their", "this patient", etc., replace with the specific patient ID from context
2. If the query is a follow-up like "and what about X?" or "what about the Y?", make it explicit by adding the entity (e.g., patient ID) from the previous conversation
3. Keep the rewritten query concise and natural
4. If no rewriting is needed (query is already self-contained), return the original query exactly
5. Only output the rewritten query, nothing else
6. Preserve the intent and meaning of the original query

Examples:
- History mentions patient 49686742, Query: "what is the patient's CVD risk?" 
  -> "what is the CVD risk for patient ID 49686742?"
- History about patient 49686742 BP readings, Query: "and what about the Cardiovascular Disease Risk?"
  -> "what is the Cardiovascular Disease Risk for patient ID 49686742?"
- History mentions John Smith, Query: "show me their BP readings"
  -> "show me BP readings for John Smith"
- Query: "how many patients are there?" (no reference needed)
  -> "how many patients are there?"
"""),
            ("user", """Conversation History:
{context}

Current Query: {query}

Rewritten Query:""")
        ])
        
        try:
            chain = rewrite_prompt | self.llm
            response = await chain.ainvoke({
                "context": conversation_context,
                "query": query
            })
            rewritten = response.content.strip()
            
            # Remove any quotes the LLM might add around the response
            rewritten = rewritten.strip('"\'')
            
            # Validate the rewritten query isn't empty or too different
            if rewritten and len(rewritten) > 5 and len(rewritten) < len(query) * 4:
                logger.info(f"Query rewritten: '{query}' -> '{rewritten}'")
                return rewritten
            else:
                logger.debug("Query rewriting returned invalid result, using original")
                return query
                
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}. Using original query.")
            return query

    async def process_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user query through the RAG pipeline with conversation memory.
        
        Args:
            query: User question
            user_id: Optional user identifier
            session_id: Session ID for conversation tracking (enables multi-turn)
        
        Returns:
            Dictionary containing answer, charts, suggestions, and metadata
        """
        trace_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        
        logger.info(f"Processing query (trace_id={trace_id}): '{query[:100]}...'")
        
        # Use the handler passed during initialization
        callbacks = [self.langfuse_trace] if self.langfuse_trace else []
        
        try:
            # Rewrite query with context
            query = await self._rewrite_query_with_context(query, session_id)
            
            # =================================================================
            # STANDARD PATH: Use agent for all queries
            # =================================================================
            # Fetch prompt fresh on every request
            if self.fixed_system_prompt:
                active_prompt = self.fixed_system_prompt
                logger.info(f"Using agent-specific system prompt for trace_id={trace_id}")
            else:
                active_prompt = self.db_service.get_latest_active_prompt()
                logger.info(f"Active global prompt fetched for trace_id={trace_id}")
            
            if not active_prompt:
                logger.warning("No active system prompt found in DB. Using default generic prompt.")
                active_prompt = DEFAULT_SYSTEM_PROMPT
                
            # Retrieve relevant few-shot examples
            few_shot_examples = self._get_relevant_examples(query)
            formatted_examples = ""
            if few_shot_examples:
                formatted_examples = "\n\nRELEVANT SQL EXAMPLES:\n" + "\n".join(few_shot_examples)
                logger.info(f"✨ Injected {len(few_shot_examples)} relevant SQL examples into prompt")

            final_prompt = f"{active_prompt}\n{formatted_examples}"

            # Step 1: Classify Intent
            schema_context = self.sql_service.cached_schema if self.sql_service.cached_schema else ""
            classification = self.intent_router.classify(query=query, schema_context=schema_context)
            
            rag_used = False
            sql_used = False
            full_response = ""
            intermediate_steps = []
            
            # Step 2: Route Based on Intent
            if classification.intent == "A":
                # Strict SQL Route
                logger.info(f"Routing intent A (SQL Only) for trace_id={trace_id}")
                sql_used = True
                full_response = self.sql_service.query(query)
                intermediate_steps.append((type('obj', (object,), {'tool': 'sql_query_tool', 'tool_input': query}), full_response))

            elif classification.intent == "B":
                # Strict Vector Route
                logger.info(f"Routing intent B (Vector Only) for trace_id={trace_id}")
                rag_used = True
                context = self._rag_search(query)
                intermediate_steps.append((type('obj', (object,), {'tool': 'rag_document_search_tool', 'tool_input': query}), context))
                
                # Synthesize Response using LLM
                synthesis_prompt = ChatPromptTemplate.from_messages([
                    ("system", "{system_prompt}\n\nUse the provided unstructured document context to answer the user's question. If the context does not contain the answer, state that you do not know based on the available information."),
                    ("user", "Context: {context}\n\nQuestion: {query}")
                ])
                chain = synthesis_prompt | self.llm
                response = await chain.ainvoke({"system_prompt": active_prompt, "context": context, "query": query})
                full_response = response.content

            elif classification.intent == "C" and classification.sql_filter:
                # Hybrid Route (C)
                logger.info(f"Routing intent C (Hybrid) for trace_id={trace_id}. Executing SQL filter: {classification.sql_filter}")
                sql_used = True
                rag_used = True
                
                # Execute SQL filter
                try:
                    # We expect the structured LLM to generate a query that returns a single column of IDs (e.g., patient_id)
                    filter_result_raw = self.sql_service.db.run(classification.sql_filter)
                    
                    # Convert raw string representation of tuples to a list of strings
                    # Ex: "[('P123',), ('P456',)]" -> ["P123", "P456"]
                    import ast
                    valid_ids = []
                    try:
                        parsed_list = ast.literal_eval(filter_result_raw)
                        if isinstance(parsed_list, list):
                            for item in parsed_list:
                                if isinstance(item, tuple) and len(item) > 0:
                                    valid_ids.append(str(item[0]))
                                else:
                                    valid_ids.append(str(item))
                    except Exception as e:
                        logger.warning(f"Could not parse SQL filter output: {e}. Raw output: {filter_result_raw}")
                    
                    if not valid_ids:
                        full_response = f"No patients matched the criteria in the structured database. Therefore, no unstructured context was searched."
                        intermediate_steps.append((type('obj', (object,), {'tool': 'sql_query_tool_filter', 'tool_input': classification.sql_filter}), filter_result_raw))
                    else:
                        logger.info(f"Extracted list of {len(valid_ids)} IDs for metadata filtering.")
                        
                        # Build ChromaDB metadata filter. Using '$in' operator on 'patient_id'
                        # Note: You might need to adjust 'patient_id' to match your exact metadata schema
                        vector_filter = {"patient_id": {"$in": valid_ids}}
                        
                        context = self._rag_search(query, filter=vector_filter)
                        
                        intermediate_steps.append((type('obj', (object,), {'tool': 'sql_query_tool_filter', 'tool_input': classification.sql_filter}), str(valid_ids)))
                        intermediate_steps.append((type('obj', (object,), {'tool': 'rag_document_search_tool_filtered', 'tool_input': query}), context))
                        
                        synthesis_prompt = ChatPromptTemplate.from_messages([
                            ("system", "{system_prompt}\n\nUse the provided unstructured document context (filtered by your numerical criteria) to answer the user's question. If the context does not contain the answer, state that you do not know based on the available information."),
                            ("user", "Context: {context}\n\nQuestion: {query}")
                        ])
                        chain = synthesis_prompt | self.llm
                        response = await chain.ainvoke({"system_prompt": active_prompt, "context": context, "query": query})
                        full_response = response.content
                        
                except Exception as e:
                        logger.error(f"Hybrid SQL filtering failed: {e}")
                        full_response = "An error occurred while evaluating the numerical filter against the structured database."
            else:
                # Fallback Route
                logger.warning(f"Routing Intent {classification.intent} fallback triggered for trace_id={trace_id}")
                result = await self.agent_with_history.ainvoke(
                    {"input": query, "system_prompt": final_prompt},
                    config={
                        "configurable": {"session_id": session_id or "default"},
                        "callbacks": callbacks,
                        # Set run_name to override the default "RunnableWithMessageHistory" name
                        "run_name": "rag_query",
                        "metadata": {
                            # Langfuse v3.x reads these special keys from metadata
                            "langfuse_user_id": user_id,
                            "langfuse_session_id": session_id,
                            "langfuse_tags": ["rag_query"],
                            # Store the clean user query for better visibility
                            "langfuse_input": query,
                            # Additional metadata for debugging
                            "trace_id": trace_id,
                            "user_query": query,
                        }
                    }
                )
                
                logger.info(f"Agent result received for trace_id={trace_id}: keys={result.keys()}")

                # Extract response
                full_response = result.get("output", "An error occurred.")
                intermediate_steps = result.get("intermediate_steps", [])
                
                # Determine which tool was used (SQL vs RAG)
                tools_used = [action.tool for action, _ in intermediate_steps]
                rag_used = "rag_document_search_tool" in tools_used
                sql_used = "sql_query_tool" in tools_used
            
            # Only get embedding info if RAG was actually used
            embedding_info = self._get_embedding_info(query) if rag_used else {}
            
            # Parse JSON output from response (chart data only now)
            # chart_data parser works heavily on JSON blocks.
            # Usually only Agent or SQL responses will have them, but let's parse safely.
            chart_data = None
            suggestions = []
            
            # Since full_response is directly synthesized now, we'll try to extract any JSON block for charts
            if sql_used and not rag_used:
                 chart_data, suggestions = self._parse_agent_output(full_response)
            else:
                 # If we did RAG, we probably don't have a chart, but we can generate suggestions separately if needed
                 # For now, just rely on process_query's followup_service background task below
                 pass
            
            # ============================================================
            # OPTIMIZATION: Start follow-up generation as background task
            # ============================================================
            followup_task = None
            if settings.enable_followup_questions:
                followup_task = asyncio.create_task(
                    self.followup_service.generate_followups(
                        original_question=query,
                        system_response=self._clean_answer(full_response),
                        # Pass callbacks to the followup service as well
                        callbacks=callbacks
                    )
                )
            
            # Format reasoning steps
            reasoning_steps = self._format_reasoning(intermediate_steps)
            
            # Wait for follow-ups with short timeout
            suggested_questions = []
            if followup_task:
                try:
                    suggested_questions = await asyncio.wait_for(followup_task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Follow-up generation timed out for trace_id={trace_id}")
                    suggested_questions = []
                except Exception as e:
                    logger.warning(f"Follow-up generation failed: {e}")
                    suggested_questions = []
            
            # Build response
            embedding_settings = get_embedding_settings()
            response = ChatResponse(
                answer=self._clean_answer(full_response),
                chart_data=chart_data,
                suggested_questions=suggested_questions,
                reasoning_steps=reasoning_steps,
                embedding_info=EmbeddingInfo(
                    model=embedding_settings.get('model_name', 'BAAI/bge-m3'),
                    dimensions=self.embedding_model.dimension,
                    search_method="hybrid" if rag_used else "structured",
                    vector_norm=embedding_info.get("norm"),
                    docs_retrieved=len([s for a, s in intermediate_steps if a.tool == "rag_document_search_tool"])
                ),
                trace_id=trace_id,
                session_id=session_id,
                timestamp=start_time
            )
            
            # ============================================================
            # IMPORTANT: Save conversation to history for multi-turn support
            # The agent_with_history path auto-saves, but direct Intent A/B/C
            # routes need manual saving for query rewriting to work
            # ============================================================
            if session_id and classification.intent in ["A", "B", "C"]:
                try:
                    history = self.get_session_history(session_id)
                    from langchain_core.messages import HumanMessage, AIMessage
                    history.add_message(HumanMessage(content=query))
                    # Save a clean version of the response (no JSON blocks)
                    history.add_message(AIMessage(content=self._clean_answer(full_response)[:1000]))
                    logger.debug(f"Saved conversation to history for session {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to save conversation history: {e}")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"✅ Query processed successfully (trace_id={trace_id}, duration={duration:.2f}s)")
            
            # Background tracking
            async def _track_and_flush():
                try:
                    from backend.services.observability_service import get_observability_service
                    obs_service = get_observability_service()
                    input_tokens = len(query.split()) * 1.3
                    output_tokens = len(full_response.split()) * 1.3
                    llm_settings = get_llm_settings()
                    await obs_service.track_usage(
                        operation="rag_pipeline",
                        model=llm_settings.get('model_name', 'gpt-4o'),
                        input_tokens=int(input_tokens),
                        output_tokens=int(output_tokens),
                        latency_ms=int(duration * 1000),
                        metadata={
                            "trace_id": trace_id,
                            "rag_used": rag_used,
                            "sql_used": sql_used,
                            "chart_generated": chart_data is not None,
                            "tools_used": [step.tool for step in reasoning_steps],
                            "user_id": user_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Background tracking failed: {e}")
            
            asyncio.create_task(_track_and_flush())
            
            return response.model_dump()
            
        except Exception as e:
            logger.error(f"Query processing failed (trace_id={trace_id}): {e}", exc_info=True)
            raise
    
    # Cached SQL examples: (examples_list, example_embeddings or None)
    _cached_examples = None
    _cached_example_embeddings = None
    
    def _get_relevant_examples(self, query: str) -> List[str]:
        """
        Retrieve relevant SQL examples using semantic search.
        
        OPTIMIZED (Task 14): Caches examples and pre-computes embeddings.
        Uses embedding similarity instead of keyword overlap for better accuracy.
        """
        try:
            # Load and cache examples on first call
            if AgentService._cached_examples is None:
                examples = self.db_service.get_sql_examples()
                AgentService._cached_examples = examples or []
                
                # Pre-compute embeddings for all examples
                if AgentService._cached_examples and self.embedding_model:
                    try:
                        example_texts = [ex['question'] for ex in AgentService._cached_examples]
                        AgentService._cached_example_embeddings = self.embedding_model.embed_documents(example_texts)
                        logger.info(f"Pre-computed embeddings for {len(example_texts)} SQL examples")
                    except Exception as e:
                        logger.warning(f"Failed to embed examples, falling back to keyword: {e}")
                        AgentService._cached_example_embeddings = None
            
            examples = AgentService._cached_examples
            if not examples:
                return []
            
            # If few examples, just return all of them (up to 3)
            if len(examples) <= 3:
                return [f"Q: {ex['question']}\nSQL: {ex['sql_query']}" for ex in examples]

            # Try embedding-based similarity (fast: cached embeddings + single query embed)
            if AgentService._cached_example_embeddings is not None:
                try:
                    query_emb = self.embedding_model.embed_query(query)
                    query_arr = np.array(query_emb)
                    example_arrs = np.array(AgentService._cached_example_embeddings)
                    
                    # Cosine similarity via dot product (embeddings are typically normalized)
                    similarities = np.dot(example_arrs, query_arr)
                    top_indices = np.argsort(similarities)[-3:][::-1]
                    
                    return [f"Q: {examples[i]['question']}\nSQL: {examples[i]['sql_query']}" for i in top_indices]
                except Exception as e:
                    logger.warning(f"Embedding-based example search failed: {e}")
            
            # Fallback: keyword overlap
            scored_examples = []
            for ex in examples:
                q_words = set(query.lower().split())
                ex_words = set(ex['question'].lower().split())
                score = len(q_words.intersection(ex_words)) * 0.1
                scored_examples.append((score, ex))
            
            scored_examples.sort(key=lambda x: x[0], reverse=True)
            top_examples = scored_examples[:3]
            return [f"Q: {ex['question']}\nSQL: {ex['sql_query']}" for _, ex in top_examples]

        except Exception as e:
            logger.warning(f"Failed to retrieve examples: {e}")
            return []

    def _get_embedding_info(self, query: str) -> Dict[str, Any]:
        """Get embedding statistics for query."""
        try:
            embedding = self.embedding_model.embed_query(query)
            return {
                "norm": float(np.linalg.norm(embedding)),
                "dimensions": len(embedding)
            }
        except Exception as e:
            logger.warning(f"Failed to get embedding info: {e}")
            return {}
    
    def _parse_agent_output(self, response: str) -> Tuple[Optional[ChartData], List[str]]:
        """Parse JSON output from agent response."""
        chart_data = None
        suggestions = []
        
        # Try to extract JSON block - handle nested braces properly
        # Look for ```json ... ``` block
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                data = json.loads(json_str)
                
                # Extract chart data - handle both wrapped and direct formats
                chart_json = None
                if "chart_json" in data:
                    chart_json = data["chart_json"]
                elif "type" in data and "data" in data:
                    # LLM returned the chart object directly
                    chart_json = data
                
                if chart_json:
                    # Compatibility fix for Chart.js style output (datasets) -> Frontend style (values)
                    if "data" in chart_json and isinstance(chart_json["data"], dict):
                        cdata = chart_json["data"]
                        if "datasets" in cdata and "values" not in cdata:
                            # Extract data from first dataset
                            try:
                                datasets = cdata["datasets"]
                                if datasets and isinstance(datasets, list):
                                    cdata["values"] = datasets[0].get("data", [])
                                    logger.info("Transformed Chart.js style 'datasets' to 'values'")
                            except Exception as e:
                                logger.warning(f"Failed to transform chart datasets: {e}")
                    
                    # Fallback: Auto-generate title if missing (LLM sometimes omits it)
                    if "title" not in chart_json or not chart_json["title"]:
                        chart_type = chart_json.get("type", "Chart")
                        chart_json["title"] = f"{chart_type.capitalize()} Visualization"
                        logger.info(f"Auto-generated missing chart title: {chart_json['title']}")

                    try:
                        chart_data = ChartData(**chart_json)
                        logger.info(f"Successfully parsed chart data: {chart_json.get('title', 'Untitled')}")
                    except Exception as ve:
                        logger.warning(f"Validation failed for chart data: {ve}")
                
                # Extract suggestions
                if questions := data.get("suggested_questions"):
                    suggestions = questions[:3]  # Limit to 3
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse agent JSON output: {e}")
                logger.debug(f"JSON string was: {json_str[:200]}...")
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to create ChartData from JSON: {e}")
        
        return chart_data, suggestions
    
    def _clean_answer(self, response: str) -> str:
        """Remove JSON block from answer text."""
        # Remove JSON code block - use [\s\S]*? to match across newlines including nested braces
        cleaned = re.sub(r'```json\s*[\s\S]*?\s*```', '', response)
        return cleaned.strip()
    
    def _format_reasoning(self, intermediate_steps: List[Tuple]) -> List[ReasoningStep]:
        """Format intermediate steps into reasoning steps."""
        steps = []
        
        for action, observation in intermediate_steps:
            # Extract tool input
            if isinstance(action.tool_input, dict):
                tool_input = action.tool_input.get("input", str(action.tool_input))
            else:
                tool_input = str(action.tool_input)
            
            steps.append(ReasoningStep(
                tool=action.tool,
                input=tool_input[:200],  # Truncate
                output=str(observation)[:200]  # Truncate
            ))
        
        return steps

    def _create_file_sql_wrapper(self, file_sql_service):
        """Create a wrapper around FileSQLService to match SQLService interface."""
        class FileSQLWrapper:
            def __init__(self, service):
                self._service = service
                # Provide cached_schema for compatibility with intent router
                self.cached_schema = service.get_schema_for_prompt()
                # Create a db-like object that supports .run() for hybrid queries
                self.db = self._create_db_runner(service)
            
            def _create_db_runner(self, service):
                """Create a db runner object that mimics LangChain's SQLDatabase.run()."""
                class DuckDBRunner:
                    def __init__(self, file_service):
                        self._service = file_service
                    
                    def run(self, sql: str) -> str:
                        """Execute raw SQL and return results as string (like LangChain SQLDatabase)."""
                        try:
                            # _execute_sql returns tuple: (columns, rows, execution_time_ms)
                            # where rows is a list of dicts
                            columns, rows, exec_time = self._service._execute_sql(sql)
                            
                            if not rows:
                                return "[]"
                            
                            # Return as list of tuples string representation
                            # e.g., "[('value1',), ('value2',)]"
                            tuple_rows = [tuple(row.values()) for row in rows]
                            return str(tuple_rows)
                        except Exception as e:
                            return f"Error executing SQL: {e}"
                
                return DuckDBRunner(service)
            
            def query(self, question: str) -> str:
                """Query wrapper that returns string like SQLService."""
                result = self._service.query(question)
                if isinstance(result, dict):
                    if result.get('status') == 'error':
                        return f"Error: {result.get('error', 'Unknown error')}"
                    return result.get('answer', str(result))
                return str(result)
        
        return FileSQLWrapper(file_sql_service)
    
    def _create_dummy_sql_service(self):
        """Create a dummy SQL service for when FileSQLService can't be initialized."""
        class DummySQLService:
            cached_schema = ""
            db = None
            
            def query(self, question: str) -> str:
                return "SQL service not available. Please ensure you have uploaded files for this agent."
        
        return DummySQLService()


# Singleton instance for default agent
_agent_service: Optional[AgentService] = None

# Cache for dedicated agent instances: {agent_id: AgentService}
# IMPORTANT: Cache key is agent_id only. Each agent has isolated:
#   - SQL service (either dedicated DB connection, or FileSQLService with allowed_tables)
#   - Vector store (lazy-loaded with agent-specific collection)
#   - System prompt
_agent_cache: Dict[int, AgentService] = {}


def clear_agent_cache(agent_id: Optional[int] = None):
    """
    Clear cached agent instances to force re-initialization.
    
    Use this when:
    - Agent configuration changes
    - Agent data source changes
    - Security/access rules change
    
    Args:
        agent_id: Specific agent to clear, or None to clear all
    """
    global _agent_cache, _agent_service
    
    if agent_id is not None:
        if agent_id in _agent_cache:
            del _agent_cache[agent_id]
            logger.info(f"Cleared agent cache for agent_id={agent_id}")
    else:
        _agent_cache.clear()
        _agent_service = None
        logger.info("Cleared all agent caches")


def get_agent_service(agent_id: Optional[int] = None, user_id: Optional[int] = None, langfuse_trace: Optional[Any] = None) -> AgentService:
    """Get agent service instance with proper data isolation.
    
    SECURITY: Each agent is completely isolated:
    - File agents: Can only access tables from their configured data file
    - Database agents: Use their own db_connection_uri
    - RAG: Uses agent-specific vector collection (vectorDbName)
    
    If agent_id is provided, checks specific user access and returns a dedicated instance.
    Dedicated instances are cached to reuse database connections.
    Otherwise returns the singleton default instance (legacy behavior).
    """
    if agent_id:
        # Check cache first
        if agent_id in _agent_cache:
            service = _agent_cache[agent_id]
            # Set request-scoped trace on cached instance
            service.langfuse_trace = langfuse_trace
            logger.debug(f"Using cached AgentService for agent_id={agent_id}")
            return service

        db = get_db_service()
        
        agent_config = db.get_agent_by_id(agent_id)
        if not agent_config:
             raise ValueError(f"Agent {agent_id} not found")

        # Verify access if user_id is provided (skip for internal system calls if user_id is None)
        if user_id:
            has_access = db.check_user_access(user_id, agent_id)
            if not has_access:
                logger.warning(f"Access denied for user {user_id} to agent {agent_id}")
                raise PermissionError(f"User {user_id} does not have access to agent {agent_id}")
        
        # For file-based agents, ALL users should use the agent creator's files
        # Files are stored per-user, so we need to use the creator's user_id
        service_user_id = user_id
        
        # Get the active config to check data_source_type
        active_config = db.get_active_config(agent_id=agent_id)
        data_source_type = active_config.get('data_source_type', 'database') if active_config else 'database'
        
        if data_source_type == 'file':
            # Use the agent creator's user_id for file-based agents
            creator_id = agent_config.get('created_by')
            if creator_id:
                logger.info(f"File-based agent {agent_id}: Using creator's data (created_by: {creator_id}) instead of user {user_id}")
                service_user_id = creator_id
            else:
                logger.warning(f"File-based agent {agent_id} has no created_by field, using requesting user's files")

        # Create new instance with full isolation
        logger.info(f"Creating new AgentService for agent_id={agent_id} with data isolation")
        service = AgentService(agent_config=agent_config, user_id=service_user_id, langfuse_trace=langfuse_trace)
        
        # Cache the service instance
        _agent_cache[agent_id] = service
        return service

    # Default/global agent (legacy behavior)
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(langfuse_trace=langfuse_trace)
    else:
        # Set request-scoped trace on cached singleton
        _agent_service.langfuse_trace = langfuse_trace
    return _agent_service

