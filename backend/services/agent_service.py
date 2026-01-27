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
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.services.sql_service import get_sql_service
from backend.services.vector_store import get_vector_store
from backend.services.embeddings import get_embedding_model
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import (
    ChatResponse, ChartData, ReasoningStep, EmbeddingInfo
)

settings = get_settings()
logger = get_logger(__name__)



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
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            temperature=settings.openai_temperature,
            model_name=settings.openai_model,
            api_key=settings.openai_api_key
        )
        
        # Create tools
        self.tools = [
            Tool(
                name="sql_query_tool",
                func=self.sql_service.query,
                description="""**PRIMARY TOOL FOR STATISTICS - Pass NATURAL LANGUAGE questions only.**

This tool accepts natural language questions (NOT SQL queries) and automatically generates and executes SQL.

When to use:
- Counting: "How many patients...", "Total number of..."
- Averages: "Average glucose level...", "Mean BMI of..."
- Aggregations: "Sum of...", "Distribution of..."
- Filtering: By age groups, gender, date ranges, biomarkers

Input format: Natural language question ONLY
Example: "Count patients with systolic BP > 140 in 2024"
DO NOT generate SQL yourself - the tool handles that internally.

Available data: patient_tracker (demographics, vitals), patient_diagnosis, prescription, lab_test results."""
            ),
            Tool(
                name="rag_patient_context_tool",
                func=self._rag_search,
                description="""**PRIMARY TOOL FOR CLINICAL CONTEXT.**
Use this to search unstructured text, medical notes, and semantic descriptions.
- Capabilities: Semantic search for symptoms, lifestyle, risk factors, and specific diagnoses.
- Use for: "Find patients who complain of...", "Show me records regarding...", "Details about patient X..."."""
            ),
        ]
        
        # Create prompt template
        # Use a placeholder for system_prompt to allow dynamic injection per request
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
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
            return_intermediate_steps=True
        )
        
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
    
    async def process_query(
        self,
        query: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user query through the RAG pipeline.
        
        Args:
            query: User question
            user_id: Optional user identifier
        
        Returns:
            Dictionary containing answer, charts, suggestions, and metadata
        """
        trace_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        logger.info(f"Processing query (trace_id={trace_id}): '{query[:100]}...'")
        
        try:
            # =================================================================
            # FAST PATH: Check if query matches a KPI template BEFORE agent
            # This prevents the agent from rewriting/losing important filters
            # =================================================================
            kpi_match = self.sql_service._check_dashboard_kpi(query)
            if kpi_match:
                sql_query, description = kpi_match
                logger.info(f"⚡ FAST PATH: KPI template matched on original query: {description}")
                
                # Execute KPI template directly (bypasses agent rewriting)
                sql_result = self.sql_service._execute_kpi_template(sql_query, description, query)
                
                # Generate suggestions based on the query type
                suggested_questions = self._generate_kpi_suggestions(query, description)
                
                # Build response
                response = ChatResponse(
                    answer=sql_result,
                    chart_data=None,  # Could enhance later to auto-generate charts
                    suggested_questions=suggested_questions,
                    reasoning_steps=[ReasoningStep(
                        tool="sql_query_tool",
                        input=f"KPI Template: {description}",
                        output=sql_result[:200]
                    )],
                    embedding_info=EmbeddingInfo(
                        model=settings.embedding_model_name,
                        dimensions=self.embedding_model.dimension,
                        search_method="kpi_template",
                        vector_norm=None,
                        docs_retrieved=0
                    ),
                    trace_id=trace_id,
                    timestamp=start_time
                )
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"✅ KPI fast-path completed (trace_id={trace_id}, duration={duration:.2f}s)")
                
                return response.model_dump()
            
            # =================================================================
            # STANDARD PATH: Use agent for complex queries
            # =================================================================
            # Fetch prompt fresh on every request
            active_prompt = self.db_service.get_latest_active_prompt()
            
            if not active_prompt:
                error_msg = "System Not Configured: No active system prompt found. Please configure the system via the Dashboard."
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            system_prompt = active_prompt

            # Retrieve relevant few-shot examples
            few_shot_examples = self._get_relevant_examples(query)
            formatted_examples = ""
            if few_shot_examples:
                formatted_examples = "\n\nRELEVANT SQL EXAMPLES:\n" + "\n".join(few_shot_examples)
                logger.info(f"✨ Injected {len(few_shot_examples)} relevant SQL examples into prompt")

            # Execute agent (don't get embedding info until we know we need it)
            # Pass system_prompt variable to the agent, creating a combined prompt
            final_prompt = f"{system_prompt}\n{formatted_examples}"
            
            result = self.agent_executor.invoke({
                "input": query,
                "system_prompt": final_prompt
            })
            
            # Extract response
            full_response = result.get("output", "An error occurred.")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Check if RAG was used
            rag_used = any(
                action.tool == "rag_patient_context_tool"
                for action, _ in intermediate_steps
            )
            
            # Only get embedding info if RAG was actually used
            if rag_used:
                embedding_info = self._get_embedding_info(query)
            else:
                embedding_info = {}
            
            # Parse JSON output from response
            chart_data, suggested_questions = self._parse_agent_output(full_response)
            
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
                    docs_retrieved=len([s for a, s in intermediate_steps if a.tool == "rag_patient_context_tool"])
                ),
                trace_id=trace_id,
                timestamp=start_time
            )
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f" Query processed successfully (trace_id={trace_id}, duration={duration:.2f}s)")
            
            return response.model_dump()
            
        except Exception as e:
            logger.error(f"Query processing failed (trace_id={trace_id}): {e}", exc_info=True)
            raise
    
    def _generate_kpi_suggestions(self, query: str, description: str) -> List[str]:
        """Generate contextual follow-up suggestions for KPI queries."""
        query_lower = query.lower()
        
        # Suggestions based on KPI type
        if 'smok' in query_lower and 'risk' in query_lower:
            return [
                "What is the overall smoking rate among NCD patients?",
                "Show high-risk patient distribution by category",
                "How many patients have poor lifestyle scores?"
            ]
        elif 'smok' in query_lower:
            return [
                "How many high-risk patients are smokers?",
                "What is the lifestyle risk score distribution?",
                "Show symptom prevalence among NCD patients"
            ]
        elif 'risk' in query_lower or 'critical' in query_lower:
            return [
                "How many critical risk patients are smokers?",
                "What is the glycemic control status distribution?",
                "Show patients with abnormal lab results"
            ]
        elif 'enroll' in query_lower:
            return [
                "How many patients are enrolled by condition?",
                "What is the community enrollment rate?",
                "Show enrolled patients with co-morbid conditions"
            ]
        elif 'screen' in query_lower or 'referr' in query_lower:
            return [
                "What is the HTN prevalence rate?",
                "How many crisis referrals occurred?",
                "Show screening yield percentage"
            ]
        else:
            return [
                "How many patients are in each risk category?",
                "What is the smoking rate among NCD patients?",
                "Show enrollment breakdown by condition"
            ]

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
        
        # Try to extract JSON block
        json_match = re.search(r'```json\s*({.*?})\s*```', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                
                # Extract chart data
                if chart_json := data.get("chart_json"):
                    chart_data = ChartData(**chart_json)
                
                # Extract suggestions
                if questions := data.get("suggested_questions"):
                    suggestions = questions[:3]  # Limit to 3
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse agent JSON output: {e}")
        
        return chart_data, suggestions
    
    def _clean_answer(self, response: str) -> str:
        """Remove JSON block from answer text."""
        # Remove JSON code block
        cleaned = re.sub(r'```json\s*{.*?}\s*```', '', response, flags=re.DOTALL)
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
