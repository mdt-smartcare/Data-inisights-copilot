"""
Batch processing engine for embedding generation.
Handles document batching, concurrent processing, and retry logic.
"""
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
import asyncio
import math
import time

from backend.services.embeddings import get_embedding_model
from backend.core.logging import get_embedding_logger

logger = get_embedding_logger()
logger.info("Embedding batch processor logger initialized")


@dataclass
class BatchResult:
    """Result of processing a single batch."""
    batch_number: int
    success: bool
    documents_processed: int
    start_idx: int = 0
    embeddings: Optional[List[List[float]]] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0


@dataclass
class BatchConfig:
    """Configuration for batch processing."""
    batch_size: int = 50
    max_concurrent: int = 3
    retry_attempts: int = 3
    retry_delay_seconds: float = 5.0
    timeout_per_batch_seconds: int = 60


class EmbeddingBatchProcessor:
    """
    Processes documents in batches for embedding generation.
    
    Features:
    - Configurable batch size
    - Concurrent batch processing
    - Automatic retry with exponential backoff
    - Progress callbacks
    """
    
    def __init__(self, config: Optional[BatchConfig] = None):
        """
        Initialize the batch processor.
        
        Args:
            config: Batch processing configuration
        """
        self.config = config or BatchConfig()
        self.embedding_model = None
        self._cancelled = False
        self._paused = False
    
    def _ensure_model(self):
        """Lazily load the embedding model."""
        if self.embedding_model is None:
            self.embedding_model = get_embedding_model()
    
    async def process_documents(
        self,
        documents: List[str],
        on_progress: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
        on_batch_complete: Optional[Callable[[BatchResult], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Process all documents in batches.
        
        Args:
            documents: List of document texts to embed
            on_progress: Async callback(processed, failed, total) for progress updates
            on_batch_complete: Async callback(BatchResult) after each batch
            
        Returns:
            Dict with results:
            {
                "success": bool,
                "total_documents": int,
                "processed_documents": int,
                "failed_documents": int,
                "embeddings": List[List[float]],
                "failed_indices": List[int],
                "total_time_seconds": float
            }
        """
        self._cancelled = False
        self._paused = False
        self._ensure_model()
        
        total_documents = len(documents)
        total_batches = math.ceil(total_documents / self.config.batch_size)
        
        logger.info(f"Starting batch processing: {total_documents} documents in {total_batches} batches")
        
        # Create batches
        batches = []
        for i in range(0, total_documents, self.config.batch_size):
            batch_docs = documents[i:i + self.config.batch_size]
            batch_num = len(batches) + 1
            batches.append((batch_num, i, batch_docs))
        
        # Results storage
        all_embeddings = [None] * total_documents
        failed_indices = []
        processed_count = 0
        failed_count = 0
        start_time = time.time()
        
        # Process batches with concurrency limit
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        async def process_with_semaphore(batch_info):
            async with semaphore:
                if self._cancelled:
                    return None
                
                while self._paused:
                    await asyncio.sleep(0.5)
                    if self._cancelled:
                        return None
                
                return await self._process_batch(*batch_info)
        
        # Process all batches
        tasks = [process_with_semaphore(batch) for batch in batches]
        
        batches_completed = 0
        
        for coro in asyncio.as_completed(tasks):
            if self._cancelled:
                break
            
            result = await coro
            if result is None:
                continue
            
            batches_completed += 1
            batch_num, start_idx, batch_docs = batches[result.batch_number - 1]
            
            if result.success and result.embeddings:
                # Store embeddings
                for j, emb in enumerate(result.embeddings):
                    all_embeddings[start_idx + j] = emb
                processed_count += result.documents_processed
            else:
                # Track failures
                for j in range(len(batch_docs)):
                    failed_indices.append(start_idx + j)
                failed_count += len(batch_docs)
            
            # Callbacks
            if on_batch_complete:
                try:
                    await on_batch_complete(result)
                except Exception as e:
                    logger.warning(f"Batch complete callback failed: {e}")
            
            if on_progress:
                try:
                    await on_progress(processed_count, failed_count, total_documents)
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")
                    
            # Detailed console progress logging
            if batches_completed > 0 and (batches_completed % 10 == 0 or batches_completed == total_batches):
                elapsed = time.time() - start_time
                if elapsed > 0 and processed_count > 0:
                    docs_per_sec = processed_count / elapsed
                    remaining_docs = total_documents - processed_count
                    if docs_per_sec > 0:
                        eta_seconds = remaining_docs / docs_per_sec
                        import datetime
                        eta_td = datetime.timedelta(seconds=int(eta_seconds))
                        percent = (processed_count / total_documents) * 100
                        logger.info(f"Batch {batches_completed}/{total_batches} | {processed_count:,}/{total_documents:,} docs | {percent:.1f}% | ETA: {eta_td}")
        
        total_time = time.time() - start_time
        
        # Filter out None embeddings (failed)
        successful_embeddings = [e for e in all_embeddings if e is not None]
        
        result = {
            "success": failed_count == 0,
            "total_documents": total_documents,
            "processed_documents": processed_count,
            "failed_documents": failed_count,
            "embeddings": all_embeddings,  # Includes None for failures
            "successful_embeddings": successful_embeddings,
            "failed_indices": failed_indices,
            "total_time_seconds": total_time,
            "average_speed": processed_count / total_time if total_time > 0 else 0,
            "cancelled": self._cancelled
        }
        
        logger.info(
            f"Batch processing complete: {processed_count}/{total_documents} succeeded, "
            f"{failed_count} failed, {total_time:.2f}s"
        )
        
        return result
    
    async def _process_batch(
        self,
        batch_number: int,
        start_index: int,
        documents: List[str]
    ) -> BatchResult:
        """
        Process a single batch with retry logic.
        
        Args:
            batch_number: Batch number for tracking
            start_index: Starting index in original document list
            documents: Documents in this batch
            
        Returns:
            BatchResult with embeddings or error
        """
        last_error = None
        
        for attempt in range(self.config.retry_attempts):
            if self._cancelled:
                return BatchResult(
                    batch_number=batch_number,
                    success=False,
                    documents_processed=0,
                    start_idx=start_index,
                    error_message="Cancelled"
                )
            
            start_time = time.time()
            
            try:
                # Generate embeddings (synchronous call wrapped in executor)
                loop = asyncio.get_event_loop()
                embeddings = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        self.embedding_model.embed_documents,
                        documents
                    ),
                    timeout=self.config.timeout_per_batch_seconds
                )
                
                processing_time = int((time.time() - start_time) * 1000)
                
                logger.info(f"Batch {batch_number} embedded: {len(documents)} documents in {processing_time}ms")
                
                return BatchResult(
                    batch_number=batch_number,
                    success=True,
                    documents_processed=len(documents),
                    start_idx=start_index,
                    embeddings=embeddings,
                    processing_time_ms=processing_time
                )
                
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.config.timeout_per_batch_seconds}s"
                logger.warning(f"Batch {batch_number} timeout (attempt {attempt + 1})")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Batch {batch_number} failed (attempt {attempt + 1}): {e}")
            
            # Exponential backoff before retry
            if attempt < self.config.retry_attempts - 1:
                delay = self.config.retry_delay_seconds * (2 ** attempt)
                await asyncio.sleep(delay)
        
        # All retries exhausted
        logger.error(f"Batch {batch_number} failed after {self.config.retry_attempts} attempts")
        
        return BatchResult(
            batch_number=batch_number,
            success=False,
            documents_processed=0,
            start_idx=start_index,
            error_message=last_error
        )
    
    def cancel(self):
        """Cancel processing."""
        self._cancelled = True
        logger.info("Batch processing cancellation requested")
    
    def pause(self):
        """Pause processing."""
        self._paused = True
        logger.info("Batch processing paused")
    
    def resume(self):
        """Resume processing."""
        self._paused = False
        logger.info("Batch processing resumed")
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    @property
    def is_paused(self) -> bool:
        return self._paused
