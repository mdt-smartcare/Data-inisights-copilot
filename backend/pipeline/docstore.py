"""
Persistent Document Store for RAG Pipeline.

This module provides disk-backed storage for parent documents during
the Small-to-Big (Parent-Child) chunking process, eliminating OOM risks
that occur with in-memory dictionaries on large medical datasets.

Bottleneck Addressed:
- SimpleInMemoryStore caused heap exhaustion on datasets > 500K documents
- SQLite provides ACID guarantees and memory-mapped I/O for efficient access

Usage:
    docstore = SQLiteDocStore(db_path="/tmp/docstore.db")
    docstore.mset([("id1", doc1), ("id2", doc2)])
    docs = docstore.mget(["id1", "id2"])
"""
import sqlite3
import pickle
import hashlib
import logging
from typing import List, Optional, Tuple, Iterator
from pathlib import Path
from contextlib import contextmanager

from langchain_core.documents import Document
from langchain_core.stores import BaseStore

logger = logging.getLogger(__name__)


class SQLiteDocStore(BaseStore[str, Document]):
    """
    SQLite-backed document store implementing LangChain's BaseStore interface.
    
    This replaces SimpleInMemoryStore to prevent memory exhaustion during
    large-scale medical data ingestion. Documents are serialized via pickle
    and stored in a SQLite database with WAL mode for concurrent read access.
    
    Memory Mitigation:
    - Documents stored on disk, not heap
    - SQLite's page cache provides LRU eviction
    - Batch operations minimize transaction overhead
    
    Attributes:
        db_path: Path to SQLite database file
        batch_size: Number of documents per batch insert (default: 1000)
    """
    
    def __init__(self, db_path: str, batch_size: int = 1000):
        """
        Initialize SQLite document store.
        
        Args:
            db_path: Path to SQLite database file. Created if not exists.
            batch_size: Documents per transaction for bulk inserts.
        """
        self.db_path = db_path
        self.batch_size = batch_size
        self._init_db()
        logger.info(f"SQLiteDocStore initialized at {db_path}")
    
    def _init_db(self):
        """Create schema with optimized settings for document storage."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Enable WAL mode for concurrent reads during embedding
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    doc_blob BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash 
                ON documents(content_hash)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def mget(self, keys: List[str]) -> List[Optional[Document]]:
        """
        Retrieve documents by IDs.
        
        Args:
            keys: List of document IDs to retrieve
            
        Returns:
            List of Documents (None for missing keys)
        """
        if not keys:
            return []
        
        results = {key: None for key in keys}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Batch fetch to avoid SQLite variable limits
            for i in range(0, len(keys), 500):
                batch_keys = keys[i:i + 500]
                placeholders = ",".join("?" * len(batch_keys))
                
                cursor.execute(
                    f"SELECT doc_id, doc_blob FROM documents WHERE doc_id IN ({placeholders})",
                    batch_keys
                )
                
                for row in cursor.fetchall():
                    doc_id = row["doc_id"]
                    doc_blob = row["doc_blob"]
                    try:
                        results[doc_id] = pickle.loads(doc_blob)
                    except Exception as e:
                        logger.warning(f"Failed to deserialize doc {doc_id}: {e}")
        
        return [results[key] for key in keys]
    
    def mset(self, key_value_pairs: List[Tuple[str, Document]]) -> None:
        """
        Store documents with their IDs.
        
        Uses batch inserts with UPSERT semantics for idempotent writes.
        
        Args:
            key_value_pairs: List of (doc_id, Document) tuples
        """
        if not key_value_pairs:
            return
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Process in batches to limit memory during serialization
            for i in range(0, len(key_value_pairs), self.batch_size):
                batch = key_value_pairs[i:i + self.batch_size]
                
                rows = []
                for doc_id, doc in batch:
                    doc_blob = pickle.dumps(doc)
                    content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
                    rows.append((doc_id, content_hash, doc_blob))
                
                cursor.executemany(
                    """INSERT INTO documents (doc_id, content_hash, doc_blob)
                       VALUES (?, ?, ?)
                       ON CONFLICT(doc_id) DO UPDATE SET
                           content_hash = excluded.content_hash,
                           doc_blob = excluded.doc_blob""",
                    rows
                )
            
            conn.commit()
        
        logger.debug(f"Stored {len(key_value_pairs)} documents to SQLite docstore")
    
    def mdelete(self, keys: List[str]) -> None:
        """
        Delete documents by IDs.
        
        Args:
            keys: List of document IDs to delete
        """
        if not keys:
            return
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for i in range(0, len(keys), 500):
                batch_keys = keys[i:i + 500]
                placeholders = ",".join("?" * len(batch_keys))
                cursor.execute(
                    f"DELETE FROM documents WHERE doc_id IN ({placeholders})",
                    batch_keys
                )
            
            conn.commit()
    
    def yield_keys(self, prefix: Optional[str] = None) -> Iterator[str]:
        """
        Iterate over all document IDs.
        
        Args:
            prefix: Optional prefix filter for IDs
            
        Yields:
            Document IDs matching the prefix
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if prefix:
                cursor.execute(
                    "SELECT doc_id FROM documents WHERE doc_id LIKE ?",
                    (f"{prefix}%",)
                )
            else:
                cursor.execute("SELECT doc_id FROM documents")
            
            for row in cursor:
                yield row["doc_id"]
    
    def count(self) -> int:
        """Return total number of documents stored."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            return cursor.fetchone()[0]
    
    def clear(self) -> None:
        """Delete all documents from the store."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents")
            conn.commit()
        logger.info("SQLiteDocStore cleared")
    
    def export_to_pickle(self, output_path: str) -> None:
        """
        Export docstore to pickle file for backward compatibility.
        
        This allows the retriever to load parent docs via the existing
        pickle-based loading mechanism.
        
        Args:
            output_path: Path to write pickle file
        """
        # Create a SimpleInMemoryStore-compatible dict
        all_docs = {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id, doc_blob FROM documents")
            
            for row in cursor:
                try:
                    all_docs[row["doc_id"]] = pickle.loads(row["doc_blob"])
                except Exception as e:
                    logger.warning(f"Skip corrupted doc {row['doc_id']}: {e}")
        
        # Wrap in SimpleInMemoryStore for compatibility
        from backend.pipeline.transform import SimpleInMemoryStore
        store = SimpleInMemoryStore()
        store._dict = all_docs
        
        with open(output_path, "wb") as f:
            pickle.dump(store, f)
        
        logger.info(f"Exported {len(all_docs)} docs to {output_path}")


class StreamingDocStore(SQLiteDocStore):
    """
    Extended SQLite docstore with streaming/generator support.
    
    Provides memory-efficient iteration for embedding pipelines
    that process documents in batches without loading all into memory.
    """
    
    def iter_batches(self, batch_size: int = 100) -> Iterator[List[Tuple[str, Document]]]:
        """
        Iterate documents in batches for memory-efficient processing.
        
        Args:
            batch_size: Number of documents per batch
            
        Yields:
            Batches of (doc_id, Document) tuples
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id, doc_blob FROM documents")
            
            batch = []
            for row in cursor:
                try:
                    doc = pickle.loads(row["doc_blob"])
                    batch.append((row["doc_id"], doc))
                    
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                except Exception as e:
                    logger.warning(f"Skip corrupted doc: {e}")
            
            if batch:
                yield batch
