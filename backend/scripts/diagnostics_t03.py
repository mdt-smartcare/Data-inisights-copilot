import asyncio
import time
import os
import sys
import psutil
from textwrap import dedent

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig
from backend.services.embeddings import preload_embedding_model
from backend.services.embedding_registry import get_embedding_registry

async def run_throughput_benchmark():
    print("Preloading model...")
    preload_embedding_model()
    registry = get_embedding_registry()
    provider = registry.get_active_provider()
    
    # 1. Prepare Data
    # Let's create a realistic sized payload (approx 500-1000 tokens per chunk)
    base_text = "The quick brown fox jumps over the lazy dog. " * 30  # ~300 words per chunk
    num_docs = 200
    test_docs = [base_text + f" Document {i}" for i in range(num_docs)]
    
    print(f"\n--- Baseline Model Inference Throughput ---")
    print(f"Provider: {provider.provider_name}, Inner Batch Size: {getattr(provider, '_batch_size', 'N/A')}")
    print(f"Testing {len(test_docs)} documents sequentially...")
    
    start_time = time.time()
    embeddings = provider.embed_documents(test_docs)
    end_time = time.time()
    
    sync_time = end_time - start_time
    chunks_per_sec = num_docs / sync_time
    print(f"Sequential processing time: {sync_time:.2f}s")
    print(f"Sequential throughput: {chunks_per_sec:.2f} chunks/sec")

    # 2. Parallel Processing (Threadpool via EmbeddingBatchProcessor)
    print("\n--- Parallel Processor Throughput (Simulating Pipeline) ---")
    
    config = BatchConfig(
        batch_size=50, 
        max_concurrent=4,  # Test multiple workers
        timeout_per_batch_seconds=120
    )
    processor = EmbeddingBatchProcessor(config=config)
    
    print(f"Batch Config: batch_size={config.batch_size}, max_concurrent={config.max_concurrent}")
    
    start_time = time.time()
    
    result = await processor.process_documents(documents=test_docs)
    
    end_time = time.time()
    async_time = end_time - start_time
    async_chunks_per_sec = num_docs / async_time
    
    print(f"Parallel processing time: {async_time:.2f}s")
    print(f"Parallel throughput: {async_chunks_per_sec:.2f} chunks/sec")
    
    print("\n--- Conclusion ---")
    if async_time < sync_time:
        print(f"Parallelization improved throughput by {(sync_time/async_time - 1)*100:.1f}%")
    else:
        print(f"Parallelization DECREASED throughput. Blocking behavior detected.")
        print("Note: SentenceTransformers model is often CPU/GPU bound. Running multiple threads against a single loaded model might cause GIL contention rather than true parallelism.")

if __name__ == "__main__":
    asyncio.run(run_throughput_benchmark())
