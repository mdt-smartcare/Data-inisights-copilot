"""
Schema Linker — Question-to-schema entity linking.

Replaces the naive keyword-matching with structured entity linking that combines:
1. Direct table/column name matching
2. Synonym resolution via DataDictionary
3. FK-based related table expansion via SchemaGraph
4. LLM fallback for ambiguous cases

Produces a SchemaLinkResult containing matched tables, columns,
pre-computed join paths, and default filters.
"""
import re
from typing import Optional, List, Dict, Set, Tuple

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from .models import SchemaLinkResult, Filter, ComparisonOperator, JoinPath
from .schema_graph import SchemaGraph
from .data_dictionary import DataDictionary

logger = get_logger(__name__)


class SchemaLinker:
    """
    Links natural language questions to relevant schema elements.
    
    Uses a multi-strategy approach:
    1. **Direct Matching**: Table/column names appearing in the question
    2. **Synonym Resolution**: Business terms mapped via DataDictionary
    3. **FK Expansion**: Related tables discovered via SchemaGraph
    4. **LLM Fallback**: For ambiguous or complex questions
    
    Usage:
        linker = SchemaLinker(schema_graph, data_dictionary)
        result = linker.link("How many active patients were screened last month?")
        # → SchemaLinkResult with tables, columns, join paths, default filters
    """
    
    def __init__(
        self,
        schema_graph: SchemaGraph,
        data_dictionary: Optional[DataDictionary] = None,
        llm: Optional[BaseChatModel] = None
    ):
        """
        Initialize SchemaLinker.
        
        Args:
            schema_graph: Schema graph for table/column lookup and FK traversal
            data_dictionary: Data dictionary for synonym resolution
            llm: Optional LLM for ambiguous cases
        """
        self.schema_graph = schema_graph
        self.data_dictionary = data_dictionary or DataDictionary()
        self.llm = llm
        
        # Build search index from schema
        self._table_name_index: Dict[str, str] = {}  # lowercase → original
        self._column_name_index: Dict[str, List[str]] = {}  # lowercase col → [tables]
        self._build_search_index()
    
    def _build_search_index(self):
        """Build searchable indexes from the schema graph."""
        for table_name, table_info in self.schema_graph.tables.items():
            # Index table names and their word parts
            self._table_name_index[table_name.lower()] = table_name
            
            # Also index by splitting underscores (e.g., "patient_tracker" → "patient", "tracker")
            for part in table_name.lower().split("_"):
                if len(part) > 2:  # Skip very short words
                    if part not in self._table_name_index:
                        self._table_name_index[part] = table_name
            
            # Index columns
            for col in table_info.columns:
                col_lower = col.name.lower()
                if col_lower not in self._column_name_index:
                    self._column_name_index[col_lower] = []
                self._column_name_index[col_lower].append(table_name)
        
        logger.info(
            f"SchemaLinker index built: {len(self._table_name_index)} table terms, "
            f"{len(self._column_name_index)} column terms"
        )
    
    def link(self, question: str, max_tables: int = 6) -> SchemaLinkResult:
        """
        Link a natural language question to schema elements.
        
        Args:
            question: User's natural language question
            max_tables: Maximum number of tables to include (prevents prompt bloat)
            
        Returns:
            SchemaLinkResult with matched tables, columns, join paths, and filters
        """
        question_lower = question.lower()
        
        matched_tables: Set[str] = set()
        matched_columns: Dict[str, List[str]] = {}
        resolved_synonyms: Dict[str, str] = {}
        
        # Strategy 1: Direct table name matching
        direct_tables = self._match_tables_direct(question_lower)
        matched_tables.update(direct_tables)
        
        # Strategy 2: Synonym resolution via DataDictionary
        synonym_tables, syn_resolved = self._match_tables_synonym(question_lower)
        matched_tables.update(synonym_tables)
        resolved_synonyms.update(syn_resolved)
        
        # Strategy 3: Column name matching (find tables that have mentioned columns)
        col_tables, col_matches = self._match_columns(question_lower)
        matched_tables.update(col_tables)
        matched_columns.update(col_matches)
        
        # Strategy 4: FK expansion — add directly related tables
        if matched_tables:
            expanded = self._expand_via_fk(matched_tables, depth=1)
            # Only add FK-expanded tables if we don't exceed max_tables
            for t in expanded:
                if len(matched_tables) < max_tables:
                    matched_tables.add(t)
        
        # Fallback: If no tables matched, use all tables (full schema)
        if not matched_tables:
            logger.info("No specific tables matched. Using full schema.")
            matched_tables = set(self.schema_graph.table_names[:max_tables])
        
        # Limit tables
        tables_list = list(matched_tables)[:max_tables]
        
        # Compute join paths between matched tables
        join_paths = self.schema_graph.get_join_paths_for_tables(tables_list)
        
        # Get default filters from data dictionary
        default_filters = []
        for table in tables_list:
            for filter_str in self.data_dictionary.get_default_filters(table):
                # Parse simple filter strings like "is_active = true"
                parsed = self._parse_filter_string(filter_str, table)
                if parsed:
                    default_filters.append(parsed)
        
        # Calculate confidence based on matching strategy
        confidence = self._calculate_confidence(
            direct_count=len(direct_tables),
            synonym_count=len(synonym_tables),
            column_count=len(col_tables),
            total_count=len(tables_list)
        )
        
        result = SchemaLinkResult(
            tables=tables_list,
            columns=matched_columns,
            join_paths=join_paths,
            default_filters=default_filters,
            resolved_synonyms=resolved_synonyms,
            confidence=confidence
        )
        
        logger.info(
            f"SchemaLinker result: {len(tables_list)} tables "
            f"(direct={len(direct_tables)}, synonym={len(synonym_tables)}, "
            f"column={len(col_tables)}), "
            f"{len(join_paths)} join paths, "
            f"{len(default_filters)} default filters, "
            f"confidence={confidence:.2f}"
        )
        
        return result
    
    # =========================================================================
    # Matching Strategies
    # =========================================================================
    
    def _match_tables_direct(self, question_lower: str) -> Set[str]:
        """Match tables by direct name occurrence in question text."""
        matched = set()
        
        for table_name in self.schema_graph.table_names:
            tl = table_name.lower()
            
            # Exact table name match
            if tl in question_lower:
                matched.add(table_name)
                continue
            
            # Match by table name parts (e.g., "patient" matches "patient_tracker")
            parts = tl.split("_")
            # Require at least 2 significant parts matching, or 1 unique part
            significant_parts = [p for p in parts if len(p) > 3]
            if significant_parts:
                matching_parts = [p for p in significant_parts if p in question_lower]
                # If > half of significant parts match, include the table
                if len(matching_parts) >= max(1, len(significant_parts) * 0.5):
                    matched.add(table_name)
        
        # Handle the demo "patient" vs "patient_tracker" conflict
        if "patient_tracker" in matched and "patient" in matched:
            if "patient_tracker" in self.schema_graph.table_names:
                matched.discard("patient")
        
        return matched
    
    def _match_tables_synonym(self, question_lower: str) -> Tuple[Set[str], Dict[str, str]]:
        """Match tables via DataDictionary synonym resolution."""
        matched = set()
        resolved = {}
        
        # Check each word and multi-word phrase against synonyms
        words = question_lower.split()
        
        # Check single words
        for word in words:
            canonical = self.data_dictionary.resolve_synonym(word)
            if canonical:
                resolved[word] = canonical
                # Map canonical back to table name
                if self.schema_graph.has_table(canonical):
                    matched.add(canonical)
                else:
                    # The canonical might be a column reference like "table.column"
                    tables = self.data_dictionary.find_tables_for_term(word)
                    matched.update(tables)
        
        # Check 2-word and 3-word phrases
        for n in [2, 3]:
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                canonical = self.data_dictionary.resolve_synonym(phrase)
                if canonical:
                    resolved[phrase] = canonical
                    if self.schema_graph.has_table(canonical):
                        matched.add(canonical)
                    else:
                        tables = self.data_dictionary.find_tables_for_term(phrase)
                        matched.update(tables)
        
        # Check business definitions
        definition = self.data_dictionary.resolve_term(question_lower)
        if definition and "table" in definition:
            table = definition["table"]
            if isinstance(table, list):
                matched.update(table)
            else:
                matched.add(table)
        
        return matched, resolved
    
    def _match_columns(self, question_lower: str) -> Tuple[Set[str], Dict[str, List[str]]]:
        """Match columns mentioned in the question and return their tables."""
        matched_tables = set()
        matched_columns: Dict[str, List[str]] = {}
        
        for col_name, tables in self._column_name_index.items():
            # Only match column names that are sufficiently specific (>3 chars)
            # and appear as whole words in the question
            if len(col_name) > 3 and re.search(rf'\b{re.escape(col_name)}\b', question_lower):
                for table in tables:
                    matched_tables.add(table)
                    if table not in matched_columns:
                        matched_columns[table] = []
                    matched_columns[table].append(col_name)
        
        return matched_tables, matched_columns
    
    def _expand_via_fk(self, tables: Set[str], depth: int = 1) -> Set[str]:
        """Expand table set by including FK-related tables."""
        expanded = set()
        for table in tables:
            related = self.schema_graph.get_related_tables(table, depth=depth)
            expanded.update(related)
        
        # Don't re-add tables already matched
        return expanded - tables
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _parse_filter_string(self, filter_str: str, table: str) -> Optional[Filter]:
        """Parse a simple filter string like 'is_active = true' into a Filter."""
        try:
            # Simple pattern: column operator value
            match = re.match(
                r'(\w+)\s*(=|!=|>|>=|<|<=|LIKE|ILIKE|IN|IS NULL|IS NOT NULL)\s*(.*)', 
                filter_str, 
                re.IGNORECASE
            )
            if match:
                column = match.group(1)
                op_str = match.group(2).upper()
                value = match.group(3).strip().strip("'\"")
                
                # Map string operator to enum
                op_map = {
                    "=": ComparisonOperator.EQ,
                    "!=": ComparisonOperator.NE,
                    ">": ComparisonOperator.GT,
                    ">=": ComparisonOperator.GTE,
                    "<": ComparisonOperator.LT,
                    "<=": ComparisonOperator.LTE,
                    "LIKE": ComparisonOperator.LIKE,
                    "ILIKE": ComparisonOperator.ILIKE,
                    "IN": ComparisonOperator.IN,
                    "IS NULL": ComparisonOperator.IS_NULL,
                    "IS NOT NULL": ComparisonOperator.IS_NOT_NULL,
                }
                
                operator = op_map.get(op_str, ComparisonOperator.EQ)
                
                # Convert string booleans
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                
                return Filter(
                    column=column,
                    operator=operator,
                    value=value,
                    table=table,
                    is_default=True
                )
        except Exception:
            pass
        
        return None
    
    def _calculate_confidence(
        self,
        direct_count: int,
        synonym_count: int,
        column_count: int,
        total_count: int
    ) -> float:
        """Calculate confidence score for the linking result."""
        if total_count == 0:
            return 0.3  # Fallback to full schema
        
        # Direct matches are highest confidence
        if direct_count > 0:
            return min(1.0, 0.7 + (direct_count * 0.1))
        
        # Synonym matches are good
        if synonym_count > 0:
            return min(0.9, 0.6 + (synonym_count * 0.1))
        
        # Column-only matches are moderate confidence
        if column_count > 0:
            return 0.5
        
        return 0.3
