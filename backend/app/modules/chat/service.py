"""
Chat application service - Full RAG pipeline with intent routing.

Handles:
- Intent classification (SQL/Vector/Hybrid)
- RAG query processing
- SQL data queries
- Vector search
- LLM response generation
- Conversation memory
- Tracing & observability
- Chart generation
"""

import uuid
import time
import asyncio
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.logging import get_logger
from app.core.utils.device import get_best_device
from app.core.utils.exceptions import AppException, ErrorCode
from app.core.config import get_settings
from app.modules.chat.schemas import (
    ChatRequest, ChatResponse, ChartData, ReasoningStep, EmbeddingInfo, SourceChunk
)
from app.modules.agents.repository import AgentRepository, AgentConfigRepository
from app.modules.ai_models.repository import AIModelRepository
from app.modules.data_sources.repository import DataSourceRepository

# Import chat module services (flat structure)
from app.modules.chat.intent_classifier import (
    IntentClassifier, IntentClassification, QueryIntent, get_intent_classifier
)
from app.modules.chat.sql_service import SQLService, SQLServiceFactory
from app.modules.chat.tracing import TracingContext, generate_trace_id
from app.modules.chat.memory import get_conversation_memory, rewrite_query_with_context
from app.modules.chat.followup import get_followup_service, generate_followups_background
from app.modules.chat.cancellation import RequestCancelled, check_cancelled
from app.modules.chat.chart_parser import parse_chart_data
from app.core.prompts import get_chart_generator_prompt, get_data_analyst_prompt, get_rag_synthesis_prompt

# FastSQL optimized pipeline (optional)
try:
    from app.modules.chat.query.fast_sql_service import (
        IntegratedFastSQLServiceFactory,
        FastSQLService,
        FastSQLResult,
        ExecutionPath
    )
    FAST_SQL_AVAILABLE = True
except ImportError as e:
    FAST_SQL_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(f"FastSQL not available: {e}")

logger = get_logger(__name__)
logger.info(f"ChatService module loaded: FAST_SQL_AVAILABLE={FAST_SQL_AVAILABLE}")


class ChatService:
    """
    Service for processing chat queries using RAG pipeline with intent routing.
    
    Flow:
    1. Classify query intent (SQL/Vector/Hybrid/Fallback)
    2. Route to appropriate handler:
       - A (SQL): Execute SQL query directly
       - B (Vector): Semantic search + LLM synthesis
       - C (Hybrid): SQL filter + Vector search + LLM synthesis
       - Fallback: Use full agent with tools
    3. Generate response with LLM
    4. Add conversation to memory
    5. Generate follow-up questions (async)
    6. Generate chart visualizations (for SQL queries)
    
    FastSQL Mode (DEFAULT: enabled):
    Automatically uses optimized pipeline when beneficial:
    - Template matching for common patterns (~5ms) - ALWAYS used when deterministic
    - Single LLM call (vs 3-4 separate calls) for complex queries
    - Pre-compiled schema manifest
    - Query memory for few-shot learning
    - Falls back gracefully to standard pipeline on errors
    """
    
    def __init__(self, db: AsyncSession, enable_fast_sql: bool = True):
        self.db = db
        self.agents = AgentRepository(db)
        self.configs = AgentConfigRepository(db)
        self.ai_models = AIModelRepository(db)
        self.data_sources = DataSourceRepository(db)
        self._settings = get_settings()
        self._intent_classifier = get_intent_classifier()
        self._memory = get_conversation_memory()
        self._followup_service = get_followup_service()
        self._sql_factory = SQLServiceFactory(self.configs, self.data_sources, self.ai_models)
        
        # FastSQL mode - enabled by default, can be disabled via settings or constructor
        # Settings can override: ENABLE_FAST_SQL=false in .env to disable globally
        settings_fast_sql = getattr(self._settings, 'enable_fast_sql', True)  # Default True
        self._use_fast_sql = enable_fast_sql and settings_fast_sql and FAST_SQL_AVAILABLE
        
        logger.info(
            f"ChatService init: enable_fast_sql={enable_fast_sql}, "
            f"settings_fast_sql={settings_fast_sql}, "
            f"FAST_SQL_AVAILABLE={FAST_SQL_AVAILABLE}, "
            f"_use_fast_sql={self._use_fast_sql}"
        )
        
        # Initialize FastSQL factory if available and enabled
        self._fast_sql_factory = None
        if self._use_fast_sql and FAST_SQL_AVAILABLE:
            self._fast_sql_factory = IntegratedFastSQLServiceFactory(
                config_repo=self.configs,
                data_source_repo=self.data_sources,
                ai_model_repo=self.ai_models
            )
            logger.info("⚡ FastSQL mode ENABLED - using optimized SQL pipeline")
        else:
            logger.info(f"FastSQL mode DISABLED: use_fast_sql={self._use_fast_sql}, available={FAST_SQL_AVAILABLE}")
    
    async def process_query(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
        fastapi_request: Optional[Request] = None,
    ) -> ChatResponse:
        """
        Process a user query through the RAG pipeline with intent routing.
        
        Args:
            request: Chat request with query and optional agent_id
            user_id: Authenticated user ID
            fastapi_request: Optional FastAPI request for cancellation detection
            
        Returns:
            ChatResponse with answer, sources, chart_data, and metadata
        """
        trace_id = generate_trace_id()
        start_time = time.time()
        session_id = request.session_id or uuid.uuid4().hex
        query = request.query.strip()
        
        # Timing dictionary to track each phase
        timings: Dict[str, float] = {}
        
        logger.info(
            "Processing chat query",
            trace_id=trace_id,
            agent_id=str(request.agent_id) if request.agent_id else None,
            query_length=len(query),
            session_id=session_id,
        )
        
        # Start tracing context
        tracing_ctx = TracingContext(
            name="chat_request",
            trace_id=trace_id,
            user_id=str(user_id),
            session_id=session_id,
            metadata={
                "agent_id": str(request.agent_id) if request.agent_id else None,
                "query_preview": query[:200] if query else None,
            },
        )
        
        try:
            with tracing_ctx:
                # Check for cancellation
                await check_cancelled(fastapi_request)
                
                # Step 1: Get agent configuration
                agent_config = None
                sql_service = None
                
                if request.agent_id:
                    agent_config = await self._get_agent_config(
                        request.agent_id, 
                        config_id=request.config_id
                    )
                    if not agent_config:
                        error_msg = (
                            f"Config {request.config_id} not found or not ready for testing"
                            if request.config_id
                            else f"Agent {request.agent_id} not found or has no active configuration"
                        )
                        raise AppException(
                            error_code=ErrorCode.RESOURCE_NOT_FOUND,
                            message=error_msg,
                            status_code=404,
                        )
                    
                    # Get SQL service for the agent's data source
                    sql_service = await self._sql_factory(
                        request.agent_id
                    )
                
                # Create LLM helper (fetches config from DB once)
                from app.modules.chat.llm_helper import LLMHelper
                llm_helper = LLMHelper(self.db, request.agent_id)
                logger.info(f"LLM Helper created for agent_id={llm_helper._model}")
                
                # Step 2: Rewrite query with conversation context
                await check_cancelled(fastapi_request)
                tracing_ctx.add_span("query_rewrite", input=query)
                
                phase_start = time.time()
                llm_config = tracing_ctx.get_llm_config()
                rewritten_query = await rewrite_query_with_context(
                    query, session_id, llm_helper=llm_helper, use_llm=True, llm_config=llm_config
                )
                timings["query_rewrite_ms"] = int((time.time() - phase_start) * 1000)
                
                tracing_ctx.update_span("query_rewrite", output=rewritten_query)
                
                # Step 3: Classify intent
                await check_cancelled(fastapi_request)
                tracing_ctx.add_span("intent_classification", input=rewritten_query)
                
                phase_start = time.time()
                schema_context = sql_service.cached_schema if sql_service else ""
                llm_config = tracing_ctx.get_llm_config()
                classification = await self._intent_classifier.classify(
                    rewritten_query,
                    llm_helper=llm_helper,
                    schema_context=schema_context,
                    llm_config=llm_config
                )
                timings["intent_classification_ms"] = int((time.time() - phase_start) * 1000)
                
                tracing_ctx.update_span(
                    "intent_classification",
                    output={"intent": classification.intent, "confidence": classification.confidence_score}
                )
                
                logger.info(
                    "Query classified",
                    intent=classification.intent,
                    confidence=classification.confidence_score,
                    trace_id=trace_id,
                )
                
                # Step 4: Route based on intent
                answer = ""
                chart_data: Optional[ChartData] = None
                dashboards: Optional[List[ChartData]] = None
                sources: List[SourceChunk] = []
                reasoning_steps: List[ReasoningStep] = []
                embedding_info = None
                comparison_insights = None
                
                # Override to fallback if confidence is too low
                final_intent = classification.intent
                if classification.confidence_score < 0.6 and final_intent in ["A", "B", "C"]:
                    logger.warning(
                        f"Low confidence ({classification.confidence_score}), falling back",
                        trace_id=trace_id,
                    )
                    final_intent = QueryIntent.FALLBACK.value
                
                if final_intent == QueryIntent.SQL_ONLY.value:
                    # Intent A: SQL only (with chart generation)
                    await check_cancelled(fastapi_request)
                    phase_start = time.time()
                    answer, reasoning_steps, chart_data = await self._handle_sql_intent(
                        rewritten_query, sql_service, agent_config, tracing_ctx, llm_helper
                    )
                    timings["sql_intent_ms"] = int((time.time() - phase_start) * 1000)
                    logger.info(
                        "TIMING: SQL intent completed",
                        trace_id=trace_id,
                        duration_ms=timings["sql_intent_ms"],
                    )
                    
                    # Generate comparison insights (optional, non-blocking)
                    # Skip if streaming is requested - comparisons will be sent via SSE
                    if sql_service and answer and not answer.startswith("No database") and not request.stream:
                        try:
                            from app.modules.chat.query.comparison_engine import generate_comparison_insights
                            
                            phase_start = time.time()
                            comp_llm = await llm_helper.get_llm(temperature=0.3)
                            schema_ctx = sql_service.cached_schema if sql_service else ""
                            
                            # Wrap with timeout - comparisons are optional, don't block main response
                            comparison_insights = await asyncio.wait_for(
                                generate_comparison_insights(
                                    original_question=rewritten_query,
                                    original_sql=reasoning_steps[0].input if reasoning_steps else rewritten_query,
                                    original_results=answer[:2000],
                                    schema_context=schema_ctx,
                                    sql_service=sql_service,
                                    llm=comp_llm,
                                    dialect="duckdb" if sql_service._is_duckdb() else "postgresql",
                                ),
                                timeout=75.0  # Max 75s for entire comparison phase
                            )
                            timings["comparison_insights_ms"] = int((time.time() - phase_start) * 1000)
                            logger.info(
                                "TIMING: Comparison insights completed",
                                trace_id=trace_id,
                                duration_ms=timings["comparison_insights_ms"],
                            )
                        except asyncio.TimeoutError:
                            timings["comparison_insights_ms"] = 75000
                            logger.info("Comparison insights timed out (75s), skipping", trace_id=trace_id)
                        except Exception as e:
                            timings["comparison_insights_ms"] = int((time.time() - phase_start) * 1000)
                            logger.debug(f"Comparison insights generation failed: {e}")
                    
                elif final_intent == QueryIntent.VECTOR_ONLY.value:
                    # Intent B: Vector only
                    await check_cancelled(fastapi_request)
                    answer, sources, reasoning_steps, embedding_info = await self._handle_vector_intent(
                        rewritten_query, agent_config, tracing_ctx, fastapi_request
                    )
                    
                elif final_intent == QueryIntent.HYBRID.value:
                    # Intent C: Hybrid (SQL filter + vector search)
                    await check_cancelled(fastapi_request)
                    answer, sources, reasoning_steps, embedding_info = await self._handle_hybrid_intent(
                        rewritten_query, classification, sql_service, agent_config, 
                        tracing_ctx, fastapi_request, llm_helper
                    )
                    
                elif final_intent == QueryIntent.DASHBOARD_GENERATOR.value:
                    # Dashboard: Generate multiple charts
                    await check_cancelled(fastapi_request)
                    answer, reasoning_steps, dashboards = await self._handle_dashboard_intent(
                        rewritten_query, sql_service, agent_config, tracing_ctx, llm_helper
                    )
                    
                else:
                    # Fallback: Use full vector search (safest default)
                    await check_cancelled(fastapi_request)
                    answer, sources, reasoning_steps, embedding_info = await self._handle_vector_intent(
                        rewritten_query, agent_config, tracing_ctx, fastapi_request
                    )
                
                # Step 5: Generate follow-up questions (async, don't block)
                # Get conversation history for context-aware followups
                conversation_history = self._memory.get_context(session_id, max_messages=5)
                
                # Get LLM config for tracing - follow-ups will be linked to parent trace
                llm_config = tracing_ctx.get_llm_config()
                
                # Add span for follow-up generation tracking
                tracing_ctx.add_span("followup_generation", input={"query": query[:100]})
                
                followup_task = asyncio.create_task(
                    generate_followups_background(
                        query, 
                        answer,
                        llm_helper=llm_helper,
                        conversation_history=conversation_history,
                        timeout=2.0,
                        llm_config=llm_config,
                    )
                )
                
                # Step 6: Save to conversation memory
                self._memory.add_exchange(session_id, query, answer)
                
                # Wait for follow-ups with timeout
                suggested_questions = []
                try:
                    suggested_questions = await asyncio.wait_for(followup_task, timeout=2.0)
                    tracing_ctx.update_span("followup_generation", output={"questions": suggested_questions})
                except asyncio.TimeoutError:
                    logger.debug("Follow-up generation timed out")
                    tracing_ctx.update_span("followup_generation", output={"error": "timeout"})
                except Exception as e:
                    logger.debug(f"Follow-up generation failed: {e}")
                    tracing_ctx.update_span("followup_generation", output={"error": str(e)})
                
                # Build response
                duration = time.time() - start_time
                timings["total_ms"] = int(duration * 1000)
                
                # Log detailed timing breakdown
                logger.info(
                    "TIMING BREAKDOWN",
                    trace_id=trace_id,
                    intent=final_intent,
                    query_rewrite_ms=timings.get("query_rewrite_ms", 0),
                    intent_classification_ms=timings.get("intent_classification_ms", 0),
                    sql_intent_ms=timings.get("sql_intent_ms", 0),
                    comparison_insights_ms=timings.get("comparison_insights_ms", 0),
                    total_ms=timings["total_ms"],
                )
                
                logger.info(
                    "Chat query completed",
                    trace_id=trace_id,
                    intent=final_intent,
                    duration_ms=int(duration * 1000),
                    sources_count=len(sources),
                    chart_generated=chart_data is not None,
                )
                
                # Default embedding info if not set
                if not embedding_info:
                    embedding_info = EmbeddingInfo(
                        model="bge-base-en-v1.5",
                        dimensions=768,
                        search_method="sql" if final_intent == "A" else "hybrid",
                        docs_retrieved=len(sources),
                    )
                
                # Set the trace output before returning
                tracing_ctx.set_trace_output(
                    output={"answer": answer[:500] if answer else None},
                    answer_preview=answer[:200] if answer else None,
                )
                
                # End the trace after all operations (including follow-up) are complete
                # This ensures parent span end time reflects actual completion
                tracing_ctx.end_trace(
                    output={
                        "answer_length": len(answer) if answer else 0,
                        "suggested_questions_count": len(suggested_questions),
                        "chart_generated": chart_data is not None,
                    }
                )
                
                return ChatResponse(
                    answer=answer,
                    chart_data=chart_data,
                    dashboards=dashboards,
                    suggested_questions=suggested_questions,
                    reasoning_steps=reasoning_steps,
                    sources=sources,
                    embedding_info=embedding_info,
                    comparison_insights=comparison_insights,
                    trace_id=trace_id,
                    session_id=session_id,
                    agent_id=str(request.agent_id) if request.agent_id else None,
                    timestamp=datetime.now(timezone.utc),
                )
                
        except RequestCancelled:
            logger.info(f"Request cancelled by client", trace_id=trace_id)
            raise AppException(
                error_code=ErrorCode.REQUEST_CANCELLED,
                message="Request cancelled by client",
                status_code=499,
            )
        except AppException:
            raise
        except Exception as e:
            logger.error(
                "Chat query failed",
                trace_id=trace_id,
                error=str(e),
                exc_info=True,
            )
            raise AppException(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to process chat query",
                status_code=500,
                details={"error": str(e)},
            )
    
    async def process_query_stream(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
        fastapi_request: Optional[Request] = None,
    ):
        """
        Process a user query and yield SSE events.
        
        Returns answer immediately, then streams comparison insights in background.
        
        Yields:
            SSE events with event type and JSON data payload
        """
        from app.modules.chat.schemas import StreamEventType
        
        trace_id = generate_trace_id()
        start_time = time.time()
        session_id = request.session_id or uuid.uuid4().hex
        query = request.query.strip()
        timings: Dict[str, float] = {}
        
        logger.info(
            "Processing STREAMING chat query",
            trace_id=trace_id,
            agent_id=str(request.agent_id) if request.agent_id else None,
            query_length=len(query),
            session_id=session_id,
        )
        
        tracing_ctx = TracingContext(
            name="chat_request_stream",
            trace_id=trace_id,
            user_id=str(user_id),
            session_id=session_id,
            metadata={
                "agent_id": str(request.agent_id) if request.agent_id else None,
                "streaming": True,
            },
        )
        
        try:
            with tracing_ctx:
                await check_cancelled(fastapi_request)
                
                # === PROGRESS: Starting ===
                yield {
                    "event": StreamEventType.PROGRESS,
                    "data": {"step": "init", "message": "Understanding your question...", "percent": 5},
                    "trace_id": trace_id,
                }
                
                # Step 1: Get agent config and SQL service
                agent_config = None
                sql_service = None
                
                if request.agent_id:
                    agent_config = await self._get_agent_config(
                        request.agent_id, 
                        config_id=request.config_id
                    )
                    if not agent_config:
                        yield {
                            "event": StreamEventType.ERROR,
                            "data": {"message": "Agent not found or has no active configuration"},
                            "trace_id": trace_id,
                        }
                        return
                    
                    sql_service = await self._sql_factory(request.agent_id)
                
                from app.modules.chat.llm_helper import LLMHelper
                llm_helper = LLMHelper(self.db, request.agent_id)
                
                # === PROGRESS: Query rewrite ===
                yield {
                    "event": StreamEventType.PROGRESS,
                    "data": {"step": "rewrite", "message": "Adding conversation context...", "percent": 10},
                    "trace_id": trace_id,
                }
                
                # Step 2: Rewrite query
                phase_start = time.time()
                llm_config = tracing_ctx.get_llm_config()
                rewritten_query = await rewrite_query_with_context(
                    query, session_id, llm_helper=llm_helper, use_llm=True, llm_config=llm_config
                )
                timings["query_rewrite_ms"] = int((time.time() - phase_start) * 1000)
                
                # === PROGRESS: Intent classification ===
                yield {
                    "event": StreamEventType.PROGRESS,
                    "data": {"step": "classify", "message": "Classifying query intent...", "percent": 15},
                    "trace_id": trace_id,
                }
                
                # Step 3: Classify intent
                phase_start = time.time()
                schema_context = sql_service.cached_schema if sql_service else ""
                classification = await self._intent_classifier.classify(
                    rewritten_query,
                    llm_helper=llm_helper,
                    schema_context=schema_context,
                    llm_config=llm_config
                )
                timings["intent_classification_ms"] = int((time.time() - phase_start) * 1000)
                
                final_intent = classification.intent
                if classification.confidence_score < 0.6 and final_intent in ["A", "B", "C"]:
                    final_intent = QueryIntent.FALLBACK.value
                
                # === PROGRESS: Intent determined ===
                intent_labels = {
                    "A": "SQL query",
                    "B": "Document search", 
                    "C": "Hybrid analysis",
                    "D": "Dashboard generation",
                }
                intent_label = intent_labels.get(final_intent, "analysis")
                yield {
                    "event": StreamEventType.PROGRESS,
                    "data": {"step": "intent", "message": f"Using {intent_label} mode...", "percent": 20},
                    "trace_id": trace_id,
                }
                
                answer = ""
                chart_data = None
                reasoning_steps = []
                sources = []
                
                # Step 4: Execute intent handler (SQL path for streaming)
                if final_intent == QueryIntent.SQL_ONLY.value:
                    # === PROGRESS: Schema retrieval ===
                    yield {
                        "event": StreamEventType.PROGRESS,
                        "data": {"step": "schema", "message": "Finding relevant tables...", "percent": 25},
                        "trace_id": trace_id,
                    }
                    
                    # Small delay to ensure progress event is sent
                    await asyncio.sleep(0.01)
                    
                    # === PROGRESS: SQL generation ===
                    yield {
                        "event": StreamEventType.PROGRESS,
                        "data": {"step": "sql_gen", "message": "Generating SQL query...", "percent": 40},
                        "trace_id": trace_id,
                    }
                    
                    phase_start = time.time()
                    answer, reasoning_steps, chart_data = await self._handle_sql_intent(
                        rewritten_query, sql_service, agent_config, tracing_ctx, llm_helper
                    )
                    timings["sql_intent_ms"] = int((time.time() - phase_start) * 1000)
                    
                    # === PROGRESS: Synthesizing ===
                    yield {
                        "event": StreamEventType.PROGRESS,
                        "data": {"step": "synthesize", "message": "Preparing response...", "percent": 85},
                        "trace_id": trace_id,
                    }
                else:
                    # === PROGRESS: Vector search ===
                    yield {
                        "event": StreamEventType.PROGRESS,
                        "data": {"step": "vector", "message": "Searching documents...", "percent": 40},
                        "trace_id": trace_id,
                    }
                    
                    # For non-SQL intents, fall back to standard processing
                    answer, sources, reasoning_steps, _ = await self._handle_vector_intent(
                        rewritten_query, agent_config, tracing_ctx, fastapi_request
                    )
                
                # === STREAM: Send answer immediately ===
                yield {
                    "event": StreamEventType.ANSWER,
                    "data": {
                        "answer": answer,
                        "intent": final_intent,
                        "session_id": session_id,
                    },
                    "trace_id": trace_id,
                }
                
                # === STREAM: Send chart data if available ===
                if chart_data:
                    yield {
                        "event": StreamEventType.CHART,
                        "data": chart_data.model_dump(),
                        "trace_id": trace_id,
                    }
                
                # === STREAM: Send reasoning steps ===
                if reasoning_steps:
                    yield {
                        "event": StreamEventType.REASONING,
                        "data": {"steps": [s.model_dump() for s in reasoning_steps]},
                        "trace_id": trace_id,
                    }
                
                # === STREAM: Generate suggestions in parallel ===
                conversation_history = self._memory.get_context(session_id, max_messages=5)
                try:
                    suggested_questions = await asyncio.wait_for(
                        generate_followups_background(
                            query, answer, llm_helper=llm_helper,
                            conversation_history=conversation_history,
                            timeout=2.0, llm_config=llm_config,
                        ),
                        timeout=3.0
                    )
                    if suggested_questions:
                        yield {
                            "event": StreamEventType.SUGGESTIONS,
                            "data": {"questions": suggested_questions},
                            "trace_id": trace_id,
                        }
                except Exception:
                    pass  # Suggestions are optional
                
                # Save to memory
                self._memory.add_exchange(session_id, query, answer)
                
                # === STREAM: Generate comparison insights in background ===
                if final_intent == QueryIntent.SQL_ONLY.value and sql_service and answer and not answer.startswith("No database"):
                    # === PROGRESS: Cross-validation ===
                    yield {
                        "event": StreamEventType.PROGRESS,
                        "data": {"step": "compare", "message": "Running cross-validation queries...", "percent": 92},
                        "trace_id": trace_id,
                    }
                    
                    try:
                        from app.modules.chat.query.comparison_engine import generate_comparison_insights
                        
                        phase_start = time.time()
                        comp_llm = await llm_helper.get_llm(temperature=0.3)
                        schema_ctx = sql_service.cached_schema if sql_service else ""
                        
                        comparison_insights = await asyncio.wait_for(
                            generate_comparison_insights(
                                original_question=rewritten_query,
                                original_sql=reasoning_steps[0].input if reasoning_steps else rewritten_query,
                                original_results=answer[:2000],
                                schema_context=schema_ctx,
                                sql_service=sql_service,
                                llm=comp_llm,
                                dialect="duckdb" if sql_service._is_duckdb() else "postgresql",
                            ),
                            timeout=75.0
                        )
                        timings["comparison_insights_ms"] = int((time.time() - phase_start) * 1000)
                        
                        if comparison_insights:
                            yield {
                                "event": StreamEventType.COMPARISON,
                                "data": {"insights": comparison_insights},
                                "trace_id": trace_id,
                            }
                            
                    except asyncio.TimeoutError:
                        logger.info("STREAM: Comparison insights timed out", trace_id=trace_id)
                    except Exception as e:
                        logger.debug(f"STREAM: Comparison generation failed: {e}")
                
                # === STREAM: Complete signal ===
                timings["total_ms"] = int((time.time() - start_time) * 1000)
                yield {
                    "event": StreamEventType.COMPLETE,
                    "data": {"timings": timings},
                    "trace_id": trace_id,
                }
                
                logger.info(
                    "STREAMING chat query completed",
                    trace_id=trace_id,
                    total_ms=timings["total_ms"],
                )
                
        except RequestCancelled:
            yield {"event": StreamEventType.ERROR, "data": {"message": "Request cancelled"}, "trace_id": trace_id}
        except AppException as e:
            logger.error(f"Stream query failed: {e.message}", exc_info=True)
            yield {"event": StreamEventType.ERROR, "data": {"message": e.message, "error_code": e.error_code}, "trace_id": trace_id}
        except Exception as e:
            logger.error(f"Stream query failed: {e}", exc_info=True)
            yield {"event": StreamEventType.ERROR, "data": {"message": str(e)}, "trace_id": trace_id}
    
    async def _handle_sql_intent(
        self,
        query: str,
        sql_service: Optional[SQLService],
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: TracingContext,
        llm_helper,
    ) -> Tuple[str, List[ReasoningStep], Optional[ChartData]]:
        """Handle Intent A: SQL-only queries. Returns answer, reasoning steps, and optional chart data."""
        import time as timing_module
        
        reasoning_steps = []
        chart_data = None
        sql_intent_start = timing_module.perf_counter()
        
        if not sql_service:
            return "No database connection configured for this agent.", reasoning_steps, None
        
        tracing_ctx.add_span("sql_query", input=query)
        
        try:
            # ============================================================
            # FastSQL Path: Optimized single-call pipeline
            # ============================================================
            logger.info(
                f"FastSQL check: use_fast_sql={self._use_fast_sql}, "
                f"factory={self._fast_sql_factory is not None}, "
                f"agent_config={agent_config is not None}"
            )
            if self._use_fast_sql and self._fast_sql_factory and agent_config:
                agent_id = agent_config.get("agent_id")
                logger.info(f"FastSQL: agent_id={agent_id}")
                if agent_id:
                    try:
                        fast_service = await self._fast_sql_factory(agent_id)
                        logger.info(f"FastSQL: service created={fast_service is not None}")
                        if fast_service:
                            logger.info(f"⚡ Using FastSQL for query: {query[:50]}...")
                            return await self._handle_fast_sql(
                                query, fast_service, sql_service, agent_config, 
                                tracing_ctx, llm_helper, sql_intent_start
                            )
                        else:
                            logger.warning("FastSQL factory returned None, using standard path")
                    except Exception as e:
                        logger.warning(f"FastSQL initialization failed: {e}, using standard path")
                else:
                    logger.info("FastSQL: skipped - no agent_id in agent_config")
            else:
                logger.info(
                    f"FastSQL: skipped - conditions not met: "
                    f"use_fast_sql={self._use_fast_sql}, "
                    f"has_factory={self._fast_sql_factory is not None}, "
                    f"has_config={agent_config is not None}"
                )
            
            # ============================================================
            # PHASE 1: SQL Generation + Validation + Execution (query_async)
            # ============================================================
            phase1_start = timing_module.perf_counter()
            llm_config = tracing_ctx.get_llm_config()
            result = await sql_service.query_async(
                query, 
                llm_helper=llm_helper,
                llm_config=llm_config
            )
            phase1_duration = timing_module.perf_counter() - phase1_start
            
            reasoning_steps.append(ReasoningStep(
                tool="sql_query",
                input=query,
                output=result[:500] if len(result) > 500 else result,
            ))
            
            tracing_ctx.update_span("sql_query", output=result[:500])
            
            # ============================================================
            # PHASE 2: Response Synthesis with Chart Generation
            # ============================================================
            phase2_start = timing_module.perf_counter()
            schema_context = sql_service.cached_schema if sql_service else ""
            raw_answer = await self._synthesize_sql_response_with_chart(
                query, result, agent_config, schema_context, tracing_ctx=tracing_ctx
            )
            phase2_duration = timing_module.perf_counter() - phase2_start
            
            # ============================================================
            # PHASE 3: Chart Parsing
            # ============================================================
            phase3_start = timing_module.perf_counter()
            chart_data, answer = parse_chart_data(raw_answer)
            phase3_duration = timing_module.perf_counter() - phase3_start
            
            if chart_data:
                logger.info(f"Chart generated: type={chart_data.type}, title={chart_data.title}")
                tracing_ctx.add_span("chart_generation", input="SQL results")
                tracing_ctx.update_span("chart_generation", output={"type": chart_data.type})
            
            # ============================================================
            # TIMING SUMMARY LOG
            # ============================================================
            total_duration = timing_module.perf_counter() - sql_intent_start
            logger.info(
                "⏱ SQL_INTENT_TIMING: "
                f"total={total_duration:.2f}s | "
                f"sql_pipeline={phase1_duration:.2f}s ({phase1_duration/total_duration*100:.1f}%) | "
                f"synthesis={phase2_duration:.2f}s ({phase2_duration/total_duration*100:.1f}%) | "
                f"chart_parse={phase3_duration:.3f}s",
                sql_pipeline_ms=int(phase1_duration * 1000),
                synthesis_ms=int(phase2_duration * 1000),
                chart_parse_ms=int(phase3_duration * 1000),
                total_ms=int(total_duration * 1000),
            )
            
            return answer, reasoning_steps, chart_data
            
        except Exception as e:
            logger.error(f"SQL query failed: {e}")
            return f"Failed to execute database query: {str(e)}", reasoning_steps, None
    
    async def _handle_fast_sql(
        self,
        query: str,
        fast_service: "FastSQLService",
        sql_service: SQLService,
        agent_config: Dict[str, Any],
        tracing_ctx: TracingContext,
        llm_helper,
        start_time: float,
    ) -> Tuple[str, List[ReasoningStep], Optional[ChartData]]:
        """
        Handle SQL generation using FastSQLService (optimized pipeline).
        
        This method uses the new optimized pipeline which:
        - Uses template matching for common patterns (~5ms)
        - Single LLM call for intent + relevance + SQL (~1s)
        - CTE rewriting for deterministic transformation
        - Query memory for few-shot learning
        
        Falls back to standard SQL service on errors.
        """
        import time as timing_module
        
        reasoning_steps = []
        chart_data = None
        
        tracing_ctx.add_span("fast_sql_generate", input=query)
        
        try:
            # Generate SQL using optimized pipeline
            fast_start = timing_module.perf_counter()
            fast_result = await fast_service.generate(query)
            fast_duration = timing_module.perf_counter() - fast_start
            
            tracing_ctx.update_span("fast_sql_generate", output={
                "intent": fast_result.intent,
                "path": fast_result.execution_path.value,
                "confidence": fast_result.confidence,
                "time_ms": fast_result.total_time_ms
            })
            
            # Log performance
            logger.info(
                f"⚡ FAST_SQL: path={fast_result.execution_path.value}, "
                f"intent={fast_result.intent}, confidence={fast_result.confidence:.2f}, "
                f"time={fast_result.total_time_ms:.0f}ms "
                f"(template={fast_result.template_time_ms:.0f}, memory={fast_result.memory_time_ms:.0f}, "
                f"llm={fast_result.llm_time_ms:.0f}, rewrite={fast_result.rewrite_time_ms:.0f})"
            )
            
            # Handle non-SQL intents
            if fast_result.intent != "sql":
                # Delegate to appropriate handler
                if fast_result.intent == "vector":
                    logger.info(f"FastSQL routed to vector search: {query[:50]}...")
                    return "This question requires document search. Please rephrase or ask a data question.", reasoning_steps, None
                elif fast_result.intent == "clarification":
                    return "Could you please clarify your question?", reasoning_steps, None
                elif fast_result.intent == "general":
                    return "This appears to be a general question not related to the data.", reasoning_steps, None
            
            # Check relevance
            if not fast_result.is_relevant:
                return "This question doesn't appear to be related to the available data.", reasoning_steps, None
            
            # Check success
            if not fast_result.is_successful or not fast_result.sql:
                error_msg = "; ".join(fast_result.errors) if fast_result.errors else "Could not generate SQL"
                logger.warning(f"FastSQL generation failed: {error_msg}")
                # Fall back to standard SQL service
                tracing_ctx.add_span("fast_sql_fallback", input="FastSQL failed, using standard")
                return await self._handle_sql_intent_standard(
                    query, sql_service, agent_config, tracing_ctx, llm_helper, start_time
                )
            
            # Execute the generated SQL via standard SQL service
            tracing_ctx.add_span("sql_execute", input=fast_result.sql[:200])
            exec_start = timing_module.perf_counter()
            
            # Use sync execute_query wrapped for async
            loop = asyncio.get_event_loop()
            results, row_count = await loop.run_in_executor(
                None, 
                sql_service.execute_query, 
                fast_result.sql
            )
            result = sql_service._format_results(results, row_count)
            exec_duration = timing_module.perf_counter() - exec_start
            
            reasoning_steps.append(ReasoningStep(
                tool="fast_sql_query",
                input=query,
                output=f"[{fast_result.execution_path.value}] {fast_result.sql[:300]}..."
            ))
            
            tracing_ctx.update_span("sql_execute", output=result[:500] if result else "empty")
            
            # Synthesize response with chart
            schema_context = sql_service.cached_schema if sql_service else ""
            raw_answer = await self._synthesize_sql_response_with_chart(
                query, result, agent_config, schema_context, tracing_ctx=tracing_ctx
            )
            
            chart_data, answer = parse_chart_data(raw_answer)
            
            if chart_data:
                logger.info(f"Chart generated: type={chart_data.type}")
                tracing_ctx.add_span("chart_generation", input={"type": chart_data.type})
            
            # Log total timing
            total_duration = timing_module.perf_counter() - start_time
            logger.info(
                f"⚡ FAST_SQL_INTENT_TIMING: total={total_duration:.2f}s | "
                f"sql_gen={fast_duration:.2f}s | exec={exec_duration:.2f}s"
            )
            
            # Learn from successful execution (async, don't block)
            if fast_result.is_successful:
                asyncio.create_task(
                    fast_service.provide_feedback(fast_result, "positive")
                )
            
            return answer, reasoning_steps, chart_data
            
        except Exception as e:
            logger.error(f"FastSQL failed, falling back: {e}")
            tracing_ctx.add_span("fast_sql_fallback", input=f"Error: {str(e)[:100]}")
            # Fall back to standard SQL service
            return await self._handle_sql_intent_standard(
                query, sql_service, agent_config, tracing_ctx, llm_helper, start_time
            )
    
    async def _handle_sql_intent_standard(
        self,
        query: str,
        sql_service: SQLService,
        agent_config: Dict[str, Any],
        tracing_ctx: TracingContext,
        llm_helper,
        start_time: float,
    ) -> Tuple[str, List[ReasoningStep], Optional[ChartData]]:
        """Standard SQL intent handling (fallback path)."""
        import time as timing_module
        
        reasoning_steps = []
        chart_data = None
        
        phase1_start = timing_module.perf_counter()
        llm_config = tracing_ctx.get_llm_config()
        result = await sql_service.query_async(
            query, 
            llm_helper=llm_helper,
            llm_config=llm_config
        )
        phase1_duration = timing_module.perf_counter() - phase1_start
        
        reasoning_steps.append(ReasoningStep(
            tool="sql_query",
            input=query,
            output=result[:500] if len(result) > 500 else result,
        ))
        
        schema_context = sql_service.cached_schema if sql_service else ""
        raw_answer = await self._synthesize_sql_response_with_chart(
            query, result, agent_config, schema_context, tracing_ctx=tracing_ctx
        )
        
        chart_data, answer = parse_chart_data(raw_answer)
        
        total_duration = timing_module.perf_counter() - start_time
        logger.info(f"SQL_INTENT_STANDARD: total={total_duration:.2f}s, sql={phase1_duration:.2f}s")
        
        return answer, reasoning_steps, chart_data
            
    async def _handle_dashboard_intent(
        self,
        query: str,
        sql_service: Optional[SQLService],
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: TracingContext,
        llm_helper,
    ) -> Tuple[str, List[ReasoningStep], Optional[List[ChartData]]]:
        """Handle Dashboard Intent: Generates multiple queries in parallel for a dashboard view."""
        reasoning_steps = []
        if not sql_service:
            return "No database connection configured for this agent.", reasoning_steps, None
            
        tracing_ctx.add_span("dashboard_generation", input=query)
        
        llm = await llm_helper.get_llm(temperature=0.2)
        
        schema_context = sql_service.cached_schema if sql_service else ""
        prompt = f"""
        The user wants a high-level overview or dashboard for the following request: "{query}"
        
        DATABASE SCHEMA:
        {schema_context}
        
        INSTRUCTIONS:
        1. Generate exactly 4 distinct natural language questions that can be answered by the database. 
        2. Use ONLY column names and table names present in the schema above. Do NOT invent columns like "patient_status" if they are not in the schema.
        3. If there are no clear metrics, focus on row counts, category distributions, or trend over time using provided date columns.
        4. Each question should be independent and designed for a specific chart type:
           - 1 Pie Chart (categorical distribution)
           - 1 Bar or Line Chart (trends or comparisons)
           - 1 Scorecard (single key metric like average or total)
           - 1 Detail or Trend Chart (time-series)
        
        Output ONLY the 4 questions, one per line. No numbering, no extra text.
        """
        
        try:
            # Pass tracing callback to capture token usage
            llm_config = tracing_ctx.get_llm_config()
            response = await llm.ainvoke(prompt, config=llm_config)
            # Split by lines and remove leading numbering (e.g., "1. ")
            questions = [re.sub(r'^\d+[\.\)]\s*', '', q.strip()) for q in response.content.splitlines() if q.strip()]

            if not questions:
                return "Failed to generate dashboard queries.", reasoning_steps, None
                
            reasoning_steps.append(ReasoningStep(
                tool="dashboard_planner",
                input=query,
                output="Generated dashboard queries:\n" + "\n".join(questions),
            ))
            
            # Get LLM config for tracing
            sub_llm_config = tracing_ctx.get_llm_config()
            
            # Helper for parallel sub-query processing (SQL + Synthesis)
            async def process_subquery(idx, sub_q):
                try:
                    # 1. Execute SQL directly asynchronously (avoids event loop mismatch)
                    sql_result = await sql_service.query_async(
                        sub_q, 
                        llm_helper=llm_helper,
                        llm_config=sub_llm_config
                    )
                    
                    # 2. Skip synthesis if query failed or returned no data
                    if not sql_result or sql_result.startswith("Failed") or "No results found" in sql_result:
                        return idx, None, sql_result
                        
                    # 3. Synthesize results with chart generation
                    raw_answer = await self._synthesize_sql_response_with_chart(
                        sub_q, sql_result, agent_config, schema_context, tracing_ctx=tracing_ctx
                    )
                    
                    # 4. Parse chart data
                    chart, _ = parse_chart_data(raw_answer)
                    return idx, chart, sql_result
                except Exception as e:
                    logger.error(f"Dashboard sub-query {idx} processing failed: {e}")
                    return idx, None, f"Error: {str(e)}"

            # Execute all sub-queries and synthesis in parallel with a semaphore to prevent resource exhaustion
            semaphore = asyncio.Semaphore(2)  # Limit to 2 concurrent sub-queries
            
            async def sem_process_subquery(idx, sub_q):
                async with semaphore:
                    return await process_subquery(idx, sub_q)

            tasks = [sem_process_subquery(i, q) for i, q in enumerate(questions)]
            results = await asyncio.gather(*tasks)
            
            dashboards = []
            # Sort results by index to maintain order
            sorted_results = sorted(results, key=lambda x: x[0])
            
            for idx, chart, sql_result in sorted_results:
                sub_query = questions[idx]
                
                reasoning_steps.append(ReasoningStep(
                    tool=f"sql_query_{idx}",
                    input=sub_query,
                    output=(sql_result[:500] if sql_result else "No result")
                ))
                
                if chart:
                    dashboards.append(chart)
            
            if not dashboards:
                main_answer = "I've analyzed your request for an overview, but I couldn't find enough specific data to generate visual charts. You can see the details of what I attempted in the reasoning steps."
            else:
                main_answer = f"Here is an overview for '{query}'. I've synthesized the available data into {len(dashboards)} charts."
                
            return main_answer, reasoning_steps, dashboards
            
        except Exception as e:
            logger.error(f"Dashboard generation failed: {e}")
            return f"Failed to generate dashboard: {str(e)}", reasoning_steps, None
    
    async def _handle_vector_intent(
        self,
        query: str,
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: TracingContext,
        fastapi_request: Optional[Request] = None,
    ) -> Tuple[str, List[SourceChunk], List[ReasoningStep], EmbeddingInfo]:
        """Handle Intent B: Vector-only queries."""
        reasoning_steps = []
        
        # Get embedding model
        tracing_ctx.add_span("embedding", input=query)
        embedding_model, embedding_info = await self._get_embedding_model(agent_config)
        
        # Embed query
        query_embedding = await self._embed_query(query, embedding_model)
        tracing_ctx.update_span("embedding", output={"dimensions": len(query_embedding)})
        
        await check_cancelled(fastapi_request)
        
        # Search vector database
        tracing_ctx.add_span("vector_search", input=query)
        vector_db_name = self._get_vector_db_name(agent_config)
        top_k = 5
        if agent_config:
            rag_config = agent_config.get("rag_config", {})
            if isinstance(rag_config, str):
                rag_config = json.loads(rag_config)
            top_k = rag_config.get("top_k_final", 5)
        
        sources, search_time = await self._search_vectors(query_embedding, vector_db_name, top_k)
        
        reasoning_steps.append(ReasoningStep(
            tool="vector_search",
            input=query,
            output=f"Retrieved {len(sources)} relevant documents",
        ))
        tracing_ctx.update_span("vector_search", output={"count": len(sources), "time_ms": search_time})
        
        await check_cancelled(fastapi_request)
        
        # Synthesize response with LLM
        tracing_ctx.add_span("llm_synthesis", input=query)
        answer = await self._synthesize_rag_response(query, sources, agent_config, tracing_ctx=tracing_ctx)
        
        reasoning_steps.append(ReasoningStep(
            tool="llm_synthesis",
            input=f"Synthesize answer from {len(sources)} sources",
            output=f"Generated {len(answer)} character response",
        ))
        tracing_ctx.update_span("llm_synthesis", output={"answer_length": len(answer)})
        
        emb_info = EmbeddingInfo(
            model=embedding_info.get("model", "bge-base-en-v1.5"),
            dimensions=embedding_info.get("dimensions", 768),
            search_method="vector",
            docs_retrieved=len(sources),
        )
        
        return answer, sources, reasoning_steps, emb_info
    
    async def _handle_hybrid_intent(
        self,
        query: str,
        classification: IntentClassification,
        sql_service: Optional[SQLService],
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: TracingContext,
        fastapi_request: Optional[Request] = None,
        llm_helper=None,
    ) -> Tuple[str, List[SourceChunk], List[ReasoningStep], EmbeddingInfo]:
        """
        Handle Intent C: Hybrid queries.
        
        For schema-aware indexing (DDL per table), this falls back to SQL generation
        since semantic schema retrieval is built into the SQL service.
        """
        reasoning_steps = []
        
        if not sql_service:
            # Fall back to pure vector search if no SQL available
            return await self._handle_vector_intent(
                query, agent_config, tracing_ctx, fastapi_request
            )
        
        # Check if we're using schema-aware indexing (no unstructured document vectors)
        chunking_config = agent_config.get("chunking_config", {}) if agent_config else {}
        if isinstance(chunking_config, str):
            chunking_config = json.loads(chunking_config)
        
        use_schema_aware = chunking_config.get("use_schema_aware_indexing", True)
        
        if use_schema_aware:
            # For schema-aware indexing, hybrid intent uses SQL generation
            # The SQL service already has semantic schema retrieval built in
            logger.info("Hybrid intent with schema-aware indexing - using SQL generation")
            answer, sql_reasoning, chart_data = await self._handle_sql_intent(
                query, sql_service, agent_config, tracing_ctx, llm_helper
            )
            
            emb_info = EmbeddingInfo(
                model="bge-base-en-v1.5",
                dimensions=768,
                search_method="hybrid_sql",
                docs_retrieved=0,
            )
            
            return answer, [], sql_reasoning, emb_info
        
        # Legacy path: SQL filter + vector search (for parent-child chunking)
        filter_ids = []
        if classification.sql_filter:
            tracing_ctx.add_span("sql_filter", input=classification.sql_filter)
            
            try:
                # Use asyncio.to_thread to prevent blocking the event loop
                filter_result = await asyncio.to_thread(sql_service.run, classification.sql_filter)
                
                # Parse IDs from result
                import ast
                try:
                    parsed = ast.literal_eval(filter_result)
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict) and 'patient_id' in item:
                                filter_ids.append(str(item['patient_id']))
                            elif isinstance(item, tuple) and len(item) > 0:
                                filter_ids.append(str(item[0]))
                            else:
                                filter_ids.append(str(item))
                except Exception:
                    logger.warning(f"Could not parse SQL filter result: {filter_result[:200]}")
                
                reasoning_steps.append(ReasoningStep(
                    tool="sql_filter",
                    input=classification.sql_filter,
                    output=f"Found {len(filter_ids)} matching IDs",
                ))
                tracing_ctx.update_span("sql_filter", output={"count": len(filter_ids)})
                
            except Exception as e:
                logger.error(f"SQL filter failed: {e}")
                reasoning_steps.append(ReasoningStep(
                    tool="sql_filter",
                    input=classification.sql_filter,
                    output=f"Filter failed: {str(e)}",
                ))
        
        if not filter_ids:
            # No IDs found, fall back to SQL generation
            logger.info("No filter IDs found, falling back to SQL generation")
            answer, sql_reasoning, chart_data = await self._handle_sql_intent(
                query, sql_service, agent_config, tracing_ctx, llm_helper
            )
            
            emb_info = EmbeddingInfo(
                model="bge-base-en-v1.5",
                dimensions=768,
                search_method="hybrid_sql_fallback",
                docs_retrieved=0,
            )
            return answer, [], sql_reasoning, emb_info
        
        await check_cancelled(fastapi_request)
        
        # Step 2: Vector search with metadata filter
        embedding_model, embedding_info = await self._get_embedding_model(agent_config)
        query_embedding = await self._embed_query(query, embedding_model)
        
        vector_db_name = self._get_vector_db_name(agent_config)
        
        # Build metadata filter for ChromaDB
        vector_filter = {"patient_id": {"$in": filter_ids}}
        
        tracing_ctx.add_span("filtered_vector_search", input=query)
        sources, search_time = await self._search_vectors(
            query_embedding, vector_db_name, 
            top_k=10, 
            metadata_filter=vector_filter
        )
        
        reasoning_steps.append(ReasoningStep(
            tool="filtered_vector_search",
            input=f"Search with {len(filter_ids)} ID filter",
            output=f"Retrieved {len(sources)} documents",
        ))
        tracing_ctx.update_span("filtered_vector_search", output={"count": len(sources)})
        
        await check_cancelled(fastapi_request)
        
        # Step 3: Synthesize response
        answer = await self._synthesize_rag_response(query, sources, agent_config, tracing_ctx=tracing_ctx)
        
        reasoning_steps.append(ReasoningStep(
            tool="llm_synthesis",
            input=f"Synthesize from {len(sources)} filtered sources",
            output=f"Generated response",
        ))
        
        emb_info = EmbeddingInfo(
            model=embedding_info.get("model", "bge-base-en-v1.5"),
            dimensions=embedding_info.get("dimensions", 768),
            search_method="hybrid",
            docs_retrieved=len(sources),
        )
        
        return answer, sources, reasoning_steps, emb_info
    
    # PHI column names that should have their values redacted
    PHI_COLUMNS = {
        'first_name', 'last_name', 'middle_name', 'name', 'patient_name', 'full_name',
        'birth_date', 'birthdate', 'dob', 'date_of_birth',
        'phone_number', 'phone', 'mobile', 'contact_number', 'telephone',
        'email', 'email_address',
        'address', 'street_address', 'home_address',
        'ssn', 'social_security_number', 'national_id', 'identity_value',
        'mrn', 'medical_record_number',
    }
    
    def _redact_tabular_phi(self, sql_result: str) -> str:
        """
        Redact PHI values from tabular SQL results based on column names.
        
        This catches names and other PHI that pattern-based redaction misses.
        """
        lines = sql_result.strip().split('\n')
        if len(lines) < 2:
            return sql_result
        
        # Parse header to find PHI columns
        header = lines[0]
        columns = [col.strip().lower() for col in header.split('|')]
        
        # Find indices of PHI columns
        phi_indices = []
        for i, col in enumerate(columns):
            if col in self.PHI_COLUMNS:
                phi_indices.append(i)
        
        if not phi_indices:
            return sql_result
        
        # Redact values in PHI columns (skip header and separator lines)
        redacted_lines = [lines[0]]  # Keep header
        phi_counter = {}
        
        for line in lines[1:]:
            # Skip separator lines (e.g., "------|------")
            if line.strip().startswith('-') or '---' in line:
                redacted_lines.append(line)
                continue
            
            parts = line.split('|')
            for i in phi_indices:
                if i < len(parts):
                    original_value = parts[i].strip()
                    if original_value and original_value.lower() not in ('none', 'null', ''):
                        # Get column name for placeholder
                        col_name = columns[i].upper()
                        if col_name not in phi_counter:
                            phi_counter[col_name] = 0
                        phi_counter[col_name] += 1
                        placeholder = f"[{col_name}_{phi_counter[col_name]:03d}]"
                        parts[i] = f" {placeholder} "
            
            redacted_lines.append('|'.join(parts))
        
        if phi_counter:
            total_redacted = sum(phi_counter.values())
            logger.info(f"Column-based PHI redacted: {total_redacted} values from columns {list(phi_counter.keys())}")
        
        return '\n'.join(redacted_lines)
    
    def _format_raw_sql_results(self, sql_result: str) -> str:
        """
        Format raw SQL results for display without LLM interpretation.
        
        Returns the SQL results in a clean, readable format with:
        - Row count summary
        - Tabular data preserved
        - No AI interpretation or analysis
        - PHI redacted for HIPAA compliance
        """
        if not sql_result or sql_result.strip() == "":
            return "No results returned from query."
        
        # Check for error messages
        if "Failed to execute query" in sql_result or "Error:" in sql_result:
            return sql_result
        
        # Apply column-based PHI redaction first (catches names in known columns)
        sql_result = self._redact_tabular_phi(sql_result)
        
        # Apply pattern-based PHI redaction (catches SSN, dates, phones in any column)
        from app.core.utils.phi_redactor import get_phi_redactor
        phi_redactor = get_phi_redactor()
        if phi_redactor.enabled:
            redaction_result = phi_redactor.redact(sql_result)
            sql_result = redaction_result.redacted_text
            if redaction_result.has_phi:
                logger.info(f"Pattern-based PHI redacted from raw SQL results: {redaction_result.phi_count} items")
        
        # Count rows (subtract header row if present)
        lines = sql_result.strip().split('\n')
        row_count = len(lines) - 1 if len(lines) > 1 else 0
        
        # Format with a header indicating raw results mode
        formatted = "**Raw Query Results**\n\n"
        formatted += f"*{row_count} row(s) returned*\n\n"
        formatted += "```\n"
        formatted += sql_result
        formatted += "\n```"
        
        return formatted
    
    async def _synthesize_sql_response_with_chart(
        self,
        query: str,
        sql_result: str,
        agent_config: Optional[Dict[str, Any]],
        schema_context: str = "",
        tracing_ctx: Optional["TracingContext"] = None,
    ) -> str:
        """Synthesize a natural language response from SQL results with chart generation."""
        # Check if synthesis should be skipped (raw results mode)
        skip_synthesis = self._settings.skip_result_synthesis
        if agent_config:
            # Agent-level config overrides global setting (check rag_config)
            rag_config = agent_config.get("rag_config", {})
            if isinstance(rag_config, str):
                rag_config = json.loads(rag_config) if rag_config else {}
            skip_synthesis = rag_config.get("skip_result_synthesis", rag_config.get("skipResultSynthesis", skip_synthesis))
        
        if skip_synthesis:
            logger.info("Skipping LLM synthesis - returning raw SQL results")
            return self._format_raw_sql_results(sql_result)
        
        from openai import AsyncOpenAI
        
        base_prompt = get_data_analyst_prompt()
        # Inject schema context for domain-aware analysis
        if schema_context:
            base_prompt = base_prompt.replace("{schema_context}", schema_context)
        else:
            base_prompt = base_prompt.replace("{schema_context}", "No schema context available.")
        
        if agent_config and agent_config.get("system_prompt"):
            base_prompt = agent_config["system_prompt"]
        
        # Append chart generation rules to the system prompt
        system_prompt = base_prompt + get_chart_generator_prompt()
        
        # Hard short-circuit: If the SQL execution pipeline failed all its retries, 
        # do NOT send the error trace to the LLM. The LLM ignores negative constraints
        # and starts writing SQL patches in the chat UI.
        if "Failed to execute query after" in sql_result:
            return (
                "I apologize, but I couldn't execute the database query to retrieve this data. "
                "The system ran into a technical limitation with the available fields. "
                "Please try asking the question in a different way or check if the target data exists."
            )
        
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        
        # Truncate large result sets to avoid overwhelming the LLM and token limits
        # For chart generation, we only need representative data, not all rows
        result_lines = sql_result.split('\n')
        if len(result_lines) > 50:
            # Keep first 40 rows + summary
            truncated_result = '\n'.join(result_lines[:40])
            truncated_result += f"\n\n[... {len(result_lines) - 40} more rows truncated for brevity ...]\n"
            truncated_result += f"Total rows: {len(result_lines) - 2}"  # Subtract header rows
            sql_result_for_llm = truncated_result
        else:
            sql_result_for_llm = sql_result
        
        # Track this generation in Langfuse
        if tracing_ctx:
            tracing_ctx.add_generation(
                name="sql_synthesis_with_chart",
                model="gpt-4o",
                input={"query": query, "results_preview": sql_result_for_llm[:500]},
            )
        
        # Apply PHI redaction to SQL results before sending to LLM
        # This protects patient names, DOBs, and other HIPAA identifiers
        from app.core.utils.phi_redactor import get_phi_redactor
        phi_redactor = get_phi_redactor()
        if phi_redactor.enabled:
            redaction_result = phi_redactor.redact(sql_result_for_llm)
            sql_result_for_llm = redaction_result.redacted_text
            if redaction_result.has_phi:
                logger.info(f"PHI redacted from synthesis input: {redaction_result.phi_count} items")
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Query: {query}\n\nResults:\n{sql_result_for_llm}\n\nProvide a clear, helpful summary of these results. If the data is suitable for visualization, include a chart JSON block."},
                ],
                temperature=0.0,
                max_tokens=3000,  # Increased from 2000 to prevent JSON truncation
            )
            content = response.choices[0].message.content
            
            # End generation tracking with usage stats
            if tracing_ctx and response.usage:
                tracing_ctx.end_generation(
                    name="sql_synthesis_with_chart",
                    output=content[:500] if content else None,
                    usage={
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    }
                )
            
            return content
        except Exception as e:
            logger.error(f"SQL response synthesis failed: {e}")
            if tracing_ctx:
                tracing_ctx.end_generation(
                    name="sql_synthesis_with_chart",
                    output={"error": str(e)},
                )
            return sql_result  # Return raw results as fallback
    
    async def _synthesize_sql_response(
        self,
        query: str,
        sql_result: str,
        agent_config: Optional[Dict[str, Any]],
        schema_context: str = "",
        tracing_ctx: Optional["TracingContext"] = None,
    ) -> str:
        """Synthesize a natural language response from SQL results (without chart)."""
        # Check if synthesis should be skipped (raw results mode)
        skip_synthesis = self._settings.skip_result_synthesis
        if agent_config:
            # Agent-level config overrides global setting (check rag_config)
            rag_config = agent_config.get("rag_config", {})
            if isinstance(rag_config, str):
                rag_config = json.loads(rag_config) if rag_config else {}
            skip_synthesis = rag_config.get("skip_result_synthesis", rag_config.get("skipResultSynthesis", skip_synthesis))
        
        if skip_synthesis:
            logger.info("Skipping LLM synthesis - returning raw SQL results")
            return self._format_raw_sql_results(sql_result)
        
        from openai import AsyncOpenAI
        
        system_prompt = get_data_analyst_prompt()
        # Inject schema context for domain-aware analysis
        if schema_context:
            system_prompt = system_prompt.replace("{schema_context}", schema_context)
        else:
            system_prompt = system_prompt.replace("{schema_context}", "No schema context available.")
        
        if agent_config and agent_config.get("system_prompt"):
            system_prompt = agent_config["system_prompt"]
        
        # Hard short-circuit: If the SQL execution pipeline failed all its retries, 
        # do NOT send the error trace to the LLM. The LLM ignores negative constraints
        # and starts writing SQL patches in the chat UI.
        if "Failed to execute query after" in sql_result:
            return (
                "I apologize, but I couldn't execute the database query to retrieve this data. "
                "The system ran into a technical limitation with the available fields. "
                "Please try asking the question in a different way or check if the target data exists."
            )
        
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        
        # Track this generation in Langfuse
        if tracing_ctx:
            tracing_ctx.add_generation(
                name="sql_synthesis",
                model="gpt-4o",
                input={"query": query, "results_preview": sql_result[:500]},
            )
        
        # Apply PHI redaction to SQL results before sending to LLM
        from app.core.utils.phi_redactor import get_phi_redactor
        phi_redactor = get_phi_redactor()
        if phi_redactor.enabled:
            redaction_result = phi_redactor.redact(sql_result)
            sql_result = redaction_result.redacted_text
            if redaction_result.has_phi:
                logger.info(f"PHI redacted from synthesis input: {redaction_result.phi_count} items")
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Query: {query}\n\nResults:\n{sql_result}\n\nProvide a clear, helpful summary of these results."},
                ],
                temperature=0.0,
                max_tokens=1000,
            )
            content = response.choices[0].message.content
            
            # End generation tracking with usage stats
            if tracing_ctx and response.usage:
                tracing_ctx.end_generation(
                    name="sql_synthesis",
                    output=content[:500] if content else None,
                    usage={
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    }
                )
            
            return content
        except Exception as e:
            logger.error(f"SQL response synthesis failed: {e}")
            if tracing_ctx:
                tracing_ctx.end_generation(
                    name="sql_synthesis",
                    output={"error": str(e)},
                )
            return sql_result  # Return raw results as fallback
    
    async def _synthesize_rag_response(
        self,
        query: str,
        sources: List[SourceChunk],
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: Optional["TracingContext"] = None,
    ) -> str:
        """Synthesize a response from RAG sources using LLM."""
        from openai import AsyncOpenAI
        
        # Build context from sources
        context_parts = []
        for i, source in enumerate(sources, 1):
            context_parts.append(f"[{i}] {source.content}")
        context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."
        
        # Get system prompt
        system_prompt = get_rag_synthesis_prompt()
        if agent_config and agent_config.get("system_prompt"):
            system_prompt = agent_config["system_prompt"]
        
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        
        # Track this generation in Langfuse
        if tracing_ctx:
            tracing_ctx.add_generation(
                name="rag_synthesis",
                model="gpt-4o",
                input={"query": query, "sources_count": len(sources)},
            )
        
        # Apply PHI redaction to RAG context before sending to LLM
        from app.core.utils.phi_redactor import get_phi_redactor
        phi_redactor = get_phi_redactor()
        if phi_redactor.enabled:
            redaction_result = phi_redactor.redact(context)
            context = redaction_result.redacted_text
            if redaction_result.has_phi:
                logger.info(f"PHI redacted from RAG context: {redaction_result.phi_count} items")
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
                ],
                temperature=0.0,
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            
            # End generation tracking with usage stats
            if tracing_ctx and response.usage:
                tracing_ctx.end_generation(
                    name="rag_synthesis",
                    output=content[:500] if content else None,
                    usage={
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    }
                )
            
            return content
        except Exception as e:
            logger.error(f"RAG response synthesis failed: {e}")
            if tracing_ctx:
                tracing_ctx.end_generation(
                    name="rag_synthesis",
                    output={"error": str(e)},
                )
            return f"I encountered an error generating a response: {str(e)}"
    
    async def _get_agent_config(
        self, 
        agent_id: uuid.UUID,
        config_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the configuration for an agent.
        
        Args:
            agent_id: The agent's UUID
            config_id: Optional specific config version ID. If provided, fetches that
                      specific config instead of the active one (for sandbox testing).
                      
        Returns:
            Configuration dict or None if not found/not ready.
        """
        config = None
        
        if config_id:
            # Fetch specific config version (for sandbox testing)
            config = await self.configs.get_by_id(config_id)
            
            # Validate: config must exist and belong to the specified agent
            if not config or str(config.agent_id) != str(agent_id):
                logger.warning(
                    "Config not found or doesn't belong to agent",
                    config_id=config_id,
                    agent_id=str(agent_id),
                )
                return None
            
            # Validate: config must have completed embeddings to be testable
            if config.embedding_status != "completed":
                logger.warning(
                    "Config embeddings not ready for testing",
                    config_id=config_id,
                    embedding_status=config.embedding_status,
                )
                return None
        else:
            # Fetch active config (default behavior)
            config = await self.configs.get_active_config(agent_id)
        
        if not config:
            return None
        
        return {
            "agent_id": str(config.agent_id),
            "config_id": config.id,  # Add config ID for vector collection name
            "data_source_id": config.data_source_id,
            "embedding_config": config.embedding_config or {},
            "rag_config": config.rag_config or {},
            "llm_config": config.llm_config or {},
            "chunking_config": config.chunking_config or {},
            "system_prompt": config.system_prompt,
            "llm_model_id": config.llm_model_id,
            "embedding_model_id": config.embedding_model_id,
            "vector_collection_name": config.vector_collection_name,  # Add vector collection name
        }
    
    async def _get_embedding_model(
        self, agent_config: Optional[Dict[str, Any]]
    ) -> Tuple[Any, Dict[str, Any]]:
        """Get the embedding model for the agent."""
        model_id = "huggingface/BAAI/bge-base-en-v1.5"
        dimensions = 768
        
        if agent_config:
            embedding_config = agent_config.get("embedding_config", {})
            if isinstance(embedding_config, str):
                embedding_config = json.loads(embedding_config)
            
            if agent_config.get("embedding_model_id"):
                ai_model = await self.ai_models.get_by_id(agent_config["embedding_model_id"])
                if ai_model:
                    model_id = ai_model.model_id
                    dimensions = 768  # Default embedding dimensions
            elif embedding_config.get("model"):
                model_id = embedding_config["model"]
                dimensions = embedding_config.get("dimensions", 768)
        
        from langchain_huggingface import HuggingFaceEmbeddings
        
        # Parse provider/model format
        if "/" in model_id:
            parts = model_id.split("/", 1)
            model_name = parts[1] if parts[0].lower() == "huggingface" else model_id
        else:
            model_name = model_id
        
        embedding_model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": get_best_device()},
            encode_kwargs={"normalize_embeddings": True},
        )
        
        return embedding_model, {"model": model_id, "dimensions": dimensions}
    
    async def _embed_query(self, query: str, embedding_model: Any) -> List[float]:
        """Embed a query string."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, embedding_model.embed_query, query)

    def _get_vector_db_name(self, agent_config: Optional[Dict[str, Any]]) -> str:
        """Get the vector database collection name for the agent."""
        if agent_config:
            # First, check for explicitly set vector_collection_name (set by embedding job)
            vector_collection = agent_config.get("vector_collection_name")
            if vector_collection:
                return vector_collection
            
            # Fallback: construct from agent_id and config_id (matches embedding service pattern)
            agent_id = agent_config.get("agent_id")
            config_id = agent_config.get("config_id")
            if agent_id and config_id:
                return f"agent_{agent_id}_config_{config_id}"
        
        return "default_collection"
    
    async def _search_vectors(
        self,
        query_embedding: List[float],
        collection_name: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict] = None,
    ) -> Tuple[List[SourceChunk], float]:
        """Search the vector database for similar documents."""
        start_time = time.time()
        
        import chromadb
        from chromadb.config import Settings
        
        chroma_path = self._settings.data_dir / "chromadb" / collection_name
        
        if not chroma_path.exists():
            logger.warning(f"Vector database not found: {collection_name}")
            return [], 0
        
        try:
            chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
            
            collection = chroma_client.get_collection(collection_name)
            
            query_params = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            
            if metadata_filter:
                query_params["where"] = metadata_filter
            
            results = collection.query(**query_params)
            
            search_time = (time.time() - start_time) * 1000
            
            sources = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else None
                    score = 1 - distance if distance is not None else None
                    
                    sources.append(SourceChunk(
                        content=doc,
                        metadata=metadata,
                        score=score,
                    ))
            
            return sources, search_time
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return [], 0
    