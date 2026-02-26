from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import require_super_admin, User
from backend.core.logging import get_logger
from backend.services.scheduler_service import (
    get_scheduler_service, SchedulerService, ScheduleType
)
import os
import chromadb
from chromadb.config import Settings

logger = get_logger(__name__)

router = APIRouter(prefix="/vector-db", tags=["Vector Database"])


# ============================================
# Pydantic Models for Schedule API
# ============================================

class ScheduleCreateRequest(BaseModel):
    """Request model for creating/updating a schedule."""
    schedule_type: str = Field(default="daily", description="Schedule type: hourly, daily, weekly, custom")
    hour: int = Field(default=2, ge=0, le=23, description="Hour of day (0-23)")
    minute: int = Field(default=0, ge=0, le=59, description="Minute (0-59)")
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6, description="Day of week (0=Mon, 6=Sun)")
    cron_expression: Optional[str] = Field(default=None, description="Custom cron expression")
    enabled: bool = Field(default=True, description="Whether schedule is active")


class ScheduleResponse(BaseModel):
    """Response model for schedule information."""
    vector_db_name: str
    enabled: bool
    schedule_type: str
    schedule_hour: int
    schedule_minute: int
    schedule_day_of_week: Optional[int] = None
    schedule_cron: Optional[str] = None
    next_run_at: Optional[str] = None
    countdown_seconds: Optional[int] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_job_id: Optional[str] = None


# ============================================
# Vector DB Status Endpoint (Enhanced)
# ============================================

@router.get("/status/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def get_vector_db_status(
    vector_db_name: str,
    db_service: DatabaseService = Depends(get_db_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get detailed statistics for a Vector Database including index count, vectors, and schedule info.
    Requires Super Admin role.
    """
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # 1. Get statistics from SQLite document_index
        cursor.execute('''
            SELECT COUNT(*) as count, MAX(updated_at) as last_updated
            FROM document_index
            WHERE vector_db_name = ?
        ''', (vector_db_name,))
        
        row = cursor.fetchone()
        document_count = row['count'] if row else 0
        last_updated = row['last_updated'] if row else None
        
        # 1.1 Get metadata from vector_db_registry
        cursor.execute('''
            SELECT embedding_model, llm, last_full_run, last_incremental_run, version
            FROM vector_db_registry
            WHERE name = ?
        ''', (vector_db_name,))
        reg_row = cursor.fetchone()
        
        registry_metadata = {
            "embedding_model": reg_row['embedding_model'] if reg_row else None,
            "llm": reg_row['llm'] if reg_row else None,
            "last_full_run": reg_row['last_full_run'] if reg_row else None,
            "last_incremental_run": reg_row['last_incremental_run'] if reg_row else None,
            "version": reg_row['version'] if reg_row else "1.0.0"
        }
        
        conn.close()

        # 2. Get vector count directly from ChromaDB
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../../data/indexes/{vector_db_name}"))
        vector_count = 0
        chroma_exists = False
        
        if os.path.exists(chroma_path):
            try:
                client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
                try:
                    collection = client.get_collection(name=vector_db_name)
                    vector_count = collection.count()
                    chroma_exists = True
                except ValueError:
                    # Collection doesn't exist
                    pass
            except Exception as e:
                logger.warning(f"Could not connect to ChromaDB at {chroma_path}: {e}")

        # 3. Get schedule information
        schedule = scheduler_service.get_schedule(vector_db_name)
        schedule_info = None
        if schedule:
            schedule_info = {
                "enabled": schedule.get('enabled', False),
                "schedule_type": schedule.get('schedule_type', 'daily'),
                "next_run_at": schedule.get('next_run_at'),
                "countdown_seconds": schedule.get('countdown_seconds'),
                "last_run_at": schedule.get('last_run_at'),
                "last_run_status": schedule.get('last_run_status')
            }

        # 4. Diagnostics & Monitoring (T06)
        diagnostics = []
        if chroma_exists and document_count > 0 and vector_count == 0:
            diagnostics.append({"level": "error", "message": "ChromaDB collection exists but is empty despite indexed documents."})
        elif chroma_exists and vector_count > 0 and document_count == 0:
            diagnostics.append({"level": "warning", "message": "Vectors exist in ChromaDB but no documents found in SQLite index."})
        
        if not chroma_exists and document_count > 0:
            diagnostics.append({"level": "error", "message": "SQLite index exists but ChromaDB directory is missing."})

        return {
            "name": vector_db_name,
            "exists": document_count > 0 or chroma_exists,
            "total_documents_indexed": document_count,
            "total_vectors": vector_count,
            "last_updated_at": last_updated,
            "embedding_model": registry_metadata["embedding_model"],
            "llm": registry_metadata["llm"],
            "last_full_run": registry_metadata["last_full_run"],
            "last_incremental_run": registry_metadata["last_incremental_run"],
            "version": registry_metadata["version"],
            "diagnostics": diagnostics,
            "schedule": schedule_info
        }
        
    except Exception as e:
        logger.error(f"Error fetching Vector DB status for {vector_db_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Vector DB status: {str(e)}"
        )


# ============================================
# Schedule Management Endpoints
# ============================================

@router.post("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def create_or_update_schedule(
    vector_db_name: str,
    request: ScheduleCreateRequest,
    current_user: User = Depends(require_super_admin),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Create or update a sync schedule for a Vector Database.
    Requires Super Admin role.
    """
    try:
        # Validate schedule_type
        try:
            schedule_type = ScheduleType(request.schedule_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid schedule_type. Must be one of: {[t.value for t in ScheduleType]}"
            )
        
        schedule = scheduler_service.create_schedule(
            vector_db_name=vector_db_name,
            schedule_type=schedule_type,
            hour=request.hour,
            minute=request.minute,
            day_of_week=request.day_of_week,
            cron_expression=request.cron_expression,
            enabled=request.enabled,
            created_by=current_user.username
        )
        
        logger.info(f"Schedule {'updated' if schedule else 'created'} for {vector_db_name} by {current_user.username}")
        
        return {
            "status": "success",
            "message": f"Schedule configured for {vector_db_name}",
            "schedule": schedule
        }
        
    except Exception as e:
        logger.error(f"Error creating schedule for {vector_db_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create schedule: {str(e)}"
        )


@router.get("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def get_schedule(
    vector_db_name: str,
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get schedule configuration for a Vector Database.
    Requires Super Admin role.
    """
    schedule = scheduler_service.get_schedule(vector_db_name)
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schedule found for vector DB: {vector_db_name}"
        )
    
    return schedule


@router.delete("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def delete_schedule(
    vector_db_name: str,
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Delete a schedule for a Vector Database.
    Requires Super Admin role.
    """
    deleted = scheduler_service.delete_schedule(vector_db_name)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schedule found for vector DB: {vector_db_name}"
        )
    
    return {
        "status": "success",
        "message": f"Schedule deleted for {vector_db_name}"
    }


@router.get("/schedules", response_model=List[Dict[str, Any]], dependencies=[Depends(require_super_admin)])
async def list_schedules(
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    List all Vector DB schedules.
    Requires Super Admin role.
    """
    return scheduler_service.list_schedules()


@router.post("/schedule/{vector_db_name}/trigger", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def trigger_sync_now(
    vector_db_name: str,
    current_user: User = Depends(require_super_admin),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Manually trigger an immediate sync for a Vector Database.
    Requires Super Admin role.
    """
    try:
        message = scheduler_service.trigger_now(vector_db_name)
        logger.info(f"Manual sync triggered for {vector_db_name} by {current_user.username}")
        
        return {
            "status": "success",
            "message": message
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error triggering sync for {vector_db_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(e)}"
        )


# ============================================
# Vector DB Name Validation Endpoint
# ============================================

@router.get("/check-name", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def check_vector_db_name(
    name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Check if a Vector DB name is valid and available.
    Requires Super Admin role.
    """
    from backend.core.vector_db_utils import validate_vector_db_name
    
    valid, message = validate_vector_db_name(name)
    if not valid:
        return {"valid": False, "message": message}
    
    # Check if already exists in registry
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT id FROM vector_db_registry WHERE name = ?', (name,))
        existing = cursor.fetchone()
        
        if existing:
            return {"valid": True, "message": "Name exists (will update existing)"}
        
        return {"valid": True, "message": "Name is available"}
        
    finally:
        conn.close()
