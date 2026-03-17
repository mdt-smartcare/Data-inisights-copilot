"""
WebSocket endpoint for real-time embedding progress updates.
"""
import asyncio
import json
from typing import Dict, Set, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import Optional

from backend.config import get_settings
from backend.services.embedding_job_service import get_embedding_job_service
from backend.core.logging import get_logger
from backend.core.security import decode_keycloak_token
from backend.sqliteDb.db import get_db_service

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

# Heartbeat interval for ETA refresh (seconds)
HEARTBEAT_INTERVAL = 15.0
# Check interval (how often to poll job state)
CHECK_INTERVAL = 1.0


@dataclass
class ProgressState:
    """Tracks the last sent progress state for deduplication."""
    processed_documents: int = 0
    failed_documents: int = 0
    status: str = ""
    phase: str = ""
    errors_count: int = 0
    
    def has_meaningful_change(self, progress) -> bool:
        """Check if progress has meaningful changes worth sending."""
        status_str = progress.status.value if hasattr(progress.status, 'value') else progress.status
        return (
            self.processed_documents != progress.processed_documents or
            self.failed_documents != progress.failed_documents or
            self.status != status_str or
            self.phase != progress.phase or
            self.errors_count != progress.errors_count
        )
    
    def update_from(self, progress) -> None:
        """Update state from progress object."""
        self.processed_documents = progress.processed_documents
        self.failed_documents = progress.failed_documents
        self.status = progress.status.value if hasattr(progress.status, 'value') else progress.status
        self.phase = progress.phase
        self.errors_count = progress.errors_count


async def verify_token(token: str) -> Optional[dict]:
    """
    Verify Keycloak JWT token for WebSocket authentication.
    
    Returns:
        Decoded token payload if valid, None otherwise.
    """
    try:
        # Use Keycloak token verification
        if settings.oidc_issuer_url and settings.oidc_client_id:
            payload = await decode_keycloak_token(
                token=token,
                issuer_url=settings.oidc_issuer_url,
                client_id=settings.oidc_client_id
            )
            # Extract user info from Keycloak token
            username = payload.get("preferred_username") or payload.get("email")
            external_id = payload.get("sub")
            if not external_id:
                return None
            
            # Look up database user ID from external_id (Keycloak sub)
            db_service = get_db_service()
            user_data = db_service.get_user_by_external_id(external_id)
            if not user_data:
                logger.warning(f"No database user found for external_id {external_id}")
                return None
            
            return {"username": username, "user_id": user_data['id'], "external_id": external_id}
        else:
            logger.warning("OIDC not configured, WebSocket auth not available")
            return None
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None


@router.websocket("/embedding-progress/{job_id}")
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
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    token_data = await verify_token(token)
    if not token_data:
        await websocket.close(code=4001, reason="Invalid token")
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
        
        # Track last sent state for deduplication
        last_state = ProgressState()
        initial_progress = job_service.get_job_progress(job_id)
        if initial_progress:
            last_state.update_from(initial_progress)
        
        last_heartbeat = asyncio.get_event_loop().time()
        
        # Keep connection alive and send updates
        while True:
            try:
                # Wait for client messages (ping/pong or close)
                # Use short timeout for responsive change detection
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=CHECK_INTERVAL
                )
                
                # Handle client commands
                try:
                    data = json.loads(message)
                    if data.get("action") == "ping":
                        await websocket.send_json({"event": "pong"})
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Timeout means no client message - check for updates
                progress = job_service.get_job_progress(job_id)
                
                if not progress:
                    # Job was deleted
                    await websocket.send_json({
                        "event": "job_deleted",
                        "job_id": job_id
                    })
                    break
                
                current_time = asyncio.get_event_loop().time()
                time_since_heartbeat = current_time - last_heartbeat
                
                # Send update if: meaningful change OR heartbeat interval reached
                has_change = last_state.has_meaningful_change(progress)
                needs_heartbeat = time_since_heartbeat >= HEARTBEAT_INTERVAL
                
                if has_change or needs_heartbeat:
                    await send_progress_update(websocket, job_id, job_service)
                    last_state.update_from(progress)
                    last_heartbeat = current_time
                    
                    if has_change:
                        logger.debug(f"Job {job_id}: Sent update (change detected)")
                    else:
                        logger.debug(f"Job {job_id}: Sent heartbeat (ETA refresh)")
                
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
