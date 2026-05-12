"""
Query Complexity Estimator

Estimates query complexity before execution to:
- Warn users about potentially slow queries
- Suggest optimizations (LIMIT, indexes)
- Enable proactive timeout adjustments

Addresses:
- No query complexity estimation before execution
- Users get timeout errors without guidance

Usage:
    from app.modules.chat.query.complexity_estimator import QueryComplexityEstimator
    
    estimator = QueryComplexityEstimator(engine)
    analysis = estimator.analyze("SELECT * FROM large_table JOIN another_table")
    
    if analysis.is_complex:
        print(f"Warning: {analysis.warning_message}")
        print(f"Suggestions: {analysis.suggestions}")
"""
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class ComplexityLevel(Enum):
    """Query complexity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class TableStats:
    """Statistics for a database table."""
    table_name: str
    row_count: int
    column_count: int
    has_primary_key: bool
    indexed_columns: List[str] = field(default_factory=list)


@dataclass
class ComplexityAnalysis:
    """Result of query complexity analysis."""
    complexity_level: ComplexityLevel
    estimated_rows: int
    join_count: int
    subquery_count: int
    aggregation_count: int
    has_full_table_scan: bool
    has_cross_join: bool
    has_limit: bool
    timeout_recommendation: int  # seconds
    warning_message: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    
    @property
    def is_complex(self) -> bool:
        """Check if query is complex enough to warn."""
        return self.complexity_level in (ComplexityLevel.HIGH, ComplexityLevel.VERY_HIGH)


class QueryComplexityEstimator:
    """
    Estimates SQL query complexity before execution.
    
    Uses heuristics and optional EXPLAIN analysis to estimate:
    - Number of rows to be processed
    - Join complexity
    - Potential full table scans
    - Timeout recommendations
    """
    
    # Thresholds for complexity levels
    HIGH_ROW_THRESHOLD = 100000
    VERY_HIGH_ROW_THRESHOLD = 1000000
    
    # Base timeout multipliers
    TIMEOUT_BASE = 30
    TIMEOUT_PER_JOIN = 10
    TIMEOUT_PER_SUBQUERY = 15
    
    def __init__(
        self,
        engine: Optional[Engine] = None,
        table_stats_cache: Optional[Dict[str, TableStats]] = None
    ):
        """
        Initialize estimator.
        
        Args:
            engine: Database engine for EXPLAIN queries
            table_stats_cache: Pre-cached table statistics
        """
        self._engine = engine
        self._table_stats: Dict[str, TableStats] = table_stats_cache or {}
    
    def analyze(
        self,
        sql: str,
        use_explain: bool = False
    ) -> ComplexityAnalysis:
        """
        Analyze SQL query complexity.
        
        Args:
            sql: SQL query to analyze
            use_explain: Whether to run EXPLAIN (requires engine)
            
        Returns:
            ComplexityAnalysis with estimates and suggestions
        """
        sql_upper = sql.upper()
        
        # Count various SQL elements
        join_count = self._count_joins(sql_upper)
        subquery_count = self._count_subqueries(sql_upper)
        aggregation_count = self._count_aggregations(sql_upper)
        has_limit = self._has_limit(sql_upper)
        has_cross_join = "CROSS JOIN" in sql_upper
        
        # Extract table names
        tables = self._extract_tables(sql)
        
        # Estimate row count
        estimated_rows = self._estimate_row_count(tables, join_count)
        
        # Check for full table scans
        has_full_table_scan = self._might_full_scan(sql_upper, tables)
        
        # Determine complexity level
        complexity = self._calculate_complexity(
            estimated_rows=estimated_rows,
            join_count=join_count,
            subquery_count=subquery_count,
            has_cross_join=has_cross_join,
            has_full_table_scan=has_full_table_scan,
            has_limit=has_limit
        )
        
        # Calculate timeout recommendation
        timeout = self._recommend_timeout(
            complexity=complexity,
            join_count=join_count,
            subquery_count=subquery_count,
            estimated_rows=estimated_rows
        )
        
        # Build warnings and suggestions
        warning, suggestions = self._build_recommendations(
            complexity=complexity,
            join_count=join_count,
            has_full_table_scan=has_full_table_scan,
            has_cross_join=has_cross_join,
            has_limit=has_limit,
            estimated_rows=estimated_rows
        )
        
        # Try EXPLAIN if requested and engine available
        if use_explain and self._engine:
            explain_info = self._run_explain(sql)
            if explain_info:
                # Update estimates based on EXPLAIN
                if explain_info.get("estimated_rows"):
                    estimated_rows = explain_info["estimated_rows"]
        
        return ComplexityAnalysis(
            complexity_level=complexity,
            estimated_rows=estimated_rows,
            join_count=join_count,
            subquery_count=subquery_count,
            aggregation_count=aggregation_count,
            has_full_table_scan=has_full_table_scan,
            has_cross_join=has_cross_join,
            has_limit=has_limit,
            timeout_recommendation=timeout,
            warning_message=warning,
            suggestions=suggestions
        )
    
    def _count_joins(self, sql_upper: str) -> int:
        """Count JOIN operations."""
        patterns = [
            r'\bJOIN\b',
            r'\bLEFT\s+JOIN\b',
            r'\bRIGHT\s+JOIN\b',
            r'\bINNER\s+JOIN\b',
            r'\bOUTER\s+JOIN\b',
            r'\bCROSS\s+JOIN\b',
        ]
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, sql_upper))
        return count
    
    def _count_subqueries(self, sql_upper: str) -> int:
        """Count subqueries (nested SELECTs)."""
        # Count SELECT statements minus 1 (the main query)
        selects = len(re.findall(r'\bSELECT\b', sql_upper))
        return max(0, selects - 1)
    
    def _count_aggregations(self, sql_upper: str) -> int:
        """Count aggregation functions."""
        functions = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP BY']
        count = 0
        for func in functions:
            if func in sql_upper:
                count += 1
        return count
    
    def _has_limit(self, sql_upper: str) -> bool:
        """Check if query has LIMIT clause."""
        return 'LIMIT' in sql_upper
    
    def _extract_tables(self, sql: str) -> List[str]:
        """Extract table names from SQL."""
        tables = set()
        patterns = [
            r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            tables.update(matches)
        return list(tables)
    
    def _estimate_row_count(
        self,
        tables: List[str],
        join_count: int
    ) -> int:
        """Estimate total rows to be processed."""
        if not tables:
            return 0
        
        # Get cached stats or use defaults
        table_rows = []
        for table in tables:
            if table in self._table_stats:
                table_rows.append(self._table_stats[table].row_count)
            else:
                # Default assumption: 10000 rows per table
                table_rows.append(10000)
        
        if not table_rows:
            return 0
        
        # For joins, estimate as product (worst case) capped at 10M
        if join_count > 0:
            estimated = 1
            for rows in table_rows:
                estimated *= rows
            # Cap at 10 million
            return min(estimated, 10000000)
        else:
            return max(table_rows)
    
    def _might_full_scan(self, sql_upper: str, tables: List[str]) -> bool:
        """Check if query might do full table scan."""
        # No WHERE clause on a table = likely full scan
        if 'WHERE' not in sql_upper:
            return True
        
        # SELECT * without LIMIT = likely problematic
        if 'SELECT *' in sql_upper.replace(' ', '') and 'LIMIT' not in sql_upper:
            return True
        
        return False
    
    def _calculate_complexity(
        self,
        estimated_rows: int,
        join_count: int,
        subquery_count: int,
        has_cross_join: bool,
        has_full_table_scan: bool,
        has_limit: bool
    ) -> ComplexityLevel:
        """Calculate overall complexity level."""
        score = 0
        
        # Row count scoring
        if estimated_rows > self.VERY_HIGH_ROW_THRESHOLD:
            score += 4
        elif estimated_rows > self.HIGH_ROW_THRESHOLD:
            score += 2
        elif estimated_rows > 10000:
            score += 1
        
        # Join scoring
        score += join_count
        
        # Subquery scoring
        score += subquery_count * 2
        
        # Cross join is very expensive
        if has_cross_join:
            score += 5
        
        # Full table scan penalty
        if has_full_table_scan:
            score += 2
        
        # LIMIT reduces score
        if has_limit:
            score = max(0, score - 2)
        
        # Map score to level
        if score >= 8:
            return ComplexityLevel.VERY_HIGH
        elif score >= 5:
            return ComplexityLevel.HIGH
        elif score >= 2:
            return ComplexityLevel.MEDIUM
        else:
            return ComplexityLevel.LOW
    
    def _recommend_timeout(
        self,
        complexity: ComplexityLevel,
        join_count: int,
        subquery_count: int,
        estimated_rows: int
    ) -> int:
        """Recommend a timeout based on complexity."""
        base = self.TIMEOUT_BASE
        
        # Add time for joins
        base += join_count * self.TIMEOUT_PER_JOIN
        
        # Add time for subqueries
        base += subquery_count * self.TIMEOUT_PER_SUBQUERY
        
        # Adjust for row count
        if estimated_rows > self.VERY_HIGH_ROW_THRESHOLD:
            base *= 3
        elif estimated_rows > self.HIGH_ROW_THRESHOLD:
            base *= 2
        
        # Cap at 5 minutes
        return min(base, 300)
    
    def _build_recommendations(
        self,
        complexity: ComplexityLevel,
        join_count: int,
        has_full_table_scan: bool,
        has_cross_join: bool,
        has_limit: bool,
        estimated_rows: int
    ) -> Tuple[Optional[str], List[str]]:
        """Build warning message and suggestions."""
        suggestions = []
        warning = None
        
        if complexity == ComplexityLevel.VERY_HIGH:
            warning = (
                f"This query is very complex and may take a long time. "
                f"Estimated rows: {estimated_rows:,}. "
                f"Consider simplifying."
            )
        elif complexity == ComplexityLevel.HIGH:
            warning = (
                f"This query is complex. "
                f"Estimated rows: {estimated_rows:,}."
            )
        
        if not has_limit and estimated_rows > 1000:
            suggestions.append("Add LIMIT clause to reduce result size")
        
        if has_cross_join:
            suggestions.append("CROSS JOIN detected - consider using explicit JOIN conditions")
        
        if has_full_table_scan and estimated_rows > 10000:
            suggestions.append("Add WHERE clause filters to avoid full table scan")
        
        if join_count > 3:
            suggestions.append("Consider breaking query into smaller parts with CTEs")
        
        return warning, suggestions
    
    def _run_explain(self, sql: str) -> Optional[Dict[str, Any]]:
        """Run EXPLAIN to get actual query plan."""
        if not self._engine:
            return None
        
        try:
            with self._engine.connect() as conn:
                # Use EXPLAIN ANALYZE for PostgreSQL
                result = conn.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))
                plan = result.fetchone()
                if plan:
                    # Parse PostgreSQL EXPLAIN JSON
                    import json
                    plan_data = json.loads(plan[0])
                    if plan_data and len(plan_data) > 0:
                        total_cost = plan_data[0].get("Plan", {}).get("Total Cost", 0)
                        return {"estimated_rows": int(total_cost)}
        except Exception as e:
            logger.debug(f"EXPLAIN failed (expected for some query types): {e}")
        
        return None
    
    def update_table_stats(
        self,
        table_name: str,
        row_count: int,
        column_count: int = 0,
        indexed_columns: Optional[List[str]] = None
    ) -> None:
        """Update cached table statistics."""
        self._table_stats[table_name] = TableStats(
            table_name=table_name,
            row_count=row_count,
            column_count=column_count,
            has_primary_key=True,
            indexed_columns=indexed_columns or []
        )
    
    def load_stats_from_db(self) -> None:
        """Load table statistics from the database."""
        if not self._engine:
            return
        
        try:
            inspector = inspect(self._engine)
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                pk = inspector.get_pk_constraint(table_name)
                indexes = inspector.get_indexes(table_name)
                
                indexed_cols = set()
                for idx in indexes:
                    indexed_cols.update(idx.get("column_names", []))
                
                # Try to get row count (approximate)
                row_count = 10000  # default
                try:
                    with self._engine.connect() as conn:
                        result = conn.execute(
                            text(f"SELECT COUNT(*) FROM {table_name}")
                        )
                        row_count = result.scalar() or 10000
                except Exception:
                    pass
                
                self._table_stats[table_name] = TableStats(
                    table_name=table_name,
                    row_count=row_count,
                    column_count=len(columns),
                    has_primary_key=bool(pk and pk.get("constrained_columns")),
                    indexed_columns=list(indexed_cols)
                )
            
            logger.info(f"Loaded stats for {len(self._table_stats)} tables")
            
        except Exception as e:
            logger.error(f"Failed to load table stats: {e}")


def get_complexity_estimator(
    engine: Optional[Engine] = None
) -> QueryComplexityEstimator:
    """Factory function for QueryComplexityEstimator."""
    return QueryComplexityEstimator(engine=engine)
