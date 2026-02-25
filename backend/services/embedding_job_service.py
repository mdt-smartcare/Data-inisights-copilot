"""
Embedding job service for managing embedding generation lifecycle.
Provides real-time progress tracking and job state management.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import uuid
import json
import math

from backend.models.rag_models import (
    EmbeddingJobStatus, EmbeddingJobProgress, EmbeddingJobSummary,
    EmbeddingJobCreate
)
from backend.models.schemas import User
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service

logger = get_logger(__name__)


class EmbeddingJobService:
    """
    Service for managing embedding job lifecycle and progress tracking.
    
    State Machine:
    QUEUED -> PREPARING -> EMBEDDING -> VALIDATING -> STORING -> COMPLETED
    
    Any state can transition to FAILED or CANCELLED.
    """
    
    def __init__(self):
        self.db = get_db_service()
    
    def create_job(
        self,
        config_id: int,
        total_documents: int,
        user: User,
        batch_size: int = 50,
        max_concurrent: int = 5
    ) -> str:
        """
        Create a new embedding job.
        
        Args:
            config_id: RAG configuration to process
            total_documents: Total number of documents to embed
            user: User starting the job
            batch_size: Documents per batch
            max_concurrent: Max concurrent batch processing
            
        Returns:
            Unique job ID
        """
        job_id = f"emb-job-{uuid.uuid4().hex[:12]}"
        total_batches = math.ceil(total_documents / batch_size)
        
        config_metadata = json.dumps({
            "batch_size": batch_size,
            "max_concurrent": max_concurrent,
            "retry_attempts": 3,
            "retry_delay_seconds": 5
        })
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO embedding_jobs 
                (job_id, config_id, status, phase, total_documents, total_batches, 
                 batch_size, started_by, config_metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, config_id, EmbeddingJobStatus.QUEUED.value,
                "Job queued for processing", total_documents, total_batches,
                batch_size, user.id, config_metadata
            ))
            
            conn.commit()
            logger.info(f"Created embedding job {job_id} for config {config_id}")
            
            return job_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create embedding job: {e}")
            raise
        finally:
            conn.close()
    
    def start_job(self, job_id: str) -> None:
        """Mark job as started and transition to PREPARING state."""
        self._update_job(
            job_id,
            status=EmbeddingJobStatus.PREPARING,
            phase="Generating documents from schema",
            started_at=datetime.now(timezone.utc).isoformat()
        )
        self._log_event(job_id, "job_started", {"status": "PREPARING"})
    
    def update_progress(
        self,
        job_id: str,
        processed_documents: int,
        current_batch: int,
        failed_documents: int = 0,
        phase: Optional[str] = None
    ) -> None:
        """
        Update job progress metrics.
        
        Args:
            job_id: The job to update
            processed_documents: Total documents processed so far
            current_batch: Current batch being processed
            failed_documents: Number of failed documents
            phase: Optional phase description update
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get total documents for percentage calculation
            cursor.execute(
                "SELECT total_documents, started_at FROM embedding_jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Job {job_id} not found for progress update")
                return
            
            total_documents = row['total_documents']
            started_at = row['started_at']
            
            # Calculate progress percentage
            progress_percentage = (processed_documents / total_documents * 100) if total_documents > 0 else 0
            
            # Calculate speed and ETA
            docs_per_second = None
            estimated_completion = None
            
            if started_at:
                try:
                    start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    if elapsed > 0 and processed_documents > 0:
                        docs_per_second = processed_documents / elapsed
                        remaining_docs = total_documents - processed_documents
                        if docs_per_second > 0:
                            remaining_seconds = remaining_docs / docs_per_second
                            estimated_completion = (datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)).isoformat()
                except Exception as e:
                    logger.debug(f"Error calculating ETA: {e}")
            
            # Build update query
            update_fields = [
                "processed_documents = ?",
                "current_batch = ?",
                "failed_documents = ?",
                "progress_percentage = ?"
            ]
            params = [processed_documents, current_batch, failed_documents, progress_percentage]
            
            if docs_per_second is not None:
                update_fields.append("documents_per_second = ?")
                params.append(docs_per_second)
            
            if estimated_completion:
                update_fields.append("estimated_completion_at = ?")
                params.append(estimated_completion)
            
            if phase:
                update_fields.append("phase = ?")
                params.append(phase)
            
            params.append(job_id)
            
            cursor.execute(
                f"UPDATE embedding_jobs SET {', '.join(update_fields)} WHERE job_id = ?",
                params
            )
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to update job progress: {e}")
        finally:
            conn.close()
    
    def transition_to_embedding(self, job_id: str) -> None:
        """Transition job to EMBEDDING state."""
        self._update_job(
            job_id,
            status=EmbeddingJobStatus.EMBEDDING,
            phase="Generating embeddings"
        )
        self._log_event(job_id, "status_change", {"from": "PREPARING", "to": "EMBEDDING"})
    
    def transition_to_validating(self, job_id: str) -> None:
        """Transition job to VALIDATING state."""
        self._update_job(
            job_id,
            status=EmbeddingJobStatus.VALIDATING,
            phase="Running quality checks"
        )
        self._log_event(job_id, "status_change", {"from": "EMBEDDING", "to": "VALIDATING"})
    
    def transition_to_storing(self, job_id: str) -> None:
        """Transition job to STORING state."""
        self._update_job(
            job_id,
            status=EmbeddingJobStatus.STORING,
            phase="Persisting vectors to database"
        )
        self._log_event(job_id, "status_change", {"from": "VALIDATING", "to": "STORING"})
    
    def complete_job(
        self,
        job_id: str,
        embedding_version_id: Optional[int] = None,
        validation_passed: bool = True
    ) -> None:
        """
        Mark job as successfully completed.
        
        Args:
            job_id: The job to complete
            embedding_version_id: Optional resulting embedding version ID
            validation_passed: Whether validation checks passed
        """
        completed_at = datetime.now(timezone.utc).isoformat()
        
        updates = {
            "status": EmbeddingJobStatus.COMPLETED,
            "phase": "Completed successfully",
            "completed_at": completed_at
        }
        
        if embedding_version_id:
            updates["embedding_version_id"] = embedding_version_id
        
        self._update_job(job_id, **updates)
        self._log_event(job_id, "job_completed", {
            "status": "COMPLETED",
            "validation_passed": validation_passed
        })
        
        logger.info(f"Embedding job {job_id} completed successfully")
    
    def fail_job(self, job_id: str, error_message: str, error_details: Optional[dict] = None) -> None:
        """
        Mark job as failed.
        
        Args:
            job_id: The job that failed
            error_message: Human-readable error message
            error_details: Optional detailed error information
        """
        completed_at = datetime.now(timezone.utc).isoformat()
        error_details_json = json.dumps(error_details) if error_details else None
        
        self._update_job(
            job_id,
            status=EmbeddingJobStatus.FAILED,
            phase="Failed",
            completed_at=completed_at,
            error_message=error_message,
            error_details=error_details_json
        )
        
        self._log_event(job_id, "job_failed", {
            "error_message": error_message,
            "error_details": error_details
        })
        
        logger.error(f"Embedding job {job_id} failed: {error_message}")
    
    def cancel_job(self, job_id: str, user: User) -> bool:
        """
        Cancel a running job.
        
        Args:
            job_id: The job to cancel
            user: User requesting cancellation
            
        Returns:
            True if cancelled, False if job was not in cancellable state
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check current status
            cursor.execute(
                "SELECT status FROM embedding_jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            current_status = row['status']
            cancellable_states = [
                EmbeddingJobStatus.QUEUED.value,
                EmbeddingJobStatus.PREPARING.value,
                EmbeddingJobStatus.EMBEDDING.value
            ]
            
            if current_status not in cancellable_states:
                logger.warning(f"Cannot cancel job {job_id} in state {current_status}")
                return False
            
            # Cancel the job
            cursor.execute("""
                UPDATE embedding_jobs 
                SET status = ?, phase = ?, completed_at = ?, cancelled_by = ?
                WHERE job_id = ?
            """, (
                EmbeddingJobStatus.CANCELLED.value,
                "Cancelled by user",
                datetime.now(timezone.utc).isoformat(),
                user.id,
                job_id
            ))
            
            conn.commit()
            
            self._log_event(job_id, "job_cancelled", {"cancelled_by": user.username})
            logger.info(f"Embedding job {job_id} cancelled by {user.username}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel job: {e}")
            return False
        finally:
            conn.close()
    
    def get_job_config(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the configuration metadata for a job."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT config_metadata FROM embedding_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row or not row['config_metadata']:
                return None
            return json.loads(row['config_metadata'])
        except Exception as e:
            logger.error(f"Failed to get job config: {e}")
            return None
        finally:
            conn.close()

    def get_job_progress(self, job_id: str) -> Optional[EmbeddingJobProgress]:
        """
        Get current progress for a job.
        
        Args:
            job_id: The job to get progress for
            
        Returns:
            EmbeddingJobProgress object or None if not found
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM embedding_jobs WHERE job_id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job = dict(row)
            
            # Calculate elapsed time
            elapsed_seconds = None
            if job.get('started_at'):
                try:
                    start_time = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                    elapsed_seconds = int((datetime.now(timezone.utc) - start_time).total_seconds())
                except:
                    pass
            
            # Calculate ETA in seconds
            eta_seconds = None
            if job.get('estimated_completion_at'):
                try:
                    eta_time = datetime.fromisoformat(job['estimated_completion_at'].replace('Z', '+00:00'))
                    eta_seconds = max(0, int((eta_time - datetime.now(timezone.utc)).total_seconds()))
                except:
                    pass
            
            # Get recent errors
            recent_errors = []
            cursor.execute("""
                SELECT event_data FROM embedding_job_events 
                WHERE job_id = (SELECT id FROM embedding_jobs WHERE job_id = ?)
                AND event_type = 'error'
                ORDER BY timestamp DESC LIMIT 5
            """, (job_id,))
            for err_row in cursor.fetchall():
                try:
                    err_data = json.loads(err_row['event_data'])
                    recent_errors.append(err_data.get('message', 'Unknown error'))
                except:
                    pass
            
            return EmbeddingJobProgress(
                job_id=job['job_id'],
                status=EmbeddingJobStatus(job['status']),
                phase=job.get('phase'),
                total_documents=job['total_documents'],
                processed_documents=job.get('processed_documents', 0),
                failed_documents=job.get('failed_documents', 0),
                progress_percentage=job.get('progress_percentage', 0.0),
                current_batch=job.get('current_batch', 0),
                total_batches=job['total_batches'],
                documents_per_second=job.get('documents_per_second'),
                estimated_time_remaining_seconds=eta_seconds,
                elapsed_seconds=elapsed_seconds,
                errors_count=job.get('failed_documents', 0),
                recent_errors=recent_errors,
                started_at=datetime.fromisoformat(job['started_at']) if job.get('started_at') else None,
                completed_at=datetime.fromisoformat(job['completed_at']) if job.get('completed_at') else None
            )
            
        except Exception as e:
            logger.error(f"Failed to get job progress: {e}")
            return None
        finally:
            conn.close()
    
    def get_job_summary(self, job_id: str) -> Optional[EmbeddingJobSummary]:
        """Get summary for a completed job."""
        progress = self.get_job_progress(job_id)
        if not progress:
            return None
        
        duration = None
        avg_speed = None
        
        if progress.started_at and progress.completed_at:
            duration = (progress.completed_at - progress.started_at).total_seconds()
            if duration > 0 and progress.processed_documents > 0:
                avg_speed = progress.processed_documents / duration
        
        return EmbeddingJobSummary(
            job_id=progress.job_id,
            status=progress.status,
            total_documents=progress.total_documents,
            processed_documents=progress.processed_documents,
            failed_documents=progress.failed_documents,
            duration_seconds=duration,
            average_speed=avg_speed,
            validation_passed=progress.failed_documents == 0,
            started_at=progress.started_at,
            completed_at=progress.completed_at
        )
    
    def list_jobs(
        self,
        user_id: Optional[int] = None,
        config_id: Optional[int] = None,
        status: Optional[EmbeddingJobStatus] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[EmbeddingJobProgress]:
        """
        List embedding jobs with optional filters.
        
        Args:
            user_id: Filter by user who started the job
            config_id: Filter by configuration ID
            status: Filter by job status
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of job progress objects
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT job_id FROM embedding_jobs WHERE 1=1"
            params = []
            
            if user_id is not None:
                query += " AND started_by = ?"
                params.append(user_id)
            
            if config_id is not None:
                query += " AND config_id = ?"
                params.append(config_id)
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            job_ids = [row['job_id'] for row in cursor.fetchall()]
            
        finally:
            conn.close()
        
        return [self.get_job_progress(jid) for jid in job_ids if self.get_job_progress(jid)]
    
    def _update_job(self, job_id: str, **kwargs) -> None:
        """Update job fields."""
        if not kwargs:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Handle enum values
            if 'status' in kwargs and isinstance(kwargs['status'], EmbeddingJobStatus):
                kwargs['status'] = kwargs['status'].value
            
            fields = [f"{k} = ?" for k in kwargs.keys()]
            values = list(kwargs.values()) + [job_id]
            
            cursor.execute(
                f"UPDATE embedding_jobs SET {', '.join(fields)} WHERE job_id = ?",
                values
            )
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to update job: {e}")
        finally:
            conn.close()
    
    def _log_event(self, job_id: str, event_type: str, event_data: Optional[dict] = None) -> None:
        """Log a job event."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get internal job ID
            cursor.execute("SELECT id FROM embedding_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return
            
            internal_id = row['id']
            event_json = json.dumps(event_data) if event_data else None
            
            cursor.execute("""
                INSERT INTO embedding_job_events (job_id, event_type, event_data)
                VALUES (?, ?, ?)
            """, (internal_id, event_type, event_json))
            
            conn.commit()
            
        except Exception as e:
            logger.debug(f"Failed to log job event: {e}")
        finally:
            conn.close()


# Singleton instance
_embedding_job_service: Optional[EmbeddingJobService] = None


def get_embedding_job_service() -> EmbeddingJobService:
    """Get or create the embedding job service singleton."""
    global _embedding_job_service
    if _embedding_job_service is None:
        _embedding_job_service = EmbeddingJobService()
    return _embedding_job_service
