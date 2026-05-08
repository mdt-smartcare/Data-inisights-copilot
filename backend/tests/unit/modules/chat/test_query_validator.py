"""
Tests for QueryValidator table extraction and validation logic.

Tests the fix for false positives where SQL functions using 'FROM' internally
(EXTRACT, SUBSTRING, etc.) were incorrectly flagged as referencing invalid tables.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.modules.chat.query.query_validator import QueryValidator, QueryValidationResult


class TestExtractTablesFromSql:
    """Tests for _extract_tables_from_sql method."""
    
    @pytest.fixture
    def validator(self):
        """Create a QueryValidator instance without database connection."""
        return QueryValidator(engine=None)
    
    def test_simple_select_from_table(self, validator):
        """Test basic SELECT FROM table extraction."""
        sql = "SELECT * FROM patients"
        tables = validator._extract_tables_from_sql(sql)
        assert "patients" in tables
        assert len(tables) == 1
    
    def test_select_with_alias(self, validator):
        """Test table extraction with table alias."""
        sql = "SELECT p.name FROM patients p WHERE p.active = true"
        tables = validator._extract_tables_from_sql(sql)
        assert "patients" in tables
        assert len(tables) == 1
    
    def test_join_tables(self, validator):
        """Test extraction of tables in JOIN clauses."""
        sql = """
            SELECT p.name, o.status 
            FROM patients p 
            LEFT JOIN observations o ON p.id = o.patient_id
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "patients" in tables
        assert "observations" in tables
        assert len(tables) == 2
    
    def test_multiple_joins(self, validator):
        """Test extraction with multiple JOIN clauses."""
        sql = """
            SELECT * FROM patients p
            INNER JOIN encounters e ON p.id = e.patient_id
            LEFT JOIN observations o ON e.id = o.encounter_id
            JOIN providers pr ON e.provider_id = pr.id
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "patients" in tables
        assert "encounters" in tables
        assert "observations" in tables
        assert "providers" in tables
        assert len(tables) == 4

    # ============================================
    # Tests for EXTRACT function (the main bug fix)
    # ============================================
    
    def test_extract_year_from_column_not_flagged_as_table(self, validator):
        """
        Test that EXTRACT(year FROM column) doesn't flag 'column' as a table.
        
        This was the original bug: query like 
        "SELECT EXTRACT(year FROM ymd) FROM bp_log_gold"
        incorrectly flagged 'ymd' as an invalid table.
        """
        sql = "SELECT EXTRACT(year FROM ymd) as year FROM bp_log_gold"
        tables = validator._extract_tables_from_sql(sql)
        assert "bp_log_gold" in tables
        assert "ymd" not in tables  # This was the bug - ymd was being flagged
        assert len(tables) == 1
    
    def test_extract_month_from_column(self, validator):
        """Test EXTRACT with MONTH unit."""
        sql = "SELECT EXTRACT(MONTH FROM created_at) FROM orders"
        tables = validator._extract_tables_from_sql(sql)
        assert "orders" in tables
        assert "created_at" not in tables
        assert len(tables) == 1
    
    def test_extract_day_from_column(self, validator):
        """Test EXTRACT with DAY unit."""
        sql = "SELECT EXTRACT(DAY FROM date_column) FROM events WHERE status = 'active'"
        tables = validator._extract_tables_from_sql(sql)
        assert "events" in tables
        assert "date_column" not in tables
        assert len(tables) == 1
    
    def test_extract_hour_minute_second(self, validator):
        """Test EXTRACT with time units."""
        sql = """
            SELECT 
                EXTRACT(HOUR FROM timestamp_col),
                EXTRACT(MINUTE FROM timestamp_col),
                EXTRACT(SECOND FROM timestamp_col)
            FROM logs
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "logs" in tables
        assert "timestamp_col" not in tables
        assert len(tables) == 1
    
    def test_extract_week_quarter_epoch(self, validator):
        """Test EXTRACT with other date/time units."""
        sql = """
            SELECT 
                EXTRACT(WEEK FROM date_col),
                EXTRACT(QUARTER FROM date_col),
                EXTRACT(EPOCH FROM timestamp_col)
            FROM financial_data
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "financial_data" in tables
        assert "date_col" not in tables
        assert "timestamp_col" not in tables
        assert len(tables) == 1
    
    def test_extract_dow_doy(self, validator):
        """Test EXTRACT with DOW (day of week) and DOY (day of year)."""
        sql = "SELECT EXTRACT(DOW FROM event_date), EXTRACT(DOY FROM event_date) FROM calendar"
        tables = validator._extract_tables_from_sql(sql)
        assert "calendar" in tables
        assert "event_date" not in tables
        assert len(tables) == 1
    
    def test_extract_with_table_alias_reference(self, validator):
        """Test EXTRACT when column is referenced with table alias."""
        sql = "SELECT EXTRACT(year FROM bp.ymd) FROM bp_log_gold bp"
        tables = validator._extract_tables_from_sql(sql)
        assert "bp_log_gold" in tables
        assert "bp" not in tables  # Alias used in EXTRACT
        assert "ymd" not in tables
        assert len(tables) == 1
    
    def test_multiple_extract_in_query(self, validator):
        """Test query with multiple EXTRACT calls."""
        sql = """
            SELECT 
                EXTRACT(year FROM bp_taken_on) as year,
                EXTRACT(month FROM bp_taken_on) as month,
                AVG(systolic) as avg_systolic
            FROM bp_log_gold
            GROUP BY EXTRACT(year FROM bp_taken_on), EXTRACT(month FROM bp_taken_on)
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "bp_log_gold" in tables
        assert "bp_taken_on" not in tables
        assert len(tables) == 1
    
    def test_extract_in_where_clause(self, validator):
        """Test EXTRACT used in WHERE clause."""
        sql = """
            SELECT * FROM observations
            WHERE EXTRACT(year FROM observation_date) = 2024
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "observations" in tables
        assert "observation_date" not in tables
        assert len(tables) == 1
    
    def test_extract_in_having_clause(self, validator):
        """Test EXTRACT used in HAVING clause."""
        sql = """
            SELECT patient_id, COUNT(*) 
            FROM visits
            GROUP BY patient_id, EXTRACT(year FROM visit_date)
            HAVING EXTRACT(year FROM visit_date) >= 2020
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "visits" in tables
        assert "visit_date" not in tables
        assert len(tables) == 1

    # ============================================
    # Tests for SUBSTRING function with FROM
    # ============================================
    
    def test_substring_from_not_flagged_as_table(self, validator):
        """Test that SUBSTRING(col FROM pos) doesn't flag 'col' as a table."""
        sql = "SELECT SUBSTRING(name FROM 1 FOR 5) FROM users"
        tables = validator._extract_tables_from_sql(sql)
        assert "users" in tables
        assert "name" not in tables
        assert len(tables) == 1
    
    def test_substring_from_without_for(self, validator):
        """Test SUBSTRING without FOR clause."""
        sql = "SELECT SUBSTRING(description FROM 10) FROM products"
        tables = validator._extract_tables_from_sql(sql)
        assert "products" in tables
        assert "description" not in tables
        assert len(tables) == 1

    # ============================================
    # Tests for OVERLAY function with FROM
    # ============================================
    
    def test_overlay_from_not_flagged_as_table(self, validator):
        """Test that OVERLAY(...FROM) doesn't flag parts as tables."""
        sql = "SELECT OVERLAY(text PLACING 'XXX' FROM 5) FROM documents"
        tables = validator._extract_tables_from_sql(sql)
        assert "documents" in tables
        assert "text" not in tables
        assert len(tables) == 1

    # ============================================
    # Tests for complex queries combining features
    # ============================================
    
    def test_complex_query_with_extract_and_joins(self, validator):
        """Test complex query with EXTRACT, JOINs, and subqueries."""
        sql = """
            SELECT 
                EXTRACT(year FROM bp.ymd) as year,
                EXTRACT(month FROM bp.ymd) as month,
                p.patient_id,
                AVG(bp.systolic) as avg_systolic
            FROM bp_log_gold bp
            INNER JOIN patient_tracker_gold p ON bp.patient_id = p.patient_id
            WHERE EXTRACT(year FROM bp.ymd) = 2024
            GROUP BY EXTRACT(year FROM bp.ymd), EXTRACT(month FROM bp.ymd), p.patient_id
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "bp_log_gold" in tables
        assert "patient_tracker_gold" in tables
        assert "bp" not in tables  # alias
        assert "ymd" not in tables  # EXTRACT column
        assert len(tables) == 2
    
    def test_subquery_with_extract(self, validator):
        """Test subquery containing EXTRACT."""
        sql = """
            SELECT * FROM (
                SELECT EXTRACT(year FROM created_at) as year, COUNT(*) 
                FROM events
                GROUP BY EXTRACT(year FROM created_at)
            ) subq
            WHERE year >= 2020
        """
        tables = validator._extract_tables_from_sql(sql)
        assert "events" in tables
        assert "created_at" not in tables
        # Note: 'subq' might be extracted as it follows FROM, but that's OK
    
    def test_case_insensitive_extract(self, validator):
        """Test that EXTRACT is handled case-insensitively."""
        sql = "SELECT extract(YEAR from date_col) FROM orders"
        tables = validator._extract_tables_from_sql(sql)
        assert "orders" in tables
        assert "date_col" not in tables
        assert len(tables) == 1
    
    def test_extract_with_extra_whitespace(self, validator):
        """Test EXTRACT with various whitespace patterns."""
        sql = "SELECT EXTRACT(  year   FROM   date_col  ) FROM orders"
        tables = validator._extract_tables_from_sql(sql)
        assert "orders" in tables
        assert "date_col" not in tables
        assert len(tables) == 1


class TestRemoveFunctionFromExpressions:
    """Tests for _remove_function_from_expressions helper method."""
    
    @pytest.fixture
    def validator(self):
        return QueryValidator(engine=None)
    
    def test_removes_extract_expression(self, validator):
        """Test that EXTRACT expressions are replaced with placeholders."""
        sql = "SELECT EXTRACT(year FROM date_col) FROM orders"
        result = validator._remove_function_from_expressions(sql)
        assert "EXTRACT" not in result.upper() or "__EXTRACT_PLACEHOLDER__" in result
        assert "FROM orders" in result.lower() or "from orders" in result.lower()
    
    def test_removes_substring_from_expression(self, validator):
        """Test that SUBSTRING...FROM expressions are replaced."""
        sql = "SELECT SUBSTRING(name FROM 1 FOR 5) FROM users"
        result = validator._remove_function_from_expressions(sql)
        assert "SUBSTRING" not in result.upper() or "__SUBSTRING_PLACEHOLDER__" in result
    
    def test_removes_overlay_expression(self, validator):
        """Test that OVERLAY expressions are replaced."""
        sql = "SELECT OVERLAY(text PLACING 'x' FROM 1) FROM docs"
        result = validator._remove_function_from_expressions(sql)
        assert "OVERLAY" not in result.upper() or "__OVERLAY_PLACEHOLDER__" in result
    
    def test_preserves_regular_from_clause(self, validator):
        """Test that regular FROM clauses are preserved."""
        sql = "SELECT * FROM patients WHERE active = true"
        result = validator._remove_function_from_expressions(sql)
        assert "FROM patients" in result


class TestValidateSqlWithExtract:
    """Integration tests for validate_sql with EXTRACT queries."""
    
    @pytest.fixture
    def validator_with_schema(self):
        """Create validator with mock schema."""
        validator = QueryValidator(engine=None)
        # Manually set up schema without database
        validator._tables = {"bp_log_gold", "patient_tracker_gold", "observations"}
        validator._table_columns = {
            "bp_log_gold": {"patient_id", "systolic", "diastolic", "ymd", "bp_taken_on"},
            "patient_tracker_gold": {"patient_id", "name", "dob"},
            "observations": {"id", "patient_id", "observation_date", "value"},
        }
        validator._schema_loaded = True
        return validator
    
    def test_extract_query_validates_successfully(self, validator_with_schema):
        """Test that EXTRACT query passes validation."""
        sql = "SELECT EXTRACT(year FROM ymd) as year FROM bp_log_gold"
        result = validator_with_schema.validate_sql(sql)
        assert result.is_valid, f"Expected valid but got: {result.error_message}"
        assert len(result.invalid_tables) == 0
    
    def test_extract_with_valid_table_and_joins(self, validator_with_schema):
        """Test EXTRACT query with JOINs validates successfully."""
        sql = """
            SELECT 
                EXTRACT(year FROM bp.ymd) as year,
                COUNT(DISTINCT bp.patient_id) as patient_count
            FROM bp_log_gold bp
            JOIN patient_tracker_gold pt ON bp.patient_id = pt.patient_id
            GROUP BY EXTRACT(year FROM bp.ymd)
        """
        result = validator_with_schema.validate_sql(sql)
        assert result.is_valid, f"Expected valid but got: {result.error_message}"
    
    def test_invalid_table_still_detected(self, validator_with_schema):
        """Test that invalid tables are still detected correctly."""
        sql = "SELECT EXTRACT(year FROM date_col) FROM nonexistent_table"
        result = validator_with_schema.validate_sql(sql)
        assert not result.is_valid
        assert "nonexistent_table" in result.invalid_tables
    
    def test_extract_column_not_flagged_as_invalid_table(self, validator_with_schema):
        """Test the specific bug case: column name not flagged as invalid table."""
        # This was the exact failing case
        sql = "SELECT EXTRACT(year FROM ymd) as year FROM bp_log_gold GROUP BY 1"
        result = validator_with_schema.validate_sql(sql)
        assert result.is_valid, f"Expected valid but got: {result.error_message}"
        assert "ymd" not in result.invalid_tables
        assert len(result.invalid_tables) == 0
