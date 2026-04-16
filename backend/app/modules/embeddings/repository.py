"""
Repository for embedding job database operations.

Provides async CRUD operations for:
- Embedding jobs
- Embedding checkpoints
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, update, delete, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.embeddings.models import EmbeddingJobModel, EmbeddingCheckpointModel
from app.modules.embeddings.schemas import EmbeddingJobStatus
from app.modules.agents.models import AgentConfigModel


class EmbeddingJobRepository:
    """Repository for embedding job database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(
        self,
        job_id: str,
        config_id: int,
        total_documents: int,
        total_batches: int,
        batch_size: int,
        started_by: str,
        config_metadata: Optional[dict] = None,
        incremental: bool = False
    ) -> EmbeddingJobModel:
        """Create a new embedding job."""
        job = EmbeddingJobModel(
            job_id=job_id,
            config_id=config_id,
            status=EmbeddingJobStatus.QUEUED.value,
            phase="Job queued for processing",
            total_documents=total_documents,
            total_batches=total_batches,
            batch_size=batch_size,
            started_by=started_by,
            config_metadata=config_metadata,
            incremental=incremental,
            created_at=datetime.utcnow()
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job
    
    async def get_by_id(self, job_id: str) -> Optional[EmbeddingJobModel]:
        """Get a job by ID."""
        stmt = select(EmbeddingJobModel).where(EmbeddingJobModel.job_id == job_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_status(
        self,
        job_id: str,
        status: EmbeddingJobStatus,
        phase: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update job status and optionally phase/error."""
        values = {"status": status.value, "updated_at": datetime.utcnow()}
        if phase:
            values["phase"] = phase
        if error_message:
            values["error_message"] = error_message
        if status == EmbeddingJobStatus.PREPARING:
            values["started_at"] = datetime.utcnow()
        if status == EmbeddingJobStatus.EMBEDDING:
            values["embedding_started_at"] = datetime.utcnow()
        if status in (EmbeddingJobStatus.COMPLETED, EmbeddingJobStatus.FAILED, EmbeddingJobStatus.CANCELLED):
            values["completed_at"] = datetime.utcnow()
        
        stmt = (
            update(EmbeddingJobModel)
            .where(EmbeddingJobModel.job_id == job_id)
            .values(**values)
        )
        result = await self.db.execute(stmt)
        
        # Update agent_config embedding_status and status based on embedding job status
        if status in (EmbeddingJobStatus.PREPARING, EmbeddingJobStatus.COMPLETED, EmbeddingJobStatus.FAILED, EmbeddingJobStatus.CANCELLED):
            # Get the job to find config_id
            job_stmt = select(EmbeddingJobModel).where(EmbeddingJobModel.job_id == job_id)
            job_result = await self.db.execute(job_stmt)
            job = job_result.scalar_one_or_none()
            
            if job and job.config_id:
                config_values = {}
                if status == EmbeddingJobStatus.PREPARING:
                    config_values["embedding_status"] = "running"
                elif status == EmbeddingJobStatus.COMPLETED:
                    # Mark config as published and embedding complete
                    config_values["status"] = "published"
                    config_values["embedding_status"] = "completed"
                elif status == EmbeddingJobStatus.FAILED:
                    config_values["embedding_status"] = "failed"
                elif status == EmbeddingJobStatus.CANCELLED:
                    config_values["embedding_status"] = "not_started"
                
                if config_values:
                    config_stmt = (
                        update(AgentConfigModel)
                        .where(AgentConfigModel.id == job.config_id)
                        .values(**config_values)
                    )
                    await self.db.execute(config_stmt)
        
        await self.db.commit()
        return result.rowcount > 0
    
    async def update_progress(
        self,
        job_id: str,
        processed_documents: int,
        current_batch: int,
        failed_documents: int = 0,
        progress_percentage: float = 0.0,
        documents_per_second: Optional[float] = None,
        estimated_completion_at: Optional[datetime] = None,
        phase: Optional[str] = None
    ) -> bool:
        """Update job progress metrics."""
        values = {
            "processed_documents": processed_documents,
            "current_batch": current_batch,
            "failed_documents": failed_documents,
            "progress_percentage": progress_percentage,
            "updated_at": datetime.utcnow()
        }
        if documents_per_second is not None:
            values["documents_per_second"] = documents_per_second
        if estimated_completion_at:
            values["estimated_completion_at"] = estimated_completion_at
        if phase:
            values["phase"] = phase
        
        stmt = (
            update(EmbeddingJobModel)
            .where(EmbeddingJobModel.job_id == job_id)
            .values(**values)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
    
    async def add_error(self, job_id: str, error_message: str) -> bool:
        """Add an error to the job's recent_errors list."""
        job = await self.get_by_id(job_id)
        if not job:
            return False
        
        recent_errors = job.recent_errors or []
        recent_errors.append(error_message)
        # Keep only last 10 errors
        if len(recent_errors) > 10:
            recent_errors = recent_errors[-10:]
        
        stmt = (
            update(EmbeddingJobModel)
            .where(EmbeddingJobModel.job_id == job_id)
            .values(
                recent_errors=recent_errors,
                errors_count=EmbeddingJobModel.errors_count + 1
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
    
    async def list_jobs(
        self,
        config_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[EmbeddingJobModel]:
        """List embedding jobs with optional filters."""
        conditions = []
        if config_id:
            conditions.append(EmbeddingJobModel.config_id == config_id)
        if status:
            conditions.append(EmbeddingJobModel.status == status)
        
        stmt = select(EmbeddingJobModel)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(desc(EmbeddingJobModel.created_at)).limit(limit)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def delete(self, job_id: str) -> bool:
        """Delete a job."""
        stmt = delete(EmbeddingJobModel).where(EmbeddingJobModel.job_id == job_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0


class EmbeddingCheckpointRepository:
    """Repository for embedding checkpoint operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_vector_db(self, vector_db_name: str) -> Optional[EmbeddingCheckpointModel]:
        """Get checkpoint by vector DB name."""
        stmt = select(EmbeddingCheckpointModel).where(
            EmbeddingCheckpointModel.vector_db_name == vector_db_name
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def upsert(
        self,
        vector_db_name: str,
        phase: str,
        checkpoint_data: Optional[dict] = None
    ) -> EmbeddingCheckpointModel:
        """Create or update a checkpoint."""
        existing = await self.get_by_vector_db(vector_db_name)
        
        if existing:
            stmt = (
                update(EmbeddingCheckpointModel)
                .where(EmbeddingCheckpointModel.vector_db_name == vector_db_name)
                .values(
                    phase=phase,
                    checkpoint_data=checkpoint_data,
                    updated_at=datetime.utcnow()
                )
            )
            await self.db.execute(stmt)
            await self.db.commit()
            return await self.get_by_vector_db(vector_db_name)
        else:
            checkpoint = EmbeddingCheckpointModel(
                vector_db_name=vector_db_name,
                phase=phase,
                checkpoint_data=checkpoint_data
            )
            self.db.add(checkpoint)
            await self.db.commit()
            await self.db.refresh(checkpoint)
            return checkpoint
    
    async def delete(self, vector_db_name: str) -> bool:
        """Delete a checkpoint."""
        stmt = delete(EmbeddingCheckpointModel).where(
            EmbeddingCheckpointModel.vector_db_name == vector_db_name
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
