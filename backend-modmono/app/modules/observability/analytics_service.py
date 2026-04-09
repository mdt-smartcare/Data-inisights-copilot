"""
Query Analytics Service.

Provides privacy-safe logging and analysis of query execution metrics.
Used to identify patterns, track accuracy, and prioritize training improvements.

PRIVACY REQUIREMENTS:
- NEVER log actual query text
- NEVER log SQL queries
- NEVER log result data
- Only log: categories, success/fail, timing, row counts
- Use query hash only for deduplication, not identification
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict

from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.logging import get_logger
from app.modules.observability.analytics_models import QueryAnalyticsModel

logger = get_logger(__name__)


# Error type to category mapping
ERROR_CATEGORIES = {
    "window_in_where": "syntax",
    "aggregate_in_where": "syntax",
    "datediff_syntax": "syntax",
    "date_sub_function": "syntax",
    "column_not_found": "semantic",
    "table_not_found": "semantic",
    "undefined_alias": "semantic",
    "column_not_in_groupby": "syntax",
    "ambiguous_column": "semantic",
    "syntax_error": "syntax",
    "timeout": "performance",
    "connection_error": "infrastructure",
    "permission_denied": "security",
    "unknown": "unknown",
}

# Suggested fixes for common error types
ERROR_FIXES = {
    "window_in_where": "Add CTE pattern training examples for window functions",
    "aggregate_in_where": "Add HAVING clause and subquery training examples",
    "datediff_syntax": "Add DuckDB DATEDIFF(part, start, end) examples",
    "date_sub_function": "Add INTERVAL arithmetic training examples",
    "column_not_found": "Review schema mapping and column name normalization",
    "table_not_found": "Verify table discovery and schema context",
    "undefined_alias": "Add JOIN alias pattern examples",
    "column_not_in_groupby": "Add GROUP BY best practice examples",
    "ambiguous_column": "Add table-qualified column reference examples",
    "syntax_error": "Review SQL generation prompt for syntax rules",
    "timeout": "Add query optimization patterns and LIMIT clauses",
}


class QueryAnalyticsService:
    """
    Service for logging and analyzing query execution metrics.
    
    All methods are privacy-safe and do not store or log actual query content.
    
    Usage:
        service = QueryAnalyticsService(session)
        
        # Log a query execution
        await service.log_query(
            query_category="temporal_comparison",
            sql_generated=True,
            sql_executed=True,
            execution_success=True,
            execution_time_ms=150,
            result_row_count=25
        )
        
        # Get analytics summary
        summary = await service.get_summary(days=7)
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize analytics service.
        
        Args:
            session: Async database session
        """
        self.session = session
    
    @staticmethod
    def _hash_query(query_text: str) -> str:
        """
        Generate a hash of the query for deduplication.
        
        The hash is used only for identifying duplicate queries,
        not for storing or recovering the original query.
        
        Args:
            query_text: The query text (will be normalized)
            
        Returns:
            SHA256 hash of the normalized query
        """
        # Normalize: lowercase, strip whitespace, remove extra spaces
        normalized = " ".join(query_text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @staticmethod
    def _categorize_error(error_type: str) -> str:
        """
        Categorize an error type into a broader category.
        
        Args:
            error_type: Specific error type
            
        Returns:
            Error category (syntax, semantic, performance, etc.)
        """
        return ERROR_CATEGORIES.get(error_type, "unknown")
    
    async def log_query(
        self,
        query_category: Optional[str] = None,
        query_complexity: Optional[str] = None,
        sql_generated: bool = False,
        sql_executed: bool = False,
        execution_success: bool = False,
        error_type: Optional[str] = None,
        generation_time_ms: Optional[int] = None,
        execution_time_ms: Optional[int] = None,
        result_row_count: Optional[int] = None,
        result_column_count: Optional[int] = None,
        data_source_type: Optional[str] = None,
        query_hash: Optional[str] = None
    ) -> int:
        """
        Log query execution metrics.
        
        PRIVACY: This method does NOT accept or log actual query content.
        Only metadata about the query execution is stored.
        
        Args:
            query_category: Category of the query (e.g., "temporal_comparison")
            query_complexity: Complexity level (simple, medium, complex)
            sql_generated: Whether SQL was successfully generated
            sql_executed: Whether SQL was executed
            execution_success: Whether execution completed successfully
            error_type: Type of error if failed (not the error message)
            generation_time_ms: Time to generate SQL
            execution_time_ms: Time to execute SQL
            result_row_count: Number of rows returned
            result_column_count: Number of columns returned
            data_source_type: Type of data source (database, csv, etc.)
            query_hash: Optional pre-computed query hash
            
        Returns:
            ID of the created analytics record
        """
        try:
            # Calculate total time
            total_time_ms = None
            if generation_time_ms is not None or execution_time_ms is not None:
                total_time_ms = (generation_time_ms or 0) + (execution_time_ms or 0)
            
            # Determine error category
            error_category = None
            if error_type:
                error_category = self._categorize_error(error_type)
            
            # Create analytics record
            record = QueryAnalyticsModel(
                query_hash=query_hash,
                query_category=query_category,
                query_complexity=query_complexity,
                sql_generated=sql_generated,
                sql_executed=sql_executed,
                execution_success=execution_success,
                error_type=error_type,
                error_category=error_category,
                generation_time_ms=generation_time_ms,
                execution_time_ms=execution_time_ms,
                total_time_ms=total_time_ms,
                result_row_count=result_row_count,
                result_column_count=result_column_count,
                data_source_type=data_source_type,
                created_at=datetime.utcnow()
            )
            
            self.session.add(record)
            await self.session.flush()
            
            logger.debug(
                "Query analytics logged",
                record_id=record.id,
                category=query_category,
                success=execution_success
            )
            
            return record.id
            
        except Exception as e:
            logger.error(f"Failed to log query analytics: {e}")
            raise
    
    async def get_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get summary statistics for recent queries.
        
        Args:
            days: Number of days to include in summary
            
        Returns:
            Dictionary with summary statistics
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get overall counts
        total_query = select(func.count(QueryAnalyticsModel.id)).where(
            QueryAnalyticsModel.created_at >= cutoff
        )
        total_result = await self.session.execute(total_query)
        total_queries = total_result.scalar() or 0
        
        if total_queries == 0:
            return {
                "period_days": days,
                "total_queries": 0,
                "success_rate": 0.0,
                "sql_generation_rate": 0.0,
                "sql_execution_rate": 0.0,
                "avg_execution_time_ms": 0,
                "avg_generation_time_ms": 0,
                "by_category": {},
                "by_error_type": {},
                "by_complexity": {}
            }
        
        # Get success counts
        success_query = select(func.count(QueryAnalyticsModel.id)).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.execution_success == True
            )
        )
        success_result = await self.session.execute(success_query)
        success_count = success_result.scalar() or 0
        
        # Get SQL generated counts
        generated_query = select(func.count(QueryAnalyticsModel.id)).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.sql_generated == True
            )
        )
        generated_result = await self.session.execute(generated_query)
        generated_count = generated_result.scalar() or 0
        
        # Get SQL executed counts
        executed_query = select(func.count(QueryAnalyticsModel.id)).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.sql_executed == True
            )
        )
        executed_result = await self.session.execute(executed_query)
        executed_count = executed_result.scalar() or 0
        
        # Get average times
        avg_query = select(
            func.avg(QueryAnalyticsModel.execution_time_ms),
            func.avg(QueryAnalyticsModel.generation_time_ms),
            func.avg(QueryAnalyticsModel.total_time_ms)
        ).where(QueryAnalyticsModel.created_at >= cutoff)
        avg_result = await self.session.execute(avg_query)
        avg_row = avg_result.one()
        
        # Get by category
        category_query = select(
            QueryAnalyticsModel.query_category,
            func.count(QueryAnalyticsModel.id).label("count"),
            func.sum(case((QueryAnalyticsModel.execution_success == True, 1), else_=0)).label("success_count")
        ).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.query_category.isnot(None)
            )
        ).group_by(QueryAnalyticsModel.query_category)
        
        category_result = await self.session.execute(category_query)
        by_category = {}
        for row in category_result:
            cat_count = row.count or 0
            cat_success = row.success_count or 0
            by_category[row.query_category] = {
                "count": cat_count,
                "success_count": cat_success,
                "success_rate": round(cat_success / cat_count, 3) if cat_count > 0 else 0.0
            }
        
        # Get by error type
        error_query = select(
            QueryAnalyticsModel.error_type,
            func.count(QueryAnalyticsModel.id).label("count")
        ).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.error_type.isnot(None)
            )
        ).group_by(QueryAnalyticsModel.error_type).order_by(func.count(QueryAnalyticsModel.id).desc())
        
        error_result = await self.session.execute(error_query)
        by_error_type = {row.error_type: row.count for row in error_result}
        
        # Get by complexity
        complexity_query = select(
            QueryAnalyticsModel.query_complexity,
            func.count(QueryAnalyticsModel.id).label("count"),
            func.sum(case((QueryAnalyticsModel.execution_success == True, 1), else_=0)).label("success_count")
        ).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.query_complexity.isnot(None)
            )
        ).group_by(QueryAnalyticsModel.query_complexity)
        
        complexity_result = await self.session.execute(complexity_query)
        by_complexity = {}
        for row in complexity_result:
            cplx_count = row.count or 0
            cplx_success = row.success_count or 0
            by_complexity[row.query_complexity] = {
                "count": cplx_count,
                "success_count": cplx_success,
                "success_rate": round(cplx_success / cplx_count, 3) if cplx_count > 0 else 0.0
            }
        
        return {
            "period_days": days,
            "total_queries": total_queries,
            "success_count": success_count,
            "success_rate": round(success_count / total_queries, 3) if total_queries > 0 else 0.0,
            "sql_generation_rate": round(generated_count / total_queries, 3) if total_queries > 0 else 0.0,
            "sql_execution_rate": round(executed_count / total_queries, 3) if total_queries > 0 else 0.0,
            "avg_execution_time_ms": round(avg_row[0] or 0),
            "avg_generation_time_ms": round(avg_row[1] or 0),
            "avg_total_time_ms": round(avg_row[2] or 0),
            "by_category": by_category,
            "by_error_type": by_error_type,
            "by_complexity": by_complexity
        }
    
    async def get_error_analytics(
        self,
        days: int = 7,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get analytics about common error patterns.
        
        Args:
            days: Number of days to analyze
            limit: Maximum number of error types to return
            
        Returns:
            List of error analytics with suggested fixes
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get total error count for percentage calculation
        total_errors_query = select(func.count(QueryAnalyticsModel.id)).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.error_type.isnot(None)
            )
        )
        total_result = await self.session.execute(total_errors_query)
        total_errors = total_result.scalar() or 0
        
        if total_errors == 0:
            return []
        
        # Get error breakdown
        error_query = select(
            QueryAnalyticsModel.error_type,
            QueryAnalyticsModel.error_category,
            func.count(QueryAnalyticsModel.id).label("count")
        ).where(
            and_(
                QueryAnalyticsModel.created_at >= cutoff,
                QueryAnalyticsModel.error_type.isnot(None)
            )
        ).group_by(
            QueryAnalyticsModel.error_type,
            QueryAnalyticsModel.error_category
        ).order_by(func.count(QueryAnalyticsModel.id).desc()).limit(limit)
        
        result = await self.session.execute(error_query)
        
        errors = []
        for row in result:
            error_type = row.error_type
            errors.append({
                "error_type": error_type,
                "error_category": row.error_category or "unknown",
                "count": row.count,
                "percentage": round(row.count / total_errors, 3),
                "suggested_fix": ERROR_FIXES.get(error_type, "Review error patterns and add relevant training examples")
            })
        
        return errors
    
    async def get_improvement_suggestions(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Generate AI-driven improvement suggestions based on failure patterns.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            List of prioritized improvement suggestions
        """
        # Get summary and error analytics
        summary = await self.get_summary(days=days)
        errors = await self.get_error_analytics(days=days, limit=20)
        
        suggestions = []
        
        # Suggestion based on overall success rate
        if summary["success_rate"] < 0.8:
            suggestions.append({
                "priority": "high",
                "area": "overall_accuracy",
                "issue": f"Overall success rate is {summary['success_rate']*100:.1f}%",
                "suggestion": "Review the most common error types and add targeted training examples",
                "impact": "high"
            })
        
        # Suggestions based on error types
        for error in errors[:5]:
            if error["count"] >= 3:
                priority = "high" if error["percentage"] > 0.2 else "medium"
                suggestions.append({
                    "priority": priority,
                    "area": "error_pattern",
                    "error_type": error["error_type"],
                    "issue": f"{error['error_type']} errors: {error['count']} occurrences ({error['percentage']*100:.1f}%)",
                    "suggestion": error["suggested_fix"],
                    "impact": "high" if error["percentage"] > 0.2 else "medium"
                })
        
        # Suggestions based on category performance
        for category, stats in summary.get("by_category", {}).items():
            if stats["count"] >= 5 and stats["success_rate"] < 0.7:
                suggestions.append({
                    "priority": "medium",
                    "area": "category_performance",
                    "category": category,
                    "issue": f"Category '{category}' has {stats['success_rate']*100:.1f}% success rate",
                    "suggestion": f"Add more training examples for '{category}' query patterns",
                    "impact": "medium"
                })
        
        # Suggestions based on complexity
        for complexity, stats in summary.get("by_complexity", {}).items():
            if complexity == "complex" and stats.get("success_rate", 1.0) < 0.6:
                suggestions.append({
                    "priority": "high",
                    "area": "complexity_handling",
                    "issue": f"Complex queries have low success rate ({stats['success_rate']*100:.1f}%)",
                    "suggestion": "Add more CTE, window function, and multi-join training examples",
                    "impact": "high"
                })
        
        # Performance suggestion
        if summary.get("avg_execution_time_ms", 0) > 5000:
            suggestions.append({
                "priority": "medium",
                "area": "performance",
                "issue": f"Average execution time is {summary['avg_execution_time_ms']}ms",
                "suggestion": "Add query optimization patterns and ensure LIMIT clauses are used",
                "impact": "medium"
            })
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return suggestions
    
    async def get_daily_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily query trend data.
        
        Args:
            days: Number of days to include
            
        Returns:
            List of daily statistics
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Use date_trunc for PostgreSQL
        trend_query = select(
            func.date_trunc('day', QueryAnalyticsModel.created_at).label("date"),
            func.count(QueryAnalyticsModel.id).label("total"),
            func.sum(case((QueryAnalyticsModel.execution_success == True, 1), else_=0)).label("success"),
            func.avg(QueryAnalyticsModel.total_time_ms).label("avg_time")
        ).where(
            QueryAnalyticsModel.created_at >= cutoff
        ).group_by(
            func.date_trunc('day', QueryAnalyticsModel.created_at)
        ).order_by(
            func.date_trunc('day', QueryAnalyticsModel.created_at)
        )
        
        result = await self.session.execute(trend_query)
        
        trend = []
        for row in result:
            total = row.total or 0
            success = row.success or 0
            trend.append({
                "date": row.date.isoformat() if row.date else None,
                "total_queries": total,
                "successful_queries": success,
                "success_rate": round(success / total, 3) if total > 0 else 0.0,
                "avg_time_ms": round(row.avg_time or 0)
            })
        
        return trend


# Singleton-style function to get service with existing session
def get_query_analytics_service(session: AsyncSession) -> QueryAnalyticsService:
    """Get a QueryAnalyticsService instance."""
    return QueryAnalyticsService(session)
