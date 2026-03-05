"""
Unit tests for Schema Normalizer.

Tests the automated column name sanitization to ensure SQL-safe identifiers.
"""

import pytest
import tempfile
import csv
import json
from pathlib import Path

from backend.pipeline.ingestion.schema_normalizer import (
    SchemaNormalizer,
    normalize_column_name,
    normalize_column_names,
    normalize_table_name,
    preprocess_csv_headers,
    generate_llm_schema_context,
)


class TestSchemaNormalizer:
    """Test the SchemaNormalizer class."""
    
    def test_basic_normalization(self):
        """Test basic column name normalization."""
        normalizer = SchemaNormalizer()
        
        # Spaces to underscores, lowercase
        assert normalizer.normalize_column("Patient Name") == "patient_name"
        assert normalizer.normalize_column("First Name") == "first_name"
        
    def test_trailing_whitespace(self):
        """Test stripping of leading/trailing whitespace."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("Patient_ID ") == "patient_id"
        assert normalizer.normalize_column("  name  ") == "name"
        
    def test_parentheses_to_suffix(self):
        """Test conversion of parentheses content to suffix."""
        normalizer = SchemaNormalizer()
        
        # Medical examples
        assert normalizer.normalize_column("Blood Pressure (Sys)") == "blood_pressure_sys"
        assert normalizer.normalize_column("Blood Pressure (Dia)") == "blood_pressure_dia"
        assert normalizer.normalize_column("Height (cm)") == "height_cm"
        assert normalizer.normalize_column("Weight (kg)") == "weight_kg"
        assert normalizer.normalize_column("Temperature (F)") == "temperature_f"
        
    def test_special_characters_removed(self):
        """Test removal of special characters."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("notes...") == "notes"
        assert normalizer.normalize_column("email@address") == "emailaddress"
        assert normalizer.normalize_column("cost$") == "cost"
        assert normalizer.normalize_column("rate%") == "rate"
        assert normalizer.normalize_column("name#1") == "name1"
        
    def test_numeric_prefix_handling(self):
        """Test that columns starting with numbers get prefixed."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("123_invalid") == "col_123_invalid"
        assert normalizer.normalize_column("1st_place") == "col_1st_place"
        assert normalizer.normalize_column("2024_data") == "col_2024_data"
        
    def test_empty_and_none_handling(self):
        """Test handling of empty and None values."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("", 0) == "col_0"
        assert normalizer.normalize_column("   ", 5) == "col_5"
        assert normalizer.normalize_column(None, 3) == "col_3"
        
    def test_unicode_normalization(self):
        """Test Unicode character handling."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("café") == "cafe"
        assert normalizer.normalize_column("naïve") == "naive"
        assert normalizer.normalize_column("señor") == "senor"
        assert normalizer.normalize_column("über") == "uber"
        
    def test_multiple_separators(self):
        """Test handling of multiple separator types."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("first-name") == "first_name"
        assert normalizer.normalize_column("last.name") == "last_name"
        assert normalizer.normalize_column("middle/name") == "middle_name"
        assert normalizer.normalize_column("other\\name") == "other_name"
        assert normalizer.normalize_column("a - b - c") == "a_b_c"
        
    def test_underscore_collapse(self):
        """Test collapsing of multiple underscores."""
        normalizer = SchemaNormalizer()
        
        assert normalizer.normalize_column("first__name") == "first_name"
        assert normalizer.normalize_column("a___b___c") == "a_b_c"
        assert normalizer.normalize_column("_leading_") == "leading"
        
    def test_max_length_truncation(self):
        """Test truncation of overly long names."""
        normalizer = SchemaNormalizer(max_length=20)
        
        long_name = "this_is_a_very_long_column_name_that_exceeds_the_limit"
        result = normalizer.normalize_column(long_name)
        assert len(result) <= 20
        assert result == "this_is_a_very_long"
        
    def test_preserve_case_option(self):
        """Test the preserve_case option."""
        normalizer = SchemaNormalizer(preserve_case=True)
        
        assert normalizer.normalize_column("PatientName") == "PatientName"
        assert normalizer.normalize_column("UPPERCASE") == "UPPERCASE"


class TestNormalizeColumns:
    """Test bulk column normalization with duplicate handling."""
    
    def test_duplicate_handling(self):
        """Test that duplicates get numeric suffixes."""
        columns = ["Name", "name", "NAME"]
        normalized, mapping = normalize_column_names(columns)
        
        assert normalized[0] == "name"
        assert normalized[1] == "name_1"
        assert normalized[2] == "name_2"
        
    def test_mapping_returned(self):
        """Test that original→normalized mapping is returned."""
        columns = ["Patient ID", "Blood Pressure (Sys)"]
        normalized, mapping = normalize_column_names(columns)
        
        assert mapping["Patient ID"] == "patient_id"
        assert mapping["Blood Pressure (Sys)"] == "blood_pressure_sys"
        
    def test_full_example(self):
        """Test the full example from the docstring."""
        columns = ["Blood Pressure (Sys)", "Patient_ID ", "notes...", "123_invalid"]
        normalized, mapping = normalize_column_names(columns)
        
        assert normalized == ["blood_pressure_sys", "patient_id", "notes", "col_123_invalid"]


class TestNormalizeTableName:
    """Test table name normalization."""
    
    def test_basic_table_name(self):
        """Test basic filename to table name conversion."""
        assert normalize_table_name("patients.csv") == "patients"
        assert normalize_table_name("Patient Data.xlsx") == "patient_data"
        
    def test_special_chars_in_filename(self):
        """Test handling of special characters in filenames."""
        assert normalize_table_name("Patient Data (2024).xlsx") == "patient_data_2024"
        assert normalize_table_name("lab-results-v2.csv") == "lab_results_v2"
        
    def test_reserved_word_handling(self):
        """Test that SQL reserved words get prefixed."""
        assert normalize_table_name("select.csv") == "t_select"
        assert normalize_table_name("table.xlsx") == "t_table"
        assert normalize_table_name("index.csv") == "t_index"


class TestPreprocessCSV:
    """Test CSV file preprocessing."""
    
    def test_preprocess_csv_headers(self):
        """Test full CSV preprocessing workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test CSV with messy headers
            input_path = Path(tmpdir) / "test_input.csv"
            output_path = Path(tmpdir) / "test_output.csv"
            
            with open(input_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Patient ID ", "Blood Pressure (Sys)", "notes..."])
                writer.writerow(["P001", "120", "Normal reading"])
                writer.writerow(["P002", "140", "Elevated"])
            
            # Process the CSV
            result = preprocess_csv_headers(str(input_path), str(output_path))
            
            # Verify results
            assert result["original_columns"] == ["Patient ID ", "Blood Pressure (Sys)", "notes..."]
            assert result["normalized_columns"] == ["patient_id", "blood_pressure_sys", "notes"]
            assert result["row_count"] == 2
            
            # Verify output file has correct headers
            with open(output_path, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader)
                assert headers == ["patient_id", "blood_pressure_sys", "notes"]
                
            # Verify mapping file was created
            mapping_file = output_path.with_suffix('.schema_map.json')
            assert mapping_file.exists()
            
            with open(mapping_file, 'r') as f:
                mapping_data = json.load(f)
                assert "original_to_normalized" in mapping_data
                assert "normalized_to_original" in mapping_data


class TestLLMSchemaContext:
    """Test LLM schema context generation."""
    
    def test_generate_context(self):
        """Test generation of LLM-friendly schema context."""
        normalized = ["patient_id", "blood_pressure_sys", "notes"]
        mapping = {
            "Patient ID": "patient_id",
            "Blood Pressure (Sys)": "blood_pressure_sys",
            "notes": "notes",
        }
        
        context = generate_llm_schema_context(normalized, mapping)
        
        assert "patient_id" in context
        assert "blood_pressure_sys" in context
        assert 'originally: "Blood Pressure (Sys)"' in context
        assert "normalized for sql" in context.lower()
        
    def test_context_with_sample_values(self):
        """Test context generation with sample values."""
        normalized = ["patient_id", "status"]
        mapping = {"patient_id": "patient_id", "status": "status"}
        samples = {
            "patient_id": ["P001", "P002", "P003"],
            "status": ["active", "inactive"],
        }
        
        context = generate_llm_schema_context(normalized, mapping, samples)
        
        assert "P001" in context
        assert "active" in context


# Run with: pytest backend/tests/test_schema_normalizer.py -v
