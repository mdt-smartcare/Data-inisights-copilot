import asyncio
import time
import psutil
import torch
import os
import sys

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig
from backend.services.embedding_registry import get_embedding_registry
from backend.services.embeddings import preload_embedding_model

def get_memory_stats():
    process = psutil.Process(os.getpid())
    ram_mb = process.memory_info().rss / 1024 / 1024
    
    vram_mb = 0
    if torch.cuda.is_available():
        vram_mb = torch.cuda.memory_allocated() / 1024 / 1024
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        # MPS memory tracking might be limited, but let's try
        try:
            vram_mb = torch.mps.current_allocated_memory() / 1024 / 1024
        except Exception:
            pass
            
    return ram_mb, vram_mb

async def run_diagnostic():
    print("Preloading model...")
    preload_embedding_model()
    registry = get_embedding_registry()
    provider = registry.get_active_provider()
    
    print(f"Active Provider: {provider.provider_name} (Dimension: {provider.dimension})")
    print(f"Provider Configured Batch Size (Inner): {getattr(provider, '_batch_size', 'N/A')}")
    
    # Outer batching config
    outer_batch_size = 50
    config = BatchConfig(batch_size=outer_batch_size, max_concurrent=2, timeout_per_batch_seconds=120)
    processor = EmbeddingBatchProcessor(config=config)
    
    print(f"Processor Configured Batch Size (Outer): {config.batch_size}")
    
    # Generate synthetic workload
    # We want varied chunk sizes to evaluate context window compliance 
    # typical chunk sizes: 200, 500, 1000 tokens ≈ roughly 4 chars per token
    synthetic_docs = []
    for i in range(100):
        length = 1000 if i % 2 == 0 else 4000  # Alternating small and large documents
        synthetic_docs.append("word " * (length // 5))  # dummy text

    print(f"Running synthetic workload of {len(synthetic_docs)} documents...")
    
    start_ram, start_vram = get_memory_stats()
    start_time = time.time()
    
    batch_latencies = []
    memory_peaks = {"ram": start_ram, "vram": start_vram}
    
    async def on_batch_complete(result):
        nonlocal memory_peaks
        ram, vram = get_memory_stats()
        memory_peaks["ram"] = max(memory_peaks["ram"], ram)
        memory_peaks["vram"] = max(memory_peaks["vram"], vram)
        
        batch_latencies.append({
            "batch_num": result.batch_number,
            "docs_processed": result.documents_processed,
            "latency_ms": result.processing_time_ms,
            "success": result.success,
            "error_message": result.error_message
        })
        print(f"Batch {result.batch_number} complete in {result.processing_time_ms}ms, "
              f"RAM: {ram:.2f}MB, VRAM: {vram:.2f}MB")
        
    result = await processor.process_documents(
        documents=synthetic_docs, 
        on_batch_complete=on_batch_complete
    )
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\n--- T01 Batch Size Audit Results ---")
    print(f"Total time: {total_time:.2f}s")
    print(f"Successful documents: {result['processed_documents']}/{result['total_documents']}")
    print(f"Failed documents: {result['failed_documents']}")
    print(f"Memory Peak RAM: {memory_peaks['ram']:.2f} MB (Start: {start_ram:.2f} MB, Delta: {memory_peaks['ram'] - start_ram:.2f} MB)")
    if torch.cuda.is_available() or (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
        print(f"Memory Peak VRAM: {memory_peaks['vram']:.2f} MB (Start: {start_vram:.2f} MB, Delta: {memory_peaks['vram'] - start_vram:.2f} MB)")
    else:
        print("Memory Peak VRAM: Device not available or tracking not supported.")
        
    if batch_latencies:
        avg_latency = sum(b['latency_ms'] for b in batch_latencies) / len(batch_latencies)
        print(f"Average Batch Latency: {avg_latency:.2f} ms")
        
        failed_batches = [b for b in batch_latencies if not b['success']]
        print(f"Failed batched / Retries implied: {len(failed_batches)}")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
