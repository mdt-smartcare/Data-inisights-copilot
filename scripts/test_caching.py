import sys
import os
import time
import asyncio
from dotenv import load_dotenv

# Set python path to backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../.env')))

from backend.services.sql_service import get_sql_service, invalidate_sql_cache

def run_test():
    """Manual caching test for Redis query cache override"""
    print("=" * 60)
    print("TESTING REDIS SQL CACHING")
    print("=" * 60)
    
    # Needs to be inside event loop context if any async imports exist under the hood
    sql_service = get_sql_service()
    
    # 1) Clear Cache
    print("\n[1] Invalidating existing cache...")
    invalidate_sql_cache()
    
    test_question = "How many patients are tracked?"
    
    # 2) First query - MISS
    print(f"\n[2] Executing first query (Expect Cache MISS): '{test_question}'")
    start = time.time()
    res1 = sql_service.query(test_question)
    duration1 = time.time() - start
    print(f"Time taken: {duration1*1000:.2f}ms")
    print(f"Result length: {len(res1)}")
    
    # 3) Second query - HIT
    print(f"\n[3] Executing second query identically (Expect Cache HIT): '{test_question}'")
    start = time.time()
    res2 = sql_service.query(test_question)
    duration2 = time.time() - start
    print(f"Time taken: {duration2*1000:.2f}ms")
    print(f"Result length: {len(res2)}")
    
    # 4) Result Evaluation
    speedup = duration1 / duration2 if duration2 > 0 else float('inf')
    print("\n[4] SUMMARY")
    print(f"Speedup: {speedup:.1f}x faster")
    if duration2 < duration1 * 0.5:
        print("✅ SUCCESS: Latency reduced significantly (likely cache hit).")
    else:
        print("❌ WARNING: Latency did not drop significantly. Cache hit failed or overhead is high.")
        
    # Same payload
    assert res1 == res2, "Cached result does not match original result"
    print("✅ Result matches perfectly.")

if __name__ == "__main__":
    run_test()
