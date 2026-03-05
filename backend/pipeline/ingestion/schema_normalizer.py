"""
Schema Normalizer — Automated column name sanitization for uploaded files.

Never trust raw column headers from user uploads. This module ensures all column
names are predictable, SQL-safe identifiers that reduce LLM hallucinations.

Examples:
    Input:  ["Blood Pressure (Sys)", "Patient_ID ", "notes...", "123_invalid"]
    Output: ["blood_pressure_sys", "patient_id", "notes", "col_123_invalid"]
"""

import re
import csv
import json
import unicodedata
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)


# Common medical/clinical abbreviations to preserve
KNOWN_ABBREVIATIONS = {
    'bmi': 'bmi',
    'bp': 'bp',
    'hr': 'hr',
    'id': 'id',
    'dob': 'dob',
    'ssn': 'ssn',
    'mrn': 'mrn',
    'icd': 'icd',
    'cpt': 'cpt',
    'npi': 'npi',
    'ehr': 'ehr',
    'emr': 'emr',
    'hba1c': 'hba1c',
    'ldl': 'ldl',
    'hdl': 'hdl',
    'ast': 'ast',
    'alt': 'alt',
    'wbc': 'wbc',
    'rbc': 'rbc',
}

# Words to remove (noise words that don't add meaning)
NOISE_WORDS = {'the', 'a', 'an', 'of', 'for', 'and', 'or', 'in', 'on', 'at', 'to'}


class SchemaNormalizer:
    """
    Normalizes column names from uploaded files to SQL-safe identifiers.
    
    Transformations applied:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase
    3. Replace spaces and special chars with underscores
    4. Remove parentheses content or convert to suffix
    5. Collapse multiple underscores
    6. Ensure doesn't start with number
    7. Handle duplicates with numeric suffixes
    8. Truncate overly long names
    """
    
    MAX_COLUMN_LENGTH = 63  # PostgreSQL limit, good default
    
    def __init__(self, preserve_case: bool = False, max_length: int = None):
        self.preserve_case = preserve_case
        self.max_length = max_length or self.MAX_COLUMN_LENGTH
    
    def normalize_column(self, col: str, index: int = 0) -> str:
        """
        Normalize a single column name to a SQL-safe identifier.
        
        Args:
            col: Raw column name from file
            index: Column index (used for fallback naming)
            
        Returns:
            Normalized, SQL-safe column name
        """
        if col is None or str(col).strip() == '':
            return f"col_{index}"
        
        original = str(col)
        normalized = original
        
        # Step 1: Strip whitespace
        normalized = normalized.strip()
        
        # Step 2: Handle unicode characters (é → e, ñ → n, etc.)
        normalized = unicodedata.normalize('NFKD', normalized)
        normalized = normalized.encode('ascii', 'ignore').decode('ascii')
        
        # Step 3: Convert parentheses content to suffix
        # "Blood Pressure (Sys)" → "Blood Pressure Sys"
        # "Height (cm)" → "Height cm"
        normalized = re.sub(r'\(([^)]+)\)', r'_\1', normalized)
        
        # Step 4: Remove other brackets
        normalized = re.sub(r'[\[\]{}<>]', '', normalized)
        
        # Step 5: Replace common separators with underscores
        # Handles: spaces, hyphens, dots, commas, slashes
        normalized = re.sub(r'[\s\-\.,/\\]+', '_', normalized)
        
        # Step 6: Remove special characters (keep only alphanumeric and underscore)
        normalized = re.sub(r'[^a-zA-Z0-9_]', '', normalized)
        
        # Step 7: Collapse multiple underscores
        normalized = re.sub(r'_+', '_', normalized)
        
        # Step 8: Strip leading/trailing underscores
        normalized = normalized.strip('_')
        
        # Step 9: Convert to lowercase (unless preserve_case is True)
        if not self.preserve_case:
            normalized = normalized.lower()
        
        # Step 10: Ensure doesn't start with a number
        if normalized and normalized[0].isdigit():
            normalized = f"col_{normalized}"
        
        # Step 11: Handle empty result
        if not normalized:
            normalized = f"col_{index}"
        
        # Step 12: Truncate if too long
        if len(normalized) > self.max_length:
            normalized = normalized[:self.max_length].rstrip('_')
        
        return normalized
    
    def normalize_columns(self, columns: List[str]) -> Tuple[List[str], Dict[str, str]]:
        """
        Normalize a list of column names, handling duplicates.
        
        Args:
            columns: List of raw column names
            
        Returns:
            Tuple of (normalized_columns, mapping_dict)
            - normalized_columns: List of normalized names
            - mapping_dict: {original_name: normalized_name}
        """
        normalized = []
        mapping = {}
        seen_names = {}  # Track counts for duplicate handling
        
        for i, col in enumerate(columns):
            # Normalize the column
            norm_col = self.normalize_column(col, i)
            
            # Handle duplicates by adding numeric suffix
            if norm_col in seen_names:
                seen_names[norm_col] += 1
                unique_col = f"{norm_col}_{seen_names[norm_col]}"
                # Ensure the suffixed version is also unique
                while unique_col in seen_names:
                    seen_names[norm_col] += 1
                    unique_col = f"{norm_col}_{seen_names[norm_col]}"
                norm_col = unique_col
            
            seen_names[norm_col] = 0
            normalized.append(norm_col)
            mapping[str(col) if col else f"col_{i}"] = norm_col
        
        return normalized, mapping
    
    def normalize_table_name(self, filename: str) -> str:
        """
        Normalize a filename to a SQL-safe table name.
        
        Args:
            filename: Original filename (e.g., "Patient Data (2024).xlsx")
            
        Returns:
            Normalized table name (e.g., "patient_data_2024")
        """
        import os
        
        # Remove extension
        name = os.path.splitext(filename)[0]
        
        # Apply same normalization as columns
        normalized = self.normalize_column(name, 0)
        
        # Ensure it's a valid table name (some additional restrictions)
        # Table names shouldn't be SQL reserved words
        reserved_words = {
            'select', 'from', 'where', 'table', 'index', 'view', 
            'create', 'drop', 'insert', 'update', 'delete', 'join',
            'order', 'group', 'having', 'limit', 'offset', 'union',
            'all', 'and', 'or', 'not', 'null', 'true', 'false',
        }
        
        if normalized in reserved_words:
            normalized = f"t_{normalized}"
        
        return normalized


# Global instance for convenience
_normalizer = SchemaNormalizer()


def normalize_column_name(col: str, index: int = 0) -> str:
    """Convenience function to normalize a single column name."""
    return _normalizer.normalize_column(col, index)


def normalize_column_names(columns: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Convenience function to normalize a list of column names."""
    return _normalizer.normalize_columns(columns)


def normalize_table_name(filename: str) -> str:
    """Convenience function to normalize a filename to table name."""
    return _normalizer.normalize_table_name(filename)


def log_normalization(original: List[str], normalized: List[str]) -> None:
    """Log the column normalization for debugging."""
    changes = []
    for orig, norm in zip(original, normalized):
        if str(orig) != norm:
            changes.append(f"  '{orig}' → '{norm}'")
    
    if changes:
        logger.info(f"Schema normalization applied ({len(changes)} columns changed):")
        for change in changes[:10]:  # Limit log output
            logger.info(change)
        if len(changes) > 10:
            logger.info(f"  ... and {len(changes) - 10} more")
    else:
        logger.info("Schema normalization: no changes needed")


# ---------------------------------------------------------------------------
# CSV Pre-Processor — Normalize headers BEFORE DuckDB reads the file
# ---------------------------------------------------------------------------

def preprocess_csv_headers(
    input_path: str,
    output_path: Optional[str] = None,
    store_mapping: bool = True,
) -> Dict[str, Any]:
    """
    Pre-process a CSV file to normalize all column headers.
    
    This function reads the CSV, normalizes headers, and writes a new CSV
    with clean headers that DuckDB can safely query.
    
    Args:
        input_path: Path to the original CSV file
        output_path: Path for the normalized CSV (default: overwrite input)
        store_mapping: Whether to save the original→normalized mapping
        
    Returns:
        Dict with:
        - original_columns: List of original column names
        - normalized_columns: List of normalized column names
        - mapping: Dict mapping original → normalized
        - mapping_file: Path to the JSON mapping file (if stored)
        - row_count: Number of data rows
    """
    input_path = Path(input_path)
    output_path = Path(output_path) if output_path else input_path
    
    # Read original headers
    with open(input_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        original_headers = next(reader)
    
    # Normalize headers
    normalized_headers, mapping = normalize_column_names(original_headers)
    
    # Log changes
    log_normalization(original_headers, normalized_headers)
    
    # Read entire file and rewrite with normalized headers
    rows = []
    with open(input_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Remap row keys to normalized names
            normalized_row = {
                mapping.get(k, k): v 
                for k, v in row.items()
            }
            rows.append(normalized_row)
    
    # Write normalized CSV
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=normalized_headers)
        writer.writeheader()
        writer.writerows(rows)
    
    result = {
        "original_columns": original_headers,
        "normalized_columns": normalized_headers,
        "mapping": mapping,
        "row_count": len(rows),
    }
    
    # Store mapping for LLM context
    if store_mapping:
        mapping_file = output_path.with_suffix('.schema_map.json')
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump({
                "original_to_normalized": mapping,
                "normalized_to_original": {v: k for k, v in mapping.items()},
                "columns": normalized_headers,
            }, f, indent=2)
        result["mapping_file"] = str(mapping_file)
        logger.info(f"Schema mapping saved to: {mapping_file}")
    
    return result


def preprocess_csv_headers_streaming(
    input_path: str,
    output_path: str,
    chunk_size: int = 10000,
) -> Dict[str, Any]:
    """
    Stream-process a large CSV file to normalize headers.
    
    For files with millions of rows, this avoids loading the entire
    file into memory.
    
    Args:
        input_path: Path to the original CSV file
        output_path: Path for the normalized CSV
        chunk_size: Number of rows to process at a time
        
    Returns:
        Dict with normalization results
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    # First pass: read only the header
    with open(input_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        original_headers = next(reader)
    
    # Normalize headers
    normalized_headers, mapping = normalize_column_names(original_headers)
    log_normalization(original_headers, normalized_headers)
    
    # Stream process the file
    row_count = 0
    with open(input_path, 'r', encoding='utf-8', newline='') as infile:
        reader = csv.DictReader(infile)
        
        with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=normalized_headers)
            writer.writeheader()
            
            for row in reader:
                # Remap keys
                normalized_row = {
                    mapping.get(k, k): v
                    for k, v in row.items()
                }
                writer.writerow(normalized_row)
                row_count += 1
                
                if row_count % chunk_size == 0:
                    logger.info(f"  Processed {row_count:,} rows...")
    
    # Store mapping
    mapping_file = output_path.with_suffix('.schema_map.json')
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump({
            "original_to_normalized": mapping,
            "normalized_to_original": {v: k for k, v in mapping.items()},
            "columns": normalized_headers,
        }, f, indent=2)
    
    logger.info(f"Streaming normalization complete: {row_count:,} rows")
    
    return {
        "original_columns": original_headers,
        "normalized_columns": normalized_headers,
        "mapping": mapping,
        "mapping_file": str(mapping_file),
        "row_count": row_count,
    }


# ---------------------------------------------------------------------------
# Schema Context for LLM — Generate readable column descriptions
# ---------------------------------------------------------------------------

def generate_llm_schema_context(
    normalized_columns: List[str],
    mapping: Dict[str, str],
    sample_values: Optional[Dict[str, List[Any]]] = None,
) -> str:
    """
    Generate a human-readable schema context for LLM prompts.
    
    This helps the LLM understand the relationship between user questions
    (which may use original column names) and the actual SQL columns.
    
    Args:
        normalized_columns: List of normalized column names
        mapping: Dict mapping original → normalized names
        sample_values: Optional dict of column → sample values
        
    Returns:
        Formatted string for inclusion in LLM system prompt
    """
    lines = ["Available columns (normalized for SQL):"]
    
    # Reverse mapping for display
    reverse_map = {v: k for k, v in mapping.items()}
    
    for col in normalized_columns:
        original = reverse_map.get(col, col)
        
        if original != col:
            line = f"  - {col} (originally: \"{original}\")"
        else:
            line = f"  - {col}"
        
        # Add sample values if available
        if sample_values and col in sample_values:
            samples = sample_values[col][:3]
            samples_str = ", ".join(repr(s) for s in samples if s is not None)
            if samples_str:
                line += f" [examples: {samples_str}]"
        
        lines.append(line)
    
    lines.append("")
    lines.append("Note: When users mention original column names, use the normalized versions in SQL.")
    
    return "\n".join(lines)


def load_schema_mapping(mapping_file: str) -> Dict[str, Any]:
    """
    Load a previously saved schema mapping from JSON.
    
    Args:
        mapping_file: Path to the .schema_map.json file
        
    Returns:
        Dict with original_to_normalized, normalized_to_original, columns
    """
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# DuckDB Integration — Normalize headers via DuckDB/Polars for speed
# ---------------------------------------------------------------------------

def normalize_csv_with_duckdb(
    input_path: str,
    output_path: str,
) -> Dict[str, Any]:
    """
    Use DuckDB to normalize CSV headers (fastest for large files).
    
    DuckDB reads the CSV, we rename columns, then export to new CSV.
    This is significantly faster than Python csv module for large files.
    
    Args:
        input_path: Path to the original CSV file
        output_path: Path for the normalized CSV
        
    Returns:
        Dict with normalization results
    """
    import duckdb
    
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    conn = duckdb.connect(":memory:")
    
    try:
        # Read CSV schema (headers only)
        schema_query = f"DESCRIBE SELECT * FROM read_csv_auto('{input_path}', header=true)"
        columns_info = conn.execute(schema_query).fetchall()
        original_headers = [col[0] for col in columns_info]
        
        # Normalize headers
        normalized_headers, mapping = normalize_column_names(original_headers)
        log_normalization(original_headers, normalized_headers)
        
        # Build column rename expressions
        rename_exprs = []
        for orig, norm in zip(original_headers, normalized_headers):
            # Quote original name to handle spaces/special chars
            quoted_orig = f'"{orig}"'
            rename_exprs.append(f'{quoted_orig} AS {norm}')
        
        select_clause = ", ".join(rename_exprs)
        
        # Export with renamed columns
        export_query = f"""
            COPY (
                SELECT {select_clause}
                FROM read_csv_auto('{input_path}', header=true)
            ) TO '{output_path}' (HEADER, DELIMITER ',')
        """
        conn.execute(export_query)
        
        # Get row count
        count_query = f"SELECT COUNT(*) FROM read_csv_auto('{input_path}', header=true)"
        row_count = conn.execute(count_query).fetchone()[0]
        
    finally:
        conn.close()
    
    # Store mapping
    mapping_file = output_path.with_suffix('.schema_map.json')
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump({
            "original_to_normalized": mapping,
            "normalized_to_original": {v: k for k, v in mapping.items()},
            "columns": normalized_headers,
        }, f, indent=2)
    
    logger.info(f"DuckDB normalization complete: {row_count:,} rows")
    
    return {
        "original_columns": original_headers,
        "normalized_columns": normalized_headers,
        "mapping": mapping,
        "mapping_file": str(mapping_file),
        "row_count": row_count,
    }
