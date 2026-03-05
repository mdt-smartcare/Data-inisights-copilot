"""
Schema Drift Detection API Routes

Provides endpoints to:
- Check for schema drift before embedding jobs
- View drift history and unresolved issues
- Acknowledge or resolve drift alerts
- Update schema snapshots
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from pydantic import BaseModel
from backend.core.permissions import require_super_admin, User
from backend.core.logging import get_logger
from backend.services.schema_drift_service import get_drift_detector, DriftSeverity
from backend.sqliteDb.db import get_db_service, DatabaseService

logger = get_logger(__name__)

router = APIRouter(prefix="/schema-drift", tags=["Schema Drift Detection"])


# ============================================
# Pydantic Models
# ============================================

class DriftCheckRequest(BaseModel):
    """Request to check for schema drift."""
    vector_db_name: str
    connection_id: int


class AcknowledgeDriftRequest(BaseModel):
    """Request to acknowledge a drift."""
    drift_id: int


class UpdateSnapshotRequest(BaseModel):
    """Request to update schema snapshot."""
    vector_db_name: str
    connection_id: int
    resolve_existing: bool = True


# ============================================
# Endpoints
# ============================================

@router.post("/check", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def check_schema_drift(
    request: DriftCheckRequest,
    current_user: User = Depends(require_super_admin)
):
    """
    Check for schema drift between stored snapshot and current database.
    Returns a detailed report of any changes detected.
    
    This should be called before starting an embedding job to prevent failures.
    """
    try:
        detector = get_drift_detector()
        report = detector.detect_drift(request.vector_db_name, request.connection_id)
        
        # Log any new critical/warning drifts
        for drift in report.drifts:
            if drift.severity in [DriftSeverity.CRITICAL, DriftSeverity.WARNING]:
                detector.log_drift(request.vector_db_name, drift)
        
        # Create notification if critical drift detected
        if report.has_critical_drift:
            _create_drift_notification(
                current_user.id,
                request.vector_db_name,
                report.critical_count,
                "critical"
            )
        elif report.has_warnings:
            _create_drift_notification(
                current_user.id,
                request.vector_db_name,
                report.warning_count,
                "warning"
            )
        
        return report.to_dict()
        
    except Exception as e:
        logger.error(f"Error checking schema drift: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check schema drift: {str(e)}"
        )


@router.get("/status/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def get_drift_status(
    vector_db_name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get current drift status for a vector DB including unresolved issues.
    """
    try:
        detector = get_drift_detector()
        unresolved = detector.get_unresolved_drifts(vector_db_name)
        
        # Get snapshot info
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT schema_snapshot_at, data_source_id
            FROM vector_db_registry
            WHERE name = ?
        ''', (vector_db_name,))
        row = cursor.fetchone()
        conn.close()
        
        critical_count = sum(1 for d in unresolved if d.get('severity') == 'critical')
        warning_count = sum(1 for d in unresolved if d.get('severity') == 'warning')
        
        return {
            "vector_db_name": vector_db_name,
            "has_snapshot": row and row['schema_snapshot_at'] is not None,
            "snapshot_at": row['schema_snapshot_at'] if row else None,
            "connection_id": row['data_source_id'] if row else None,
            "unresolved_count": len(unresolved),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "unresolved_drifts": unresolved,
            "can_run_embedding": critical_count == 0
        }
        
    except Exception as e:
        logger.error(f"Error getting drift status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get drift status: {str(e)}"
        )


@router.post("/acknowledge", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def acknowledge_drift(
    request: AcknowledgeDriftRequest,
    current_user: User = Depends(require_super_admin)
):
    """
    Acknowledge a drift alert. This marks it as seen but doesn't resolve it.
    Useful when you're aware of a change but haven't fixed it yet.
    """
    try:
        detector = get_drift_detector()
        success = detector.acknowledge_drift(request.drift_id, current_user.username)
        
        if success:
            return {
                "status": "success",
                "message": f"Drift {request.drift_id} acknowledged",
                "acknowledged_by": current_user.username
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Drift {request.drift_id} not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging drift: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to acknowledge drift: {str(e)}"
        )


@router.post("/resolve/{drift_id}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def resolve_drift(
    drift_id: int,
    current_user: User = Depends(require_super_admin)
):
    """
    Mark a specific drift as resolved.
    """
    try:
        detector = get_drift_detector()
        success = detector.resolve_drift(drift_id, current_user.username)
        
        if success:
            return {
                "status": "success",
                "message": f"Drift {drift_id} resolved",
                "resolved_by": current_user.username
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Drift {drift_id} not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving drift: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve drift: {str(e)}"
        )


@router.post("/snapshot/update", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def update_schema_snapshot(
    request: UpdateSnapshotRequest,
    current_user: User = Depends(require_super_admin)
):
    """
    Capture and store a new schema snapshot for a vector DB.
    This is useful after schema changes to update the baseline.
    
    Optionally resolves all existing drift alerts.
    """
    try:
        detector = get_drift_detector()
        
        # Capture new snapshot
        snapshot = detector.capture_schema_snapshot(request.connection_id)
        
        # Store it
        success = detector.store_schema_snapshot(request.vector_db_name, snapshot)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store schema snapshot"
            )
        
        # Optionally resolve existing drifts
        resolved_count = 0
        if request.resolve_existing:
            resolved_count = detector.resolve_all_drifts(
                request.vector_db_name, 
                current_user.username
            )
        
        table_count = len(snapshot.get("tables", {}))
        column_count = sum(
            len(t.get("columns", {})) 
            for t in snapshot.get("tables", {}).values()
        )
        
        return {
            "status": "success",
            "message": f"Schema snapshot updated for {request.vector_db_name}",
            "snapshot_info": {
                "tables": table_count,
                "columns": column_count,
                "captured_at": snapshot.get("captured_at")
            },
            "resolved_drifts": resolved_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schema snapshot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schema snapshot: {str(e)}"
        )


@router.get("/history/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def get_drift_history(
    vector_db_name: str,
    include_resolved: bool = False,
    limit: int = 50,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get drift detection history for a vector DB.
    """
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        if include_resolved:
            cursor.execute('''
                SELECT id, vector_db_name, drift_type, severity, entity_name,
                       details, detected_at, resolved_at, resolved_by,
                       acknowledged_at, acknowledged_by
                FROM schema_drift_logs
                WHERE vector_db_name = ?
                ORDER BY detected_at DESC
                LIMIT ?
            ''', (vector_db_name, limit))
        else:
            cursor.execute('''
                SELECT id, vector_db_name, drift_type, severity, entity_name,
                       details, detected_at, resolved_at, resolved_by,
                       acknowledged_at, acknowledged_by
                FROM schema_drift_logs
                WHERE vector_db_name = ? AND resolved_at IS NULL
                ORDER BY detected_at DESC
                LIMIT ?
            ''', (vector_db_name, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return {
            "vector_db_name": vector_db_name,
            "total_records": len(rows),
            "include_resolved": include_resolved,
            "history": [dict(row) for row in rows]
        }
        
    except Exception as e:
        logger.error(f"Error getting drift history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get drift history: {str(e)}"
        )


# ============================================
# Helper Functions
# ============================================

def _create_drift_notification(user_id: int, vector_db_name: str, count: int, severity: str):
    """Create a notification for detected schema drift."""
    try:
        from backend.sqliteDb.db import get_db_service
        db_service = get_db_service()
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        if severity == "critical":
            title = "🚨 Critical Schema Drift Detected"
            message = f"{count} breaking schema change(s) detected for '{vector_db_name}'. Embedding jobs will fail until resolved."
            priority = "high"
        else:
            title = "⚠️ Schema Changes Detected"
            message = f"{count} schema change(s) detected for '{vector_db_name}'. Review before running embedding jobs."
            priority = "medium"
        
        cursor.execute('''
            INSERT INTO notifications (user_id, type, priority, title, message, action_url, action_label)
            VALUES (?, 'schema_drift', ?, ?, ?, ?, ?)
        ''', (
            user_id,
            priority,
            title,
            message,
            f"/data-management?tab=vectors&drift={vector_db_name}",
            "View Details"
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Failed to create drift notification: {e}")
