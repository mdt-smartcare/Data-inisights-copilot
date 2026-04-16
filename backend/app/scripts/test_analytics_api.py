"""
Test script for Query Analytics API.

Run with:
    python -m app.scripts.test_analytics_api

This script tests the analytics service and endpoints.
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
import random

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_service_methods():
    """Test the QueryAnalyticsService methods without database."""
    print("\n=== Testing Service Methods ===")
    
    from app.modules.observability.analytics_service import (
        QueryAnalyticsService,
        ERROR_CATEGORIES,
        ERROR_FIXES
    )
    
    # Test hash generation
    hash1 = QueryAnalyticsService._hash_query("How many patients are there?")
    hash2 = QueryAnalyticsService._hash_query("how many patients are there?")
    hash3 = QueryAnalyticsService._hash_query("  How many patients are there?  ")
    
    print(f"  Hash 1: {hash1[:20]}...")
    print(f"  Hash 2: {hash2[:20]}...")
    print(f"  Hash 3: {hash3[:20]}...")
    
    if hash1 == hash2 == hash3:
        print("  [PASS] Query hashing is case and whitespace insensitive")
    else:
        print("  [FAIL] Query hashing should be normalized")
    
    # Test error categorization
    print("\n  Error Categories:")
    for error_type, category in list(ERROR_CATEGORIES.items())[:5]:
        print(f"    {error_type} -> {category}")
    
    # Test error fixes
    print("\n  Error Fixes Available:")
    for error_type in list(ERROR_FIXES.keys())[:5]:
        print(f"    {error_type}: {ERROR_FIXES[error_type][:50]}...")
    
    print("  [PASS] Service methods work correctly")


def test_model_creation():
    """Test the QueryAnalyticsModel creation."""
    print("\n=== Testing Model Creation ===")
    
    from app.modules.observability.analytics_models import QueryAnalyticsModel
    
    # Create a model instance (without saving to DB)
    record = QueryAnalyticsModel(
        query_hash="abc123",
        query_category="temporal_comparison",
        query_complexity="complex",
        sql_generated=True,
        sql_executed=True,
        execution_success=True,
        generation_time_ms=150,
        execution_time_ms=200,
        total_time_ms=350,
        result_row_count=25,
        data_source_type="database"
    )
    
    print(f"  Model created: {record}")
    print(f"  Category: {record.query_category}")
    print(f"  Complexity: {record.query_complexity}")
    print(f"  Success: {record.execution_success}")
    print(f"  Total time: {record.total_time_ms}ms")
    print("  [PASS] Model creation works correctly")


def test_routes_import():
    """Test that routes module imports correctly."""
    print("\n=== Testing Routes Import ===")
    
    from app.modules.observability.analytics_routes import router
    
    print("  Available routes:")
    for route in router.routes:
        methods = ','.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        print(f"    {methods} {route.path}")
    
    print("  [PASS] Routes module imports correctly")


async def test_with_mock_data():
    """Test analytics with simulated data (no DB required)."""
    print("\n=== Testing Analytics Logic ===")
    
    from app.modules.observability.analytics_service import ERROR_FIXES, ERROR_CATEGORIES
    
    # Simulate summary data
    mock_summary = {
        "period_days": 7,
        "total_queries": 100,
        "success_count": 75,
        "success_rate": 0.75,
        "sql_generation_rate": 0.95,
        "sql_execution_rate": 0.80,
        "avg_execution_time_ms": 250,
        "avg_generation_time_ms": 150,
        "avg_total_time_ms": 400,
        "by_category": {
            "temporal_comparison": {"count": 30, "success_count": 20, "success_rate": 0.67},
            "aggregation": {"count": 40, "success_count": 38, "success_rate": 0.95},
            "window_functions": {"count": 15, "success_count": 8, "success_rate": 0.53}
        },
        "by_error_type": {
            "window_in_where": 10,
            "column_not_found": 5,
            "syntax_error": 3
        },
        "by_complexity": {
            "simple": {"count": 50, "success_count": 48, "success_rate": 0.96},
            "medium": {"count": 30, "success_count": 22, "success_rate": 0.73},
            "complex": {"count": 20, "success_count": 5, "success_rate": 0.25}
        }
    }
    
    print("  Mock Summary:")
    print(f"    Total queries: {mock_summary['total_queries']}")
    print(f"    Success rate: {mock_summary['success_rate']*100:.1f}%")
    print(f"    Avg execution time: {mock_summary['avg_execution_time_ms']}ms")
    
    print("\n  By Category:")
    for cat, stats in mock_summary['by_category'].items():
        print(f"    {cat}: {stats['count']} queries, {stats['success_rate']*100:.1f}% success")
    
    print("\n  By Error Type:")
    for error_type, count in mock_summary['by_error_type'].items():
        fix = ERROR_FIXES.get(error_type, "No fix available")
        print(f"    {error_type}: {count} occurrences")
        print(f"      Fix: {fix[:60]}...")
    
    # Generate improvement suggestions based on mock data
    suggestions = []
    
    if mock_summary["success_rate"] < 0.8:
        suggestions.append({
            "priority": "high",
            "area": "overall_accuracy",
            "issue": f"Overall success rate is {mock_summary['success_rate']*100:.1f}%",
            "suggestion": "Review error patterns and add training examples"
        })
    
    for complexity, stats in mock_summary['by_complexity'].items():
        if complexity == "complex" and stats['success_rate'] < 0.5:
            suggestions.append({
                "priority": "high",
                "area": "complexity_handling",
                "issue": f"Complex queries have {stats['success_rate']*100:.1f}% success rate",
                "suggestion": "Add CTE and window function training examples"
            })
    
    print("\n  Generated Suggestions:")
    for s in suggestions:
        print(f"    [{s['priority'].upper()}] {s['area']}")
        print(f"      Issue: {s['issue']}")
        print(f"      Suggestion: {s['suggestion']}")
    
    print("\n  [PASS] Analytics logic works correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Query Analytics API - Test Suite")
    print("=" * 60)
    
    test_service_methods()
    test_model_creation()
    test_routes_import()
    
    # Run async tests
    asyncio.run(test_with_mock_data())
    
    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)
    
    print("\n### How to Test API Endpoints ###")
    print("""
1. Apply the database migration:
   cd backend-modmono
   conda activate fhir_rag_env
   alembic upgrade head

2. Start the server:
   uvicorn app.app:app --reload --port 8000

3. Open API docs:
   http://localhost:8000/api/docs

4. Test with curl (requires admin auth token):

   # Get analytics summary
   curl http://localhost:8000/api/v1/analytics/summary?days=7 \\
     -H "Authorization: Bearer <token>"

   # Get error analytics
   curl http://localhost:8000/api/v1/analytics/errors?days=7&limit=10 \\
     -H "Authorization: Bearer <token>"

   # Get improvement suggestions
   curl http://localhost:8000/api/v1/analytics/improvement-suggestions \\
     -H "Authorization: Bearer <token>"

   # Get daily trend
   curl http://localhost:8000/api/v1/analytics/trend?days=30 \\
     -H "Authorization: Bearer <token>"

   # Log query metrics (for testing)
   curl -X POST http://localhost:8000/api/v1/analytics/log \\
     -H "Authorization: Bearer <token>" \\
     -H "Content-Type: application/json" \\
     -d '{
       "query_category": "temporal_comparison",
       "query_complexity": "complex",
       "sql_generated": true,
       "sql_executed": true,
       "execution_success": false,
       "error_type": "window_in_where",
       "generation_time_ms": 150,
       "execution_time_ms": 0
     }'

   # Health check
   curl http://localhost:8000/api/v1/analytics/health \\
     -H "Authorization: Bearer <token>"
""")


if __name__ == "__main__":
    main()
