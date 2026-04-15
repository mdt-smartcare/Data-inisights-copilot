"""
Train SQL Examples - Load curated Q&A pairs into the vector store.

This script loads SQL training examples from JSON files into the SQLExamplesStore
for few-shot learning to improve NL2SQL accuracy.

Run with:
    python -m app.scripts.train_sql_examples
    python -m app.scripts.train_sql_examples --file custom_examples.json
    python -m app.scripts.train_sql_examples --clear --file examples.json
    python -m app.scripts.train_sql_examples --golden-dataset eval/datasets/golden.json

Features:
    - Loads examples from JSON training files
    - Optional extraction from golden evaluation datasets
    - PII/sensitive data validation before loading
    - Progress logging with statistics
    - Graceful error handling
"""
import asyncio
import argparse
import json
import re
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.utils.logging import get_logger, configure_logging
from app.modules.sql_examples.store import get_sql_examples_store, reset_sql_examples_store

logger = get_logger(__name__)

# Default paths
DEFAULT_TRAINING_FILE = Path(__file__).parent.parent / "config" / "sql_training_examples.json"


# ============================================
# PII Detection Patterns
# ============================================

# Patterns that may indicate PII or sensitive data
PII_PATTERNS = [
    # Email addresses
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'email address'),
    
    # Phone numbers (various formats)
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', 'phone number'),
    (r'\b\+\d{1,3}[-.\s]?\d{3,}\b', 'international phone'),
    
    # SSN patterns
    (r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b', 'SSN-like number'),
    
    # Credit card patterns
    (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', 'credit card number'),
    
    # IP addresses
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'IP address'),
    
    # Common name patterns (first + last with capitals)
    (r'\b[A-Z][a-z]+ [A-Z][a-z]+\b(?=.*(?:patient|user|person|customer|employee))', 'potential real name'),
    
    # Specific identifiers that shouldn't be in training data
    (r'\bMRN[-:\s]?\d+\b', 'medical record number'),
    (r'\bSSN[-:\s]?\d+\b', 'social security number'),
    (r'\bDOB[-:\s]?\d+\b', 'date of birth identifier'),
    
    # Street addresses
    (r'\b\d+\s+[A-Z][a-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln)\b', 'street address'),
]

# Words that are acceptable in generic SQL examples (not PII)
ALLOWED_GENERIC_TERMS = {
    'entity_id', 'record_id', 'patient_id', 'user_id', 'group_id',
    'value_1', 'value_2', 'category', 'measurement_date', 'event_timestamp',
    'records', 'entities', 'measurements', 'activity_log',
    'john', 'jane', 'doe',  # Common placeholder names
}


def check_for_pii(text: str) -> List[Tuple[str, str]]:
    """
    Check text for potential PII patterns.
    
    Args:
        text: Text to check (question or SQL)
        
    Returns:
        List of (matched_text, pattern_type) tuples for any PII found
    """
    findings = []
    text_lower = text.lower()
    
    for pattern, pattern_type in PII_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Skip if it's a known generic term
            if match.lower() in ALLOWED_GENERIC_TERMS:
                continue
            findings.append((match, pattern_type))
    
    return findings


def validate_examples_for_pii(examples: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """
    Validate all examples for PII content.
    
    Args:
        examples: List of example dictionaries
        
    Returns:
        Tuple of (clean_examples, flagged_examples)
    """
    clean = []
    flagged = []
    
    for example in examples:
        question = example.get('question', '')
        sql = example.get('sql', '')
        description = example.get('description', '')
        
        # Check all text fields
        all_text = f"{question} {sql} {description}"
        pii_findings = check_for_pii(all_text)
        
        if pii_findings:
            example['_pii_findings'] = pii_findings
            flagged.append(example)
        else:
            clean.append(example)
    
    return clean, flagged


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Load and parse a JSON file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Parsed JSON content
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def train_from_file(file_path: Path, skip_pii_check: bool = False) -> int:
    """
    Load SQL examples from a JSON training file into the vector store.
    
    Expected JSON structure:
    {
        "version": "1.0",
        "examples": [
            {
                "id": "unique_id",
                "category": "category_name",
                "question": "Natural language question",
                "sql": "SQL query",
                "description": "Description",
                "tags": ["tag1", "tag2"]
            }
        ]
    }
    
    Args:
        file_path: Path to JSON training file
        skip_pii_check: If True, skip PII validation (not recommended)
        
    Returns:
        Number of examples successfully added
    """
    logger.info(f"Loading training examples from: {file_path}")
    
    # Load JSON
    try:
        data = load_json_file(file_path)
    except FileNotFoundError:
        logger.error(f"Training file not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in training file: {e}")
        raise
    
    # Extract examples
    examples = data.get('examples', [])
    if not examples:
        logger.warning("No examples found in training file")
        return 0
    
    version = data.get('version', 'unknown')
    logger.info(f"Found {len(examples)} examples (version: {version})")
    
    # PII validation
    if not skip_pii_check:
        clean_examples, flagged_examples = validate_examples_for_pii(examples)
        
        if flagged_examples:
            logger.warning(f"Found {len(flagged_examples)} examples with potential PII:")
            for ex in flagged_examples:
                findings = ex.get('_pii_findings', [])
                logger.warning(
                    f"  - Example '{ex.get('id', 'unknown')}': "
                    f"{[f'{t}: {m}' for m, t in findings]}"
                )
            logger.warning("Skipping flagged examples. Use --skip-pii-check to force load.")
            examples = clean_examples
    
    if not examples:
        logger.warning("No valid examples to load after PII filtering")
        return 0
    
    # Get store and add examples
    store = get_sql_examples_store()
    
    logger.info(f"Adding {len(examples)} examples to vector store...")
    added_count = await store.add_examples_batch(examples)
    
    logger.info(f"Successfully added {added_count}/{len(examples)} examples")
    
    return added_count


async def train_from_golden_dataset(file_path: Path, skip_pii_check: bool = False) -> int:
    """
    Extract SQL examples from a golden evaluation dataset.
    
    Golden datasets typically have a different structure focused on evaluation.
    This function extracts question-SQL pairs and converts them to training format.
    
    Expected structures supported:
    - List of {"question": ..., "expected_sql": ...} or {"query": ..., "sql": ...}
    - Dict with "test_cases" or "examples" key containing the above
    
    Args:
        file_path: Path to golden dataset JSON
        skip_pii_check: If True, skip PII validation
        
    Returns:
        Number of examples successfully added
    """
    logger.info(f"Extracting examples from golden dataset: {file_path}")
    
    # Load JSON
    try:
        data = load_json_file(file_path)
    except FileNotFoundError:
        logger.error(f"Golden dataset not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in golden dataset: {e}")
        raise
    
    # Extract test cases from various formats
    test_cases = []
    
    if isinstance(data, list):
        test_cases = data
    elif isinstance(data, dict):
        # Try common keys
        for key in ['test_cases', 'examples', 'tests', 'queries', 'data']:
            if key in data and isinstance(data[key], list):
                test_cases = data[key]
                break
    
    if not test_cases:
        logger.warning("No test cases found in golden dataset")
        return 0
    
    logger.info(f"Found {len(test_cases)} test cases in golden dataset")
    
    # Convert to training format
    examples = []
    for i, tc in enumerate(test_cases):
        # Extract question (try various keys)
        question = (
            tc.get('question') or 
            tc.get('query') or 
            tc.get('natural_language') or
            tc.get('nl_query') or
            tc.get('input')
        )
        
        # Extract SQL (try various keys)
        sql = (
            tc.get('expected_sql') or 
            tc.get('sql') or 
            tc.get('ground_truth') or
            tc.get('target') or
            tc.get('output')
        )
        
        if not question or not sql:
            logger.debug(f"Skipping test case {i}: missing question or sql")
            continue
        
        # Build training example
        example = {
            'id': tc.get('id', f'golden_{i}'),
            'category': tc.get('category', 'golden_dataset'),
            'question': question,
            'sql': sql,
            'description': tc.get('description', 'Extracted from golden evaluation dataset'),
            'tags': tc.get('tags', ['golden_dataset', 'evaluation'])
        }
        examples.append(example)
    
    logger.info(f"Converted {len(examples)} test cases to training format")
    
    if not examples:
        logger.warning("No valid examples extracted from golden dataset")
        return 0
    
    # PII validation
    if not skip_pii_check:
        clean_examples, flagged_examples = validate_examples_for_pii(examples)
        
        if flagged_examples:
            logger.warning(f"Found {len(flagged_examples)} examples with potential PII")
            examples = clean_examples
    
    if not examples:
        logger.warning("No valid examples to load after PII filtering")
        return 0
    
    # Get store and add examples
    store = get_sql_examples_store()
    
    logger.info(f"Adding {len(examples)} golden examples to vector store...")
    added_count = await store.add_examples_batch(examples)
    
    logger.info(f"Successfully added {added_count}/{len(examples)} golden examples")
    
    return added_count


async def clear_examples() -> None:
    """Clear all examples from the vector store."""
    logger.info("Clearing existing SQL examples from vector store...")
    store = get_sql_examples_store()
    await store.clear()
    # Reset singleton to ensure fresh state
    reset_sql_examples_store()
    logger.info("Cleared all SQL examples")


async def get_store_stats() -> Dict[str, Any]:
    """Get current statistics from the SQL examples store."""
    store = get_sql_examples_store()
    health = await store.health_check()
    return health


def print_banner():
    """Print script banner."""
    print("=" * 70)
    print("SQL Examples Training Script")
    print("=" * 70)
    print()


def print_summary(stats_before: Dict, stats_after: Dict, added: int, source: str):
    """Print training summary."""
    print()
    print("=" * 70)
    print("TRAINING SUMMARY")
    print("=" * 70)
    print(f"  Source:              {source}")
    print(f"  Examples added:      {added}")
    print(f"  Store before:        {stats_before.get('example_count', 0)} examples")
    print(f"  Store after:         {stats_after.get('example_count', 0)} examples")
    print(f"  Backend:             {stats_after.get('backend', 'unknown')}")
    print(f"  Collection:          {stats_after.get('collection', 'unknown')}")
    print(f"  Embedding model:     {stats_after.get('embedding_model', 'unknown')}")
    print("=" * 70)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Load SQL training examples into the vector store for few-shot learning.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.scripts.train_sql_examples
  python -m app.scripts.train_sql_examples --file custom_examples.json
  python -m app.scripts.train_sql_examples --clear --file examples.json
  python -m app.scripts.train_sql_examples --golden-dataset eval/datasets/golden.json
  python -m app.scripts.train_sql_examples --file examples.json --golden-dataset golden.json
        """
    )
    
    parser.add_argument(
        '--file', '-f',
        type=Path,
        default=DEFAULT_TRAINING_FILE,
        help=f'Path to JSON training file (default: {DEFAULT_TRAINING_FILE})'
    )
    
    parser.add_argument(
        '--golden-dataset', '-g',
        type=Path,
        default=None,
        help='Optional path to golden evaluation dataset for additional examples'
    )
    
    parser.add_argument(
        '--clear', '-c',
        action='store_true',
        help='Clear existing examples before training'
    )
    
    parser.add_argument(
        '--skip-pii-check',
        action='store_true',
        help='Skip PII validation (not recommended for production)'
    )
    
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show current store statistics, do not train'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    configure_logging(log_level=log_level, json_logs=False)
    
    print_banner()
    
    try:
        # Get initial stats
        stats_before = await get_store_stats()
        
        if args.stats_only:
            print("Current Store Statistics:")
            print(f"  Backend:         {stats_before.get('backend', 'unknown')}")
            print(f"  Collection:      {stats_before.get('collection', 'unknown')}")
            print(f"  Exists:          {stats_before.get('collection_exists', False)}")
            print(f"  Example count:   {stats_before.get('example_count', 0)}")
            print(f"  Embedding model: {stats_before.get('embedding_model', 'unknown')}")
            print(f"  Healthy:         {stats_before.get('healthy', False)}")
            return
        
        print(f"Initial store state: {stats_before.get('example_count', 0)} examples")
        print()
        
        # Clear if requested
        if args.clear:
            await clear_examples()
            # Refresh stats after clear
            stats_before = await get_store_stats()
            print(f"After clear: {stats_before.get('example_count', 0)} examples")
            print()
        
        total_added = 0
        sources = []
        
        # Load from training file
        if args.file and args.file.exists():
            print(f"Loading from training file: {args.file}")
            try:
                added = await train_from_file(args.file, skip_pii_check=args.skip_pii_check)
                total_added += added
                sources.append(str(args.file))
                print(f"  Added {added} examples from training file")
            except Exception as e:
                logger.error(f"Failed to load training file: {e}")
                print(f"  ERROR: {e}")
        elif args.file and not args.file.exists():
            print(f"WARNING: Training file not found: {args.file}")
        
        # Load from golden dataset if provided
        if args.golden_dataset:
            print(f"\nLoading from golden dataset: {args.golden_dataset}")
            try:
                added = await train_from_golden_dataset(
                    args.golden_dataset, 
                    skip_pii_check=args.skip_pii_check
                )
                total_added += added
                sources.append(str(args.golden_dataset))
                print(f"  Added {added} examples from golden dataset")
            except Exception as e:
                logger.error(f"Failed to load golden dataset: {e}")
                print(f"  ERROR: {e}")
        
        # Get final stats
        stats_after = await get_store_stats()
        
        # Print summary
        source_str = ', '.join(sources) if sources else 'None'
        print_summary(stats_before, stats_after, total_added, source_str)
        
        if total_added > 0:
            print("\nSQL examples store is ready for few-shot retrieval!")
            print("The NL2SQL pipeline will now use these examples to improve accuracy.")
        else:
            print("\nNo examples were added. Check the file paths and content.")
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Training failed: {e}")
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
