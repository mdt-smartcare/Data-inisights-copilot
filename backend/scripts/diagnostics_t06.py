import asyncio
import time
import os
import sys

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embeddings import preload_embedding_model
from backend.services.embedding_registry import get_embedding_registry
from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig

# Mock for typical Langchain/tiktoken logic to estimate tokens
def est_tokens(text):
    return len(text.split()) * 1.3  # Rough approximation

async def mock_vector_db_insert(batch_size):
    # Simulate network latency to Vector DB
    latency = 0.05 + (batch_size * 0.001)
    await asyncio.sleep(latency)
    return latency * 1000

async def run_pipeline_trace():
    print("--- Full Pipeline Trace Replay Starting ---")
    
    t0 = time.time()
    preload_embedding_model()
    t1 = time.time()
    warmup_time = (t1 - t0) * 1000
    print(f"[TRACE] Model Load & Warmup Time: {warmup_time:.2f}ms")
    
    registry = get_embedding_registry()
    provider = registry.get_active_provider()
    print(f"[TRACE] Active Provider: {provider.provider_name} (Dimension: {provider.dimension})")

    # Generate synthetic docs matching typical varied load
    # Scale down the workload as it caused a segfault
    num_docs = 100
    test_docs = []
    total_tokens_est = 0
    for i in range(num_docs):
        # mix small and large chunks
        size = 150 if i % 2 == 0 else 400
        text = "word " * size
        test_docs.append(text)
        total_tokens_est += est_tokens(text)
        
    print(f"[TRACE] Total Documents: {num_docs}")
    print(f"[TRACE] Total Tokens (Est): {total_tokens_est:.0f}")

    config = BatchConfig(batch_size=25, max_concurrent=2)
    processor = EmbeddingBatchProcessor(config=config)
    
    execution_log = []
    
    async def trace_batch(result):
        batch_start_idx = (result.batch_number - 1) * config.batch_size
        batch_docs = test_docs[batch_start_idx : batch_start_idx + result.documents_processed]
        batch_tokens = sum(est_tokens(d) for d in batch_docs)
        
        # Simulate Insertion
        insert_latency = await mock_vector_db_insert(result.documents_processed)
        
        log_entry = {
            "batch": result.batch_number,
            "docs": result.documents_processed,
            "tokens": batch_tokens,
            "embed_time_ms": result.processing_time_ms,
            "insert_time_ms": insert_latency,
            "total_batch_time": result.processing_time_ms + insert_latency,
            "success": result.success
        }
        execution_log.append(log_entry)
        print(f"[TRACE] Batch {result.batch_number} - Docs: {log_entry['docs']}, Tokens: {log_entry['tokens']:.0f}, "
              f"Embed: {log_entry['embed_time_ms']}ms, DB Insert: {log_entry['insert_time_ms']:.2f}ms")
            
    print("\n[TRACE] Starting batch processing...")
    t_start_pipeline = time.time()
    
    result = await processor.process_documents(
        documents=test_docs, 
        on_batch_complete=trace_batch
    )
    
    t_end_pipeline = time.time()
    total_pipeline_time = t_end_pipeline - t_start_pipeline
    
    print("\n--- Final Pipeline Trace Report ---")
    print(f"Total Pipeline Runtime: {total_pipeline_time:.2f}s")
    print(f"Total Documents Processed: {result['processed_documents']}")
    print(f"Failed Documents: {result['failed_documents']}")
    
    if execution_log:
        embed_times = [log['embed_time_ms'] for log in execution_log]
        insert_times = [log['insert_time_ms'] for log in execution_log]
        
        print(f"\nAverage Embed Time per Batch: {sum(embed_times)/len(embed_times):.2f}ms")
        print(f"Max Embed Time (Slow Batch): {max(embed_times):.2f}ms")
        
        # Calculate P95
        embed_times.sort()
        p95_idx = int(len(embed_times) * 0.95)
        print(f"P95 Embed Time: {embed_times[p95_idx]:.2f}ms")
        
        print(f"\nAverage DB Insert Latency: {sum(insert_times)/len(insert_times):.2f}ms")
        print(f"Max DB Insert Latency: {max(insert_times):.2f}ms")

if __name__ == "__main__":
    asyncio.run(run_pipeline_trace())
