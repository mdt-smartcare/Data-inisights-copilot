import asyncio
import time
import os
import sys
import psutil
import gc

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig
from backend.services.embeddings import preload_embedding_model

def get_ram_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def get_vram_mb():
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / 1024 / 1024
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.mps.current_allocated_memory() / 1024 / 1024
    except ImportError:
        pass
    return 0

async def run_memory_diagnostic():
    print("Preloading model for memory testing...")
    preload_embedding_model()
    
    # Wait a sec to stabilize baseline memory
    time.sleep(1)
    gc.collect()
    baseline_ram = get_ram_mb()
    baseline_vram = get_vram_mb()
    
    print(f"Baseline RAM: {baseline_ram:.2f} MB")
    print(f"Baseline VRAM: {baseline_vram:.2f} MB")
    
    # Scale down the workload as it caused a segfault
    num_docs = 200
    test_docs = []
    for i in range(num_docs):
        # mix small and large chunks
        size = 200 if i % 2 == 0 else 600
        test_docs.append("word " * size)
        
    config = BatchConfig(batch_size=50, max_concurrent=2)
    processor = EmbeddingBatchProcessor(config=config)
    
    print(f"\nProcessing {num_docs} documents in batches of {config.batch_size}...")
    
    memory_history = []
    
    async def track_memory(result):
        gc.collect()
        ram = get_ram_mb()
        vram = get_vram_mb()
        memory_history.append((result.batch_number, ram, vram))
        print(f"Batch {result.batch_number} - RAM: {ram:.2f}MB, VRAM: {vram:.2f}MB")
            
    result = await processor.process_documents(
        documents=test_docs, 
        on_batch_complete=track_memory
    )
    
    # Post execution
    gc.collect()
    end_ram = get_ram_mb()
    end_vram = get_vram_mb()
    
    print("\n--- T04 Memory Pressure Diagnostics Results ---")
    print(f"Processed Docs: {result['processed_documents']}/{result['total_documents']} (Failures: {result['failed_documents']})")
    print(f"Final RAM: {end_ram:.2f} MB (Delta from baseline: {end_ram - baseline_ram:.2f} MB)")
    print(f"Final VRAM: {end_vram:.2f} MB (Delta from baseline: {end_vram - baseline_vram:.2f} MB)")
    
    peak_run_ram = max((m[1] for m in memory_history)) if memory_history else 0
    print(f"Peak RAM during processing: {peak_run_ram:.2f} MB")

    if end_ram - baseline_ram > 150:
        print("WARNING: Possible RAM leak detected. Memory footprint significantly higher after execution.")
    else:
        print("PASS: Object retention is within expected limits.")

if __name__ == "__main__":
    asyncio.run(run_memory_diagnostic())
