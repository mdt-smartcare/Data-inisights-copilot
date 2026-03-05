"""
Batch processing engine for embedding generation.
Handles document batching, concurrent processing, and retry logic.
"""
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set, Tuple
from dataclasses import dataclass, field
import asyncio
import math
import time
import os
import hashlib

from backend.services.embeddings import get_embedding_model
from backend.core.logging import get_embedding_logger

logger = get_embedding_logger()
logger.info("Embedding batch processor logger initialized")


# =============================================================================
# Memory-Based Configuration Constants
# =============================================================================

# Estimated memory per document during embedding (in MB)
# This accounts for: tokenization, model inference, embedding storage
ESTIMATED_MB_PER_DOC = 0.5  # ~500KB per document (conservative estimate)

# Minimum memory headroom to maintain (in MB)
MIN_MEMORY_HEADROOM_MB = 512  # Keep at least 512MB free

# Batch size constraints
MIN_BATCH_SIZE = 10
MAX_BATCH_SIZE = 500
DEFAULT_BATCH_SIZE = 128  # Match model's internal batch size for optimal GPU utilization

# Concurrency constraints
MIN_CONCURRENT = 1
MAX_CONCURRENT = 8
DEFAULT_CONCURRENT = 3


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
    """
    Configuration for batch processing.
    
    Supports both static configuration and dynamic auto-configuration
    based on available system resources.
    
    Usage:
        # Static configuration
        config = BatchConfig(batch_size=100, max_concurrent=4)
        
        # Auto-configure based on available RAM
        config = BatchConfig.auto_configure()
        
        # Auto-configure with model-specific memory estimate
        config = BatchConfig.auto_configure(mb_per_doc=0.8)
    """
    batch_size: int = DEFAULT_BATCH_SIZE
    max_concurrent: int = DEFAULT_CONCURRENT
    retry_attempts: int = 3
    retry_delay_seconds: float = 5.0
    timeout_per_batch_seconds: int = 60
    # Track if this config was auto-generated
    auto_configured: bool = field(default=False, repr=False)
    
    @classmethod
    def auto_configure(
        cls,
        mb_per_doc: float = ESTIMATED_MB_PER_DOC,
        memory_headroom_mb: float = MIN_MEMORY_HEADROOM_MB,
        target_memory_percent: float = 0.6,
        min_batch_size: int = MIN_BATCH_SIZE,
        max_batch_size: int = MAX_BATCH_SIZE,
        min_concurrent: int = MIN_CONCURRENT,
        max_concurrent: int = MAX_CONCURRENT
    ) -> 'BatchConfig':
        """
        Automatically configure batch processing based on available system resources.
        
        Task 2.2: Uses psutil to dynamically adjust batch size based on:
        - Available RAM
        - CPU core count
        - Configurable safety margins
        
        Args:
            mb_per_doc: Estimated memory usage per document in MB (default: 0.5)
            memory_headroom_mb: Minimum free memory to maintain in MB (default: 512)
            target_memory_percent: Target percentage of available memory to use (default: 0.6)
            min_batch_size: Minimum batch size (default: 10)
            max_batch_size: Maximum batch size (default: 500)
            min_concurrent: Minimum concurrent batches (default: 1)
            max_concurrent: Maximum concurrent batches (default: 8)
            
        Returns:
            BatchConfig with optimized settings for the current system
            
        Example:
            >>> config = BatchConfig.auto_configure()
            >>> print(f"Batch size: {config.batch_size}, Concurrent: {config.max_concurrent}")
        """
        try:
            import psutil
            
            # Get system memory info
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            total_mb = mem.total / (1024 * 1024)
            memory_percent_used = mem.percent
            
            # Get CPU info
            cpu_count = os.cpu_count() or 4
            
            # Calculate usable memory (available minus headroom)
            usable_mb = max(0, available_mb - memory_headroom_mb)
            target_mb = usable_mb * target_memory_percent
            
            # Calculate optimal batch size
            # Formula: target_memory / (mb_per_doc * concurrent_factor)
            # We assume each concurrent batch needs its own memory allocation
            concurrent_factor = min(max_concurrent, max(min_concurrent, cpu_count // 2))
            
            # Memory per concurrent batch
            memory_per_batch = target_mb / concurrent_factor
            
            # Documents per batch based on memory
            optimal_batch_size = int(memory_per_batch / mb_per_doc)
            
            # Clamp to valid range
            batch_size = max(min_batch_size, min(max_batch_size, optimal_batch_size))
            
            # Adjust concurrency based on CPU and memory
            # More memory = can handle more concurrent batches
            if available_mb > 8000:  # > 8GB available
                num_concurrent = min(max_concurrent, max(4, cpu_count // 2))
            elif available_mb > 4000:  # > 4GB available
                num_concurrent = min(max_concurrent, max(3, cpu_count // 3))
            elif available_mb > 2000:  # > 2GB available
                num_concurrent = min(max_concurrent, max(2, cpu_count // 4))
            else:  # Low memory
                num_concurrent = min_concurrent
            
            # Adjust timeout based on batch size (larger batches need more time)
            base_timeout = 60
            timeout = base_timeout + (batch_size // 50) * 10  # +10s per 50 docs
            timeout = min(timeout, 300)  # Cap at 5 minutes
            
            logger.info(
                f"Task 2.2: Auto-configured batch processing | "
                f"System: {total_mb:.0f}MB total, {available_mb:.0f}MB available ({memory_percent_used:.1f}% used), {cpu_count} CPUs | "
                f"Config: batch_size={batch_size}, max_concurrent={num_concurrent}, timeout={timeout}s"
            )
            
            return cls(
                batch_size=batch_size,
                max_concurrent=num_concurrent,
                retry_attempts=3,
                retry_delay_seconds=5.0,
                timeout_per_batch_seconds=timeout,
                auto_configured=True
            )
            
        except ImportError:
            logger.warning("psutil not available, using default BatchConfig")
            return cls(auto_configured=False)
        except Exception as e:
            logger.warning(f"Auto-configuration failed: {e}, using defaults")
            return cls(auto_configured=False)
    
    @classmethod
    def for_low_memory(cls) -> 'BatchConfig':
        """
        Preset configuration for low-memory environments (< 4GB available).
        
        Returns:
            BatchConfig optimized for memory-constrained systems
        """
        return cls(
            batch_size=25,
            max_concurrent=2,
            retry_attempts=3,
            retry_delay_seconds=5.0,
            timeout_per_batch_seconds=90,
            auto_configured=True
        )
    
    @classmethod
    def for_high_throughput(cls) -> 'BatchConfig':
        """
        Preset configuration for high-memory, high-CPU environments.
        Optimized for maximum throughput.
        
        Returns:
            BatchConfig optimized for speed on powerful systems
        """
        return cls(
            batch_size=200,
            max_concurrent=6,
            retry_attempts=2,
            retry_delay_seconds=2.0,
            timeout_per_batch_seconds=120,
            auto_configured=True
        )
    
    def get_memory_estimate_mb(self, total_documents: int) -> float:
        """
        Estimate total memory usage for processing a document set.
        
        Args:
            total_documents: Number of documents to process
            
        Returns:
            Estimated memory usage in MB
        """
        # Concurrent batches * batch size * memory per doc
        docs_in_flight = self.max_concurrent * self.batch_size
        active_docs = min(docs_in_flight, total_documents)
        return active_docs * ESTIMATED_MB_PER_DOC


class EmbeddingBatchProcessor:
    """
    Processes documents in batches for embedding generation.
    
    Features:
    - Configurable batch size
    - Concurrent batch processing
    - Automatic retry with exponential backoff
    - Progress callbacks
    - Stateful job resuming (filters out already-embedded documents)
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
        self._existing_ids: Optional[Set[str]] = None
        self._skipped_count: int = 0
    
    def _ensure_model(self):
        """Lazily load the embedding model."""
        if self.embedding_model is None:
            self.embedding_model = get_embedding_model()
    
    def set_existing_ids(self, existing_ids: Set[str]) -> None:
        """
        Set the IDs of documents that already exist in the vector store.
        
        Used for stateful job resuming - documents with these IDs will be
        skipped during batch processing to avoid re-embedding.
        
        Args:
            existing_ids: Set of document IDs already in the vector store
        """
        self._existing_ids = existing_ids
        logger.info(f"Stateful resuming enabled: {len(existing_ids)} existing documents will be skipped")
    
    def generate_chunk_id(self, content: str, parent_id: str = "unknown") -> str:
        """
        Generate a chunk ID matching the embedding job logic.
        
        Args:
            content: The document content
            parent_id: The parent document ID
            
        Returns:
            SHA256 hash of content + parent_id
        """
        return hashlib.sha256(f"{content}{parent_id}".encode()).hexdigest()
    
    def filter_batch_for_delta(
        self, 
        documents: List[str],
        doc_objects: Optional[List[Any]] = None,
        start_idx: int = 0
    ) -> Tuple[List[str], List[int], int]:
        """
        Filter a batch to only include documents not already embedded.
        
        Args:
            documents: List of document content strings
            doc_objects: Optional list of document objects with metadata
            start_idx: Starting index in the original document list
            
        Returns:
            Tuple of (filtered_documents, original_indices, skipped_count)
        """
        if self._existing_ids is None or len(self._existing_ids) == 0:
            # No existing IDs set, process all documents
            return documents, list(range(start_idx, start_idx + len(documents))), 0
        
        filtered_docs = []
        original_indices = []
        skipped = 0
        
        for i, content in enumerate(documents):
            # Get parent_id from document object if available
            parent_id = "unknown"
            if doc_objects and i < len(doc_objects):
                doc = doc_objects[i]
                if hasattr(doc, 'metadata') and isinstance(doc.metadata, dict):
                    parent_id = doc.metadata.get("doc_id", "unknown")
            
            chunk_id = self.generate_chunk_id(content, parent_id)
            
            if chunk_id not in self._existing_ids:
                filtered_docs.append(content)
                original_indices.append(start_idx + i)
            else:
                skipped += 1
        
        return filtered_docs, original_indices, skipped

    async def process_documents_with_resume(
        self,
        documents: List[str],
        doc_objects: Optional[List[Any]] = None,
        on_progress: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
        on_batch_complete: Optional[Callable[['BatchResult'], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Process documents with stateful job resuming support.
        
        Filters out already-embedded documents before processing batches,
        preventing redundant embedding generation on job restart.
        
        Args:
            documents: List of document texts to embed
            doc_objects: Optional list of document objects (for metadata access)
            on_progress: Async callback(processed, failed, total) for progress updates
            on_batch_complete: Async callback(BatchResult) after each batch
            
        Returns:
            Dict with results including skipped document count
        """
        self._cancelled = False
        self._paused = False
        self._skipped_count = 0
        self._ensure_model()
        
        total_documents = len(documents)
        
        # If we have existing IDs, filter documents first
        if self._existing_ids and len(self._existing_ids) > 0:
            logger.info(f"Checking {total_documents} documents against {len(self._existing_ids)} existing embeddings...")
            
            filtered_docs = []
            filtered_objects = []
            index_mapping = []  # Maps filtered index -> original index
            
            for i, content in enumerate(documents):
                parent_id = "unknown"
                if doc_objects and i < len(doc_objects):
                    doc = doc_objects[i]
                    if hasattr(doc, 'metadata') and isinstance(doc.metadata, dict):
                        parent_id = doc.metadata.get("doc_id", "unknown")
                
                chunk_id = self.generate_chunk_id(content, parent_id)
                
                if chunk_id not in self._existing_ids:
                    filtered_docs.append(content)
                    if doc_objects:
                        filtered_objects.append(doc_objects[i])
                    index_mapping.append(i)
                else:
                    self._skipped_count += 1
            
            logger.info(
                f"Stateful resume: Skipped {self._skipped_count} already-embedded documents, "
                f"processing {len(filtered_docs)} new/missing documents"
            )
            
            if len(filtered_docs) == 0:
                logger.info("All documents already embedded - nothing to process")
                return {
                    "success": True,
                    "total_documents": total_documents,
                    "processed_documents": 0,
                    "failed_documents": 0,
                    "skipped_documents": self._skipped_count,
                    "embeddings": [None] * total_documents,
                    "successful_embeddings": [],
                    "failed_indices": [],
                    "total_time_seconds": 0,
                    "average_speed": 0,
                    "cancelled": False,
                    "resumed": True
                }
            
            # Process only the filtered documents
            result = await self._process_filtered_documents(
                filtered_docs=filtered_docs,
                index_mapping=index_mapping,
                total_original=total_documents,
                on_progress=on_progress,
                on_batch_complete=on_batch_complete
            )
            result["skipped_documents"] = self._skipped_count
            result["resumed"] = True
            return result
        
        # No existing IDs - process all documents normally
        result = await self.process_documents(
            documents=documents,
            on_progress=on_progress,
            on_batch_complete=on_batch_complete
        )
        result["skipped_documents"] = 0
        result["resumed"] = False
        return result
    
    async def _process_filtered_documents(
        self,
        filtered_docs: List[str],
        index_mapping: List[int],
        total_original: int,
        on_progress: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
        on_batch_complete: Optional[Callable[['BatchResult'], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Process pre-filtered documents while maintaining original indices.
        
        Args:
            filtered_docs: Documents to process (already filtered)
            index_mapping: Maps filtered index -> original index
            total_original: Total count of original documents
            on_progress: Progress callback
            on_batch_complete: Batch completion callback
        """
        total_filtered = len(filtered_docs)
        total_batches = math.ceil(total_filtered / self.config.batch_size)
        
        logger.info(f"Processing {total_filtered} documents in {total_batches} batches (resuming job)")
        
        # Create batches with mapping info
        batches = []
        for i in range(0, total_filtered, self.config.batch_size):
            batch_docs = filtered_docs[i:i + self.config.batch_size]
            batch_indices = index_mapping[i:i + self.config.batch_size]
            batch_num = len(batches) + 1
            batches.append((batch_num, i, batch_docs, batch_indices))
        
        # Results storage - sized for original document count
        all_embeddings = [None] * total_original
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
                
                batch_num, filtered_start, batch_docs, batch_indices = batch_info
                return await self._process_batch(batch_num, filtered_start, batch_docs), batch_indices
        
        tasks = [process_with_semaphore(batch) for batch in batches]
        batches_completed = 0
        
        for coro in asyncio.as_completed(tasks):
            if self._cancelled:
                break
            
            task_result = await coro
            if task_result is None:
                continue
            
            result, batch_indices = task_result
            batches_completed += 1
            
            if result.success and result.embeddings:
                # Store embeddings at ORIGINAL indices
                for j, emb in enumerate(result.embeddings):
                    if j < len(batch_indices):
                        original_idx = batch_indices[j]
                        all_embeddings[original_idx] = emb
                processed_count += result.documents_processed
            else:
                # Track failures using original indices
                for j in range(len(batch_indices)):
                    if j < len(batch_indices):
                        failed_indices.append(batch_indices[j])
                failed_count += len(batch_indices)
            
            # Adjust batch result to use original index for callback
            if batch_indices:
                result.start_idx = batch_indices[0]
            
            if on_batch_complete:
                try:
                    await on_batch_complete(result)
                except Exception as e:
                    logger.warning(f"Batch complete callback failed: {e}")
            
            # Progress includes skipped documents
            total_handled = processed_count + self._skipped_count
            if on_progress:
                try:
                    await on_progress(total_handled, failed_count, total_original)
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")
            
            # Progress logging
            if batches_completed > 0 and (batches_completed % 10 == 0 or batches_completed == total_batches):
                elapsed = time.time() - start_time
                if elapsed > 0 and processed_count > 0:
                    docs_per_sec = processed_count / elapsed
                    remaining_docs = total_filtered - processed_count
                    if docs_per_sec > 0:
                        eta_seconds = remaining_docs / docs_per_sec
                        import datetime
                        eta_td = datetime.timedelta(seconds=int(eta_seconds))
                        percent = (total_handled / total_original) * 100
                        logger.info(
                            f"Batch {batches_completed}/{total_batches} | "
                            f"{processed_count:,} new + {self._skipped_count:,} skipped = {total_handled:,}/{total_original:,} | "
                            f"{percent:.1f}% | ETA: {eta_td}"
                        )
        
        total_time = time.time() - start_time
        successful_embeddings = [e for e in all_embeddings if e is not None]
        
        return {
            "success": failed_count == 0,
            "total_documents": total_original,
            "processed_documents": processed_count,
            "failed_documents": failed_count,
            "embeddings": all_embeddings,
            "successful_embeddings": successful_embeddings,
            "failed_indices": failed_indices,
            "total_time_seconds": total_time,
            "average_speed": processed_count / total_time if total_time > 0 else 0,
            "cancelled": self._cancelled
        }

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
        logger.info(f"Batch config: size={self.config.batch_size}, concurrent={self.config.max_concurrent}, timeout={self.config.timeout_per_batch_seconds}s")
        
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
        
        # Process batches sequentially to avoid async issues in background tasks
        # This is more reliable than concurrent processing in FastAPI background context
        logger.info(f"Processing {len(batches)} batches sequentially...")
        
        for batch_num, start_idx, batch_docs in batches:
            if self._cancelled:
                logger.info("Batch processing cancelled")
                break
            
            while self._paused:
                await asyncio.sleep(0.5)
                if self._cancelled:
                    break
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_docs)} docs)...")
            
            result = await self._process_batch(batch_num, start_idx, batch_docs)
            
            if result.success and result.embeddings:
                # Store embeddings
                for j, emb in enumerate(result.embeddings):
                    all_embeddings[start_idx + j] = emb
                processed_count += result.documents_processed
                logger.info(f"Batch {batch_num} completed: {result.documents_processed} docs in {result.processing_time_ms}ms")
            else:
                # Track failures
                for j in range(len(batch_docs)):
                    failed_indices.append(start_idx + j)
                failed_count += len(batch_docs)
                logger.error(f"Batch {batch_num} failed: {result.error_message}")
            
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
                    
            # Detailed console progress logging every 10 batches
            if batch_num % 10 == 0 or batch_num == total_batches:
                elapsed = time.time() - start_time
                if elapsed > 0 and processed_count > 0:
                    docs_per_sec = processed_count / elapsed
                    remaining_docs = total_documents - processed_count
                    if docs_per_sec > 0:
                        eta_seconds = remaining_docs / docs_per_sec
                        import datetime
                        eta_td = datetime.timedelta(seconds=int(eta_seconds))
                        percent = (processed_count / total_documents) * 100
                        logger.info(f"Progress: Batch {batch_num}/{total_batches} | {processed_count:,}/{total_documents:,} docs | {percent:.1f}% | ETA: {eta_td}")
        
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
        
        Task 2.3: Uses native async embedding when provider supports it,
        otherwise falls back to run_in_executor for sync providers.
        
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
                # Task 2.3: Check if provider supports native async
                if hasattr(self.embedding_model, 'supports_async') and self.embedding_model.supports_async:
                    # Use native async embedding (e.g., OpenAI)
                    logger.debug(f"Batch {batch_number}: Using native async embedding")
                    embeddings = await asyncio.wait_for(
                        self.embedding_model.aembed_documents(documents),
                        timeout=self.config.timeout_per_batch_seconds
                    )
                else:
                    # Fallback: wrap sync call in executor (e.g., BGE, SentenceTransformers)
                    # Use asyncio.get_running_loop() instead of deprecated get_event_loop()
                    logger.debug(f"Batch {batch_number}: Using executor-wrapped sync embedding")
                    loop = asyncio.get_running_loop()
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
                import traceback
                logger.error(f"Batch {batch_number} traceback: {traceback.format_exc()}")
            
            # Exponential backoff before retry
            if attempt < self.config.retry_attempts - 1:
                delay = self.config.retry_delay_seconds * (2 ** attempt)
                await asyncio.sleep(delay)
        
        # All retries exhausted
        logger.error(f"Batch {batch_number} failed after {self.config.retry_attempts} attempts: {last_error}")
        
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
    
    @property
    def skipped_count(self) -> int:
        """Number of documents skipped due to already being embedded."""
        return self._skipped_count
