import asyncio
import hashlib
import numpy as np
import os
import sys

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embeddings import preload_embedding_model, get_embedding_model
from backend.services.embedding_registry import get_embedding_registry

def cosine_similarity(v1, v2):
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def get_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def run_diagnostic():
    print("Preloading model...")
    preload_embedding_model()
    
    registry = get_embedding_registry()
    provider = registry.get_active_provider()
    print(f"Active Provider: {provider.provider_name} (Dimension: {provider.dimension})")

    # Set random seeds explicitly as per check requirements
    import torch
    import random
    SEED = 42
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)

    test_docs = [
        "The quick brown fox jumps over the lazy dog.",
        "RAG relies on high quality retrieval.",
        "Healthcare and FHIR standards.",
        "Determinism in embeddings is crucial for caching.",
        "Word " * 250  # Check longer tokens
    ]

    print(f"\nEvaluating {len(test_docs)} documents for embedding consistency...\n")
    
    # Run 1
    print("Run 1...")
    embeddings_run_1 = provider.embed_documents(test_docs)
    
    # Run 2
    print("Run 2...")
    embeddings_run_2 = provider.embed_documents(test_docs)
    
    print("\n--- T02 Embedding Consistency Check Results ---")
    
    all_consistent = True
    for i, (doc, e1, e2) in enumerate(zip(test_docs, embeddings_run_1, embeddings_run_2)):
        sim = cosine_similarity(e1, e2)
        doc_hash = get_hash(doc)
        
        # Check exact floating point match
        exact_match = np.allclose(e1, e2, atol=1e-8)
        
        status = "PASS" if exact_match else "WARN"
        if not exact_match and sim < 0.9999:
            status = "FAIL"
            all_consistent = False
            
        print(f"Doc {i+1} [Hash: {doc_hash[:8]}]")
        print(f"  Exact Float Match: {exact_match}")
        print(f"  Cosine Similarity: {sim:.8f} ({status})")

    if all_consistent:
        print("\nConclusion: Embeddings are deterministic and highly stable.")
    else:
        print("\nConclusion: Embedding drift detected! Non-deterministic behavior observed.")

if __name__ == "__main__":
    run_diagnostic()
