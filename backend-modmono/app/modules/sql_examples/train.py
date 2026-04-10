#!/usr/bin/env python3
"""
Script to load SQL training examples into the vector store.

Usage:
    python -m app.modules.sql_examples.train --load
    python -m app.modules.sql_examples.train --clear
    python -m app.modules.sql_examples.train --status
"""
import argparse
import asyncio
import json
from pathlib import Path

# Setup path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.modules.sql_examples.store import get_sql_examples_store, reset_sql_examples_store
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Path to training examples JSON
EXAMPLES_FILE = Path(__file__).parent / "training_examples.json"


async def load_examples():
    """Load SQL examples from JSON file into vector store."""
    if not EXAMPLES_FILE.exists():
        print(f"❌ Training examples file not found: {EXAMPLES_FILE}")
        return False
    
    print(f"📂 Loading examples from: {EXAMPLES_FILE}")
    
    with open(EXAMPLES_FILE, "r") as f:
        data = json.load(f)
    
    examples = data.get("examples", [])
    if not examples:
        print("❌ No examples found in file")
        return False
    
    print(f"📊 Found {len(examples)} examples to load")
    
    # Get the store
    store = get_sql_examples_store()
    
    # Load examples in batch
    count = await store.add_examples_batch(examples)
    
    print(f"✅ Successfully loaded {count} examples into vector store")
    
    # Verify
    total = await store.get_example_count()
    print(f"📈 Total examples in store: {total}")
    
    return True


async def clear_examples():
    """Clear all examples from the vector store."""
    print("🗑️  Clearing all SQL examples...")
    
    store = get_sql_examples_store()
    await store.clear()
    
    print("✅ All examples cleared")
    return True


async def show_status():
    """Show the status of the SQL examples store."""
    print("📊 SQL Examples Store Status")
    print("-" * 40)
    
    store = get_sql_examples_store()
    health = await store.health_check()
    
    for key, value in health.items():
        print(f"  {key}: {value}")
    
    return health.get("healthy", False)


async def test_search(query: str):
    """Test searching for similar examples."""
    print(f"🔍 Searching for: '{query}'")
    print("-" * 40)
    
    store = get_sql_examples_store()
    examples = await store.get_similar_examples(query, top_k=3, min_score=0.3)
    
    if not examples:
        print("  No similar examples found")
        return
    
    for i, ex in enumerate(examples, 1):
        print(f"\n  Example {i} (score: {ex['score']:.3f}):")
        print(f"    Q: {ex['question'][:80]}...")
        print(f"    Category: {ex['category']}")


def main():
    parser = argparse.ArgumentParser(description="Manage SQL training examples")
    parser.add_argument("--load", action="store_true", help="Load examples from JSON file")
    parser.add_argument("--clear", action="store_true", help="Clear all examples")
    parser.add_argument("--status", action="store_true", help="Show store status")
    parser.add_argument("--test", type=str, help="Test search with a query")
    
    args = parser.parse_args()
    
    if args.load:
        asyncio.run(load_examples())
    elif args.clear:
        asyncio.run(clear_examples())
    elif args.status:
        asyncio.run(show_status())
    elif args.test:
        asyncio.run(test_search(args.test))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
