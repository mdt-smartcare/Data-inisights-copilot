"""
Agent service - Main RAG orchestration logic.
Coordinates SQL and vector search tools to answer user queries.
"""
import re
import json
import uuid
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.services.sql_service import get_sql_service, SQLService
from backend.services.vector_store import get_vector_store
from backend.services.embeddings import get_embedding_model
from backend.services.followup_service import FollowUpService
from backend.services.llm_registry import get_llm_registry
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
    
    def __init__(self, agent_config: Optional[Dict[str, Any]] = None):
        """Initialize the agent with tools and LLM."""
        logger.info(f"Initializing AgentService (Config: {agent_config.get('name') if agent_config else 'Default'})")
        
        # Initialize services
        self.db_service = get_db_service()
        self.agent_config = agent_config

        if agent_config and agent_config.get('db_connection_uri'):
            logger.info(f"Connecting to dedicated agent database: {agent_config['db_connection_uri']}")
            self.sql_service = SQLService(database_url=agent_config['db_connection_uri'])
            self.fixed_system_prompt = agent_config.get('system_prompt')
        else:
            self.sql_service = get_sql_service()
            self.fixed_system_prompt = None
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
        self.llm = self._llm_registry.get_langchain_llm()
        
        # Create tools
        # SQL Agent tool accepts natural language questions and handles SQL generation internally.
        self.tools = [
            Tool(
                name="sql_query_tool",
                func=self.sql_service.query,
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
        self.followup_service = FollowUpService(llm=self.llm)
        
        logger.info("AgentService initialized successfully")
    
    @property
    def vector_store(self):
        """Lazy load vector store only when needed."""
        if self._vector_store is None:
            logger.info("⚡ Lazy loading vector store on first use...")
            self._vector_store = get_vector_store()
            logger.info("✅ Vector store loaded")
        return self._vector_store
    
    def _rag_search(self, query: str) -> str:
        """RAG tool wrapper that returns string for agent."""
        docs = self.vector_store.search(query)  # Uses lazy-loaded property
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
        start_time = datetime.utcnow()
        
        # Get Langfuse callback handler for tracing
        # This groups ALL LLM calls for this query under ONE trace
        from backend.core.tracing import get_tracing_manager
        tracer = get_tracing_manager()
        
        # Create callback handler with trace context - this is the KEY fix
        # All LangChain operations will be grouped under this single trace
        langfuse_handler = tracer.get_langchain_callback(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            trace_name="rag_query"
        )
        
        # Build callbacks list for LangChain
        callbacks = [langfuse_handler] if langfuse_handler else []
        
        logger.info(f"Processing query (trace_id={trace_id}): '{query[:100]}...'")
        
        try:
            # =================================================================
            # STANDARD PATH: Use agent for all queries
            # Domain-specific logic removed in favor of dynamic prompt configuration
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

            # Execute agent with conversation memory
            # Pass system_prompt variable to the agent, creating a combined prompt
            final_prompt = f"{active_prompt}\n{formatted_examples}"
            
            logger.info(f"Invoking agent for trace_id={trace_id}")
            # Use stateful execution with session-based history
            # Pass callbacks to group all LLM calls under one trace
            # Include langfuse metadata in config for proper trace-level user/session mapping
            result = await self.agent_with_history.ainvoke(
                {"input": query, "system_prompt": final_prompt},
                config={
                    "configurable": {"session_id": session_id or "default"},
                    "callbacks": callbacks,  # This links all LLM calls to our trace
                    "metadata": {
                        "langfuse_user_id": user_id,
                        "langfuse_session_id": session_id,
                        "langfuse_tags": ["rag_query"],
                        "trace_id": trace_id,
                    }
                }
            )
            
            # Update trace with session_id, user_id, and name for proper filtering in Langfuse UI
            # This must be called AFTER the LangChain operation creates the trace
            tracer.update_current_trace_metadata(
                name="rag_query",
                session_id=session_id,
                user_id=user_id,
                metadata={"query_length": len(query), "trace_id": trace_id}
            )
            
            logger.info(f"Agent result received for trace_id={trace_id}: keys={result.keys()}")

            # Extract response
            full_response = result.get("output", "An error occurred.")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Check if RAG was used
            rag_used = any(
                action.tool == "rag_document_search_tool"
                for action, _ in intermediate_steps
            )
            
            # Only get embedding info if RAG was actually used
            if rag_used:
                embedding_info = self._get_embedding_info(query)
            else:
                embedding_info = {}
            
            # DEBUG: Write full response to file for diagnosis
            try:
                with open("/tmp/llm_response_debug.txt", "w") as f:
                    f.write(f"=== LLM RESPONSE (trace_id={trace_id}) ===\n")
                    f.write(full_response)
                    f.write("\n=== END RESPONSE ===\n")
            except Exception as debug_err:
                logger.warning(f"Failed to write debug file: {debug_err}")
            
            # Parse JSON output from response (chart data only now)
            chart_data, _ = self._parse_agent_output(full_response)
            if chart_data:
                logger.info(f"Chart data parsed: {chart_data.title}")
            else:
                logger.warning(f"NO CHART DATA PARSED from response (trace_id={trace_id})")
            
            # Generate LLM-powered follow-up questions based on response content
            # Pass the same callbacks to group follow-up generation under the same trace
            if settings.enable_followup_questions:
                suggested_questions = await self.followup_service.generate_followups(
                    original_question=query,
                    system_response=self._clean_answer(full_response),
                    callbacks=callbacks  # Group under same trace
                )
            else:
                suggested_questions = []
            
            # Format reasoning steps
            reasoning_steps = self._format_reasoning(intermediate_steps)
            
            # Build response
            response = ChatResponse(
                answer=self._clean_answer(full_response),
                chart_data=chart_data,
                suggested_questions=suggested_questions,
                reasoning_steps=reasoning_steps,
                embedding_info=EmbeddingInfo(
                    model=settings.embedding_model_name,
                    dimensions=self.embedding_model.dimension,
                    search_method="hybrid" if rag_used else "structured",
                    vector_norm=embedding_info.get("norm"),
                    docs_retrieved=len([s for a, s in intermediate_steps if a.tool == "rag_document_search_tool"])
                ),
                trace_id=trace_id,
                session_id=session_id,
                timestamp=start_time
            )
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"✅ Query processed successfully (trace_id={trace_id}, duration={duration:.2f}s)")
            
            # ============================================================
            # Track usage metrics for observability dashboard
            # ============================================================
            try:
                from backend.services.observability_service import get_observability_service
                obs_service = get_observability_service()
                
                # Estimate token counts (rough approximation)
                # In production, you'd get this from LLM response metadata
                input_tokens = len(query.split()) * 1.3  # ~1.3 tokens per word
                output_tokens = len(full_response.split()) * 1.3
                
                await obs_service.track_usage(
                    operation="rag_pipeline",
                    model=settings.openai_model,
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    latency_ms=int(duration * 1000),
                    metadata={
                        "trace_id": trace_id,
                        "rag_used": rag_used,
                        "chart_generated": chart_data is not None,
                        "tools_used": [step.tool for step in reasoning_steps],
                        "user_id": user_id
                    }
                )
                logger.debug(f"Usage tracked for trace_id={trace_id}")
            except Exception as track_err:
                logger.warning(f"Failed to track usage metrics: {track_err}")
            
            # Flush Langfuse to ensure trace is sent
            tracer.flush()
            
            return response.model_dump()
            
        except Exception as e:
            logger.error(f"Query processing failed (trace_id={trace_id}): {e}", exc_info=True)
            # Flush even on error to capture partial trace
            tracer.flush()
            raise
    

    def _get_relevant_examples(self, query: str) -> List[str]:
        """
        Retrieve relevant SQL examples using semantic search.
        Refactored to be robust and fail-safe.
        """
        try:
            examples = self.db_service.get_sql_examples()
            if not examples:
                return []
            
            # If few examples, just return all of them (up to 3)
            if len(examples) <= 3:
                return [f"Q: {ex['question']}\nSQL: {ex['sql_query']}" for ex in examples]

            # Semantic search
            query_embedding = self.embedding_model.embed_query(query)
            
            scored_examples = []
            for ex in examples:
                # In a real prod env, embeddings should be cached/stored in DB
                # For now, we compute on fly or rely on keyword fallback if too slow
                # Optimisation: caching this in memory would be good if list grows
                
                # Simple keyword overlap as baseline score
                score = 0
                q_words = set(query.lower().split())
                ex_words = set(ex['question'].lower().split())
                overlap = len(q_words.intersection(ex_words))
                score += overlap * 0.1
                
                scored_examples.append((score, ex))
            
            # Sort by score DESC
            scored_examples.sort(key=lambda x: x[0], reverse=True)
            
            # Take top 3
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


# Singleton instance for default agent
_agent_service: Optional[AgentService] = None

# Cache for dedicated agent instances: {agent_id: AgentService}
_agent_cache: Dict[int, AgentService] = {}


def get_agent_service(agent_id: Optional[int] = None, user_id: Optional[int] = None) -> AgentService:
    """Get agent service instance.
    
    If agent_id is provided, checks specific user access and returns a dedicated instance.
    Dedicated instances are cached to reuse database connections.
    Otherwise returns the singleton default instance (legacy behavior).
    """
    if agent_id:
        db = get_db_service()
        # Verify access if user_id is provided (skip for internal system calls if user_id is None)
        if user_id:
            has_access = db.check_user_access(user_id, agent_id)
            if not has_access:
                logger.warning(f"Access denied for user {user_id} to agent {agent_id}")
                raise PermissionError(f"User {user_id} does not have access to agent {agent_id}")
        
        # Check cache first
        if agent_id in _agent_cache:
            return _agent_cache[agent_id]
            
        agent_config = db.get_agent_by_id(agent_id)
        if not agent_config:
             raise ValueError(f"Agent {agent_id} not found")
             
        # Create and cache new instance
        service = AgentService(agent_config=agent_config)
        _agent_cache[agent_id] = service
        return service

    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
