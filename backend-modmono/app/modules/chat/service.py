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
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.logging import get_logger
from app.core.utils.exceptions import AppException, ErrorCode
from app.core.config import get_settings
from app.modules.chat.schemas import (
    ChatRequest, ChatResponse, ChartData, ReasoningStep, EmbeddingInfo, SourceChunk
)
from app.modules.agents.repository import AgentRepository, AgentConfigRepository
from app.modules.ai_models.repository import AIModelRepository

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

logger = get_logger(__name__)


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
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.agents = AgentRepository(db)
        self.configs = AgentConfigRepository(db)
        self.ai_models = AIModelRepository(db)
        self._settings = get_settings()
        self._intent_classifier = get_intent_classifier()
        self._memory = get_conversation_memory()
        self._followup_service = get_followup_service()
    
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
            metadata={"agent_id": str(request.agent_id) if request.agent_id else None},
        )
        
        try:
            with tracing_ctx:
                # Check for cancellation
                await check_cancelled(fastapi_request)
                
                # Step 1: Get agent configuration
                agent_config = None
                sql_service = None
                
                if request.agent_id:
                    agent_config = await self._get_agent_config(request.agent_id)
                    if not agent_config:
                        raise AppException(
                            error_code=ErrorCode.RESOURCE_NOT_FOUND,
                            message=f"Agent {request.agent_id} not found or has no active configuration",
                            status_code=404,
                        )
                    
                    # Get SQL service for the agent's data source
                    sql_service = await SQLServiceFactory.from_agent_config(
                        request.agent_id, self.db
                    )
                
                # Step 2: Rewrite query with conversation context
                await check_cancelled(fastapi_request)
                tracing_ctx.add_span("query_rewrite", input=query)
                
                rewritten_query = await rewrite_query_with_context(
                    query, session_id, use_llm=True
                )
                
                tracing_ctx.update_span("query_rewrite", output=rewritten_query)
                
                # Step 3: Classify intent
                await check_cancelled(fastapi_request)
                tracing_ctx.add_span("intent_classification", input=rewritten_query)
                
                schema_context = sql_service.cached_schema if sql_service else ""
                classification = self._intent_classifier.classify(
                    rewritten_query, 
                    schema_context=schema_context
                )
                
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
                sources: List[SourceChunk] = []
                reasoning_steps: List[ReasoningStep] = []
                embedding_info = None
                
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
                    answer, reasoning_steps, chart_data = await self._handle_sql_intent(
                        rewritten_query, sql_service, agent_config, tracing_ctx
                    )
                    
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
                        tracing_ctx, fastapi_request
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
                
                followup_task = asyncio.create_task(
                    generate_followups_background(
                        query, 
                        answer, 
                        conversation_history=conversation_history,
                        timeout=2.0
                    )
                )
                
                # Step 6: Save to conversation memory
                self._memory.add_exchange(session_id, query, answer)
                
                # Wait for follow-ups with timeout
                suggested_questions = []
                try:
                    suggested_questions = await asyncio.wait_for(followup_task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.debug("Follow-up generation timed out")
                except Exception as e:
                    logger.debug(f"Follow-up generation failed: {e}")
                
                # Build response
                duration = time.time() - start_time
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
                
                return ChatResponse(
                    answer=answer,
                    chart_data=chart_data,
                    suggested_questions=suggested_questions,
                    reasoning_steps=reasoning_steps,
                    sources=sources,
                    embedding_info=embedding_info,
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
    
    async def _handle_sql_intent(
        self,
        query: str,
        sql_service: Optional[SQLService],
        agent_config: Optional[Dict[str, Any]],
        tracing_ctx: TracingContext,
    ) -> Tuple[str, List[ReasoningStep], Optional[ChartData]]:
        """Handle Intent A: SQL-only queries. Returns answer, reasoning steps, and optional chart data."""
        reasoning_steps = []
        chart_data = None
        
        if not sql_service:
            return "No database connection configured for this agent.", reasoning_steps, None
        
        tracing_ctx.add_span("sql_query", input=query)
        
        try:
            # Execute natural language SQL query
            result = sql_service.query(query)
            
            reasoning_steps.append(ReasoningStep(
                tool="sql_query",
                input=query,
                output=result[:500] if len(result) > 500 else result,
            ))
            
            tracing_ctx.update_span("sql_query", output=result[:500])
            
            # Synthesize response with LLM (includes chart generation instructions)
            raw_answer = await self._synthesize_sql_response_with_chart(query, result, agent_config)
            
            # Parse chart data from LLM response
            chart_data, answer = parse_chart_data(raw_answer)
            
            if chart_data:
                logger.info(f"Chart generated: type={chart_data.type}, title={chart_data.title}")
                tracing_ctx.add_span("chart_generation", input="SQL results")
                tracing_ctx.update_span("chart_generation", output={"type": chart_data.type})
            
            return answer, reasoning_steps, chart_data
            
        except Exception as e:
            logger.error(f"SQL query failed: {e}")
            return f"Failed to execute database query: {str(e)}", reasoning_steps, None
    
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
        answer = await self._synthesize_rag_response(query, sources, agent_config)
        
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
                query, sql_service, agent_config, tracing_ctx
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
                filter_result = sql_service.run(classification.sql_filter)
                
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
                query, sql_service, agent_config, tracing_ctx
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
        answer = await self._synthesize_rag_response(query, sources, agent_config)
        
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
    
    async def _synthesize_sql_response_with_chart(
        self,
        query: str,
        sql_result: str,
        agent_config: Optional[Dict[str, Any]],
    ) -> str:
        """Synthesize a natural language response from SQL results with chart generation."""
        from openai import AsyncOpenAI
        
        base_prompt = get_data_analyst_prompt()
        if agent_config and agent_config.get("system_prompt"):
            base_prompt = agent_config["system_prompt"]
        
        # Append chart generation rules to the system prompt
        system_prompt = base_prompt + get_chart_generator_prompt()
        
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Query: {query}\n\nResults:\n{sql_result}\n\nProvide a clear, helpful summary of these results. If the data is suitable for visualization, include a chart JSON block."},
                ],
                temperature=0.0,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"SQL response synthesis failed: {e}")
            return sql_result  # Return raw results as fallback
    
    async def _synthesize_sql_response(
        self,
        query: str,
        sql_result: str,
        agent_config: Optional[Dict[str, Any]],
    ) -> str:
        """Synthesize a natural language response from SQL results (without chart)."""
        from openai import AsyncOpenAI
        
        system_prompt = get_data_analyst_prompt()
        if agent_config and agent_config.get("system_prompt"):
            system_prompt = agent_config["system_prompt"]
        
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        
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
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"SQL response synthesis failed: {e}")
            return sql_result  # Return raw results as fallback
    
    async def _synthesize_rag_response(
        self,
        query: str,
        sources: List[SourceChunk],
        agent_config: Optional[Dict[str, Any]],
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
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"RAG response synthesis failed: {e}")
            return f"I encountered an error generating a response: {str(e)}"
    
    async def _get_agent_config(self, agent_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get the active configuration for an agent."""
        config = await self.configs.get_active_config(agent_id)
        if not config:
            return None
        
        return {
            "agent_id": str(config.agent_id),
            "data_source_id": config.data_source_id,
            "embedding_config": config.embedding_config or {},
            "rag_config": config.rag_config or {},
            "llm_config": config.llm_config or {},
            "chunking_config": config.chunking_config or {},
            "system_prompt": config.system_prompt,
            "llm_model_id": config.llm_model_id,
            "embedding_model_id": config.embedding_model_id,
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
                    dimensions = ai_model.dimensions or 768
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
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        
        return embedding_model, {"model": model_id, "dimensions": dimensions}
    
    async def _embed_query(self, query: str, embedding_model: Any) -> List[float]:
        """Embed a query string."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, embedding_model.embed_query, query)
    
    def _get_vector_db_name(self, agent_config: Optional[Dict[str, Any]]) -> str:
        """Get the vector database name for the agent."""
        if agent_config:
            embedding_config = agent_config.get("embedding_config", {})
            if isinstance(embedding_config, str):
                embedding_config = json.loads(embedding_config)
            return embedding_config.get("vector_db_name", "default_collection")
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
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get chat service health status."""
        status = {
            "healthy": True,
            "llm_available": bool(self._settings.openai_api_key),
            "vector_db_available": (self._settings.data_dir / "chromadb").exists(),
            "active_sessions": self._memory.session_count,
            "message": "Service operational",
        }
        
        if not status["llm_available"]:
            status["healthy"] = False
            status["message"] = "LLM provider not configured"
        
        return status
