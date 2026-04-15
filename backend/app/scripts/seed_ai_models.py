"""
Seed AI Models - Default models for the system.

This seeds the ai_models table with commonly used models so users
understand the fields and have working defaults.

Run with: python -m app.scripts.seed_ai_models

Models seeded:
- LLM: OpenAI GPT-4o (cloud, requires API key)
- Embedding: BAAI/bge-base-en-v1.5 (local, needs download)
- Embedding: OpenAI text-embedding-3-small (cloud, requires API key)
- Reranker: BAAI/bge-reranker-v2-m3 (local, needs download)
"""
import asyncio
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.session import get_session_factory
from app.modules.ai_models.models import AIModel


# ============================================
# Seed Data - Realistic defaults
# ============================================

SEED_MODELS = [
    # ==========================================
    # LLM Models
    # ==========================================
    {
        "model_id": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "model_type": "llm",
        "provider_name": "openai",
        "deployment_type": "cloud",
        "description": "OpenAI's flagship model. Fast, smart, supports vision. Good for RAG.",
        
        # Cloud config
        "api_base_url": "https://api.openai.com/v1",
        "api_key_env_var": "OPENAI_API_KEY",  # Read from environment
        
        # Model specs
        "context_length": 128000,  # 128K context window
        
        # RAG hints
        "recommended_chunk_size": 1500,
        "compatibility_notes": "Works well with any embedding model. Supports function calling.",
        
        # Status
        "is_default": True,  # Set as default LLM
        "download_status": "ready",  # Cloud models are always ready
    },
    {
        "model_id": "openai/gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "model_type": "llm",
        "provider_name": "openai",
        "deployment_type": "cloud",
        "description": "Smaller, faster, cheaper GPT-4o. Good for high-volume use cases.",
        
        "api_base_url": "https://api.openai.com/v1",
        "api_key_env_var": "OPENAI_API_KEY",
        
        "context_length": 128000,
        "recommended_chunk_size": 1500,
        "compatibility_notes": "Cost-effective option. Same capabilities as GPT-4o but faster.",
        
        "is_default": False,
        "download_status": "ready",
    },
    
    # ==========================================
    # Embedding Models
    # ==========================================
    {
        "model_id": "huggingface/BAAI/bge-base-en-v1.5",
        "display_name": "BGE-M3 (Local)",
        "model_type": "embedding",
        "provider_name": "huggingface",
        "deployment_type": "local",
        "description": "Best multilingual embedding model. Supports 100+ languages. Runs locally.",
        
        # Local config
        "hf_model_id": "BAAI/bge-base-en-v1.5",
        "local_path": "./data/models/BAAI/bge-base-en-v1.5",
        
        # Model specs
        "dimensions": 1024,
        "max_input_tokens": 8192,
        
        # RAG hints
        "recommended_chunk_size": 512,
        "compatibility_notes": "Best paired with bge-reranker-v2-m3. Excellent for medical text.",
        
        "is_default": True,  # Set as default embedding
        "download_status": "not_downloaded",  # Needs download
    },
    {
        "model_id": "openai/text-embedding-3-small",
        "display_name": "OpenAI Embedding 3 Small",
        "model_type": "embedding",
        "provider_name": "openai",
        "deployment_type": "cloud",
        "description": "OpenAI's efficient embedding model. Good balance of cost and quality.",
        
        "api_base_url": "https://api.openai.com/v1",
        "api_key_env_var": "OPENAI_API_KEY",
        
        "dimensions": 1536,
        "max_input_tokens": 8191,
        
        "recommended_chunk_size": 512,
        "compatibility_notes": "Use with OpenAI LLMs for best results. Fast API response.",
        
        "is_default": False,
        "download_status": "ready",
    },
    {
        "model_id": "huggingface/BAAI/bge-base-en-v1.5",
        "display_name": "BGE-Base EN (Local)",
        "model_type": "embedding",
        "provider_name": "huggingface",
        "deployment_type": "local",
        "description": "Fast local embedding model. English only. Good for prototyping.",
        
        "hf_model_id": "BAAI/bge-base-en-v1.5",
        "local_path": "./data/models/BAAI/bge-base-en-v1.5",
        
        "dimensions": 768,
        "max_input_tokens": 512,
        
        "recommended_chunk_size": 400,
        "compatibility_notes": "Smaller model, faster inference. English only.",
        
        "is_default": False,
        "download_status": "not_downloaded",
    },
    
    # ==========================================
    # Reranker Models
    # ==========================================
    {
        "model_id": "huggingface/BAAI/bge-reranker-v2-m3",
        "display_name": "BGE Reranker v2 M3 (Local)",
        "model_type": "reranker",
        "provider_name": "huggingface",
        "deployment_type": "local",
        "description": "Best multilingual reranker. Pairs perfectly with bge-base-en-v1.5 embeddings.",
        
        "hf_model_id": "BAAI/bge-reranker-v2-m3",
        "local_path": "./data/models/BAAI/bge-reranker-v2-m3",
        
        "max_input_tokens": 8192,
        
        "compatibility_notes": "Use with bge-base-en-v1.5 embeddings for best results. Improves retrieval accuracy.",
        
        "is_default": True,  # Set as default reranker
        "download_status": "not_downloaded",
    },
    {
        "model_id": "huggingface/BAAI/bge-reranker-base",
        "display_name": "BGE Reranker Base (Local)",
        "model_type": "reranker",
        "provider_name": "huggingface",
        "deployment_type": "local",
        "description": "Fast reranker for English. Good balance of speed and accuracy.",
        
        "hf_model_id": "BAAI/bge-reranker-base",
        "local_path": "./data/models/BAAI/bge-reranker-base",
        
        "max_input_tokens": 512,
        
        "compatibility_notes": "Use with bge-base-en embeddings. Faster than v2-m3.",
        
        "is_default": False,
        "download_status": "not_downloaded",
    },
]


async def seed_models(session: AsyncSession):
    """Seed the ai_models table with default models."""
    from sqlalchemy import select, func
    
    # Check if already seeded
    result = await session.execute(select(func.count(AIModel.id)))
    count = result.scalar() or 0
    
    if count > 0:
        print(f"✓ ai_models table already has {count} models. Skipping seed.")
        return
    
    print("Seeding AI models...")
    
    for model_data in SEED_MODELS:
        model = AIModel(**model_data)
        session.add(model)
        print(f"  + {model_data['model_type']:10} | {model_data['model_id']:40} | {model_data['deployment_type']}")
    
    await session.commit()
    print(f"\n✓ Seeded {len(SEED_MODELS)} models successfully!")
    
    # Print summary
    print("\n" + "="*70)
    print("SUMMARY - Default Models:")
    print("="*70)
    print(f"  LLM:       openai/gpt-4o (cloud, uses OPENAI_API_KEY env var)")
    print(f"  Embedding: huggingface/BAAI/bge-base-en-v1.5 (local, needs download)")
    print(f"  Reranker:  huggingface/BAAI/bge-reranker-v2-m3 (local, needs download)")
    print("="*70)
    print("\nNext steps:")
    print("  1. Set OPENAI_API_KEY in .env for cloud models")
    print("  2. Download local models via UI or API")
    print("  3. Models will appear in /api/v1/ai-models/available")


async def main():
    """Main entry point."""
    print("=" * 70)
    print("AI Models Seed Script")
    print("=" * 70)
    
    # Get session
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed_models(session)


if __name__ == "__main__":
    asyncio.run(main())
