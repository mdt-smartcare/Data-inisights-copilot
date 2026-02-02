"""
Unit tests for backend/services/embedding_job_service.py EmbeddingJobService

Tests job creation, state transitions, and progress tracking.
"""
import pytest
from unittest.mock import MagicMock, patch
import os
import tempfile
import json


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def mock_db_service(temp_db):
    """Create a mock database service with embedding job tables."""
    from backend.sqliteDb.db import DatabaseService
    
    service = DatabaseService(db_path=temp_db)
    
    conn = service.get_connection()
    cursor = conn.cursor()
    
    # Create embedding jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embedding_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            config_id INTEGER,
            status TEXT NOT NULL DEFAULT 'queued',
            phase TEXT,
            total_documents INTEGER DEFAULT 0,
            processed_documents INTEGER DEFAULT 0,
            failed_documents INTEGER DEFAULT 0,
            total_batches INTEGER DEFAULT 0,
            current_batch INTEGER DEFAULT 0,
            batch_size INTEGER DEFAULT 50,
            progress_percentage REAL DEFAULT 0.0,
            documents_per_second REAL,
            estimated_completion_at TEXT,
            started_by INTEGER,
            started_at TEXT,
            completed_at TEXT,
            cancelled_by INTEGER,
            error_message TEXT,
            error_details TEXT,
            config_metadata TEXT,
            embedding_version_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Create embedding job events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embedding_job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.commit()
    conn.close()
    
    return service


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = 1
    user.username = "testuser"
    return user


@pytest.fixture
def embedding_job_service(mock_db_service):
    """Create an EmbeddingJobService with mocked database."""
    with patch('backend.services.embedding_job_service.get_db_service') as mock_db:
        mock_db.return_value = mock_db_service
        
        from backend.services.embedding_job_service import EmbeddingJobService
        service = EmbeddingJobService()
        yield service


class TestEmbeddingJobServiceInitialization:
    """Tests for EmbeddingJobService initialization."""
    
    def test_service_has_db(self, embedding_job_service):
        """Test that service has database connection."""
        assert embedding_job_service.db is not None


class TestCreateJob:
    """Tests for job creation."""
    
    def test_create_job_returns_job_id(self, embedding_job_service, mock_user):
        """Test that create_job returns a job ID."""
        job_id = embedding_job_service.create_job(
            config_id=1,
            total_documents=100,
            user=mock_user
        )
        
        assert job_id is not None
        assert job_id.startswith("emb-job-")
    
    def test_create_job_with_custom_batch_size(self, embedding_job_service, mock_user):
        """Test creating job with custom batch size."""
        job_id = embedding_job_service.create_job(
            config_id=1,
            total_documents=100,
            user=mock_user,
            batch_size=25
        )
        
        # Job should be created
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress is not None
    
    def test_create_job_calculates_total_batches(self, embedding_job_service, mock_user, mock_db_service):
        """Test that total batches is calculated correctly."""
        job_id = embedding_job_service.create_job(
            config_id=1,
            total_documents=100,
            user=mock_user,
            batch_size=30  # 100/30 = 4 batches (ceiling)
        )
        
        # Verify in database
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT total_batches FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['total_batches'] == 4  # ceil(100/30)
    
    def test_create_job_stores_metadata(self, embedding_job_service, mock_user, mock_db_service):
        """Test that config metadata is stored."""
        job_id = embedding_job_service.create_job(
            config_id=1,
            total_documents=50,
            user=mock_user,
            batch_size=10,
            max_concurrent=3
        )
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT config_metadata FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        metadata = json.loads(row['config_metadata'])
        assert metadata['batch_size'] == 10
        assert metadata['max_concurrent'] == 3


class TestJobStateTransitions:
    """Tests for job state machine."""
    
    def test_start_job(self, embedding_job_service, mock_user, mock_db_service):
        """Test starting a job transitions to PREPARING."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(
            config_id=1,
            total_documents=100,
            user=mock_user
        )
        
        embedding_job_service.start_job(job_id)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, started_at FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.PREPARING.value
        assert row['started_at'] is not None
    
    def test_transition_to_embedding(self, embedding_job_service, mock_user, mock_db_service):
        """Test transition to EMBEDDING state."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.start_job(job_id)
        embedding_job_service.transition_to_embedding(job_id)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.EMBEDDING.value
    
    def test_transition_to_validating(self, embedding_job_service, mock_user, mock_db_service):
        """Test transition to VALIDATING state."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.transition_to_validating(job_id)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.VALIDATING.value
    
    def test_transition_to_storing(self, embedding_job_service, mock_user, mock_db_service):
        """Test transition to STORING state."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.transition_to_storing(job_id)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.STORING.value


class TestCompleteJob:
    """Tests for job completion."""
    
    def test_complete_job_success(self, embedding_job_service, mock_user, mock_db_service):
        """Test completing a job successfully."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.complete_job(job_id)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, completed_at FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.COMPLETED.value
        assert row['completed_at'] is not None
    
    def test_complete_job_with_embedding_version(self, embedding_job_service, mock_user, mock_db_service):
        """Test completing job with embedding version ID."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.complete_job(job_id, embedding_version_id=42)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT embedding_version_id FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['embedding_version_id'] == 42


class TestFailJob:
    """Tests for job failure."""
    
    def test_fail_job(self, embedding_job_service, mock_user, mock_db_service):
        """Test failing a job."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.fail_job(job_id, "Connection timeout")
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_message FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.FAILED.value
        assert row['error_message'] == "Connection timeout"
    
    def test_fail_job_with_details(self, embedding_job_service, mock_user, mock_db_service):
        """Test failing job with error details."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        
        error_details = {
            "exception": "ConnectionError",
            "traceback": "...",
            "batch_id": 5
        }
        embedding_job_service.fail_job(job_id, "Batch processing failed", error_details)
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT error_details FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        stored_details = json.loads(row['error_details'])
        assert stored_details['exception'] == "ConnectionError"


class TestCancelJob:
    """Tests for job cancellation."""
    
    def test_cancel_queued_job(self, embedding_job_service, mock_user, mock_db_service):
        """Test cancelling a queued job."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        
        result = embedding_job_service.cancel_job(job_id, mock_user)
        
        assert result is True
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == EmbeddingJobStatus.CANCELLED.value
    
    def test_cancel_embedding_job(self, embedding_job_service, mock_user, mock_db_service):
        """Test cancelling a job during embedding."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.transition_to_embedding(job_id)
        
        result = embedding_job_service.cancel_job(job_id, mock_user)
        
        assert result is True
    
    def test_cannot_cancel_completed_job(self, embedding_job_service, mock_user):
        """Test that completed jobs cannot be cancelled."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.complete_job(job_id)
        
        result = embedding_job_service.cancel_job(job_id, mock_user)
        
        assert result is False
    
    def test_cancel_nonexistent_job(self, embedding_job_service, mock_user):
        """Test cancelling a non-existent job."""
        result = embedding_job_service.cancel_job("nonexistent-job", mock_user)
        
        assert result is False


class TestUpdateProgress:
    """Tests for progress updates."""
    
    def test_update_progress(self, embedding_job_service, mock_user, mock_db_service):
        """Test updating job progress."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.start_job(job_id)
        
        embedding_job_service.update_progress(
            job_id,
            processed_documents=50,
            current_batch=2,
            failed_documents=1
        )
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT processed_documents, current_batch, failed_documents, progress_percentage 
            FROM embedding_jobs WHERE job_id = ?
        """, (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['processed_documents'] == 50
        assert row['current_batch'] == 2
        assert row['failed_documents'] == 1
        assert row['progress_percentage'] == 50.0
    
    def test_update_progress_with_phase(self, embedding_job_service, mock_user, mock_db_service):
        """Test updating progress with phase description."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        
        embedding_job_service.update_progress(
            job_id,
            processed_documents=25,
            current_batch=1,
            phase="Processing batch 1 of 4"
        )
        
        conn = mock_db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phase FROM embedding_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['phase'] == "Processing batch 1 of 4"
    
    def test_update_progress_nonexistent_job(self, embedding_job_service):
        """Test updating progress for non-existent job doesn't raise."""
        # Should not raise, just log warning
        embedding_job_service.update_progress(
            "nonexistent-job",
            processed_documents=10,
            current_batch=1
        )


class TestGetJobProgress:
    """Tests for retrieving job progress."""
    
    def test_get_job_progress_exists(self, embedding_job_service, mock_user):
        """Test getting progress for existing job."""
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        
        progress = embedding_job_service.get_job_progress(job_id)
        
        assert progress is not None
        assert progress.job_id == job_id
        assert progress.total_documents == 100
    
    def test_get_job_progress_not_found(self, embedding_job_service):
        """Test getting progress for non-existent job returns None."""
        progress = embedding_job_service.get_job_progress("nonexistent-job")
        
        assert progress is None
    
    def test_get_job_progress_includes_status(self, embedding_job_service, mock_user):
        """Test that progress includes status."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        embedding_job_service.transition_to_embedding(job_id)
        
        progress = embedding_job_service.get_job_progress(job_id)
        
        assert progress.status == EmbeddingJobStatus.EMBEDDING


class TestJobStateMachine:
    """Tests for the complete state machine flow."""
    
    def test_full_job_lifecycle(self, embedding_job_service, mock_user):
        """Test complete job lifecycle: create -> start -> embed -> validate -> store -> complete."""
        from backend.models.rag_models import EmbeddingJobStatus
        
        # Create
        job_id = embedding_job_service.create_job(config_id=1, total_documents=100, user=mock_user)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.QUEUED
        
        # Start (PREPARING)
        embedding_job_service.start_job(job_id)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.PREPARING
        
        # EMBEDDING
        embedding_job_service.transition_to_embedding(job_id)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.EMBEDDING
        
        # Update progress
        embedding_job_service.update_progress(job_id, processed_documents=100, current_batch=4)
        
        # VALIDATING
        embedding_job_service.transition_to_validating(job_id)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.VALIDATING
        
        # STORING
        embedding_job_service.transition_to_storing(job_id)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.STORING
        
        # COMPLETED
        embedding_job_service.complete_job(job_id)
        progress = embedding_job_service.get_job_progress(job_id)
        assert progress.status == EmbeddingJobStatus.COMPLETED
