"""
Persistent Document Store for RAG Pipeline.

Provides disk-backed storage for parent documents during the Small-to-Big 
(Parent-Child) chunking process, eliminating OOM risks that occur with 
in-memory dictionaries on large medical datasets.

Features:
- SQLite-backed storage (JSON columns, ~3x faster than pickle)
- LangChain BaseStore interface compatibility
- Batch operations for efficiency
- Export to pickle for backward compatibility
- Streaming iteration for memory-efficient processing
"""
import sqlite3
import json
import pickle
from typing import List, Optional, Tuple, Iterator
from pathlib import Path
from contextlib import contextmanager

from langchain_core.documents import Document
from langchain_core.stores import BaseStore

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class SQLiteDocStore(BaseStore[str, Document]):
    """
    SQLite-backed document store implementing LangChain's BaseStore interface.
    
    This replaces SimpleInMemoryStore to prevent memory exhaustion during
    large-scale data ingestion. Documents are stored as JSON columns
    (page_content + metadata) for fast serialization.
    
    Memory Mitigation:
    - Documents stored on disk, not heap
    - SQLite's page cache provides LRU eviction
    - Batch operations minimize transaction overhead
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
            
            # Check if table exists and what schema it has
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # Check if this is old pickle schema or new JSON schema
                cursor.execute("PRAGMA table_info(documents)")
                columns = {row[1] for row in cursor.fetchall()}
                
                if "doc_blob" in columns and "page_content" not in columns:
                    # Old pickle schema — migrate to JSON
                    logger.info("Migrating docstore from pickle to JSON schema...")
                    self._migrate_pickle_to_json(conn)
            else:
                # Create new JSON-based schema
                cursor.execute("""
                    CREATE TABLE documents (
                        doc_id TEXT PRIMARY KEY,
                        page_content TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_id ON documents(doc_id)")
            
            conn.commit()
    
    def _migrate_pickle_to_json(self, conn):
        """Migrate existing pickle-based docstore to JSON columns."""
        cursor = conn.cursor()
        
        # Add new columns
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN page_content TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        
        # Migrate existing data
        cursor.execute("SELECT doc_id, doc_blob FROM documents WHERE page_content = '' AND doc_blob IS NOT NULL")
        rows = cursor.fetchall()
        
        migrated = 0
        for row in rows:
            doc_id = row[0]
            doc_blob = row[1]
            try:
                doc = pickle.loads(doc_blob)
                metadata_json = json.dumps(doc.metadata, default=str)
                cursor.execute(
                    "UPDATE documents SET page_content = ?, metadata = ? WHERE doc_id = ?",
                    (doc.page_content, metadata_json, doc_id)
                )
                migrated += 1
            except Exception as e:
                logger.warning(f"Failed to migrate doc {doc_id}: {e}")
        
        conn.commit()
        logger.info(f"Migrated {migrated} documents from pickle to JSON")
    
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
                    f"SELECT doc_id, page_content, metadata FROM documents WHERE doc_id IN ({placeholders})",
                    batch_keys
                )
                
                for row in cursor.fetchall():
                    doc_id = row["doc_id"]
                    try:
                        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                        results[doc_id] = Document(
                            page_content=row["page_content"],
                            metadata=metadata
                        )
                    except Exception as e:
                        logger.warning(f"Failed to deserialize doc {doc_id}: {e}")
        
        return [results[key] for key in keys]
    
    def mset(self, key_value_pairs: List[Tuple[str, Document]]) -> None:
        """
        Store documents with their IDs.
        
        Args:
            key_value_pairs: List of (doc_id, Document) tuples
        """
        if not key_value_pairs:
            return
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Process in batches
            for i in range(0, len(key_value_pairs), self.batch_size):
                batch = key_value_pairs[i:i + self.batch_size]
                
                rows = []
                for doc_id, doc in batch:
                    metadata_json = json.dumps(doc.metadata, default=str)
                    rows.append((doc_id, doc.page_content, metadata_json))
                
                cursor.executemany(
                    """INSERT INTO documents (doc_id, page_content, metadata)
                       VALUES (?, ?, ?)
                       ON CONFLICT(doc_id) DO UPDATE SET
                           page_content = excluded.page_content,
                           metadata = excluded.metadata""",
                    rows
                )
            
            conn.commit()
        
        logger.debug(f"Stored {len(key_value_pairs)} documents to SQLite docstore")
    
    def mdelete(self, keys: List[str]) -> None:
        """Delete documents by IDs."""
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
    
    def __len__(self) -> int:
        """Return total number of documents stored."""
        return self.count()
    
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
        from app.modules.embeddings.transform import SimpleInMemoryStore
        
        all_docs = {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id, page_content, metadata FROM documents")
            
            for row in cursor:
                try:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    all_docs[row["doc_id"]] = Document(
                        page_content=row["page_content"],
                        metadata=metadata
                    )
                except Exception as e:
                    logger.warning(f"Skip corrupted doc {row['doc_id']}: {e}")
        
        # Wrap in SimpleInMemoryStore for compatibility
        store = SimpleInMemoryStore()
        store._dict = all_docs
        
        with open(output_path, "wb") as f:
            pickle.dump(store, f)
        
        logger.info(f"Exported {len(all_docs)} docs to {output_path}")

# // NOTE: Never used
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
            cursor.execute("SELECT doc_id, page_content, metadata FROM documents")
            
            batch = []
            for row in cursor:
                try:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    doc = Document(page_content=row["page_content"], metadata=metadata)
                    batch.append((row["doc_id"], doc))
                    
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                except Exception as e:
                    logger.warning(f"Skip corrupted doc: {e}")
            
            if batch:
                yield batch
    
    def get_all_documents(self) -> List[Document]:
        """
        Get all documents (use with caution for large datasets).
        
        Returns:
            List of all documents
        """
        docs = []
        for batch in self.iter_batches(batch_size=1000):
            docs.extend([doc for _, doc in batch])
        return docs
