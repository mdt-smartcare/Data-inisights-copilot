from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import require_admin, User
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
# Helper function to calculate directory size
# ============================================

def get_directory_size(path: str) -> int:
    """Calculate total size of a directory in bytes."""
    total_size = 0
    if os.path.exists(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    pass
    return total_size


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


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

@router.get("/status/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def get_vector_db_status(
    vector_db_name: str,
    db_service: DatabaseService = Depends(get_db_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get detailed statistics for a Vector Database including index count, vectors, and schedule info.
    Requires Admin role or above.
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
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../data/indexes/{vector_db_name}"))
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

@router.post("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def create_or_update_schedule(
    vector_db_name: str,
    request: ScheduleCreateRequest,
    current_user: User = Depends(require_admin),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Create or update a sync schedule for a Vector Database.
    Requires Admin role or above.
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


@router.get("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def get_schedule(
    vector_db_name: str,
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Get schedule configuration for a Vector Database.
    Requires Admin role or above.
    """
    schedule = scheduler_service.get_schedule(vector_db_name)
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schedule found for vector DB: {vector_db_name}"
        )
    
    return schedule


@router.delete("/schedule/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def delete_schedule(
    vector_db_name: str,
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Delete a schedule for a Vector Database.
    Requires Admin role or above.
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


@router.get("/schedules", response_model=List[Dict[str, Any]], dependencies=[Depends(require_admin)])
async def list_schedules(
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    List all Vector DB schedules.
    Requires Admin role or above.
    """
    return scheduler_service.list_schedules()


@router.post("/schedule/{vector_db_name}/trigger", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def trigger_sync_now(
    vector_db_name: str,
    current_user: User = Depends(require_admin),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Manually trigger an immediate sync for a Vector Database.
    Requires Admin role or above.
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

@router.get("/check-name", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def check_vector_db_name(
    name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Check if a Vector DB name is valid and available.
    Requires Admin role or above.
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


# ============================================
# Vector DB Registry - List All Vector Databases
# ============================================

@router.get("/registry", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def list_all_vector_databases(
    db_service: DatabaseService = Depends(get_db_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    List all Vector Databases with their disk sizes, document counts, and sync status.
    Provides a centralized registry view for IT admins.
    Requires Super Admin role.
    """
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # Get all vector DBs from registry
        cursor.execute('''
            SELECT 
                r.id,
                r.name,
                r.data_source_id,
                r.created_at,
                r.created_by,
                r.embedding_model,
                r.llm,
                r.last_full_run,
                r.last_incremental_run,
                r.version
            FROM vector_db_registry r
            ORDER BY r.created_at DESC
        ''')
        
        registry_rows = cursor.fetchall()
        
        # Get document counts per vector DB
        cursor.execute('''
            SELECT vector_db_name, COUNT(*) as doc_count, MAX(updated_at) as last_updated
            FROM document_index
            GROUP BY vector_db_name
        ''')
        doc_counts = {row['vector_db_name']: {'count': row['doc_count'], 'last_updated': row['last_updated']} 
                      for row in cursor.fetchall()}
        
        conn.close()
        
        # Base path for ChromaDB indexes
        indexes_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/indexes"))
        vector_stores_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../vector_stores"))
        
        vector_dbs = []
        total_disk_size = 0
        
        for row in registry_rows:
            name = row['name']
            
            # Calculate disk size from ChromaDB folder
            chroma_path = os.path.join(indexes_base_path, name)
            alt_chroma_path = os.path.join(vector_stores_path, name)
            
            disk_size_bytes = 0
            chroma_exists = False
            vector_count = 0
            
            # Check primary path
            if os.path.exists(chroma_path):
                disk_size_bytes = get_directory_size(chroma_path)
                chroma_exists = True
            # Check alternate path
            elif os.path.exists(alt_chroma_path):
                disk_size_bytes = get_directory_size(alt_chroma_path)
                chroma_path = alt_chroma_path
                chroma_exists = True
            
            # Get vector count from ChromaDB
            if chroma_exists:
                try:
                    client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
                    try:
                        collection = client.get_collection(name=name)
                        vector_count = collection.count()
                    except ValueError:
                        pass
                except Exception as e:
                    logger.warning(f"Could not read ChromaDB for {name}: {e}")
            
            total_disk_size += disk_size_bytes
            
            # Get schedule info
            schedule = scheduler_service.get_schedule(name)
            schedule_info = None
            if schedule:
                schedule_info = {
                    "enabled": schedule.get('enabled', False),
                    "schedule_type": schedule.get('schedule_type', 'daily'),
                    "next_run_at": schedule.get('next_run_at'),
                    "last_run_at": schedule.get('last_run_at'),
                    "last_run_status": schedule.get('last_run_status')
                }
            
            # Get document count
            doc_info = doc_counts.get(name, {'count': 0, 'last_updated': None})
            
            # Determine health status
            health_status = "healthy"
            if not chroma_exists:
                health_status = "missing"
            elif vector_count == 0 and doc_info['count'] > 0:
                health_status = "error"
            elif schedule_info and schedule_info.get('last_run_status') == 'failed':
                health_status = "warning"
            
            vector_dbs.append({
                "id": row['id'],
                "name": name,
                "data_source_id": row['data_source_id'],
                "created_at": row['created_at'],
                "created_by": row['created_by'],
                "embedding_model": row['embedding_model'],
                "llm": row['llm'],
                "version": row['version'] or "1.0.0",
                "last_full_run": row['last_full_run'],
                "last_incremental_run": row['last_incremental_run'],
                "disk_size_bytes": disk_size_bytes,
                "disk_size_formatted": format_size(disk_size_bytes),
                "document_count": doc_info['count'],
                "vector_count": vector_count,
                "last_updated": doc_info['last_updated'],
                "chroma_exists": chroma_exists,
                "schedule": schedule_info,
                "health_status": health_status
            })
        
        # Also scan for orphaned ChromaDB folders (exist on disk but not in registry)
        orphaned_dbs = []
        registered_names = {row['name'] for row in registry_rows}
        
        for scan_path in [indexes_base_path, vector_stores_path]:
            if os.path.exists(scan_path):
                for folder_name in os.listdir(scan_path):
                    folder_path = os.path.join(scan_path, folder_name)
                    if os.path.isdir(folder_path) and folder_name not in registered_names:
                        # Check if it's a valid ChromaDB folder
                        if os.path.exists(os.path.join(folder_path, "chroma.sqlite3")):
                            disk_size_bytes = get_directory_size(folder_path)
                            total_disk_size += disk_size_bytes
                            
                            vector_count = 0
                            try:
                                client = chromadb.PersistentClient(path=folder_path, settings=Settings(anonymized_telemetry=False))
                                collections = client.list_collections()
                                for coll in collections:
                                    vector_count += coll.count()
                            except Exception:
                                pass
                            
                            orphaned_dbs.append({
                                "name": folder_name,
                                "path": folder_path,
                                "disk_size_bytes": disk_size_bytes,
                                "disk_size_formatted": format_size(disk_size_bytes),
                                "vector_count": vector_count,
                                "health_status": "orphaned"
                            })
                            registered_names.add(folder_name)  # Avoid duplicates
        
        return {
            "status": "success",
            "total_vector_dbs": len(vector_dbs),
            "total_disk_size_bytes": total_disk_size,
            "total_disk_size_formatted": format_size(total_disk_size),
            "vector_dbs": vector_dbs,
            "orphaned_dbs": orphaned_dbs
        }
        
    except Exception as e:
        logger.error(f"Error listing vector databases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list vector databases: {str(e)}"
        )


@router.delete("/registry/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def delete_vector_database(
    vector_db_name: str,
    delete_files: bool = True,
    current_user: User = Depends(require_admin),
    db_service: DatabaseService = Depends(get_db_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """
    Delete a Vector Database from the registry and optionally remove its files.
    Requires Super Admin role.
    """
    import shutil
    
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # Check if exists in registry
        cursor.execute('SELECT id FROM vector_db_registry WHERE name = ?', (vector_db_name,))
        existing = cursor.fetchone()
        
        if not existing:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector DB '{vector_db_name}' not found in registry"
            )
        
        # Delete from registry
        cursor.execute('DELETE FROM vector_db_registry WHERE name = ?', (vector_db_name,))
        
        # Delete from document_index
        cursor.execute('DELETE FROM document_index WHERE vector_db_name = ?', (vector_db_name,))
        
        conn.commit()
        conn.close()
        
        # Delete schedule if exists
        try:
            scheduler_service.delete_schedule(vector_db_name)
        except Exception:
            pass
        
        # Delete files if requested
        files_deleted = False
        if delete_files:
            indexes_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/indexes"))
            vector_stores_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../vector_stores"))
            
            for base_path in [indexes_base_path, vector_stores_path]:
                chroma_path = os.path.join(base_path, vector_db_name)
                if os.path.exists(chroma_path):
                    try:
                        shutil.rmtree(chroma_path)
                        files_deleted = True
                        logger.info(f"Deleted ChromaDB folder: {chroma_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete ChromaDB folder {chroma_path}: {e}")
        
        logger.info(f"Vector DB '{vector_db_name}' deleted by {current_user.username}")
        
        return {
            "status": "success",
            "message": f"Vector DB '{vector_db_name}' deleted successfully",
            "files_deleted": files_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vector database {vector_db_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete vector database: {str(e)}"
        )
