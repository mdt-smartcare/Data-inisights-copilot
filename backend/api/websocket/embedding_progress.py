"""
WebSocket endpoint for real-time embedding progress updates.
"""
import asyncio
import json
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from jose import JWTError, jwt

from backend.config import get_settings
from backend.services.embedding_job_service import get_embedding_job_service
from backend.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()

# Connection manager for WebSocket clients
class ProgressConnectionManager:
    """Manages WebSocket connections for embedding progress updates."""
    
    def __init__(self):
        # job_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}")
    
    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")
    
    async def broadcast_progress(self, job_id: str, progress_data: dict):
        """Send progress update to all connections watching a job."""
        if job_id not in self.active_connections:
            return
        
        message = json.dumps({
            "event": "embedding_progress",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **progress_data
        })
        
        dead_connections = set()
        for connection in self.active_connections[job_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[job_id].discard(conn)


# Global connection manager
manager = ProgressConnectionManager()


def verify_token(token: str) -> bool:
    """Verify JWT token for WebSocket authentication."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        return username is not None
    except JWTError:
        return False


@router.websocket("/ws/embedding-progress/{job_id}")
async def embedding_progress_websocket(
    websocket: WebSocket,
    job_id: str,
    token: str = Query(None)
):
    """
    WebSocket endpoint for real-time embedding progress updates.
    
    Connect to this endpoint to receive progress updates every 1-2 seconds
    while an embedding job is running.
    
    Authentication:
        Pass JWT token as query parameter: ?token=<jwt_token>
    
    Messages Sent:
        {
            "event": "embedding_progress",
            "job_id": "emb-job-abc123",
            "status": "EMBEDDING",
            "progress": {
                "total_documents": 1247,
                "processed_documents": 935,
                "percentage": 75.0,
                "current_batch": 19,
                "total_batches": 25
            },
            "performance": {
                "documents_per_second": 7.8,
                "estimated_time_remaining_seconds": 120,
                "elapsed_seconds": 60
            },
            "timestamp": "2026-01-28T12:00:00Z"
        }
    """
    # Verify authentication
    if not token or not verify_token(token):
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    job_service = get_embedding_job_service()
    
    # Check if job exists
    initial_progress = job_service.get_job_progress(job_id)
    if not initial_progress:
        await websocket.close(code=4004, reason="Job not found")
        return
    
    await manager.connect(websocket, job_id)
    
    try:
        # Send initial progress immediately
        await send_progress_update(websocket, job_id, job_service)
        
        # Keep connection alive and send updates
        while True:
            try:
                # Wait for client messages (ping/pong or close)
                # Use a shorter timeout to send progress updates regularly
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=2.0  # Send updates every 2 seconds
                )
                
                # Handle client commands
                try:
                    data = json.loads(message)
                    if data.get("action") == "ping":
                        await websocket.send_json({"event": "pong"})
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Timeout means no client message - send progress update
                progress = job_service.get_job_progress(job_id)
                
                if not progress:
                    # Job was deleted
                    await websocket.send_json({
                        "event": "job_deleted",
                        "job_id": job_id
                    })
                    break
                
                await send_progress_update(websocket, job_id, job_service)
                
                # Check if job is complete
                if progress.status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    await websocket.send_json({
                        "event": "job_finished",
                        "job_id": job_id,
                        "status": progress.status.value if hasattr(progress.status, 'value') else progress.status,
                        "final_progress": progress.progress_percentage
                    })
                    # Keep connection open for a bit for client to receive final message
                    await asyncio.sleep(1)
                    break
                    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
    finally:
        manager.disconnect(websocket, job_id)


async def send_progress_update(websocket: WebSocket, job_id: str, job_service):
    """Send a progress update to a single WebSocket."""
    progress = job_service.get_job_progress(job_id)
    if not progress:
        return
    
    message = {
        "event": "embedding_progress",
        "job_id": progress.job_id,
        "status": progress.status.value if hasattr(progress.status, 'value') else progress.status,
        "phase": progress.phase,
        "progress": {
            "total_documents": progress.total_documents,
            "processed_documents": progress.processed_documents,
            "failed_documents": progress.failed_documents,
            "percentage": round(progress.progress_percentage, 1),
            "current_batch": progress.current_batch,
            "total_batches": progress.total_batches
        },
        "performance": {
            "documents_per_second": round(progress.documents_per_second, 2) if progress.documents_per_second else None,
            "estimated_time_remaining_seconds": progress.estimated_time_remaining_seconds,
            "elapsed_seconds": progress.elapsed_seconds
        },
        "errors": {
            "count": progress.errors_count,
            "recent": progress.recent_errors
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await websocket.send_json(message)


async def broadcast_to_job_watchers(job_id: str, progress_data: dict):
    """Broadcast progress to all clients watching a job."""
    await manager.broadcast_progress(job_id, progress_data)
