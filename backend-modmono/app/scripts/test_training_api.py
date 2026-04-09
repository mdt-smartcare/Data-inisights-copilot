"""
Test script for Training Management API endpoints.

Run with:
    python -m app.scripts.test_training_api

This script tests the training endpoints without authentication (for local testing).
For production testing, use proper authentication tokens.
"""
import asyncio
import json
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.modules.sql_examples.routes import (
    TrainingExampleCreate,
    contains_pii,
    generate_example_id,
    ALLOWED_CATEGORIES,
    PII_PATTERNS
)
from app.modules.sql_examples.store import get_sql_examples_store


def test_pii_detection():
    """Test PII pattern detection."""
    print("\n=== Testing PII Detection ===")
    
    # Should detect PII
    pii_texts = [
        "SELECT * FROM patients WHERE name = 'John Smith'",
        "Find patient with SSN 123-45-6789",
        "Email is john.doe@example.com",
        "Patient ID: MRN-123456789",
        "Call 555-123-4567",
    ]
    
    # Should NOT detect PII
    safe_texts = [
        "SELECT COUNT(*) FROM patients",
        "Show first record per patient_id",
        "Calculate average blood pressure",
        "WITH cte AS (SELECT * FROM records) SELECT * FROM cte",
    ]
    
    print("\nTexts that SHOULD be flagged as PII:")
    for text in pii_texts:
        result = contains_pii(text)
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {text[:50]}...")
    
    print("\nTexts that should NOT be flagged as PII:")
    for text in safe_texts:
        result = contains_pii(text)
        status = "PASS" if not result else "FAIL"
        print(f"  [{status}] {text[:50]}...")


def test_validation():
    """Test Pydantic validation."""
    print("\n=== Testing Validation ===")
    
    # Valid example
    try:
        valid = TrainingExampleCreate(
            question="How many patients have high blood pressure?",
            sql="SELECT COUNT(*) FROM patients WHERE systolic > 140",
            category="blood_pressure",
            tags=["count", "filter"]
        )
        print(f"  [PASS] Valid example accepted: {valid.question[:40]}...")
    except Exception as e:
        print(f"  [FAIL] Valid example rejected: {e}")
    
    # Invalid - contains PII in question
    try:
        invalid = TrainingExampleCreate(
            question="Find John Smith's records",
            sql="SELECT * FROM patients",
            category="general"
        )
        print(f"  [FAIL] PII in question not caught")
    except ValueError as e:
        print(f"  [PASS] PII in question caught: {str(e)[:50]}...")
    
    # Invalid - dangerous SQL
    try:
        invalid = TrainingExampleCreate(
            question="Delete old records",
            sql="DELETE FROM patients WHERE created_at < '2020-01-01'",
            category="general"
        )
        print(f"  [FAIL] Dangerous SQL not caught")
    except ValueError as e:
        print(f"  [PASS] Dangerous SQL caught: {str(e)[:50]}...")
    
    # Invalid - bad category
    try:
        invalid = TrainingExampleCreate(
            question="Test query for something",
            sql="SELECT * FROM test_table",
            category="invalid_category"
        )
        print(f"  [FAIL] Invalid category not caught")
    except ValueError as e:
        print(f"  [PASS] Invalid category caught: {str(e)[:50]}...")
    
    # Invalid - SQL starts with INSERT
    try:
        invalid = TrainingExampleCreate(
            question="Add a new record",
            sql="INSERT INTO patients VALUES (1, 'test')",
            category="general"
        )
        print(f"  [FAIL] INSERT SQL not caught")
    except ValueError as e:
        print(f"  [PASS] INSERT SQL caught: {str(e)[:50]}...")


def test_id_generation():
    """Test deterministic ID generation."""
    print("\n=== Testing ID Generation ===")
    
    question = "Show patient blood pressure readings"
    sql = "SELECT * FROM bp_readings WHERE patient_id = ?"
    
    id1 = generate_example_id(question, sql)
    id2 = generate_example_id(question, sql)
    id3 = generate_example_id(question + " ", sql)  # With trailing space
    
    print(f"  ID 1: {id1[:20]}...")
    print(f"  ID 2: {id2[:20]}...")
    print(f"  ID 3 (with space): {id3[:20]}...")
    
    if id1 == id2:
        print("  [PASS] Same inputs produce same ID")
    else:
        print("  [FAIL] Same inputs produce different IDs")
    
    # Note: ID3 might differ due to the extra space - that's expected
    # The store normalizes with strip() so it should match


async def test_store_operations():
    """Test SQL Examples Store operations."""
    print("\n=== Testing Store Operations ===")
    
    try:
        store = get_sql_examples_store()
        print(f"  [PASS] Store initialized with backend: {store.backend_type}")
        
        # Health check
        health = await store.health_check()
        print(f"  [INFO] Store health: {health.get('healthy')}")
        print(f"  [INFO] Example count: {health.get('example_count', 0)}")
        
        # Add a test example
        success = await store.add_example(
            question="Test question for API validation",
            sql="SELECT 1 AS test_value",
            category="general",
            tags=["test", "validation"],
            description="Test example for API testing"
        )
        
        if success:
            print("  [PASS] Example added successfully")
        else:
            print("  [FAIL] Failed to add example")
        
        # Search for similar
        results = await store.get_similar_examples(
            question="Test query for validation",
            top_k=3,
            min_score=0.0
        )
        
        print(f"  [INFO] Similar examples found: {len(results)}")
        for r in results[:2]:
            print(f"         - {r['question'][:40]}... (score: {r['score']:.2f})")
        
        # Get count
        count = await store.get_example_count()
        print(f"  [INFO] Total examples in store: {count}")
        
    except Exception as e:
        print(f"  [ERROR] Store operation failed: {e}")


def test_categories():
    """Test allowed categories."""
    print("\n=== Allowed Categories ===")
    for cat in ALLOWED_CATEGORIES:
        print(f"  - {cat}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Training Management API - Test Suite")
    print("=" * 60)
    
    test_pii_detection()
    test_validation()
    test_id_generation()
    test_categories()
    
    # Run async tests
    print("\n" + "=" * 60)
    print("Async Store Tests (requires vector store)")
    print("=" * 60)
    
    try:
        asyncio.run(test_store_operations())
    except Exception as e:
        print(f"\n  [SKIP] Store tests skipped: {e}")
    
    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)
    
    print("\n### How to Test API Endpoints ###")
    print("""
1. Start the server:
   cd backend-modmono
   conda activate fhir_rag_env
   uvicorn app.app:app --reload --port 8000

2. Open API docs:
   http://localhost:8000/api/docs

3. Test with curl (requires auth token in production):

   # Get categories
   curl http://localhost:8000/api/v1/training/categories

   # Get stats
   curl http://localhost:8000/api/v1/training/stats

   # Add example (admin only)
   curl -X POST http://localhost:8000/api/v1/training/examples \\
     -H "Content-Type: application/json" \\
     -H "Authorization: Bearer <token>" \\
     -d '{
       "question": "How many patients have diabetes?",
       "sql": "SELECT COUNT(*) FROM patients WHERE has_diabetes = TRUE",
       "category": "diagnoses",
       "tags": ["count", "condition"]
     }'

   # Search examples
   curl "http://localhost:8000/api/v1/training/examples/search?question=blood+pressure&top_k=5"

   # Bulk upload (admin only)
   curl -X POST http://localhost:8000/api/v1/training/bulk \\
     -H "Authorization: Bearer <token>" \\
     -F "file=@training_examples.json"
""")


if __name__ == "__main__":
    main()
