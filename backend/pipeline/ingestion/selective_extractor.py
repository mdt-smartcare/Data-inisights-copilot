"""
Selective Column Extractor — Identifies and extracts only unstructured text columns for RAG.

For 6.5M row datasets, NEVER embed structured columns (Age, Patient_ID, Blood_Pressure).
RAG should only process unstructured, free-text columns (doctor_notes, clinical_history).

Architecture:
1. Column Classification: Automatically detect structured vs unstructured columns
2. Selective Extraction: Only yield text columns for embedding pipeline
3. Schema Awareness: Integrate with DuckDB schema for accurate type detection
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ColumnType(Enum):
    """Classification of column types for RAG extraction."""
    STRUCTURED_NUMERIC = "structured_numeric"      # age, blood_pressure, bmi
    STRUCTURED_ID = "structured_id"                # patient_id, record_id
    STRUCTURED_CATEGORICAL = "structured_categorical"  # gender, status, type
    STRUCTURED_DATE = "structured_date"            # dob, encounter_date
    STRUCTURED_BOOLEAN = "structured_boolean"      # is_active, has_diabetes
    UNSTRUCTURED_TEXT = "unstructured_text"        # notes, history, description
    UNKNOWN = "unknown"


@dataclass
class ColumnClassification:
    """Result of column classification."""
    name: str
    column_type: ColumnType
    avg_length: float = 0.0
    unique_ratio: float = 0.0
    sample_values: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""


@dataclass 
class ExtractionConfig:
    """Configuration for selective column extraction."""
    # Columns explicitly marked for RAG (override auto-detection)
    include_columns: Set[str] = field(default_factory=set)
    # Columns explicitly excluded from RAG
    exclude_columns: Set[str] = field(default_factory=set)
    # Minimum average text length to consider as unstructured
    min_text_length: int = 50
    # Maximum unique ratio for categorical (low = categorical, high = free text)
    categorical_unique_threshold: float = 0.1
    # Patterns indicating structured ID columns
    id_patterns: List[str] = field(default_factory=lambda: [
        r'.*_id$', r'^id$', r'.*_code$', r'.*_number$', r'^mrn$', r'^ssn$', r'^npi$'
    ])
    # Patterns indicating unstructured text columns
    text_patterns: List[str] = field(default_factory=lambda: [
        r'.*_notes?$', r'.*_history$', r'.*_description$', r'.*_comments?$',
        r'.*_narrative$', r'.*_summary$', r'.*_text$', r'.*_remarks?$',
        r'^notes?$', r'^comments?$', r'^description$', r'^summary$',
        r'clinical_.*', r'doctor_.*', r'physician_.*', r'nurse_.*',
        r'assessment.*', r'diagnosis_text.*', r'treatment_plan.*',
        r'chief_complaint.*', r'hpi$', r'history_of_present_illness',
        r'review_of_systems', r'physical_exam.*', r'impression.*',
        r'plan_of_care.*', r'discharge_.*', r'progress_.*'
    ])
    # Patterns indicating date columns
    date_patterns: List[str] = field(default_factory=lambda: [
        r'.*_date$', r'.*_time$', r'.*_at$', r'^date$', r'^dob$',
        r'created_.*', r'updated_.*', r'modified_.*', r'^timestamp$'
    ])
    # Patterns indicating boolean columns
    boolean_patterns: List[str] = field(default_factory=lambda: [
        r'^is_.*', r'^has_.*', r'^was_.*', r'^can_.*', r'^should_.*',
        r'.*_flag$', r'.*_indicator$', r'^active$', r'^enabled$', r'^deleted$'
    ])


class SelectiveColumnExtractor:
    """
    Extracts only unstructured text columns from datasets for RAG embedding.
    
    For a 6.5M row clinical dataset:
    - Structured columns (age, bp, gender) → Text-to-SQL only
    - Unstructured columns (doctor_notes, clinical_history) → RAG embedding
    
    This dramatically reduces embedding costs and improves retrieval quality.
    """
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        self.config = config or ExtractionConfig()
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._compiled_patterns = {
            'id': [re.compile(p, re.IGNORECASE) for p in self.config.id_patterns],
            'text': [re.compile(p, re.IGNORECASE) for p in self.config.text_patterns],
            'date': [re.compile(p, re.IGNORECASE) for p in self.config.date_patterns],
            'boolean': [re.compile(p, re.IGNORECASE) for p in self.config.boolean_patterns],
        }
    
    def _matches_pattern(self, column_name: str, pattern_type: str) -> bool:
        """Check if column name matches any pattern of given type."""
        patterns = self._compiled_patterns.get(pattern_type, [])
        return any(p.match(column_name) for p in patterns)
    
    def _analyze_column_values(
        self, 
        column_name: str, 
        values: List[Any],
        duckdb_type: Optional[str] = None
    ) -> ColumnClassification:
        """
        Analyze column values to determine if structured or unstructured.
        
        Args:
            column_name: Name of the column
            values: Sample values from the column
            duckdb_type: DuckDB data type if available
            
        Returns:
            ColumnClassification with type and confidence
        """
        # Filter out None/empty values
        non_null_values = [v for v in values if v is not None and str(v).strip()]
        
        if not non_null_values:
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.UNKNOWN,
                confidence=0.0,
                reason="No non-null values"
            )
        
        # Calculate statistics
        str_values = [str(v) for v in non_null_values]
        avg_length = sum(len(v) for v in str_values) / len(str_values)
        unique_values = set(str_values)
        unique_ratio = len(unique_values) / len(str_values) if str_values else 0
        
        # Sample values for inspection
        sample_values = list(unique_values)[:5]
        
        # Priority 1: Check explicit include/exclude
        if column_name in self.config.include_columns:
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.UNSTRUCTURED_TEXT,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=1.0,
                reason="Explicitly included in config"
            )
        
        if column_name in self.config.exclude_columns:
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.STRUCTURED_CATEGORICAL,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=1.0,
                reason="Explicitly excluded in config"
            )
        
        # Priority 2: Check DuckDB type
        if duckdb_type:
            type_lower = duckdb_type.lower()
            if any(t in type_lower for t in ['int', 'float', 'double', 'decimal', 'numeric']):
                return ColumnClassification(
                    name=column_name,
                    column_type=ColumnType.STRUCTURED_NUMERIC,
                    avg_length=avg_length,
                    unique_ratio=unique_ratio,
                    sample_values=sample_values,
                    confidence=0.95,
                    reason=f"DuckDB type is numeric: {duckdb_type}"
                )
            if any(t in type_lower for t in ['date', 'time', 'timestamp']):
                return ColumnClassification(
                    name=column_name,
                    column_type=ColumnType.STRUCTURED_DATE,
                    avg_length=avg_length,
                    unique_ratio=unique_ratio,
                    sample_values=sample_values,
                    confidence=0.95,
                    reason=f"DuckDB type is temporal: {duckdb_type}"
                )
            if 'bool' in type_lower:
                return ColumnClassification(
                    name=column_name,
                    column_type=ColumnType.STRUCTURED_BOOLEAN,
                    avg_length=avg_length,
                    unique_ratio=unique_ratio,
                    sample_values=sample_values,
                    confidence=0.95,
                    reason=f"DuckDB type is boolean: {duckdb_type}"
                )
        
        # Priority 3: Pattern matching on column name
        if self._matches_pattern(column_name, 'id'):
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.STRUCTURED_ID,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.9,
                reason="Column name matches ID pattern"
            )
        
        if self._matches_pattern(column_name, 'text'):
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.UNSTRUCTURED_TEXT,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.9,
                reason="Column name matches text pattern"
            )
        
        if self._matches_pattern(column_name, 'date'):
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.STRUCTURED_DATE,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.85,
                reason="Column name matches date pattern"
            )
        
        if self._matches_pattern(column_name, 'boolean'):
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.STRUCTURED_BOOLEAN,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.85,
                reason="Column name matches boolean pattern"
            )
        
        # Priority 4: Statistical analysis
        # Check if values are numeric
        try:
            numeric_count = sum(1 for v in str_values if self._is_numeric(v))
            if numeric_count / len(str_values) > 0.9:
                return ColumnClassification(
                    name=column_name,
                    column_type=ColumnType.STRUCTURED_NUMERIC,
                    avg_length=avg_length,
                    unique_ratio=unique_ratio,
                    sample_values=sample_values,
                    confidence=0.8,
                    reason=f"{numeric_count}/{len(str_values)} values are numeric"
                )
        except Exception:
            pass
        
        # Check for categorical (low unique ratio, short values)
        if unique_ratio < self.config.categorical_unique_threshold and avg_length < 30:
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.STRUCTURED_CATEGORICAL,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.75,
                reason=f"Low unique ratio ({unique_ratio:.2%}) suggests categorical"
            )
        
        # Check for free text (high unique ratio, long values)
        if avg_length >= self.config.min_text_length and unique_ratio > 0.5:
            return ColumnClassification(
                name=column_name,
                column_type=ColumnType.UNSTRUCTURED_TEXT,
                avg_length=avg_length,
                unique_ratio=unique_ratio,
                sample_values=sample_values,
                confidence=0.7,
                reason=f"High avg length ({avg_length:.0f}) and unique ratio ({unique_ratio:.2%}) suggests free text"
            )
        
        # Default: treat as structured categorical (safer default)
        return ColumnClassification(
            name=column_name,
            column_type=ColumnType.STRUCTURED_CATEGORICAL,
            avg_length=avg_length,
            unique_ratio=unique_ratio,
            sample_values=sample_values,
            confidence=0.5,
            reason="Default classification - no strong indicators"
        )
    
    def _is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric."""
        try:
            float(value.replace(',', ''))
            return True
        except (ValueError, AttributeError):
            return False
    
    def classify_columns(
        self, 
        column_names: List[str],
        sample_data: Dict[str, List[Any]],
        duckdb_types: Optional[Dict[str, str]] = None
    ) -> Dict[str, ColumnClassification]:
        """
        Classify all columns in a dataset.
        
        Args:
            column_names: List of column names
            sample_data: Dict mapping column name to sample values
            duckdb_types: Optional dict of DuckDB types per column
            
        Returns:
            Dict mapping column name to classification
        """
        classifications = {}
        
        for col in column_names:
            values = sample_data.get(col, [])
            duckdb_type = duckdb_types.get(col) if duckdb_types else None
            
            classification = self._analyze_column_values(col, values, duckdb_type)
            classifications[col] = classification
            
            logger.debug(
                f"Column '{col}': {classification.column_type.value} "
                f"(confidence: {classification.confidence:.0%}, reason: {classification.reason})"
            )
        
        return classifications
    
    def get_text_columns(
        self,
        column_names: List[str],
        sample_data: Dict[str, List[Any]],
        duckdb_types: Optional[Dict[str, str]] = None,
        min_confidence: float = 0.6
    ) -> List[str]:
        """
        Get only the unstructured text columns suitable for RAG embedding.
        
        Args:
            column_names: List of all column names
            sample_data: Sample data for analysis
            duckdb_types: Optional DuckDB types
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of column names to embed for RAG
        """
        classifications = self.classify_columns(column_names, sample_data, duckdb_types)
        
        text_columns = [
            col for col, cls in classifications.items()
            if cls.column_type == ColumnType.UNSTRUCTURED_TEXT
            and cls.confidence >= min_confidence
        ]
        
        logger.info(
            f"Selective extraction: {len(text_columns)}/{len(column_names)} columns "
            f"identified as unstructured text for RAG"
        )
        
        for col in text_columns:
            cls = classifications[col]
            logger.info(f"  → {col}: {cls.reason}")
        
        return text_columns
    
    def get_extraction_summary(
        self,
        classifications: Dict[str, ColumnClassification]
    ) -> Dict[str, Any]:
        """
        Generate a summary of column classifications for UI display.
        
        Returns:
            Summary dict with counts and details per type
        """
        summary = {
            "total_columns": len(classifications),
            "by_type": {},
            "text_columns": [],
            "structured_columns": [],
        }
        
        for col, cls in classifications.items():
            type_name = cls.column_type.value
            if type_name not in summary["by_type"]:
                summary["by_type"][type_name] = []
            
            summary["by_type"][type_name].append({
                "name": col,
                "confidence": cls.confidence,
                "reason": cls.reason,
                "avg_length": cls.avg_length,
                "sample_values": cls.sample_values[:3],
            })
            
            if cls.column_type == ColumnType.UNSTRUCTURED_TEXT:
                summary["text_columns"].append(col)
            else:
                summary["structured_columns"].append(col)
        
        return summary


# Convenience function
def get_selective_extractor(config: Optional[ExtractionConfig] = None) -> SelectiveColumnExtractor:
    """Get a SelectiveColumnExtractor instance."""
    return SelectiveColumnExtractor(config)
