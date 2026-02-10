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
from backend.services.sql_service import get_sql_service
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
    
    def __init__(self):
        """Initialize the agent with tools and LLM."""
        logger.info("Initializing AgentService")
        
        # Initialize services
        self.sql_service = get_sql_service()
        self.db_service = get_db_service()
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
        
        # Start Langfuse Trace for the entire pipeline
        from backend.core.tracing import get_tracing_manager
        tracer = get_tracing_manager()
        
        with tracer.trace_operation(name="rag_pipeline", input=query, user_id=user_id, session_id=session_id) as trace_span:
            logger.info(f"Processing query (trace_id={trace_id}): '{query[:100]}...'")
            
            try:
                # =================================================================
                # STANDARD PATH: Use agent for all queries
                # Domain-specific logic removed in favor of dynamic prompt configuration
                # =================================================================
                # Fetch prompt fresh on every request
                active_prompt = self.db_service.get_latest_active_prompt()
                logger.info(f"Active prompt fetched for trace_id={trace_id}")
                
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
                result = await self.agent_with_history.ainvoke(
                    {"input": query, "system_prompt": final_prompt},
                    config={"configurable": {"session_id": session_id or "default"}}
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
                if settings.enable_followup_questions:
                    suggested_questions = await self.followup_service.generate_followups(
                        original_question=query,
                        system_response=self._clean_answer(full_response)
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
                logger.info(f" Query processed successfully (trace_id={trace_id}, duration={duration:.2f}s)")
                
                # Update trace output
                if trace_span:
                    from langfuse.decorators import langfuse_context
                    langfuse_context.update_current_trace(
                        output=response.model_dump(),
                        metadata={"rag_used": rag_used, "chart_generated": chart_data is not None}
                    )
                
                return response.model_dump()
                
            except Exception as e:
                logger.error(f"Query processing failed (trace_id={trace_id}): {e}", exc_info=True)
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


# Singleton instance
_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """Get singleton agent service instance."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
