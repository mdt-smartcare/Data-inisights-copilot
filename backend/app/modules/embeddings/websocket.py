"""
WebSocket endpoint for real-time embedding progress updates.

Provides:
- Real-time progress streaming for embedding jobs
- Authentication via query parameter token
- Automatic reconnection support
- Heartbeat for ETA refresh
"""
import asyncio
import json
from typing import Dict, Set, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.auth.security import decode_oidc_token
from app.modules.embeddings.repository import EmbeddingJobRepository
from app.modules.embeddings.schemas import EmbeddingJobStatus

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()


# ============================================
# Connection Manager
# ============================================

class ProgressConnectionManager:
    """
    Manages WebSocket connections for embedding progress updates.
    
    Tracks connections per job_id for targeted broadcasting.
    """
    
    def __init__(self):
        # job_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}")
    
    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")
    
    async def broadcast_progress(self, job_id: str, progress_data: dict) -> None:
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
    
    def get_connection_count(self, job_id: str) -> int:
        """Get number of active connections for a job."""
        return len(self.active_connections.get(job_id, set()))


# Global connection manager
manager = ProgressConnectionManager()

# Timing constants
HEARTBEAT_INTERVAL = 15.0  # Send heartbeat every 15s for ETA refresh
CHECK_INTERVAL = 1.0       # Check for updates every 1s


# ============================================
# Progress State Tracking
# ============================================

@dataclass
class ProgressState:
    """
    Tracks the last sent progress state for deduplication.
    
    Only sends updates when meaningful changes occur to reduce
    unnecessary network traffic.
    """
    processed_documents: int = 0
    failed_documents: int = 0
    status: str = ""
    phase: str = ""
    current_batch: int = 0
    
    def has_meaningful_change(self, progress) -> bool:
        """Check if progress has meaningful changes worth sending."""
        status_str = progress.status.value if hasattr(progress.status, 'value') else progress.status
        return (
            self.processed_documents != progress.processed_documents or
            self.failed_documents != progress.failed_documents or
            self.status != status_str or
            self.phase != (progress.phase or "") or
            self.current_batch != progress.current_batch
        )
    
    def update_from(self, progress) -> None:
        """Update state from progress object."""
        self.processed_documents = progress.processed_documents
        self.failed_documents = progress.failed_documents
        self.status = progress.status.value if hasattr(progress.status, 'value') else progress.status
        self.phase = progress.phase or ""
        self.current_batch = progress.current_batch


# ============================================
# Authentication Helper
# ============================================

async def verify_websocket_token(token: str) -> Optional[dict]:
    """
    Verify JWT token for WebSocket authentication.
    
    Args:
        token: JWT token from query parameter
        
    Returns:
        Decoded token payload if valid, None otherwise.
    """
    try:
        if not settings.oidc_issuer_url or not settings.oidc_client_id:
            logger.warning("OIDC not configured, WebSocket auth not available")
            return None
        
        payload = await decode_oidc_token(
            token=token,
            issuer_url=settings.oidc_issuer_url,
            client_id=settings.oidc_client_id
        )
        
        # Extract user info
        username = payload.get("preferred_username") or payload.get("email")
        external_id = payload.get("sub")
        
        if not external_id:
            return None
        
        return {
            "username": username,
            "external_id": external_id,
            "roles": payload.get("realm_access", {}).get("roles", [])
        }
        
    except Exception as e:
        logger.debug(f"WebSocket token verification failed: {e}")
        return None


# ============================================
# Progress Serialization
# ============================================

def serialize_progress(progress) -> dict:
    """
    Serialize EmbeddingJobProgress to WebSocket message format.
    
    Matches the format expected by frontend clients.
    """
    return {
        "job_id": progress.job_id,
        "status": progress.status.value if hasattr(progress.status, 'value') else progress.status,
        "phase": progress.phase,
        "progress": {
            "total_documents": progress.total_documents,
            "processed_documents": progress.processed_documents,
            "failed_documents": progress.failed_documents,
            "percentage": progress.progress_percentage,
            "current_batch": progress.current_batch,
            "total_batches": progress.total_batches,
        },
        "performance": {
            "documents_per_second": progress.documents_per_second,
            "estimated_time_remaining_seconds": progress.estimated_time_remaining_seconds,
            "elapsed_seconds": progress.elapsed_seconds,
        },
        "errors": {
            "count": progress.errors_count or 0,
            "recent": progress.recent_errors or [],
        }
    }


# ============================================
# Database Session Factory for WebSocket
# ============================================

def get_websocket_db_session():
    """
    Create an async session for WebSocket handlers.
    
    WebSocket handlers run outside the normal request lifecycle,
    so they need their own session management.
    """
    database_url = settings.postgres_async_uri
    
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    return session_factory


_ws_session_factory = None


def get_ws_session_factory():
    """Get or create the WebSocket session factory singleton."""
    global _ws_session_factory
    if _ws_session_factory is None:
        _ws_session_factory = get_websocket_db_session()
    return _ws_session_factory


# ============================================
# WebSocket Endpoint
# ============================================

@router.websocket("/embedding-progress/{job_id}")
async def embedding_progress_websocket(
    websocket: WebSocket,
    job_id: str,
    token: str = Query(None)
):
    """
    WebSocket endpoint for real-time embedding progress updates.
    
    Connect to receive progress updates every 1-2 seconds while
    an embedding job is running.
    
    Authentication:
        Pass JWT token as query parameter: ?token=<jwt_token>
    
    Messages Sent:
        ```json
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
                "estimated_time_remaining_seconds": 120
            },
            "timestamp": "2026-01-28T12:00:00Z"
        }
        ```
    
    Client Commands:
        - {"action": "ping"} - Server responds with {"event": "pong"}
    
    Events:
        - embedding_progress: Regular progress update
        - job_finished: Job completed/failed/cancelled
        - job_deleted: Job was deleted
        - pong: Response to ping
    """
    logger.info(f"WebSocket connection attempt for job {job_id}")
    
    # Verify authentication
    if not token:
        logger.warning(f"WebSocket for job {job_id}: No token provided")
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    token_data = await verify_websocket_token(token)
    if not token_data:
        logger.warning(f"WebSocket for job {job_id}: Token verification failed")
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    logger.info(f"WebSocket for job {job_id}: Auth passed for user {token_data.get('username')}")
    
    # Get database session for WebSocket
    session_factory = get_ws_session_factory()
    
    async with session_factory() as db:
        repo = EmbeddingJobRepository(db)
        
        # Check if job exists
        job = await repo.get_by_id(job_id)
        if not job:
            logger.warning(f"WebSocket for job {job_id}: Job not found in database")
            await websocket.close(code=4004, reason="Job not found")
            return
        
        logger.info(f"WebSocket for job {job_id}: Job found, status={job.status}")
        await manager.connect(websocket, job_id)
        
        try:
            # Send initial progress
            from app.modules.embeddings.service import EmbeddingJobService
            service = EmbeddingJobService(db)
            progress = await service.get_progress(job_id)
            
            if progress:
                initial_msg = {
                    "event": "embedding_progress",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **serialize_progress(progress)
                }
                logger.info(f"WebSocket for job {job_id}: Sending initial progress, status={progress.status}")
                await websocket.send_json(initial_msg)
            
            # Track state for deduplication
            last_state = ProgressState()
            if progress:
                last_state.update_from(progress)
            
            last_heartbeat = asyncio.get_event_loop().time()
            
            # Keep connection alive and send updates
            while True:
                try:
                    # Wait for client messages (ping/pong or close)
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
                    # Expire all cached objects to ensure we get fresh data from the database
                    db.expire_all()
                    progress = await service.get_progress(job_id)
                    
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
                        await websocket.send_json({
                            "event": "embedding_progress",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            **serialize_progress(progress)
                        })
                        last_state.update_from(progress)
                        last_heartbeat = current_time
                        
                        if has_change:
                            logger.debug(f"Job {job_id}: Sent update (change detected)")
                        else:
                            logger.debug(f"Job {job_id}: Sent heartbeat (ETA refresh)")
                    
                    # Check if job is complete
                    if progress.status in (
                        EmbeddingJobStatus.COMPLETED,
                        EmbeddingJobStatus.FAILED,
                        EmbeddingJobStatus.CANCELLED
                    ):
                        await websocket.send_json({
                            "event": "job_finished",
                            "job_id": job_id,
                            "status": progress.status.value,
                            "final_progress": progress.progress_percentage
                        })
                        # Keep connection open briefly for client to receive
                        await asyncio.sleep(1)
                        break
        
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected for job {job_id}")
        except Exception as e:
            logger.error(f"WebSocket error for job {job_id}: {e}")
        finally:
            manager.disconnect(websocket, job_id)


# ============================================
# Broadcast Helper (for external use)
# ============================================

async def broadcast_job_progress(job_id: str, progress_data: dict) -> None:
    """
    Broadcast progress update to all connected WebSocket clients.
    
    Call this from the embedding service when progress changes.
    
    Args:
        job_id: The job identifier
        progress_data: Progress data dictionary
    """
    await manager.broadcast_progress(job_id, progress_data)
