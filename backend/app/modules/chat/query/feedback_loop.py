"""
Query Feedback Loop Service

Records failed SQL queries and their corrections to improve future generations.
This addresses the "No Feedback Loop" shortcoming by:

1. Storing failed queries with their error messages
2. Storing successful corrections
3. Providing negative examples to prevent repeating mistakes
4. Auto-generating training examples from corrections

Usage:
    from app.modules.chat.query.feedback_loop import FeedbackLoop
    
    feedback = FeedbackLoop(agent_id="uuid")
    
    # Record a failure
    feedback.record_failure(
        question="How many active patients?",
        failed_sql="SELECT COUNT(*) FROM patient_gold WHERE patient_id IS NOT NULL",
        error="column patient_id does not exist"
    )
    
    # Record a correction
    feedback.record_correction(
        question="How many active patients?",
        failed_sql="SELECT COUNT(*) FROM patient_gold WHERE patient_id IS NOT NULL",
        corrected_sql="SELECT COUNT(DISTINCT res_id) FROM patient_gold",
        correction_reason="patient_gold uses res_id, not patient_id"
    )
    
    # Get negative examples for prompt
    negative_examples = feedback.get_negative_examples(question="patient count")
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import hashlib

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FailedQuery:
    """Record of a failed SQL query."""
    id: str
    question: str
    failed_sql: str
    error_message: str
    timestamp: str
    agent_id: Optional[str] = None
    tables_attempted: Optional[List[str]] = None
    correction: Optional[str] = None
    correction_reason: Optional[str] = None
    was_corrected: bool = False


@dataclass
class QueryCorrection:
    """Record of a successful correction."""
    id: str
    question: str
    original_sql: str
    corrected_sql: str
    correction_reason: str
    timestamp: str
    agent_id: Optional[str] = None
    error_type: Optional[str] = None  # e.g., "column_not_found", "fhir_violation"


class FeedbackLoop:
    """
    Service for tracking failed queries and corrections to improve NL2SQL.
    
    Stores feedback in JSON files per agent, enabling:
    - Negative example injection to prevent repeated mistakes
    - Pattern detection for common errors
    - Training data generation from corrections
    """
    
    # Directory for feedback storage
    FEEDBACK_DIR = Path(__file__).parent.parent.parent.parent / "data" / "feedback"
    
    def __init__(
        self, 
        agent_id: Optional[str] = None,
        max_history: int = 100
    ):
        """
        Initialize feedback loop.
        
        Args:
            agent_id: Agent ID for per-agent feedback storage
            max_history: Maximum number of records to keep
        """
        self._agent_id = agent_id or "global"
        self._max_history = max_history
        
        # In-memory cache
        self._failures: Dict[str, FailedQuery] = {}
        self._corrections: Dict[str, QueryCorrection] = {}
        
        # Ensure directory exists
        self.FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self._load_data()
    
    def _get_storage_path(self, data_type: str) -> Path:
        """Get path for storing feedback data."""
        return self.FEEDBACK_DIR / f"{self._agent_id}_{data_type}.json"
    
    def _load_data(self) -> None:
        """Load existing feedback data from disk."""
        # Load failures
        failures_path = self._get_storage_path("failures")
        if failures_path.exists():
            try:
                with open(failures_path, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        failure = FailedQuery(**item)
                        self._failures[failure.id] = failure
                logger.debug(f"Loaded {len(self._failures)} failure records")
            except Exception as e:
                logger.error(f"Failed to load failure records: {e}")
        
        # Load corrections
        corrections_path = self._get_storage_path("corrections")
        if corrections_path.exists():
            try:
                with open(corrections_path, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        correction = QueryCorrection(**item)
                        self._corrections[correction.id] = correction
                logger.debug(f"Loaded {len(self._corrections)} correction records")
            except Exception as e:
                logger.error(f"Failed to load correction records: {e}")
    
    def _save_data(self) -> None:
        """Save feedback data to disk."""
        try:
            # Save failures
            failures_path = self._get_storage_path("failures")
            with open(failures_path, 'w') as f:
                json.dump([asdict(f) for f in self._failures.values()], f, indent=2)
            
            # Save corrections
            corrections_path = self._get_storage_path("corrections")
            with open(corrections_path, 'w') as f:
                json.dump([asdict(c) for c in self._corrections.values()], f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save feedback data: {e}")
    
    def _generate_id(self, question: str, sql: str) -> str:
        """Generate a unique ID for a query."""
        content = f"{question}:{sql}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]
    
    def record_failure(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        tables_attempted: Optional[List[str]] = None
    ) -> str:
        """
        Record a failed SQL query.
        
        Args:
            question: Original natural language question
            failed_sql: The SQL that failed
            error_message: Error message from execution
            tables_attempted: Tables referenced in the query
            
        Returns:
            ID of the failure record
        """
        failure_id = self._generate_id(question, failed_sql)
        
        failure = FailedQuery(
            id=failure_id,
            question=question,
            failed_sql=failed_sql,
            error_message=error_message,
            timestamp=datetime.utcnow().isoformat(),
            agent_id=self._agent_id,
            tables_attempted=tables_attempted
        )
        
        self._failures[failure_id] = failure
        self._trim_history()
        self._save_data()
        
        logger.info(f"Recorded failure: {failure_id}", 
                   question=question[:50], 
                   error=error_message[:100])
        
        return failure_id
    
    def record_correction(
        self,
        question: str,
        failed_sql: str,
        corrected_sql: str,
        correction_reason: str,
        error_type: Optional[str] = None
    ) -> str:
        """
        Record a successful correction.
        
        Args:
            question: Original natural language question
            failed_sql: The SQL that failed
            corrected_sql: The corrected SQL that worked
            correction_reason: Why the correction was needed
            error_type: Type of error (e.g., "column_not_found")
            
        Returns:
            ID of the correction record
        """
        correction_id = self._generate_id(question, corrected_sql)
        
        correction = QueryCorrection(
            id=correction_id,
            question=question,
            original_sql=failed_sql,
            corrected_sql=corrected_sql,
            correction_reason=correction_reason,
            timestamp=datetime.utcnow().isoformat(),
            agent_id=self._agent_id,
            error_type=error_type
        )
        
        self._corrections[correction_id] = correction
        
        # Mark any matching failure as corrected
        failure_id = self._generate_id(question, failed_sql)
        if failure_id in self._failures:
            self._failures[failure_id].was_corrected = True
            self._failures[failure_id].correction = corrected_sql
            self._failures[failure_id].correction_reason = correction_reason
        
        self._trim_history()
        self._save_data()
        
        logger.info(f"Recorded correction: {correction_id}",
                   question=question[:50],
                   error_type=error_type)
        
        return correction_id
    
    def get_negative_examples(
        self,
        question: Optional[str] = None,
        max_examples: int = 3
    ) -> List[Dict[str, str]]:
        """
        Get negative examples to inject into prompt.
        
        These show the LLM what NOT to do.
        
        Args:
            question: Current question (for relevance matching)
            max_examples: Maximum examples to return
            
        Returns:
            List of negative example dicts with keys:
            - wrong_sql: The incorrect SQL
            - error: Why it was wrong
            - correct_sql: The corrected SQL (if available)
        """
        examples = []
        
        # If question provided, filter corrections by relevance first
        if question:
            question_words = set(question.lower().split())
            relevant_corrections = []
            for correction in self._corrections.values():
                correction_words = set(correction.question.lower().split())
                # Check word overlap (at least 2 common words for relevance)
                overlap = question_words & correction_words
                if len(overlap) >= 2:
                    relevant_corrections.append(correction)
            
            # Sort by timestamp, most recent first
            relevant_corrections.sort(key=lambda x: x.timestamp, reverse=True)
            
            for correction in relevant_corrections[:max_examples]:
                examples.append({
                    "wrong_sql": correction.original_sql,
                    "error": correction.correction_reason,
                    "correct_sql": correction.corrected_sql
                })
        
        # Fall back to recent corrections if not enough relevant
        if len(examples) < max_examples:
            remaining = max_examples - len(examples)
            recent_corrections = list(self._corrections.values())[-remaining:]
            for correction in recent_corrections:
                if correction.original_sql not in [e["wrong_sql"] for e in examples]:
                    examples.append({
                        "wrong_sql": correction.original_sql,
                        "error": correction.correction_reason,
                        "correct_sql": correction.corrected_sql
                    })
        
        # If still not enough, add uncorrected failures
        if len(examples) < max_examples:
            remaining = max_examples - len(examples)
            uncorrected = [
                f for f in self._failures.values() 
                if not f.was_corrected
            ][-remaining:]
            
            for failure in uncorrected:
                examples.append({
                    "wrong_sql": failure.failed_sql,
                    "error": failure.error_message,
                    "correct_sql": None
                })
        
        return examples[:max_examples]
    
    def get_common_error_patterns(self) -> Dict[str, int]:
        """
        Analyze common error patterns.
        
        Returns:
            Dict mapping error pattern to count
        """
        patterns = {}
        
        for failure in self._failures.values():
            error = failure.error_message.lower()
            
            # Categorize errors
            if "column" in error and "does not exist" in error:
                pattern = "column_not_found"
            elif "table" in error and "does not exist" in error:
                pattern = "table_not_found"
            elif "patient_id" in error and "patient_gold" in failure.failed_sql.lower():
                pattern = "fhir_patient_gold_patient_id"
            elif "syntax error" in error:
                pattern = "syntax_error"
            elif "timeout" in error:
                pattern = "query_timeout"
            else:
                pattern = "other"
            
            patterns[pattern] = patterns.get(pattern, 0) + 1
        
        return patterns
    
    def export_as_training_data(self) -> List[Dict[str, str]]:
        """
        Export corrections as training data for few-shot examples.
        
        Returns:
            List of training examples in format:
            {"question": ..., "sql": ..., "category": ...}
        """
        training_data = []
        
        for correction in self._corrections.values():
            training_data.append({
                "question": correction.question,
                "sql": correction.corrected_sql,
                "category": correction.error_type or "correction",
                "notes": f"Corrected from: {correction.original_sql[:100]}..."
            })
        
        return training_data
    
    def format_negative_examples_for_prompt(
        self,
        max_examples: int = 2
    ) -> str:
        """
        Format negative examples as a prompt section.
        
        Returns:
            Formatted string for prompt injection
        """
        examples = self.get_negative_examples(max_examples=max_examples)
        
        if not examples:
            return ""
        
        parts = ["COMMON MISTAKES TO AVOID:", ""]
        
        for i, example in enumerate(examples, 1):
            parts.append(f"Mistake {i}:")
            parts.append(f"  WRONG: {example['wrong_sql'][:150]}")
            parts.append(f"  Error: {example['error'][:100]}")
            if example.get('correct_sql'):
                parts.append(f"  CORRECT: {example['correct_sql'][:150]}")
            parts.append("")
        
        return "\n".join(parts)
    
    def _trim_history(self) -> None:
        """Trim history to max_history items."""
        # Keep most recent failures
        if len(self._failures) > self._max_history:
            sorted_failures = sorted(
                self._failures.items(),
                key=lambda x: x[1].timestamp,
                reverse=True
            )
            self._failures = dict(sorted_failures[:self._max_history])
        
        # Keep most recent corrections
        if len(self._corrections) > self._max_history:
            sorted_corrections = sorted(
                self._corrections.items(),
                key=lambda x: x[1].timestamp,
                reverse=True
            )
            self._corrections = dict(sorted_corrections[:self._max_history])


# Module-level cache for feedback loop instances
_feedback_instances: Dict[str, FeedbackLoop] = {}


def get_feedback_loop(agent_id: Optional[str] = None) -> FeedbackLoop:
    """
    Get a FeedbackLoop instance for the specified agent.
    
    Args:
        agent_id: Agent ID for per-agent feedback
        
    Returns:
        FeedbackLoop instance
    """
    cache_key = agent_id or "global"
    
    if cache_key not in _feedback_instances:
        _feedback_instances[cache_key] = FeedbackLoop(agent_id=agent_id)
    
    return _feedback_instances[cache_key]
