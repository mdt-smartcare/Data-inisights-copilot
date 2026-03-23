"""
Schema Drift Detection Service

Detects changes in database schemas that could break embedding jobs.
Compares current schema against stored snapshots and alerts users
before running jobs that would fail due to missing tables/columns.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from backend.core.logging import get_logger
from backend.database.db import get_db_service

logger = get_logger(__name__)


class DriftType(str, Enum):
    TABLE_REMOVED = "table_removed"
    TABLE_ADDED = "table_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_ADDED = "column_added"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_NULLABLE_CHANGED = "column_nullable_changed"


class DriftSeverity(str, Enum):
    CRITICAL = "critical"  # Will break embedding jobs
    WARNING = "warning"    # May affect results
    INFO = "info"          # Informational only


@dataclass
class SchemaDrift:
    """Represents a single schema drift detection."""
    drift_type: DriftType
    severity: DriftSeverity
    entity_name: str
    table_name: Optional[str] = None
    column_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_type": self.drift_type.value,
            "severity": self.severity.value,
            "entity_name": self.entity_name,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "message": self.message
        }


@dataclass
class DriftReport:
    """Complete drift detection report."""
    vector_db_name: str
    has_critical_drift: bool
    has_warnings: bool
    total_drifts: int
    critical_count: int
    warning_count: int
    info_count: int
    drifts: List[SchemaDrift]
    checked_at: str
    can_run_embedding: bool
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "vector_db_name": self.vector_db_name,
            "has_critical_drift": self.has_critical_drift,
            "has_warnings": self.has_warnings,
            "total_drifts": self.total_drifts,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "drifts": [d.to_dict() for d in self.drifts],
            "checked_at": self.checked_at,
            "can_run_embedding": self.can_run_embedding,
            "summary": self.summary
        }


class SchemaDriftDetector:
    """
    Detects schema drift between stored snapshots and current database state.
    """
    
    def __init__(self, db_service=None):
        self.db_service = db_service or get_db_service()
    
    def capture_schema_snapshot(self, connection_id: int) -> Dict[str, Any]:
        """
        Capture current schema from a database connection.
        Returns a normalized schema representation.
        """
        from backend.api.routes.data import get_connection_schema_internal
        
        try:
            schema_info = get_connection_schema_internal(connection_id)
            
            # Normalize schema into a comparable format
            snapshot = {
                "connection_id": connection_id,
                "captured_at": datetime.utcnow().isoformat(),
                "tables": {}
            }
            
            if schema_info and "schema" in schema_info:
                details = schema_info["schema"].get("details", {})
                for table_name, columns in details.items():
                    snapshot["tables"][table_name] = {
                        "columns": {}
                    }
                    for col in columns:
                        col_name = col.get("column_name") or col.get("name")
                        snapshot["tables"][table_name]["columns"][col_name] = {
                            "type": col.get("data_type") or col.get("type"),
                            "nullable": col.get("is_nullable", "YES") == "YES",
                            "default": col.get("column_default")
                        }
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Failed to capture schema snapshot: {e}")
            raise
    
    def store_schema_snapshot(self, vector_db_name: str, snapshot: Dict[str, Any]) -> bool:
        """Store schema snapshot for a vector DB."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE vector_db_registry 
                SET schema_snapshot = %s, schema_snapshot_at = CURRENT_TIMESTAMP
                WHERE name = %s
            ''', (json.dumps(snapshot), vector_db_name))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Stored schema snapshot for vector DB: {vector_db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store schema snapshot: {e}")
            return False
    
    def get_stored_snapshot(self, vector_db_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored schema snapshot for a vector DB."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT schema_snapshot, schema_snapshot_at
                FROM vector_db_registry
                WHERE name = %s
            ''', (vector_db_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row['schema_snapshot']:
                return json.loads(row['schema_snapshot'])
            return None
            
        except Exception as e:
            logger.error(f"Failed to get stored snapshot: {e}")
            return None
    
    def detect_drift(self, vector_db_name: str, connection_id: int) -> DriftReport:
        """
        Compare current schema against stored snapshot and detect drift.
        """
        drifts: List[SchemaDrift] = []
        
        # Get stored snapshot
        stored_snapshot = self.get_stored_snapshot(vector_db_name)
        
        if not stored_snapshot:
            return DriftReport(
                vector_db_name=vector_db_name,
                has_critical_drift=False,
                has_warnings=True,
                total_drifts=0,
                critical_count=0,
                warning_count=0,
                info_count=0,
                drifts=[],
                checked_at=datetime.utcnow().isoformat(),
                can_run_embedding=True,
                summary="No schema snapshot found. Will capture on next embedding run."
            )
        
        # Capture current schema
        try:
            current_snapshot = self.capture_schema_snapshot(connection_id)
        except Exception as e:
            return DriftReport(
                vector_db_name=vector_db_name,
                has_critical_drift=True,
                has_warnings=False,
                total_drifts=1,
                critical_count=1,
                warning_count=0,
                info_count=0,
                drifts=[SchemaDrift(
                    drift_type=DriftType.TABLE_REMOVED,
                    severity=DriftSeverity.CRITICAL,
                    entity_name="database",
                    message=f"Failed to connect to database: {str(e)}"
                )],
                checked_at=datetime.utcnow().isoformat(),
                can_run_embedding=False,
                summary=f"Cannot connect to database: {str(e)}"
            )
        
        stored_tables = stored_snapshot.get("tables", {})
        current_tables = current_snapshot.get("tables", {})
        
        # Check for removed tables (CRITICAL)
        for table_name in stored_tables:
            if table_name not in current_tables:
                drifts.append(SchemaDrift(
                    drift_type=DriftType.TABLE_REMOVED,
                    severity=DriftSeverity.CRITICAL,
                    entity_name=table_name,
                    table_name=table_name,
                    message=f"Table '{table_name}' was removed from the database"
                ))
        
        # Check for added tables (INFO)
        for table_name in current_tables:
            if table_name not in stored_tables:
                drifts.append(SchemaDrift(
                    drift_type=DriftType.TABLE_ADDED,
                    severity=DriftSeverity.INFO,
                    entity_name=table_name,
                    table_name=table_name,
                    message=f"New table '{table_name}' was added to the database"
                ))
        
        # Check columns in existing tables
        for table_name in stored_tables:
            if table_name not in current_tables:
                continue  # Already handled as table removal
            
            stored_cols = stored_tables[table_name].get("columns", {})
            current_cols = current_tables[table_name].get("columns", {})
            
            # Check for removed columns (CRITICAL)
            for col_name in stored_cols:
                if col_name not in current_cols:
                    drifts.append(SchemaDrift(
                        drift_type=DriftType.COLUMN_REMOVED,
                        severity=DriftSeverity.CRITICAL,
                        entity_name=f"{table_name}.{col_name}",
                        table_name=table_name,
                        column_name=col_name,
                        message=f"Column '{col_name}' was removed from table '{table_name}'"
                    ))
            
            # Check for added columns (INFO)
            for col_name in current_cols:
                if col_name not in stored_cols:
                    drifts.append(SchemaDrift(
                        drift_type=DriftType.COLUMN_ADDED,
                        severity=DriftSeverity.INFO,
                        entity_name=f"{table_name}.{col_name}",
                        table_name=table_name,
                        column_name=col_name,
                        message=f"New column '{col_name}' was added to table '{table_name}'"
                    ))
            
            # Check for type changes in existing columns (WARNING)
            for col_name in stored_cols:
                if col_name not in current_cols:
                    continue
                
                stored_type = stored_cols[col_name].get("type", "").lower()
                current_type = current_cols[col_name].get("type", "").lower()
                
                if stored_type != current_type:
                    drifts.append(SchemaDrift(
                        drift_type=DriftType.COLUMN_TYPE_CHANGED,
                        severity=DriftSeverity.WARNING,
                        entity_name=f"{table_name}.{col_name}",
                        table_name=table_name,
                        column_name=col_name,
                        old_value=stored_type,
                        new_value=current_type,
                        message=f"Column '{col_name}' type changed from '{stored_type}' to '{current_type}'"
                    ))
        
        # Calculate summary
        critical_count = sum(1 for d in drifts if d.severity == DriftSeverity.CRITICAL)
        warning_count = sum(1 for d in drifts if d.severity == DriftSeverity.WARNING)
        info_count = sum(1 for d in drifts if d.severity == DriftSeverity.INFO)
        
        has_critical = critical_count > 0
        has_warnings = warning_count > 0
        
        if has_critical:
            summary = f"CRITICAL: {critical_count} breaking change(s) detected. Embedding job will fail."
        elif has_warnings:
            summary = f"WARNING: {warning_count} schema change(s) may affect results."
        elif info_count > 0:
            summary = f"INFO: {info_count} new element(s) detected. Consider re-indexing."
        else:
            summary = "No schema drift detected."
        
        return DriftReport(
            vector_db_name=vector_db_name,
            has_critical_drift=has_critical,
            has_warnings=has_warnings,
            total_drifts=len(drifts),
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            drifts=drifts,
            checked_at=datetime.utcnow().isoformat(),
            can_run_embedding=not has_critical,
            summary=summary
        )
    
    def log_drift(self, vector_db_name: str, drift: SchemaDrift) -> int:
        """Log a detected drift to the database."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO schema_drift_logs 
                (vector_db_name, drift_type, severity, entity_name, details)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                vector_db_name,
                drift.drift_type.value,
                drift.severity.value,
                drift.entity_name,
                json.dumps(drift.to_dict())
            ))
            
            drift_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return drift_id
            
        except Exception as e:
            logger.error(f"Failed to log drift: {e}")
            return -1
    
    def get_unresolved_drifts(self, vector_db_name: str) -> List[Dict[str, Any]]:
        """Get all unresolved drift logs for a vector DB."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, vector_db_name, drift_type, severity, entity_name, 
                       details, detected_at, acknowledged_at, acknowledged_by
                FROM schema_drift_logs
                WHERE vector_db_name = %s AND resolved_at IS NULL
                ORDER BY 
                    CASE severity 
                        WHEN 'critical' THEN 1 
                        WHEN 'warning' THEN 2 
                        ELSE 3 
                    END,
                    detected_at DESC
            ''', (vector_db_name,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get unresolved drifts: {e}")
            return []
    
    def acknowledge_drift(self, drift_id: int, acknowledged_by: str) -> bool:
        """Mark a drift as acknowledged (user is aware but hasn't fixed it)."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE schema_drift_logs
                SET acknowledged_at = CURRENT_TIMESTAMP, acknowledged_by = %s
                WHERE id = %s
            ''', (acknowledged_by, drift_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to acknowledge drift: {e}")
            return False
    
    def resolve_drift(self, drift_id: int, resolved_by: str) -> bool:
        """Mark a drift as resolved (schema has been fixed or snapshot updated)."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE schema_drift_logs
                SET resolved_at = CURRENT_TIMESTAMP, resolved_by = %s
                WHERE id = %s
            ''', (resolved_by, drift_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to resolve drift: {e}")
            return False
    
    def resolve_all_drifts(self, vector_db_name: str, resolved_by: str) -> int:
        """Resolve all unresolved drifts for a vector DB (typically after re-snapshotting)."""
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE schema_drift_logs
                SET resolved_at = CURRENT_TIMESTAMP, resolved_by = %s
                WHERE vector_db_name = %s AND resolved_at IS NULL
            ''', (resolved_by, vector_db_name))
            
            count = cursor.rowcount
            conn.commit()
            conn.close()
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to resolve all drifts: {e}")
            return 0


# Singleton instance
_drift_detector: Optional[SchemaDriftDetector] = None


def get_drift_detector() -> SchemaDriftDetector:
    """Get or create the schema drift detector singleton."""
    global _drift_detector
    if _drift_detector is None:
        _drift_detector = SchemaDriftDetector()
    return _drift_detector
