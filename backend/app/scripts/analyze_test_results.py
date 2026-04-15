"""
Test Results Analyzer - Analyze NL2SQL test failures and suggest training improvements.

This script analyzes test results to identify failure patterns and generates
suggestions for training examples to improve the model's accuracy.

Run with:
    python -m app.scripts.analyze_test_results --input results.json --output analysis.md
    python -m app.scripts.analyze_test_results --input results.json --export-suggestions suggestions.json

Features:
    - Pattern-based failure categorization
    - SQL anti-pattern detection
    - Training example suggestions
    - Priority-ranked improvement recommendations
"""
import argparse
import json
import re
import sys
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from enum import Enum

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.utils.logging import get_logger, configure_logging

logger = get_logger(__name__)


# ============================================
# Failure Pattern Definitions
# ============================================

FAILURE_PATTERNS: Dict[str, Dict[str, Any]] = {
    "window_in_where": {
        "name": "Window Function in WHERE",
        "regex": r"WHERE[^;]*\b(LAG|LEAD|ROW_NUMBER|RANK|DENSE_RANK|NTILE|FIRST_VALUE|LAST_VALUE|NTH_VALUE)\s*\(",
        "error_keywords": ["window function", "WHERE clause cannot contain", "window functions are not allowed"],
        "description": "Window functions cannot be used directly in WHERE clauses",
        "fix": "Use CTE pattern: WITH ranked AS (SELECT *, ROW_NUMBER() OVER (...) as rn FROM table) SELECT * FROM ranked WHERE rn = 1",
        "example_question": "Show the first record for each patient",
        "example_sql": """WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY created_at) as rn
    FROM records
)
SELECT * FROM ranked WHERE rn = 1""",
        "priority_weight": 3,
        "tags": ["window", "cte", "duckdb"]
    },
    
    "aggregate_in_where": {
        "name": "Aggregate Function in WHERE",
        "regex": r"WHERE[^;]*\b(AVG|SUM|COUNT|STDDEV|VARIANCE|MIN|MAX)\s*\(",
        "error_keywords": ["aggregate", "WHERE clause cannot contain", "aggregate functions are not allowed in WHERE"],
        "description": "Aggregate functions cannot be used directly in WHERE clauses",
        "fix": "Use subquery or CTE with HAVING clause for aggregate filtering",
        "example_question": "Find patients with above average visits",
        "example_sql": """SELECT patient_id, COUNT(*) as visit_count
FROM visits
GROUP BY patient_id
HAVING COUNT(*) > (SELECT AVG(cnt) FROM (SELECT COUNT(*) as cnt FROM visits GROUP BY patient_id))""",
        "priority_weight": 3,
        "tags": ["aggregate", "subquery", "having"]
    },
    
    "datediff_two_args": {
        "name": "DATEDIFF with 2 Arguments",
        "regex": r"DATEDIFF\s*\(\s*[^,]+\s*,\s*[^,)]+\s*\)",
        "error_keywords": ["DATEDIFF", "argument", "expected 3 arguments", "wrong number of arguments"],
        "description": "DuckDB DATEDIFF requires 3 arguments: DATEDIFF(part, start, end)",
        "fix": "Use 3-argument syntax: DATEDIFF('day', start_date, end_date)",
        "example_question": "Calculate days between admission and discharge",
        "example_sql": "SELECT DATEDIFF('day', admission_date, discharge_date) as days_stayed FROM admissions",
        "priority_weight": 2,
        "tags": ["date", "duckdb", "syntax"]
    },
    
    "date_sub_function": {
        "name": "DATE_SUB Function (Not Supported)",
        "regex": r"DATE_SUB\s*\(",
        "error_keywords": ["DATE_SUB", "does not exist", "function date_sub", "unknown function"],
        "description": "DATE_SUB is not supported in DuckDB",
        "fix": "Use interval arithmetic: date_column - INTERVAL '90 days'",
        "example_question": "Find records from the last 90 days",
        "example_sql": "SELECT * FROM records WHERE created_at >= CURRENT_DATE - INTERVAL '90 days'",
        "priority_weight": 2,
        "tags": ["date", "duckdb", "syntax"]
    },
    
    "dateadd_function": {
        "name": "DATEADD Function (Wrong Syntax)",
        "regex": r"DATEADD\s*\([^)]*\)",
        "error_keywords": ["DATEADD", "does not exist", "function dateadd"],
        "description": "DATEADD may have different syntax in DuckDB",
        "fix": "Use interval arithmetic: date_column + INTERVAL '30 days'",
        "example_question": "Calculate date 30 days from now",
        "example_sql": "SELECT CURRENT_DATE + INTERVAL '30 days' as future_date",
        "priority_weight": 2,
        "tags": ["date", "duckdb", "syntax"]
    },
    
    "month_function": {
        "name": "MONTH() Function",
        "regex": r"\bMONTH\s*\([^)]+\)",
        "error_keywords": ["MONTH", "does not exist", "function month"],
        "description": "Use DATE_TRUNC or EXTRACT instead of MONTH()",
        "fix": "Use EXTRACT(MONTH FROM date_col) or DATE_TRUNC('month', date_col)",
        "example_question": "Group records by month",
        "example_sql": "SELECT DATE_TRUNC('month', created_at) as month, COUNT(*) FROM records GROUP BY 1",
        "priority_weight": 1,
        "tags": ["date", "duckdb", "syntax"]
    },
    
    "year_function": {
        "name": "YEAR() Function",
        "regex": r"\bYEAR\s*\([^)]+\)",
        "error_keywords": ["YEAR", "does not exist", "function year"],
        "description": "Use DATE_TRUNC or EXTRACT instead of YEAR()",
        "fix": "Use EXTRACT(YEAR FROM date_col) or DATE_TRUNC('year', date_col)",
        "example_question": "Group records by year",
        "example_sql": "SELECT EXTRACT(YEAR FROM created_at) as year, COUNT(*) FROM records GROUP BY 1",
        "priority_weight": 1,
        "tags": ["date", "duckdb", "syntax"]
    },
    
    "undefined_column": {
        "name": "Undefined Column Reference",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["column", "not found", "does not exist", "unknown column", "no such column"],
        "description": "Referenced column does not exist in the table",
        "fix": "Verify column names match the schema exactly (case-sensitive in some databases)",
        "example_question": "N/A - Schema-specific issue",
        "example_sql": "-- Check schema: SELECT column_name FROM information_schema.columns WHERE table_name = 'your_table'",
        "priority_weight": 2,
        "tags": ["schema", "column"]
    },
    
    "undefined_table": {
        "name": "Undefined Table Reference",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["table", "not found", "does not exist", "unknown table", "no such table", "relation"],
        "description": "Referenced table does not exist in the database",
        "fix": "Verify table names match the schema exactly",
        "example_question": "N/A - Schema-specific issue",
        "example_sql": "-- Check tables: SELECT table_name FROM information_schema.tables",
        "priority_weight": 2,
        "tags": ["schema", "table"]
    },
    
    "undefined_alias": {
        "name": "Undefined Table Alias",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["alias", "not found", "undefined", "missing FROM-clause entry"],
        "description": "Table alias used without being defined in FROM/JOIN",
        "fix": "Ensure all table aliases are defined in FROM or JOIN clauses",
        "example_question": "Join patients with their visits",
        "example_sql": "SELECT p.name, v.visit_date FROM patients p JOIN visits v ON p.id = v.patient_id",
        "priority_weight": 2,
        "tags": ["alias", "join"]
    },
    
    "column_not_in_groupby": {
        "name": "Column Not in GROUP BY",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["must appear in the GROUP BY", "not in GROUP BY", "not contained in GROUP BY", "unaggregated column"],
        "description": "Selected column not included in GROUP BY and not aggregated",
        "fix": "Add column to GROUP BY or wrap in aggregate function (MAX, MIN, ANY_VALUE)",
        "example_question": "Get latest visit per patient with details",
        "example_sql": """SELECT patient_id, MAX(visit_date) as last_visit, 
       MAX(diagnosis) as diagnosis  -- or use ANY_VALUE if available
FROM visits GROUP BY patient_id""",
        "priority_weight": 2,
        "tags": ["groupby", "aggregate"]
    },
    
    "ambiguous_column": {
        "name": "Ambiguous Column Reference",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["ambiguous", "ambiguously"],
        "description": "Column name exists in multiple tables without table qualifier",
        "fix": "Prefix column with table name or alias: table.column",
        "example_question": "Join tables with same column names",
        "example_sql": "SELECT p.id, p.name, v.id as visit_id FROM patients p JOIN visits v ON p.id = v.patient_id",
        "priority_weight": 1,
        "tags": ["join", "alias"]
    },
    
    "syntax_error": {
        "name": "General Syntax Error",
        "regex": r"",  # Detected via error keywords
        "error_keywords": ["syntax error", "parse error", "unexpected token", "expected"],
        "description": "SQL syntax error",
        "fix": "Review SQL syntax for missing keywords, commas, or parentheses",
        "example_question": "N/A - Generic syntax issue",
        "example_sql": "-- Common fixes: check parentheses balance, comma placement, keyword spelling",
        "priority_weight": 1,
        "tags": ["syntax"]
    },
    
    "division_by_zero": {
        "name": "Division by Zero",
        "regex": r"/\s*0\b|/\s*\(\s*SELECT.*COUNT.*=\s*0",
        "error_keywords": ["division by zero", "divide by zero"],
        "description": "Potential division by zero in calculation",
        "fix": "Use NULLIF to prevent division by zero: value / NULLIF(divisor, 0)",
        "example_question": "Calculate percentage safely",
        "example_sql": "SELECT numerator * 100.0 / NULLIF(denominator, 0) as percentage FROM data",
        "priority_weight": 1,
        "tags": ["arithmetic", "null"]
    },
    
    "string_aggregation": {
        "name": "String Aggregation Syntax",
        "regex": r"GROUP_CONCAT|STRING_AGG\s*\([^,]+\)",
        "error_keywords": ["GROUP_CONCAT", "STRING_AGG", "does not exist"],
        "description": "String aggregation function syntax varies by database",
        "fix": "DuckDB uses STRING_AGG(column, delimiter) or LIST_AGG",
        "example_question": "Concatenate diagnosis codes per patient",
        "example_sql": "SELECT patient_id, STRING_AGG(diagnosis_code, ', ') as diagnoses FROM conditions GROUP BY patient_id",
        "priority_weight": 1,
        "tags": ["aggregate", "string", "duckdb"]
    },
    
    "limit_offset_syntax": {
        "name": "LIMIT/OFFSET Syntax",
        "regex": r"LIMIT\s+\d+\s*,\s*\d+",  # MySQL style LIMIT offset, count
        "error_keywords": ["LIMIT", "OFFSET", "syntax"],
        "description": "LIMIT syntax varies between databases",
        "fix": "Use standard syntax: LIMIT count OFFSET offset",
        "example_question": "Get page 2 of results (10 per page)",
        "example_sql": "SELECT * FROM records ORDER BY id LIMIT 10 OFFSET 10",
        "priority_weight": 1,
        "tags": ["pagination", "syntax"]
    },
    
    "boolean_comparison": {
        "name": "Boolean Comparison Issue",
        "regex": r"=\s*['\"]?(true|false|True|False|TRUE|FALSE)['\"]?",
        "error_keywords": ["boolean", "true", "false", "cannot compare"],
        "description": "Boolean comparison syntax issue",
        "fix": "Use unquoted TRUE/FALSE in DuckDB: WHERE is_active = TRUE",
        "example_question": "Find active records",
        "example_sql": "SELECT * FROM records WHERE is_active = TRUE AND is_deleted = FALSE",
        "priority_weight": 1,
        "tags": ["boolean", "syntax"]
    },
    
    "cte_syntax": {
        "name": "CTE Syntax Error",
        "regex": r"WITH\s+\w+\s+SELECT",  # Missing AS
        "error_keywords": ["WITH", "CTE", "common table expression", "AS expected"],
        "description": "Common Table Expression syntax error",
        "fix": "Ensure CTE has AS keyword: WITH cte_name AS (SELECT ...)",
        "example_question": "Use CTE for complex query",
        "example_sql": "WITH active_patients AS (SELECT * FROM patients WHERE is_active = TRUE) SELECT * FROM active_patients",
        "priority_weight": 1,
        "tags": ["cte", "syntax"]
    },
    
    "subquery_alias": {
        "name": "Subquery Missing Alias",
        "regex": r"\)\s+(WHERE|AND|OR|JOIN|ON|GROUP|ORDER|LIMIT)",
        "error_keywords": ["subquery", "alias", "must have an alias", "derived table"],
        "description": "Subquery in FROM clause requires an alias",
        "fix": "Add alias to subquery: (SELECT ...) AS subquery_alias",
        "example_question": "Use subquery in FROM clause",
        "example_sql": "SELECT * FROM (SELECT patient_id, COUNT(*) as cnt FROM visits GROUP BY patient_id) AS visit_counts WHERE cnt > 5",
        "priority_weight": 1,
        "tags": ["subquery", "alias"]
    },
    
    "null_comparison": {
        "name": "NULL Comparison with Equals",
        "regex": r"[!=<>]=?\s*NULL\b",
        "error_keywords": [],  # Usually doesn't error, but returns wrong results
        "description": "Using = or != with NULL doesn't work as expected",
        "fix": "Use IS NULL or IS NOT NULL for NULL comparisons",
        "example_question": "Find records with missing values",
        "example_sql": "SELECT * FROM records WHERE discharge_date IS NULL",
        "priority_weight": 1,
        "tags": ["null", "comparison"]
    },
    
    "consecutive_streak_wrong": {
        "name": "Consecutive Streak Detection",
        "regex": r"(consecutive|streak|in.a.row)",
        "error_keywords": ["window", "consecutive", "sequence"],
        "description": "Consecutive streak detection requires ROW_NUMBER difference technique",
        "fix": "Use ROW_NUMBER() subtraction to identify groups of consecutive values",
        "example_question": "Find consecutive days with readings",
        "example_sql": """WITH dated AS (
    SELECT DISTINCT DATE(reading_date) as dt FROM readings
), 
numbered AS (
    SELECT dt, dt - INTERVAL '1 day' * ROW_NUMBER() OVER (ORDER BY dt) as grp
    FROM dated
)
SELECT MIN(dt) as streak_start, MAX(dt) as streak_end, COUNT(*) as streak_length
FROM numbered GROUP BY grp ORDER BY streak_length DESC""",
        "priority_weight": 3,
        "tags": ["streak", "window", "complex"]
    },
}


# ============================================
# Data Classes
# ============================================

class Priority(Enum):
    """Priority level for training suggestions."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FailureCategory:
    """A category of test failures with associated results."""
    pattern_id: str
    pattern_name: str
    description: str
    fix_suggestion: str
    failure_count: int
    test_ids: List[str] = field(default_factory=list)
    sample_errors: List[str] = field(default_factory=list)
    sample_sql: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrainingSuggestion:
    """A suggested training example based on failure analysis."""
    category: str
    pattern_name: str
    question_template: str
    correct_sql: str
    based_on_failures: int
    priority: Priority
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['priority'] = self.priority.value
        return d


@dataclass
class AnalysisReport:
    """Complete analysis report with categories and suggestions."""
    timestamp: str
    total_failures_analyzed: int
    categories: List[FailureCategory]
    suggestions: List[TrainingSuggestion]
    uncategorized_count: int
    uncategorized_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'total_failures_analyzed': self.total_failures_analyzed,
            'categories': [c.to_dict() for c in self.categories],
            'suggestions': [s.to_dict() for s in self.suggestions],
            'uncategorized_count': self.uncategorized_count,
            'uncategorized_errors': self.uncategorized_errors
        }


# ============================================
# Test Result (imported from run_sql_tests or reconstructed)
# ============================================

@dataclass
class TestResult:
    """Reconstructed TestResult for standalone analysis."""
    test_id: str
    question: str
    status: str
    generated_sql: str = ""
    expected_sql: Optional[str] = None
    sql_executed: bool = False
    sql_error: Optional[str] = None
    result_match: bool = False
    row_count: int = 0
    column_names: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestResult':
        """Create TestResult from dictionary."""
        return cls(
            test_id=data.get('test_id', 'unknown'),
            question=data.get('question', ''),
            status=data.get('status', 'error'),
            generated_sql=data.get('generated_sql', ''),
            expected_sql=data.get('expected_sql'),
            sql_executed=data.get('sql_executed', False),
            sql_error=data.get('sql_error'),
            result_match=data.get('result_match', False),
            row_count=data.get('row_count', 0),
            column_names=data.get('column_names', []),
            execution_time_ms=data.get('execution_time_ms', 0.0),
            generation_time_ms=data.get('generation_time_ms', 0.0),
            notes=data.get('notes', ''),
            tags=data.get('tags', [])
        )


# ============================================
# Test Results Analyzer
# ============================================

class TestResultsAnalyzer:
    """
    Analyzes test results to identify failure patterns and suggest improvements.
    
    Usage:
        analyzer = TestResultsAnalyzer(results)
        categories = analyzer.categorize_failures()
        suggestions = analyzer.suggest_training_examples()
        report = analyzer.generate_improvement_report()
    """
    
    def __init__(self, results: List[TestResult]):
        """
        Initialize analyzer with test results.
        
        Args:
            results: List of TestResult objects to analyze
        """
        self.results = results
        self.failures = [r for r in results if r.status in ('failed', 'error')]
        self._categorized: Optional[Dict[str, List[TestResult]]] = None
        self._uncategorized: List[TestResult] = []
    
    def categorize_failures(self) -> Dict[str, List[TestResult]]:
        """
        Categorize failures by pattern.
        
        Returns:
            Dictionary mapping pattern_id to list of matching TestResults
        """
        if self._categorized is not None:
            return self._categorized
        
        categorized: Dict[str, List[TestResult]] = defaultdict(list)
        uncategorized: List[TestResult] = []
        
        for result in self.failures:
            matched = False
            
            for pattern_id, pattern in FAILURE_PATTERNS.items():
                if self._matches_pattern(result, pattern):
                    categorized[pattern_id].append(result)
                    matched = True
                    break  # Each failure goes to first matching category
            
            if not matched:
                uncategorized.append(result)
        
        self._categorized = dict(categorized)
        self._uncategorized = uncategorized
        
        logger.info(
            f"Categorized {len(self.failures)} failures: "
            f"{len(self._categorized)} categories, {len(uncategorized)} uncategorized"
        )
        
        return self._categorized
    
    def _matches_pattern(self, result: TestResult, pattern: Dict[str, Any]) -> bool:
        """
        Check if a test result matches a failure pattern.
        
        Checks both SQL regex patterns and error message keywords.
        """
        # Check regex pattern against generated SQL
        regex = pattern.get('regex', '')
        if regex and result.generated_sql:
            if re.search(regex, result.generated_sql, re.IGNORECASE):
                return True
        
        # Check error keywords against sql_error
        error_keywords = pattern.get('error_keywords', [])
        if error_keywords and result.sql_error:
            error_lower = result.sql_error.lower()
            for keyword in error_keywords:
                if keyword.lower() in error_lower:
                    return True
        
        return False
    
    def get_failure_categories(self) -> List[FailureCategory]:
        """
        Get detailed failure category objects.
        
        Returns:
            List of FailureCategory objects with statistics
        """
        categorized = self.categorize_failures()
        categories = []
        
        for pattern_id, failures in categorized.items():
            pattern = FAILURE_PATTERNS.get(pattern_id, {})
            
            # Collect sample errors and SQL (limited for privacy)
            sample_errors = []
            sample_sql = []
            for f in failures[:5]:  # Limit samples
                if f.sql_error and f.sql_error not in sample_errors:
                    sample_errors.append(f.sql_error[:200])
                if f.generated_sql and len(sample_sql) < 3:
                    sample_sql.append(f.generated_sql[:300])
            
            category = FailureCategory(
                pattern_id=pattern_id,
                pattern_name=pattern.get('name', pattern_id),
                description=pattern.get('description', ''),
                fix_suggestion=pattern.get('fix', ''),
                failure_count=len(failures),
                test_ids=[f.test_id for f in failures],
                sample_errors=sample_errors,
                sample_sql=sample_sql,
                tags=pattern.get('tags', [])
            )
            categories.append(category)
        
        # Sort by failure count descending
        categories.sort(key=lambda c: c.failure_count, reverse=True)
        
        return categories
    
    def suggest_training_examples(self) -> List[TrainingSuggestion]:
        """
        Generate suggested training Q&A pairs based on failure patterns.
        
        Returns:
            List of TrainingSuggestion objects prioritized by failure frequency
        """
        categorized = self.categorize_failures()
        suggestions = []
        
        for pattern_id, failures in categorized.items():
            pattern = FAILURE_PATTERNS.get(pattern_id, {})
            
            if not pattern:
                continue
            
            # Determine priority based on failure count and weight
            failure_count = len(failures)
            weight = pattern.get('priority_weight', 1)
            score = failure_count * weight
            
            if score >= 9:
                priority = Priority.CRITICAL
            elif score >= 5:
                priority = Priority.HIGH
            elif score >= 2:
                priority = Priority.MEDIUM
            else:
                priority = Priority.LOW
            
            # Create suggestion from pattern
            suggestion = TrainingSuggestion(
                category=pattern_id,
                pattern_name=pattern.get('name', pattern_id),
                question_template=pattern.get('example_question', f"[Template for {pattern_id}]"),
                correct_sql=pattern.get('example_sql', pattern.get('fix', '')),
                based_on_failures=failure_count,
                priority=priority,
                tags=pattern.get('tags', []),
                notes=f"Fix: {pattern.get('fix', 'See documentation')}"
            )
            suggestions.append(suggestion)
        
        # Sort by priority (critical first) then by failure count
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3
        }
        suggestions.sort(key=lambda s: (priority_order[s.priority], -s.based_on_failures))
        
        return suggestions
    
    def generate_analysis_report(self) -> AnalysisReport:
        """
        Generate a complete analysis report.
        
        Returns:
            AnalysisReport with all categories and suggestions
        """
        categories = self.get_failure_categories()
        suggestions = self.suggest_training_examples()
        
        # Get uncategorized errors (sanitized)
        uncategorized_errors = []
        for r in self._uncategorized[:10]:  # Limit for report
            if r.sql_error:
                uncategorized_errors.append(r.sql_error[:150])
        
        return AnalysisReport(
            timestamp=datetime.utcnow().isoformat(),
            total_failures_analyzed=len(self.failures),
            categories=categories,
            suggestions=suggestions,
            uncategorized_count=len(self._uncategorized),
            uncategorized_errors=uncategorized_errors
        )
    
    def generate_improvement_report(self) -> str:
        """
        Generate a markdown improvement report.
        
        Returns:
            Markdown-formatted report string
        """
        report = self.generate_analysis_report()
        
        lines = [
            "# NL2SQL Test Failure Analysis Report",
            "",
            f"**Generated:** {report.timestamp}",
            f"**Total Failures Analyzed:** {report.total_failures_analyzed}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
        ]
        
        # Summary statistics
        if report.categories:
            lines.extend([
                f"- **{len(report.categories)}** distinct failure patterns identified",
                f"- **{report.uncategorized_count}** failures could not be categorized",
                f"- **{len(report.suggestions)}** training suggestions generated",
                "",
            ])
            
            # Top issues
            top_3 = report.categories[:3]
            if top_3:
                lines.append("### Top Issues to Address:")
                lines.append("")
                for i, cat in enumerate(top_3, 1):
                    lines.append(f"{i}. **{cat.pattern_name}** - {cat.failure_count} failures")
                lines.append("")
        else:
            lines.extend([
                "No categorizable failure patterns found.",
                "",
            ])
        
        # Detailed breakdown
        lines.extend([
            "---",
            "",
            "## Failure Category Breakdown",
            "",
        ])
        
        for category in report.categories:
            priority_badge = ""
            if category.failure_count >= 5:
                priority_badge = " [HIGH PRIORITY]"
            elif category.failure_count >= 3:
                priority_badge = " [MEDIUM PRIORITY]"
            
            lines.extend([
                f"### {category.pattern_name}{priority_badge}",
                "",
                f"**Count:** {category.failure_count} failures",
                f"**Tags:** {', '.join(category.tags) if category.tags else 'none'}",
                "",
                f"**Description:** {category.description}",
                "",
                f"**Fix:** {category.fix_suggestion}",
                "",
            ])
            
            if category.test_ids:
                lines.append("**Affected Tests:**")
                for test_id in category.test_ids[:10]:
                    lines.append(f"- {test_id}")
                if len(category.test_ids) > 10:
                    lines.append(f"- ... and {len(category.test_ids) - 10} more")
                lines.append("")
            
            if category.sample_sql:
                lines.append("**Sample Generated SQL (with issue):**")
                lines.append("```sql")
                lines.append(category.sample_sql[0])
                lines.append("```")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        # Training suggestions
        lines.extend([
            "## Recommended Training Examples",
            "",
            "Add these examples to improve model accuracy:",
            "",
        ])
        
        for i, suggestion in enumerate(report.suggestions, 1):
            priority_emoji = {
                Priority.CRITICAL: "[CRITICAL]",
                Priority.HIGH: "[HIGH]",
                Priority.MEDIUM: "[MEDIUM]",
                Priority.LOW: "[LOW]"
            }.get(suggestion.priority, "")
            
            lines.extend([
                f"### {i}. {suggestion.pattern_name} {priority_emoji}",
                "",
                f"**Based on:** {suggestion.based_on_failures} failures",
                f"**Tags:** {', '.join(suggestion.tags)}",
                "",
                "**Example Question:**",
                f"> {suggestion.question_template}",
                "",
                "**Correct SQL:**",
                "```sql",
                suggestion.correct_sql,
                "```",
                "",
                f"**Notes:** {suggestion.notes}",
                "",
                "---",
                "",
            ])
        
        # Uncategorized failures
        if report.uncategorized_count > 0:
            lines.extend([
                "## Uncategorized Failures",
                "",
                f"**Count:** {report.uncategorized_count}",
                "",
                "These failures don't match known patterns and may require manual investigation:",
                "",
            ])
            
            for error in report.uncategorized_errors:
                lines.append(f"- `{error}`")
            
            if report.uncategorized_count > len(report.uncategorized_errors):
                lines.append(f"- ... and {report.uncategorized_count - len(report.uncategorized_errors)} more")
            
            lines.append("")
        
        # Action items
        lines.extend([
            "---",
            "",
            "## Recommended Actions",
            "",
            "1. **Immediate:** Add training examples for CRITICAL and HIGH priority patterns",
            "2. **Short-term:** Update prompt templates to include fixes for top failure patterns",
            "3. **Long-term:** Review uncategorized failures and add new pattern definitions",
            "",
            "---",
            "",
            "*Generated by NL2SQL Test Results Analyzer*",
        ])
        
        return "\n".join(lines)
    
    def export_suggestions_json(self) -> str:
        """
        Export training suggestions as JSON for direct import.
        
        Returns:
            JSON string with suggestions in training format
        """
        suggestions = self.suggest_training_examples()
        
        export_data = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "source": "test_failure_analysis",
            "suggestions": [s.to_dict() for s in suggestions],
            "training_examples": []
        }
        
        # Convert suggestions to training example format
        for s in suggestions:
            if s.question_template and not s.question_template.startswith('['):
                export_data["training_examples"].append({
                    "question": s.question_template,
                    "sql": s.correct_sql,
                    "category": s.category,
                    "tags": s.tags,
                    "source": "auto_generated_from_failures"
                })
        
        return json.dumps(export_data, indent=2)


# ============================================
# File Loaders
# ============================================

def load_results_json(file_path: Path) -> List[TestResult]:
    """
    Load test results from a JSON file.
    
    Supports formats:
    - Direct list of results
    - Object with 'results' key (from run_sql_tests output)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle different formats
    if isinstance(data, list):
        raw_results = data
    elif isinstance(data, dict):
        raw_results = data.get('results', [])
    else:
        raw_results = []
    
    results = []
    for raw in raw_results:
        try:
            result = TestResult.from_dict(raw)
            results.append(result)
        except Exception as e:
            logger.warning(f"Failed to parse result: {e}")
    
    logger.info(f"Loaded {len(results)} test results from: {file_path}")
    return results


# ============================================
# CLI
# ============================================

def print_banner():
    """Print script banner."""
    print("=" * 70)
    print("NL2SQL Test Results Analyzer")
    print("=" * 70)
    print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze NL2SQL test results and suggest improvements.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.scripts.analyze_test_results --input results.json --output analysis.md
  python -m app.scripts.analyze_test_results --input results.json --export-suggestions suggestions.json
  python -m app.scripts.analyze_test_results --input results.json --format json
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        type=Path,
        required=True,
        help='Path to test results JSON file (from run_sql_tests --save-results)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Path for output report (default: stdout)'
    )
    
    parser.add_argument(
        '--format', '-f',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )
    
    parser.add_argument(
        '--export-suggestions',
        type=Path,
        default=None,
        help='Export training suggestions to JSON file'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--show-patterns',
        action='store_true',
        help='Show available failure patterns and exit'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    configure_logging(log_level=log_level, json_logs=False)
    
    print_banner()
    
    # Show patterns and exit if requested
    if args.show_patterns:
        print("Available Failure Patterns:")
        print("-" * 50)
        for pattern_id, pattern in FAILURE_PATTERNS.items():
            print(f"\n{pattern_id}:")
            print(f"  Name: {pattern.get('name', 'N/A')}")
            print(f"  Description: {pattern.get('description', 'N/A')}")
            print(f"  Tags: {', '.join(pattern.get('tags', []))}")
        sys.exit(0)
    
    try:
        # Validate input file
        if not args.input.exists():
            print(f"ERROR: Input file not found: {args.input}")
            sys.exit(1)
        
        # Load results
        print(f"Loading results from: {args.input}")
        results = load_results_json(args.input)
        
        if not results:
            print("ERROR: No results found in input file")
            sys.exit(1)
        
        print(f"Loaded {len(results)} test results")
        
        # Create analyzer
        analyzer = TestResultsAnalyzer(results)
        
        # Count failures
        failure_count = len(analyzer.failures)
        print(f"Found {failure_count} failures to analyze")
        
        if failure_count == 0:
            print("\nNo failures found - all tests passed!")
            sys.exit(0)
        
        # Categorize and analyze
        print("\nAnalyzing failure patterns...")
        categories = analyzer.categorize_failures()
        print(f"Identified {len(categories)} failure categories")
        
        # Generate output
        if args.format == 'json':
            report = analyzer.generate_analysis_report()
            output_content = json.dumps(report.to_dict(), indent=2)
        else:
            output_content = analyzer.generate_improvement_report()
        
        # Write or print output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_content)
            print(f"\nReport saved to: {args.output}")
        else:
            print()
            print(output_content)
        
        # Export suggestions if requested
        if args.export_suggestions:
            suggestions_json = analyzer.export_suggestions_json()
            with open(args.export_suggestions, 'w', encoding='utf-8') as f:
                f.write(suggestions_json)
            print(f"\nTraining suggestions exported to: {args.export_suggestions}")
        
        # Print summary
        print()
        print("=" * 50)
        categories_list = analyzer.get_failure_categories()
        if categories_list:
            top_category = categories_list[0]
            print(f"TOP ISSUE: {top_category.pattern_name} ({top_category.failure_count} failures)")
        print(f"TOTAL: {len(categories)} categories, {len(analyzer._uncategorized)} uncategorized")
        print("=" * 50)
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
