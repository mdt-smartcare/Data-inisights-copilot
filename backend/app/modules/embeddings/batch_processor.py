"""
Batch processing engine for embedding generation.
Handles document batching, concurrent processing, and retry logic.

Ported from old backend's embedding_batch_processor.py for performance parity.
"""
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set, Tuple
from dataclasses import dataclass, field
import asyncio
import math
import time
import os
import hashlib

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Memory-Based Configuration Constants
# =============================================================================

# Estimated memory per document during embedding (in MB)
ESTIMATED_MB_PER_DOC = 0.5  # ~500KB per document (conservative estimate)

# Minimum memory headroom to maintain (in MB)
MIN_MEMORY_HEADROOM_MB = 512  # Keep at least 512MB free

# Batch size constraints
MIN_BATCH_SIZE = 10
MAX_BATCH_SIZE = 500
DEFAULT_BATCH_SIZE = 50

# Concurrency constraints
MIN_CONCURRENT = 1
MAX_CONCURRENT = 8
DEFAULT_CONCURRENT = 5


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
    """
    batch_size: int = DEFAULT_BATCH_SIZE
    max_concurrent: int = DEFAULT_CONCURRENT
    retry_attempts: int = 3
    retry_delay_seconds: float = 5.0
    timeout_per_batch_seconds: int = 60
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
        
        Uses psutil to dynamically adjust batch size based on:
        - Available RAM
        - CPU core count
        - Configurable safety margins
        """
        try:
            import psutil
            
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            total_mb = mem.total / (1024 * 1024)
            memory_percent_used = mem.percent
            
            cpu_count = os.cpu_count() or 4
            
            usable_mb = max(0, available_mb - memory_headroom_mb)
            target_mb = usable_mb * target_memory_percent
            
            concurrent_factor = min(max_concurrent, max(min_concurrent, cpu_count // 2))
            memory_per_batch = target_mb / concurrent_factor
            optimal_batch_size = int(memory_per_batch / mb_per_doc)
            
            batch_size = max(min_batch_size, min(max_batch_size, optimal_batch_size))
            
            if available_mb > 8000:
                num_concurrent = min(max_concurrent, max(4, cpu_count // 2))
            elif available_mb > 4000:
                num_concurrent = min(max_concurrent, max(3, cpu_count // 3))
            elif available_mb > 2000:
                num_concurrent = min(max_concurrent, max(2, cpu_count // 4))
            else:
                num_concurrent = min_concurrent
            
            base_timeout = 60
            timeout = base_timeout + (batch_size // 50) * 10
            timeout = min(timeout, 300)
            
            logger.info(
                f"Auto-configured batch processing | "
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
        """Preset for low-memory environments (< 4GB available)."""
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
        """Preset for high-memory, high-CPU environments."""
        return cls(
            batch_size=200,
            max_concurrent=6,
            retry_attempts=2,
            retry_delay_seconds=2.0,
            timeout_per_batch_seconds=120,
            auto_configured=True
        )
    
    def get_memory_estimate_mb(self, total_documents: int) -> float:
        """Estimate total memory usage for processing a document set."""
        docs_in_flight = self.max_concurrent * self.batch_size
        active_docs = min(docs_in_flight, total_documents)
        return active_docs * ESTIMATED_MB_PER_DOC


class EmbeddingBatchProcessor:
    """
    Processes documents in batches for embedding generation.
    
    Features:
    - Configurable batch size
    - Concurrent batch processing (for API providers)
    - Sequential processing (for local GPU models)
    - Automatic retry with exponential backoff
    - Progress callbacks
    - Stateful job resuming (filters out already-embedded documents)
    - Pause/cancel support
    """
    
    def __init__(
        self, 
        config: Optional[BatchConfig] = None,
        embed_fn: Optional[Callable] = None
    ):
        """
        Initialize the batch processor.
        
        Args:
            config: Batch processing configuration
            embed_fn: Embedding function (sync or async)
        """
        self.config = config or BatchConfig()
        self.embed_fn = embed_fn
        self._cancelled = False
        self._paused = False
        self._existing_ids: Optional[Set[str]] = None
        self._skipped_count: int = 0
    
    def set_embed_function(self, embed_fn: Callable) -> None:
        """Set the embedding function."""
        self.embed_fn = embed_fn
    
    def set_existing_ids(self, existing_ids: Set[str]) -> None:
        """
        Set IDs of documents already in vector store for resume support.
        
        Documents with these IDs will be skipped during processing.
        """
        self._existing_ids = existing_ids
        logger.info(f"Stateful resuming enabled: {len(existing_ids)} existing documents will be skipped")
    
    def generate_chunk_id(self, content: str, parent_id: str = "unknown") -> str:
        """Generate a chunk ID matching the embedding job logic."""
        return hashlib.sha256(f"{content}{parent_id}".encode()).hexdigest()
    
    async def process_documents(
        self,
        documents: List[Dict[str, Any]],
        on_progress: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
        on_batch_complete: Optional[Callable[[BatchResult], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Process all documents in batches.
        
        Args:
            documents: List of document dicts with 'id', 'content', 'metadata'
            on_progress: Async callback(processed, failed, total)
            on_batch_complete: Async callback(BatchResult) after each batch
            
        Returns:
            Dict with processing results
        """
        if not self.embed_fn:
            raise ValueError("Embedding function not set. Call set_embed_function() first.")
        
        self._cancelled = False
        self._paused = False
        self._skipped_count = 0
        
        total_documents = len(documents)
        
        # Filter out already-embedded documents if resuming
        if self._existing_ids and len(self._existing_ids) > 0:
            filtered_docs = []
            for doc in documents:
                parent_id = doc.get('metadata', {}).get('doc_id', doc.get('id', 'unknown'))
                chunk_id = self.generate_chunk_id(doc['content'], parent_id)
                
                if chunk_id not in self._existing_ids:
                    filtered_docs.append(doc)
                else:
                    self._skipped_count += 1
            
            logger.info(
                f"Stateful resume: Skipped {self._skipped_count} already-embedded documents, "
                f"processing {len(filtered_docs)} new documents"
            )
            
            if len(filtered_docs) == 0:
                return {
                    "success": True,
                    "total_documents": total_documents,
                    "processed_documents": 0,
                    "failed_documents": 0,
                    "skipped_documents": self._skipped_count,
                    "total_time_seconds": 0,
                    "average_speed": 0,
                    "cancelled": False,
                    "resumed": True
                }
            
            documents = filtered_docs
        
        total_to_process = len(documents)
        total_batches = math.ceil(total_to_process / self.config.batch_size)
        
        logger.info(f"Starting batch processing: {total_to_process} documents in {total_batches} batches")
        logger.info(f"Batch config: size={self.config.batch_size}, concurrent={self.config.max_concurrent}")
        
        # Create batches
        batches = []
        for i in range(0, total_to_process, self.config.batch_size):
            batch_docs = documents[i:i + self.config.batch_size]
            batch_num = len(batches) + 1
            batches.append((batch_num, i, batch_docs))
        
        # Results tracking
        processed_count = 0
        failed_count = 0
        start_time = time.time()
        
        # Check if embed function is async
        is_async = asyncio.iscoroutinefunction(self.embed_fn)
        
        # Sequential processing for local GPU models (optimal for MPS/CUDA)
        logger.info(f"Processing {len(batches)} batches sequentially (local model optimization)...")
        
        for batch_num, start_idx, batch_docs in batches:
            if self._cancelled:
                logger.info("Batch processing cancelled")
                break
            
            while self._paused:
                await asyncio.sleep(0.5)
                if self._cancelled:
                    break
            
            result = await self._process_batch(batch_num, start_idx, batch_docs, is_async)
            
            if result.success:
                processed_count += result.documents_processed
            else:
                failed_count += len(batch_docs)
                logger.error(f"Batch {batch_num} failed: {result.error_message}")
            
            if on_batch_complete:
                try:
                    await on_batch_complete(result)
                except Exception as e:
                    logger.warning(f"Batch complete callback failed: {e}")
            
            # Progress includes skipped documents
            total_handled = processed_count + self._skipped_count
            if on_progress:
                try:
                    await on_progress(total_handled, failed_count, total_documents)
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")
            
            # Progress logging every 10 batches
            if batch_num % 10 == 0 or batch_num == total_batches:
                elapsed = time.time() - start_time
                if elapsed > 0 and processed_count > 0:
                    docs_per_sec = processed_count / elapsed
                    remaining = total_to_process - processed_count
                    eta_seconds = remaining / docs_per_sec if docs_per_sec > 0 else 0
                    percent = (total_handled / total_documents) * 100
                    logger.info(
                        f"Batch {batch_num}/{total_batches} | "
                        f"{processed_count:,} processed + {self._skipped_count:,} skipped | "
                        f"{percent:.1f}% | {docs_per_sec:.1f} docs/sec | ETA: {eta_seconds:.0f}s"
                    )
        
        total_time = time.time() - start_time
        
        return {
            "success": failed_count == 0,
            "total_documents": total_documents,
            "processed_documents": processed_count,
            "failed_documents": failed_count,
            "skipped_documents": self._skipped_count,
            "total_time_seconds": total_time,
            "average_speed": processed_count / total_time if total_time > 0 else 0,
            "cancelled": self._cancelled,
            "resumed": self._skipped_count > 0
        }
    
    async def _process_batch(
        self,
        batch_number: int,
        start_index: int,
        documents: List[Dict[str, Any]],
        is_async: bool
    ) -> BatchResult:
        """
        Process a single batch with retry logic.
        """
        last_error = None
        texts = [doc["content"] for doc in documents]
        
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
                if is_async:
                    embeddings = await asyncio.wait_for(
                        self.embed_fn(texts),
                        timeout=self.config.timeout_per_batch_seconds
                    )
                else:
                    # Sync function - call directly (we're in background thread)
                    embeddings = self.embed_fn(texts)
                
                processing_time = int((time.time() - start_time) * 1000)
                
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
