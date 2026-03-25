import asyncio
import uuid
from backend.pipeline.vector_stores.factory import VectorStoreFactory

async def main():
    print("Testing Qdrant Integration...")
    
    provider = "qdrant"
    collection_name = "test_qdrant_celery_verification"
    
    print(f"Initializing {provider} Vector Store...")
    vector_store = VectorStoreFactory.get_provider(provider, collection_name=collection_name)
    
    print("Deleting collection if exists...")
    await vector_store.delete_collection()
    
    print("Upserting test batch...")
    # Mock data
    doc_id = str(uuid.uuid4())
    fake_embedding = [0.1] * 1024  # Assuming BGE-M3 1024 dims
    
    await vector_store.upsert_batch(
        ids=[doc_id],
        documents=["This is a test document for Qdrant Scale Testing"],
        embeddings=[fake_embedding],
        metadatas=[{"source_id": "test_src"}]
    )
    print("Upsert successful!")
    
    print("Searching vector store...")
    results = await vector_store.search(
        query_embedding=fake_embedding,
        top_k=2
    )
    
    print(f"Search Results: {len(results)}")
    if results:
        print(f"Top result doc: {results[0]['document']}")
        
    print("Cleaning up...")
    await vector_store.delete_collection()
    print("Integration verification complete!")

if __name__ == "__main__":
    asyncio.run(main())
