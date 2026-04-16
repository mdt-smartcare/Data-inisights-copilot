"""
Query Planner — Two-stage query generation (Stage 1).

Decomposes a natural language question into a structured QueryPlan
(entities, metrics, filters, grouping, joins) before SQL generation.

This intermediate representation:
- Grounds the LLM in specific schema elements
- Constrains SQL generation to valid tables and columns
- Makes the query logic explainable and auditable
- Enables pre-computation of join paths via SchemaGraph
"""
from typing import Optional, List

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.core.utils.logging import get_logger
from app.core.prompts import get_query_planner_prompt
from .models import (
    QueryPlan, Metric, Filter, OrderSpec, TimeRange,
    JoinSpec, SchemaLinkResult
)
from .schema_graph import SchemaGraph
from .fuzzy_matcher import FuzzyMatcher

logger = get_logger(__name__)


# Load system prompt from external template file
def _get_plan_system_template():
    return get_query_planner_prompt()


_PLAN_USER_TEMPLATE = """DATABASE SCHEMA:
{schema_context}

{data_dictionary_context}

USER QUESTION: {question}

Generate the query plan as a JSON object matching the QueryPlan schema."""


class QueryPlanner:
    """
    Decomposes natural language questions into structured QueryPlans.
    
    Stage 1 of the two-stage generation pipeline:
    Question → QueryPlan → SQL
    
    Usage:
        planner = QueryPlanner(llm=llm_fast)
        plan = planner.plan(
            question="How many patients were screened last quarter?",
            schema_link_result=linker_result
        )
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        schema_graph: Optional[SchemaGraph] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize QueryPlanner.
        
        Args:
            llm: LLM for plan extraction (recommend fast model like gpt-3.5-turbo)
            schema_graph: Optional SchemaGraph for join-path enrichment
            system_prompt: Optional custom system prompt (uses default if not provided)
        """
        self.llm = llm
        self.schema_graph = schema_graph
        
        # Create structured output chain
        self.structured_llm = llm.with_structured_output(QueryPlan)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt or _get_plan_system_template()),
            ("user", _PLAN_USER_TEMPLATE)
        ])
    
    def plan(
        self,
        question: str,
        schema_context: str,
        data_dictionary_context: str = "",
        schema_link_result: Optional[SchemaLinkResult] = None
    ) -> QueryPlan:
        """
        Generate a structured query plan from a natural language question.
        
        Args:
            question: User's natural language question
            schema_context: Formatted schema text (from SchemaGraph.to_prompt_format)
            data_dictionary_context: Optional data dictionary context
            schema_link_result: Optional SchemaLinkResult for filter injection
            
        Returns:
            QueryPlan with entities, metrics, filters, grouping, etc.
        """
        logger.info(f"Planning query: '{question[:80]}...'")
        
        try:
            chain = self.prompt | self.structured_llm
            
            plan = chain.invoke({
                "question": question,
                "schema_context": schema_context,
                "data_dictionary_context": data_dictionary_context or "No additional context."
            })
            
            # Enrich plan with SchemaGraph join paths
            if self.schema_graph and len(plan.entities) > 1:
                plan = self._enrich_join_strategy(plan)
            
            # Entity Resolution: Fuzzy match categorical filters
            cat_map = self._parse_categorical_values(schema_context)
            if cat_map:
                matcher = FuzzyMatcher(threshold=0.6)
                for f in plan.filters:
                    if f.column in cat_map and isinstance(f.value, str):
                        matched = matcher.match_categorical_value(f.value, cat_map[f.column])
                        if matched and matched != f.value:
                            logger.info(f"Fuzzy matched filter '{f.value}' -> '{matched}' for column '{f.column}'")
                            f.value = matched
            
            # Inject default filters from schema link result
            if schema_link_result and schema_link_result.default_filters:
                plan = self._inject_default_filters(plan, schema_link_result)
            
            logger.info(
                f"Query plan: {len(plan.entities)} tables, "
                f"{len(plan.metrics)} metrics, "
                f"{len(plan.filters)} filters, "
                f"{len(plan.join_strategy)} joins — "
                f"{plan.reasoning}"
            )
            
            return plan
            
        except Exception as e:
            logger.warning(f"Query planning failed: {e}. Generating minimal plan.")
            return self._fallback_plan(question, schema_link_result)
    
    def _parse_categorical_values(self, schema_context: str) -> dict:
        """Parse the schema context to extract valid categorical values for columns."""
        import re
        cat_map = {}
        for line in schema_context.split('\n'):
            line = line.strip()
            if line.startswith('- ') and ':' in line:
                parts = line[2:].split(':', 1)
                if len(parts) == 2:
                    col_name = parts[0].strip()
                    vals_part = parts[1].strip()
                    vals = re.findall(r"'([^']*)'", vals_part)
                    if vals:
                        cat_map[col_name] = vals
        return cat_map

    def _enrich_join_strategy(self, plan: QueryPlan) -> QueryPlan:
        """
        Populate join_strategy based on SchemaGraph FK relationships.
        
        Only adds joins if the plan doesn't already specify them.
        """
        if plan.join_strategy:
            return plan  # Plan already has explicit joins
        
        if not self.schema_graph or len(plan.entities) <= 1:
            return plan
        
        join_specs = []
        anchor = plan.entities[0]
        
        for target in plan.entities[1:]:
            path = self.schema_graph.get_join_path(anchor, target)
            if path:
                for step in path.steps:
                    join_specs.append(JoinSpec(
                        left_table=step.from_table,
                        left_column=step.from_column,
                        right_table=step.to_table,
                        right_column=step.to_column,
                        join_type=step.join_type
                    ))
                # Chain: next join starts from the previous target
                anchor = target
            else:
                logger.warning(
                    f"No FK path found between '{anchor}' and '{target}'. "
                    "LLM will need to determine join logic."
                )
        
        plan.join_strategy = join_specs
        return plan
    
    def _inject_default_filters(
        self,
        plan: QueryPlan,
        link_result: SchemaLinkResult
    ) -> QueryPlan:
        """Inject default filters that aren't already in the plan."""
        existing_columns = {(f.table, f.column) for f in plan.filters}
        
        for default_filter in link_result.default_filters:
            key = (default_filter.table, default_filter.column)
            if key not in existing_columns:
                plan.filters.append(default_filter)
        
        return plan
    
    def _fallback_plan(
        self,
        question: str,
        link_result: Optional[SchemaLinkResult] = None
    ) -> QueryPlan:
        """Generate a minimal plan when LLM planning fails."""
        entities = []
        if link_result:
            entities = link_result.tables
        
        return QueryPlan(
            entities=entities,
            reasoning=f"Fallback plan for: {question[:100]}"
        )
    
    def plan_to_prompt_context(self, plan: QueryPlan) -> str:
        """
        Format a QueryPlan as prompt context for Stage 2 SQL generation.
        
        This is injected into the SQL generation prompt to constrain
        the LLM to follow the planned structure.
        """
        parts = ["QUERY PLAN (follow this structure):"]
        
        if plan.reasoning:
            parts.append(f"  Approach: {plan.reasoning}")
        
        if plan.entities:
            parts.append(f"  Tables: {', '.join(plan.entities)}")
        
        if plan.select_columns:
            parts.append(f"  Select: {', '.join(plan.select_columns)}")
        
        if plan.metrics:
            metric_strs = []
            for m in plan.metrics:
                func = m.function.value
                if func == "COUNT_DISTINCT":
                    metric_strs.append(f"COUNT(DISTINCT {m.column})")
                else:
                    metric_strs.append(f"{func}({m.column})")
                if m.alias:
                    metric_strs[-1] += f" AS {m.alias}"
            parts.append(f"  Metrics: {', '.join(metric_strs)}")
        
        if plan.filters:
            filter_strs = []
            for f in plan.filters:
                prefix = "[DEFAULT] " if f.is_default else ""
                table_prefix = f"{f.table}." if f.table else ""
                filter_strs.append(
                    f"{prefix}{table_prefix}{f.column} {f.operator.value} {f.value}"
                )
            parts.append(f"  Filters: {'; '.join(filter_strs)}")
        
        if plan.grouping:
            parts.append(f"  Group By: {', '.join(plan.grouping)}")
        
        if plan.ordering:
            order_strs = [f"{o.column} {o.direction}" for o in plan.ordering]
            parts.append(f"  Order By: {', '.join(order_strs)}")
        
        if plan.limit:
            parts.append(f"  Limit: {plan.limit}")
        
        if plan.time_range:
            tr = plan.time_range
            if tr.relative:
                parts.append(f"  Time Range: {tr.relative} on {tr.column}")
            else:
                parts.append(f"  Time Range: {tr.start} to {tr.end} on {tr.column}")
        
        if plan.join_strategy:
            join_strs = []
            for j in plan.join_strategy:
                join_strs.append(
                    f"{j.join_type} {j.right_table} ON "
                    f"{j.left_table}.{j.left_column} = {j.right_table}.{j.right_column}"
                )
            parts.append(f"  Joins:\n    " + "\n    ".join(join_strs))
        
        return "\n".join(parts)
