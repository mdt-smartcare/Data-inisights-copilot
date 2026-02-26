import os
import sys

def run_diagnostic():
    print("--- T07 Frontend vs Diagnostic Pipeline Comparison ---")
    
    print("\n1. Batch Size & Concurrency")
    print("Frontend API Payload allows passing `batch_size` and `max_concurrent`.")
    print("BUT `_run_embedding_job` in `embedding_progress.py` hardcodes:")
    print("  processor = EmbeddingBatchProcessor(BatchConfig(batch_size=50, max_concurrent=5))")
    print("This means UI-driven overrides are IGNORED during execution.")
    
    print("\n2. Chunking Logic")
    print("Diagnostic pipeline uses synthetic data directly.")
    print("Frontend pipeline uses LangChain's RecursiveCharacterTextSplitter.")
    print("Default chunk_size=800, chunk_overlap=150, but can be overridden by config.")
    
    print("\n3. Vector DB Write Mode")
    print("Frontend pipeline collects EVERYTHING into memory in `result = await processor.process_documents(...)`")
    print("Then it performs SYNCHRONOUS bulk upsert to ChromaDB in batches of 1000:")
    print("  collection.upsert(...)")
    print("This causes a massive memory spike at the end of the pipeline for large document sets, unlike the mocked async stream in diagnostics.")
    
    print("\n4. Tokenization Behavior")
    print("Frontend uses SentenceTransformers internally inside `embed_documents`.")
    print("Tokenization is handled by the HuggingFace tokenizer synchronously inside the thread pool executor.")
    
    print("\n5. Retry and Backoff")
    print("EmbeddingBatchProcessor implements 3 retries with exponential backoff starting at 5 seconds.")
    print("However, the Vector DB upsert step has NO RETRY LOGIC. If ChromaDB times out on a 1000-chunk batch, the entire job fails after embeddings were already computed.")
    
    print("\nSUMMARY OF DIVERGENT PATHS:")
    print("- Ignored UI overrides for batch configs.")
    print("- Synchronous, memory-heavy Vector DB upsert vs assumed async streaming.")
    print("- Lack of retry logic on the final database insertion step.")
    
if __name__ == "__main__":
    run_diagnostic()
