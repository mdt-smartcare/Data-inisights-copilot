"""
Agent service - Main RAG orchestration logic.
Coordinates SQL and vector search tools to answer user queries.
"""
import re
import json
import uuid
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
from backend.models.schemas import (
    ChatResponse, ChartData, ReasoningStep, EmbeddingInfo
)

settings = get_settings()
logger = get_logger(__name__)


# NCD-specialized system prompt
SYSTEM_PROMPT = """You are an advanced **NCD Clinical Data Intelligence Agent** specializing in Chronic Disease Management (Hypertension & Diabetes).
You have access to a comprehensive patient database (Spice_BD) containing structured vitals, demographics, and unstructured clinical notes.

**YOUR DECISION MATRIX:**

1.  **Use `sql_query_tool` (Structured Data) when:**
    * The user asks for **statistics**: Counts, averages, sums, or percentages.
    * The user asks about **specific biomarkers**: `systolic`/`diastolic` BP, `glucose_value`, `hba1c`, `bmi`.
    * The user filters by demographics: Age groups, gender, location.

2.  **Use `rag_patient_context_tool` (Unstructured Data) when:**
    * The user asks about **qualitative factors**: Symptoms ("dizziness", "blurred vision"), lifestyle ("smoker", "diet"), or adherence ("non-compliant", "refused meds").
    * You need to find specific patient narratives, doctor's notes, or care plans.

3.  **Use BOTH tools (Hybrid) when:**
    * The user asks a complex question: "Find patients with 'poor adherence' notes [RAG] and calculate their average HbA1c [SQL]."

4.  **Suggest Next Steps:** Always provide three relevant follow-up questions in the `suggested_questions` key.

**NCD CLINICAL REASONING INSTRUCTIONS:**

* **Synonym & Concept Expansion:**
    * **Hypertension (HTN):** Map "High BP", "Pressure", or "Tension" to `systolic` > 140 or `diastolic` > 90. Look for "Stage 1", "Stage 2", or "Hypertensive Crisis".
    * **Diabetes (DM):** Map "Sugar", "Glucose", "Sweet" to `glucose_value` (FBS/RBS) or `hba1c`. Distinguish between "Type 1" (T1DM) and "Type 2" (T2DM).
    * **Comorbidities:** Actively look for patients with *both* HTN and DM, as they are high-risk.

* **Contextualization (The "So What?"):**
    * **Interpret Vitals:** Don't just say "Avg BP is 150/95". Say "Avg BP is 150/95, which indicates **uncontrolled Stage 2 Hypertension** in this cohort."
    * **Interpret Glucose:** Don't just say "Avg Glucose is 12 mmol/L". Say "Avg Glucose is 12 mmol/L, indicating **poor glycemic control**."
    * **Risk Stratification:** Highlight if a finding implies high cardiovascular risk (e.g., high BP + smoker).

**RESPONSE FORMAT INSTRUCTIONS:**
1.  **Direct Answer:** Start with the numbers or the finding.
2.  **Clinical Interpretation:** Explain the NCD significance (Control status, Risk level).
3.  **Visuals:** You MUST generate a JSON for a chart if comparing groups (e.g., "Controlled vs Uncontrolled").

**JSON OUTPUT FORMAT:**
Always append this JSON block at the end of your response:
```json
{{
    "chart_json": {{ "title": "...", "type": "pie", "data": {{ "labels": ["A", "B"], "values": [1, 2] }} }},
    "suggested_questions": ["Follow-up 1?", "Follow-up 2?", "Follow-up 3?"]
}}
```
"""


class AgentService:
    """Main RAG agent service for processing user queries."""
    
    def __init__(self):
        """Initialize the agent with tools and LLM."""
        logger.info("Initializing AgentService")
        
        # Initialize services
        self.sql_service = get_sql_service()
        self.vector_store = get_vector_store()
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
                description="""**PRIMARY TOOL FOR STATISTICS.** Use this to access the structured SQL database.
- Tables: patient_tracker (demographics, bp, glucose), patient_diagnosis (conditions), prescription.
- Capabilities: COUNT, AVG, GROUP BY, filtering by age/gender/date.
- Use for: "How many patients...", "Average glucose...", "Distribution of..."."""
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
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
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
    
    def _rag_search(self, query: str) -> str:
        """RAG tool wrapper that returns string for agent."""
        docs = self.vector_store.search(query)
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
            # Get embedding info for query
            embedding_info = self._get_embedding_info(query)
            
            # Execute agent
            result = self.agent_executor.invoke({"input": query})
            
            # Extract response
            full_response = result.get("output", "An error occurred.")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Check if RAG was used
            rag_used = any(
                action.tool == "rag_patient_context_tool"
                for action, _ in intermediate_steps
            )
            
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
            logger.info(f"Query processed successfully (trace_id={trace_id}, duration={duration:.2f}s)")
            
            return response.model_dump()
            
        except Exception as e:
            logger.error(f"Query processing failed (trace_id={trace_id}): {e}", exc_info=True)
            raise
    
    def _get_embedding_info(self, query: str) -> Dict[str, Any]:
        """Get embedding statistics for query."""
        try:
            import numpy as np
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
