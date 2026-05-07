"""
Query Audit Trail

Provides structured logging for all SQL queries for:
- Debugging and troubleshooting
- Compliance and auditing
- Performance analysis
- Training data collection

Usage:
    from app.modules.chat.query.audit_trail import QueryAuditTrail, get_audit_trail
    
    audit = get_audit_trail()
    
    # Record a query
    audit.record(
        question="How many patients?",
        generated_sql="SELECT COUNT(*) FROM patients",
        execution_time_ms=150,
        row_count=1,
        status="success"
    )
    
    # Query history
    recent = audit.get_recent(limit=10, status="failed")
"""
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from collections import deque
from enum import Enum

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class QueryStatus(Enum):
    """Query execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"


@dataclass
class QueryAuditRecord:
    """Single query audit record."""
    id: str
    timestamp: str
    agent_id: Optional[str]
    tenant_id: Optional[str]
    user_id: Optional[str]
    
    # Query details
    question: str
    generated_sql: str
    tables_used: List[str]
    
    # Execution details
    status: str
    execution_time_ms: int
    row_count: Optional[int]
    error_message: Optional[str]
    
    # Validation details
    validation_passed: bool
    validation_issues: List[str]
    
    # Context
    schema_version: Optional[str]
    few_shot_examples_used: int
    retry_count: int
    
    # Metadata
    complexity_level: Optional[str] = None
    query_plan: Optional[Dict[str, Any]] = None


class QueryAuditTrail:
    """
    Audit trail for SQL queries with both in-memory and file storage.
    
    Features:
    - In-memory ring buffer for recent queries
    - JSON file persistence for long-term storage
    - Filtering and querying capabilities
    - Automatic log rotation
    """
    
    # Maximum records in memory
    MAX_MEMORY_RECORDS = 1000
    
    # Maximum records per file
    MAX_FILE_RECORDS = 10000
    
    # Audit log directory
    AUDIT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "audit"
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        enable_file_logging: bool = True
    ):
        """
        Initialize audit trail.
        
        Args:
            agent_id: Agent ID for filtering
            enable_file_logging: Whether to persist to files
        """
        self._agent_id = agent_id
        self._enable_file_logging = enable_file_logging
        
        # In-memory buffer
        self._records: deque = deque(maxlen=self.MAX_MEMORY_RECORDS)
        self._lock = threading.RLock()
        
        # Statistics
        self._stats = {
            "total_queries": 0,
            "successful": 0,
            "failed": 0,
            "timeouts": 0,
            "total_execution_time_ms": 0,
        }
        
        # Ensure directory exists
        if enable_file_logging:
            self.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    
    def _generate_id(self) -> str:
        """Generate a unique record ID."""
        import uuid
        return str(uuid.uuid4())[:12]
    
    def record(
        self,
        question: str,
        generated_sql: str,
        status: str = "success",
        execution_time_ms: int = 0,
        row_count: Optional[int] = None,
        error_message: Optional[str] = None,
        tables_used: Optional[List[str]] = None,
        validation_passed: bool = True,
        validation_issues: Optional[List[str]] = None,
        few_shot_examples_used: int = 0,
        retry_count: int = 0,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        schema_version: Optional[str] = None,
        complexity_level: Optional[str] = None,
        query_plan: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record a query execution.
        
        Returns:
            Record ID
        """
        record_id = self._generate_id()
        
        record = QueryAuditRecord(
            id=record_id,
            timestamp=datetime.utcnow().isoformat(),
            agent_id=self._agent_id,
            tenant_id=tenant_id,
            user_id=user_id,
            question=question,
            generated_sql=generated_sql,
            tables_used=tables_used or [],
            status=status,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            error_message=error_message,
            validation_passed=validation_passed,
            validation_issues=validation_issues or [],
            schema_version=schema_version,
            few_shot_examples_used=few_shot_examples_used,
            retry_count=retry_count,
            complexity_level=complexity_level,
            query_plan=query_plan
        )
        
        with self._lock:
            self._records.append(record)
            self._update_stats(record)
        
        # Persist to file
        if self._enable_file_logging:
            self._persist_record(record)
        
        logger.info(
            "Audit record created",
            record_id=record_id,
            status=status,
            execution_time_ms=execution_time_ms,
            tables_used=tables_used,
            question=question[:50] + "..." if len(question) > 50 else question
        )
        
        return record_id
    
    def _update_stats(self, record: QueryAuditRecord) -> None:
        """Update statistics."""
        self._stats["total_queries"] += 1
        self._stats["total_execution_time_ms"] += record.execution_time_ms
        
        if record.status == "success":
            self._stats["successful"] += 1
        elif record.status == "timeout":
            self._stats["timeouts"] += 1
        else:
            self._stats["failed"] += 1
    
    def _persist_record(self, record: QueryAuditRecord) -> None:
        """Persist a record to file."""
        try:
            # Use date-based files for easy rotation
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            file_path = self.AUDIT_DIR / f"queries_{date_str}.jsonl"
            
            with open(file_path, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to persist audit record: {e}")
    
    def get_recent(
        self,
        limit: int = 100,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        min_execution_time_ms: Optional[int] = None
    ) -> List[QueryAuditRecord]:
        """
        Get recent queries with optional filtering.
        
        Args:
            limit: Maximum records to return
            status: Filter by status
            agent_id: Filter by agent
            min_execution_time_ms: Filter by minimum execution time
            
        Returns:
            List of matching records (most recent first)
        """
        with self._lock:
            records = list(self._records)
        
        # Apply filters
        filtered = []
        for r in reversed(records):  # Most recent first
            if status and r.status != status:
                continue
            if agent_id and r.agent_id != agent_id:
                continue
            if min_execution_time_ms and r.execution_time_ms < min_execution_time_ms:
                continue
            
            filtered.append(r)
            if len(filtered) >= limit:
                break
        
        return filtered
    
    def get_failed_queries(
        self,
        limit: int = 50,
        days: int = 7
    ) -> List[QueryAuditRecord]:
        """Get recent failed queries for debugging."""
        return self.get_recent(limit=limit, status="failed")
    
    def get_slow_queries(
        self,
        threshold_ms: int = 5000,
        limit: int = 50
    ) -> List[QueryAuditRecord]:
        """Get queries that exceeded a time threshold."""
        return self.get_recent(
            limit=limit,
            min_execution_time_ms=threshold_ms
        )
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get aggregate statistics."""
        with self._lock:
            stats = dict(self._stats)
            
            if stats["total_queries"] > 0:
                stats["avg_execution_time_ms"] = (
                    stats["total_execution_time_ms"] / stats["total_queries"]
                )
                stats["success_rate"] = (
                    stats["successful"] / stats["total_queries"]
                )
            else:
                stats["avg_execution_time_ms"] = 0
                stats["success_rate"] = 0
            
            return stats
    
    def get_table_usage_stats(self) -> Dict[str, int]:
        """Get statistics on which tables are queried most."""
        table_counts: Dict[str, int] = {}
        
        with self._lock:
            for record in self._records:
                for table in record.tables_used:
                    table_counts[table] = table_counts.get(table, 0) + 1
        
        # Sort by count
        return dict(sorted(
            table_counts.items(),
            key=lambda x: x[1],
            reverse=True
        ))
    
    def get_error_patterns(self) -> Dict[str, int]:
        """Analyze common error patterns."""
        patterns: Dict[str, int] = {}
        
        with self._lock:
            for record in self._records:
                if record.status != "success" and record.error_message:
                    # Extract error type
                    error_lower = record.error_message.lower()
                    
                    if "column" in error_lower and "not exist" in error_lower:
                        pattern = "column_not_found"
                    elif "table" in error_lower and "not exist" in error_lower:
                        pattern = "table_not_found"
                    elif "timeout" in error_lower:
                        pattern = "timeout"
                    elif "syntax" in error_lower:
                        pattern = "syntax_error"
                    elif "permission" in error_lower:
                        pattern = "permission_denied"
                    else:
                        pattern = "other"
                    
                    patterns[pattern] = patterns.get(pattern, 0) + 1
        
        return dict(sorted(patterns.items(), key=lambda x: x[1], reverse=True))
    
    def export_for_training(
        self,
        min_success_only: bool = True
    ) -> List[Dict[str, str]]:
        """
        Export successful queries as training data.
        
        Returns:
            List of {question, sql} pairs
        """
        training_data = []
        
        with self._lock:
            for record in self._records:
                if min_success_only and record.status != "success":
                    continue
                
                training_data.append({
                    "question": record.question,
                    "sql": record.generated_sql,
                    "tables": ",".join(record.tables_used),
                })
        
        return training_data
    
    def cleanup_old_files(self, days_to_keep: int = 30) -> int:
        """
        Clean up old audit files.
        
        Args:
            days_to_keep: Number of days of logs to keep
            
        Returns:
            Number of files deleted
        """
        if not self._enable_file_logging:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
        deleted = 0
        
        try:
            for file_path in self.AUDIT_DIR.glob("queries_*.jsonl"):
                # Parse date from filename
                try:
                    date_str = file_path.stem.replace("queries_", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < cutoff:
                        file_path.unlink()
                        deleted += 1
                        logger.info(f"Deleted old audit file: {file_path}")
                except ValueError:
                    continue
                    
        except Exception as e:
            logger.error(f"Error cleaning up audit files: {e}")
        
        return deleted


# Global instance
_audit_trail: Optional[QueryAuditTrail] = None
_audit_lock = threading.Lock()


def get_audit_trail(agent_id: Optional[str] = None) -> QueryAuditTrail:
    """Get the global audit trail instance."""
    global _audit_trail
    
    with _audit_lock:
        if _audit_trail is None:
            _audit_trail = QueryAuditTrail(agent_id=agent_id)
        return _audit_trail


def reset_audit_trail() -> None:
    """Reset the global audit trail (for testing)."""
    global _audit_trail
    with _audit_lock:
        _audit_trail = None
