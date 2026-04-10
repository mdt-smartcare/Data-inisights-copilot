"""
Background download manager for AI models.

Handles:
- Background model downloads with progress tracking
- Download queue management
- Progress polling
- Cancellation support

Uses FastAPI BackgroundTasks + database state for persistence.
"""
import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.core.settings import get_settings
from .huggingface_service import HuggingFaceHubService, get_hf_service


logger = logging.getLogger(__name__)


async def update_model_download_status(
    model_id: int, 
    status: str, 
    progress: int = 0, 
    error: Optional[str] = None,
    local_path: Optional[str] = None
):
    """
    Update model download status directly in the database.
    
    This is called from background tasks when a download completes
    to ensure the status is persisted immediately.
    """
    try:
        from app.core.database.connection import get_database
        from app.modules.ai_models.models import AIModel
        
        db = get_database()
        if db is None or not db.is_connected:
            logger.error("Database not connected, cannot update download status")
            return
        
        async with db.session() as session:
            # Build update statement
            values = {
                'download_status': status,
                'download_progress': progress,
                'download_error': error,
            }
            if local_path:
                values['local_path'] = local_path
            
            stmt = (
                update(AIModel)
                .where(AIModel.id == model_id)
                .values(**values)
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(f"Updated model {model_id} download status to '{status}'")
    except Exception as e:
        logger.error(f"Failed to update download status for model {model_id}: {e}")


class DownloadProgress:
    """Tracks download progress for a single model."""
    
    def __init__(self, model_id: int, hf_model_id: str, local_path: str):
        self.model_id = model_id
        self.hf_model_id = hf_model_id
        self.local_path = local_path
        self.status = "pending"  # pending, downloading, ready, error, not_downloaded
        self.progress_percent = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.error_message: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of this download."""
        self._cancelled = True
        self.status = "not_downloaded"
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "hf_model_id": self.hf_model_id,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DownloadManager:
    """
    Manages background model downloads.
    
    Example:
        manager = get_download_manager()
        
        # Start download
        job_id = await manager.start_download(
            model_id=1,
            hf_model_id="BAAI/bge-base-en-v1.5",
            local_path="./data/models/BAAI/bge-base-en-v1.5"
        )
        
        # Check progress
        progress = manager.get_progress(model_id=1)
        print(progress.progress_percent)
        
        # Cancel
        manager.cancel_download(model_id=1)
    """
    
    def __init__(self):
        self._downloads: Dict[int, DownloadProgress] = {}  # model_id -> progress
        self._tasks: Dict[int, asyncio.Task] = {}  # model_id -> asyncio task
        self._queue: list = []  # Queue of pending downloads: (model_id, hf_model_id, local_path, revision, on_complete)
        self._current_download: Optional[int] = None  # Currently downloading model_id
        self._lock = asyncio.Lock()
        self._hf_service = get_hf_service()
    
    async def start_download(
        self,
        model_id: int,
        hf_model_id: str,
        local_path: str,
        revision: str = "main",
        on_complete: Optional[Callable[[int, bool, Optional[str]], None]] = None
    ) -> DownloadProgress:
        """
        Queue a background download. Only one download runs at a time.
        
        Args:
            model_id: Database model ID
            hf_model_id: HuggingFace model ID (e.g., 'BAAI/bge-base-en-v1.5')
            local_path: Local directory to save model
            revision: Git revision (default 'main')
            on_complete: Optional callback(model_id, success, error_message)
            
        Returns:
            DownloadProgress tracker
        """
        async with self._lock:
            # Check if already in progress or queued
            if model_id in self._downloads:
                existing = self._downloads[model_id]
                if existing.status in ("pending", "downloading"):
                    return existing
            
            # Create progress tracker (starts in pending state)
            progress = DownloadProgress(model_id, hf_model_id, local_path)
            self._downloads[model_id] = progress
            
            # If nothing is currently downloading, start immediately
            if self._current_download is None:
                self._current_download = model_id
                task = asyncio.create_task(
                    self._download_task(progress, revision, on_complete)
                )
                self._tasks[model_id] = task
            else:
                # Add to queue - will be processed when current download finishes
                self._queue.append((model_id, hf_model_id, local_path, revision, on_complete))
                logger.info(f"Queued download for {hf_model_id} (position {len(self._queue)})")
            
            return progress
    
    async def _process_queue(self):
        """Start the next download in the queue if any."""
        async with self._lock:
            if not self._queue:
                self._current_download = None
                return
            
            # Get next item from queue
            model_id, hf_model_id, local_path, revision, on_complete = self._queue.pop(0)
            
            # Get existing progress tracker
            progress = self._downloads.get(model_id)
            if not progress:
                # Shouldn't happen, but create one just in case
                progress = DownloadProgress(model_id, hf_model_id, local_path)
                self._downloads[model_id] = progress
            
            self._current_download = model_id
            logger.info(f"Starting queued download for {hf_model_id}")
            
            task = asyncio.create_task(
                self._download_task(progress, revision, on_complete)
            )
            self._tasks[model_id] = task
    
    async def _download_task(
        self,
        progress: DownloadProgress,
        revision: str,
        on_complete: Optional[Callable[[int, bool, Optional[str]], None]]
    ):
        """Background download task."""
        try:
            progress.status = "downloading"
            progress.started_at = datetime.utcnow()
            
            # Update DB status immediately
            await update_model_download_status(progress.model_id, "downloading", 5)
            
            # Ensure directory exists
            local_dir = Path(progress.local_path)
            local_dir.mkdir(parents=True, exist_ok=True)
            
            # Check cancellation
            if progress.is_cancelled:
                return
            
            # Update progress
            progress.progress_percent = 5
            
            # Get expected model size (estimate) from HF
            expected_size = await self._get_expected_model_size(progress.hf_model_id)
            if expected_size:
                progress.total_bytes = expected_size
            
            # Start download in background and monitor progress
            download_task = asyncio.create_task(
                self._hf_service.download_model(
                    model_id=progress.hf_model_id,
                    local_path=progress.local_path,
                    revision=revision
                )
            )
            
            # Monitor download progress while waiting
            while not download_task.done():
                if progress.is_cancelled:
                    download_task.cancel()
                    break
                
                # Calculate current downloaded size
                current_size = self._get_directory_size(local_dir)
                progress.downloaded_bytes = current_size
                
                # Calculate percentage
                if progress.total_bytes and progress.total_bytes > 0:
                    pct = min(95, int((current_size / progress.total_bytes) * 100))
                else:
                    # No expected size - use time-based estimate
                    elapsed = (datetime.utcnow() - progress.started_at).total_seconds()
                    pct = min(90, 5 + int(elapsed / 2))  # Gradual increase over time
                
                progress.progress_percent = max(progress.progress_percent, pct)
                
                # Update DB periodically (every ~10% change or every iteration)
                await update_model_download_status(
                    progress.model_id, "downloading", progress.progress_percent
                )
                
                await asyncio.sleep(2)  # Check every 2 seconds
            
            # Get result
            try:
                success = await download_task
            except asyncio.CancelledError:
                success = False
            
            if progress.is_cancelled:
                # Clean up partial download
                if local_dir.exists():
                    shutil.rmtree(local_dir, ignore_errors=True)
                await update_model_download_status(progress.model_id, "not_downloaded", 0)
                return
            
            if success:
                progress.status = "ready"
                progress.progress_percent = 100
                progress.completed_at = datetime.utcnow()
                
                # Calculate final downloaded size
                if local_dir.exists():
                    total_size = self._get_directory_size(local_dir)
                    progress.downloaded_bytes = total_size
                    progress.total_bytes = total_size
                
                # Update DB to ready
                await update_model_download_status(
                    progress.model_id, "ready", 100, None, progress.local_path
                )
            else:
                progress.status = "error"
                progress.error_message = "Download failed - check logs for details"
                await update_model_download_status(
                    progress.model_id, "error", 0, progress.error_message
                )
            
            # Callback
            if on_complete:
                try:
                    on_complete(
                        progress.model_id,
                        success,
                        progress.error_message
                    )
                except Exception as e:
                    logger.error(f"Download callback error: {e}")
                    
        except asyncio.CancelledError:
            progress.status = "not_downloaded"
            await update_model_download_status(progress.model_id, "not_downloaded", 0)
            raise
        except Exception as e:
            logger.exception(f"Download failed for {progress.hf_model_id}")
            progress.status = "error"
            progress.error_message = str(e)
            await update_model_download_status(progress.model_id, "error", 0, str(e))
            
            if on_complete:
                try:
                    on_complete(progress.model_id, False, str(e))
                except Exception:
                    pass
        finally:
            # Process next item in queue
            asyncio.create_task(self._process_queue())
    
    def _get_directory_size(self, path: Path) -> int:
        """Get total size of all files in directory (in bytes)."""
        if not path.exists():
            return 0
        try:
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        except Exception:
            return 0
    
    async def _get_expected_model_size(self, hf_model_id: str) -> Optional[int]:
        """
        Try to get expected model size from HuggingFace API.
        
        Returns estimated total size in bytes, or None if unavailable.
        """
        try:
            info = await self._hf_service.get_model_info(hf_model_id)
            if info:
                # Common model sizes (estimates)
                model_sizes = {
                    'bge-base-en-v1.5': 2_200_000_000,  # ~2.2GB
                    'bge-small': 130_000_000,  # ~130MB
                    'bge-base': 440_000_000,  # ~440MB
                    'bge-large': 1_340_000_000,  # ~1.34GB
                    'bge-reranker-v2-m3': 1_100_000_000,  # ~1.1GB
                    'bge-reranker-base': 280_000_000,  # ~280MB
                    'e5-small': 130_000_000,
                    'e5-base': 440_000_000,
                    'e5-large': 1_340_000_000,
                }
                
                # Check if we have a known estimate
                model_name = hf_model_id.split('/')[-1].lower()
                for key, size in model_sizes.items():
                    if key in model_name:
                        return size
                
                # Default estimate based on model type
                if 'small' in model_name:
                    return 150_000_000
                elif 'base' in model_name:
                    return 500_000_000
                elif 'large' in model_name:
                    return 1_500_000_000
                else:
                    return 1_000_000_000  # 1GB default estimate
        except Exception as e:
            logger.debug(f"Could not get model size estimate: {e}")
        
        return None
    
    def get_progress(self, model_id: int) -> Optional[DownloadProgress]:
        """Get download progress for a model."""
        return self._downloads.get(model_id)
    
    def get_queue_position(self, model_id: int) -> Optional[int]:
        """Get queue position for a pending model (1-based). Returns None if not queued."""
        for i, (m, _, _, _, _) in enumerate(self._queue):
            if m == model_id:
                return i + 1
        return None
    
    def get_queue_size(self) -> int:
        """Get number of models waiting in queue."""
        return len(self._queue)
    
    def get_all_downloads(self) -> Dict[int, DownloadProgress]:
        """Get all download progress trackers."""
        return dict(self._downloads)
    
    async def cancel_download(self, model_id: int) -> bool:
        """
        Cancel a download.
        
        Returns:
            True if cancelled, False if not found or already completed
        """
        async with self._lock:
            progress = self._downloads.get(model_id)
            if not progress:
                return False
            
            if progress.status not in ("pending", "downloading"):
                return False
            
            was_current = (self._current_download == model_id)
            
            progress.cancel()
            
            # Remove from queue if pending
            self._queue = [(m, h, l, r, c) for m, h, l, r, c in self._queue if m != model_id]
            
            # Cancel task
            task = self._tasks.get(model_id)
            if task and not task.done():
                task.cancel()
            
            # Clean up partial download
            local_dir = Path(progress.local_path)
            if local_dir.exists():
                shutil.rmtree(local_dir, ignore_errors=True)
            
            # If this was the current download, clear it and process queue
            if was_current:
                self._current_download = None
        
        # Process queue outside the lock (will acquire it internally)
        if was_current:
            await self._process_queue()
        
        return True
    
    async def cleanup_completed(self, older_than_hours: int = 24):
        """Remove completed/failed downloads from memory."""
        async with self._lock:
            cutoff = datetime.utcnow()
            to_remove = []
            
            for model_id, progress in self._downloads.items():
                if progress.status in ("completed", "failed", "cancelled"):
                    if progress.completed_at:
                        age_hours = (cutoff - progress.completed_at).total_seconds() / 3600
                        if age_hours > older_than_hours:
                            to_remove.append(model_id)
            
            for model_id in to_remove:
                del self._downloads[model_id]
                self._tasks.pop(model_id, None)


# Singleton instance
_download_manager: Optional[DownloadManager] = None


def get_download_manager() -> DownloadManager:
    """Get or create the download manager singleton."""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager()
    return _download_manager
