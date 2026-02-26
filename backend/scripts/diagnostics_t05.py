import asyncio
import numpy as np
import os
import sys

# Ensure backend acts as root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.services.embeddings import preload_embedding_model
from backend.services.embedding_registry import get_embedding_registry

def run_vector_quality_analysis():
    print("Preloading model for vector quality analysis...")
    preload_embedding_model()
    
    registry = get_embedding_registry()
    provider = registry.get_active_provider()
    print(f"Active Provider: {provider.provider_name} (Dimension: {provider.dimension})")

    # Generate a varied set of documents
    test_docs = [
        "The quick brown fox jumps over the lazy dog.",
        "Clinical trials show a 20% improvement in patient outcomes when using the new protocol.",
        "SELECT * FROM patients WHERE age > 65 AND status = 'active';",
        "Short.",
        "A somewhat longer sentence that contains more semantic information but isn't overly complex.",
    ]
    # Add some repetitive / out of distribution text
    test_docs.append("word " * 50)
    test_docs.append("xyz123 " * 10)

    print(f"\nEvaluating {len(test_docs)} documents for vector quality...\n")
    
    embeddings = provider.embed_documents(test_docs)
    vectors = np.array(embeddings)
    
    # 1. Norm Distribution
    norms = np.linalg.norm(vectors, axis=1)
    print("--- Norm Distribution ---")
    print(f"Mean Norm: {np.mean(norms):.4f}")
    print(f"Norm StdDev: {np.std(norms):.6f}")
    print(f"Min Norm: {np.min(norms):.4f}, Max Norm: {np.max(norms):.4f}")
    print("Are vectors normalized? ", "Yes" if np.allclose(norms, 1.0, atol=1e-5) else "No")
    
    # 2. Mean/Variance Stability across dimensions
    print("\n--- Dimension Statistics ---")
    dim_means = np.mean(vectors, axis=0)
    dim_vars = np.var(vectors, axis=0)
    print(f"Mean of dimension means: {np.mean(dim_means):.6f} (Expected ~0 for centered)")
    print(f"Mean of dimension variances: {np.mean(dim_vars):.6f}")
    print(f"Max dimension variance: {np.max(dim_vars):.6f} (Dim {np.argmax(dim_vars)})")
    
    # 3. Outlier Vectors (Based on distance from centroid)
    print("\n--- Outlier Detection ---")
    centroid = np.mean(vectors, axis=0)
    if np.linalg.norm(centroid) > 0:
        centroid = centroid / np.linalg.norm(centroid)  # normalize centroid
        
    similarities_to_centroid = np.dot(vectors, centroid)
    print(f"Mean similarity to centroid: {np.mean(similarities_to_centroid):.4f}")
    
    outlier_idx = np.argmin(similarities_to_centroid)
    print(f"Most anomalous document: Index {outlier_idx} (Sim to centroid: {similarities_to_centroid[outlier_idx]:.4f})")
    print(f"Content preview: '{test_docs[outlier_idx][:50]}...'")
    
    # 4. Cosine Similarity Histogram (Pairwise)
    print("\n--- Pairwise Cosine Similarity ---")
    n_docs = len(test_docs)
    sim_matrix = np.zeros((n_docs, n_docs))
    for i in range(n_docs):
        for j in range(n_docs):
            sim_matrix[i, j] = np.dot(vectors[i], vectors[j]) / (norms[i] * norms[j])
            
    # Extract lower triangle (excluding diagonal)
    tril_indices = np.tril_indices(n_docs, k=-1)
    pairwise_sims = sim_matrix[tril_indices]
    
    print(f"Mean Pairwise Similarity: {np.mean(pairwise_sims):.4f}")
    print(f"Max Pairwise Similarity: {np.max(pairwise_sims):.4f}")
    print(f"Min Pairwise Similarity: {np.min(pairwise_sims):.4f}")
    
    print("\nConclusion: Vector stats calculated successfully.")

if __name__ == "__main__":
    run_vector_quality_analysis()
