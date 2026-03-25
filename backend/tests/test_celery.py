import os
import sys
import time

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath('.'))

from backend.pipeline.workers.embedding_worker import process_embedding_batch

def test_celery():
    print("Dispatching test task to Celery...")
    
    # Mock data
    batch_run_id = "test_run_001"
    table_name = "test_table"
    serialized_chunks = [
        {
            "chunk_id": "chunk_001",
            "content": "Patient presents with severe headache and nausea.",
            "parent_id": "doc_001",
            "metadata": {"source": "test", "doc_id": "doc_001"},
            "is_parent": False
        },
        {
            "chunk_id": "chunk_002",
            "content": "Patient was prescribed 500mg generic ibuprofen.",
            "parent_id": "doc_001",
            "metadata": {"source": "test", "doc_id": "doc_001"},
            "is_parent": False
        }
    ]
    
    # Send to queue
    try:
        result = process_embedding_batch.delay(batch_run_id, table_name, serialized_chunks)
        print(f"Task dispatched with ID: {result.id}")
        
        print("Task sent to queue. Check celery logs to verify execution.")
        return True
    except Exception as e:
        print(f"Task failed: {e}")
        return False

if __name__ == "__main__":
    test_celery()
