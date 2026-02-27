"""
Embedding Job Checkpoint Service - Enables resume from any phase.

Provides persistent checkpointing for long-running embedding jobs:
- Phase 1: Extraction checkpoint (table data saved to disk)
- Phase 2: Document creation checkpoint (documents saved to SQLite)
- Phase 3: Chunking checkpoint (child chunks saved to SQLite)
- Phase 4: Embedding checkpoint (already handled by ChromaDB)

Each checkpoint is stored in the job's vector DB directory and can be
used to resume a failed/cancelled job without re-processing earlier phases.
"""
import os
import json
import sqlite3
import pickle
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

from backend.core.logging import get_embedding_logger

logger = get_embedding_logger()


class CheckpointPhase(str, Enum):
    """Phases that can be checkpointed."""
    EXTRACTION = "extraction"
    DOCUMENTS = "documents"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETE = "complete"


@dataclass
class CheckpointMetadata:
    """Metadata about a checkpoint."""
    job_id: str
    config_id: int
    phase: CheckpointPhase
    created_at: str
    total_items: int
    checksum: str  # For integrity verification
    incremental: bool
    extra: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['phase'] = self.phase.value
        return d
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'CheckpointMetadata':
        d['phase'] = CheckpointPhase(d['phase'])
        return cls(**d)


class EmbeddingCheckpointService:
    """
    Service for managing embedding job checkpoints.
    
    Checkpoints are stored in the vector DB directory:
    data/indexes/{vector_db_name}/checkpoints/
        ├── metadata.json          # Current checkpoint state
        ├── extraction.pkl         # Extracted table data
        ├── documents.db           # SQLite DB with documents
        └── chunks.db              # SQLite DB with child chunks
    """
    
    CHECKPOINT_DIR = "checkpoints"
    METADATA_FILE = "metadata.json"
    EXTRACTION_FILE = "extraction.pkl"
    DOCUMENTS_DB = "documents.db"
    CHUNKS_DB = "chunks.db"
    
    def __init__(self, base_path: str, vector_db_name: str):
        """
        Initialize checkpoint service.
        
        Args:
            base_path: Base path to data/indexes directory
            vector_db_name: Name of the vector DB (used as subdirectory)
        """
        self.base_path = Path(base_path)
        self.vector_db_name = vector_db_name
        self.checkpoint_path = self.base_path / vector_db_name / self.CHECKPOINT_DIR
        self.checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Checkpoint service initialized at {self.checkpoint_path}")
    
    def _get_file_path(self, filename: str) -> Path:
        """Get full path to a checkpoint file."""
        return self.checkpoint_path / filename
    
    def _compute_checksum(self, data: Any) -> str:
        """Compute MD5 checksum of data for integrity verification."""
        if isinstance(data, (list, dict)):
            data_str = json.dumps(data, sort_keys=True, default=str)
        else:
            data_str = str(data)
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def _init_sqlite_db(self, db_path: Path, table_schema: str) -> sqlite3.Connection:
        """Initialize a SQLite database with the given schema."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # Use executescript for multiple statements (CREATE TABLE + CREATE INDEX)
        conn.executescript(table_schema)
        conn.commit()
        return conn
    
    # =========================================================================
    # Metadata Management
    # =========================================================================
    
    def save_metadata(self, metadata: CheckpointMetadata) -> None:
        """Save checkpoint metadata."""
        metadata_path = self._get_file_path(self.METADATA_FILE)
        with open(metadata_path, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        logger.info(f"Checkpoint metadata saved: phase={metadata.phase.value}, items={metadata.total_items}")
    
    def load_metadata(self) -> Optional[CheckpointMetadata]:
        """Load checkpoint metadata if it exists."""
        metadata_path = self._get_file_path(self.METADATA_FILE)
        if not metadata_path.exists():
            return None
        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)
            return CheckpointMetadata.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint metadata: {e}")
            return None
    
    def get_resume_phase(self) -> Optional[CheckpointPhase]:
        """
        Determine which phase to resume from based on existing checkpoints.
        
        Returns the NEXT phase to run (not the completed one).
        """
        metadata = self.load_metadata()
        if not metadata:
            return None
        
        # Return the next phase after the completed one
        phase_order = [
            CheckpointPhase.EXTRACTION,
            CheckpointPhase.DOCUMENTS,
            CheckpointPhase.CHUNKING,
            CheckpointPhase.EMBEDDING,
            CheckpointPhase.COMPLETE
        ]
        
        try:
            current_idx = phase_order.index(metadata.phase)
            if current_idx < len(phase_order) - 1:
                return phase_order[current_idx + 1]
            return CheckpointPhase.COMPLETE
        except ValueError:
            return None
    
    def clear_checkpoints(self) -> None:
        """Clear all checkpoints (for full rebuild)."""
        import shutil
        if self.checkpoint_path.exists():
            shutil.rmtree(self.checkpoint_path)
            self.checkpoint_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cleared all checkpoints for {self.vector_db_name}")
    
    # =========================================================================
    # Phase 1: Extraction Checkpoint
    # =========================================================================
    
    def save_extraction_checkpoint(
        self,
        job_id: str,
        config_id: int,
        table_data: Dict[str, List[Dict]],
        incremental: bool = False
    ) -> None:
        """
        Save extracted table data to disk.
        
        Args:
            job_id: Current job ID
            config_id: Configuration ID
            table_data: Dict mapping table names to list of row dicts
            incremental: Whether this is an incremental run
        """
        extraction_path = self._get_file_path(self.EXTRACTION_FILE)
        
        # Calculate total rows
        total_rows = sum(len(rows) for rows in table_data.values())
        
        # Save table data as pickle (efficient for large data)
        with open(extraction_path, 'wb') as f:
            pickle.dump(table_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Save metadata
        metadata = CheckpointMetadata(
            job_id=job_id,
            config_id=config_id,
            phase=CheckpointPhase.EXTRACTION,
            created_at=datetime.utcnow().isoformat(),
            total_items=total_rows,
            checksum=self._compute_checksum(list(table_data.keys())),
            incremental=incremental,
            extra={"tables": list(table_data.keys()), "row_counts": {k: len(v) for k, v in table_data.items()}}
        )
        self.save_metadata(metadata)
        
        logger.info(f"Extraction checkpoint saved: {len(table_data)} tables, {total_rows} total rows")
    
    def load_extraction_checkpoint(self) -> Optional[Dict[str, List[Dict]]]:
        """
        Load extracted table data from checkpoint.
        
        Returns:
            Dict mapping table names to list of row dicts, or None if not found
        """
        extraction_path = self._get_file_path(self.EXTRACTION_FILE)
        if not extraction_path.exists():
            return None
        
        try:
            with open(extraction_path, 'rb') as f:
                table_data = pickle.load(f)
            
            total_rows = sum(len(rows) for rows in table_data.values())
            logger.info(f"Loaded extraction checkpoint: {len(table_data)} tables, {total_rows} rows")
            return table_data
        except Exception as e:
            logger.error(f"Failed to load extraction checkpoint: {e}")
            return None
    
    # =========================================================================
    # Phase 2: Documents Checkpoint
    # =========================================================================
    
    def save_documents_checkpoint(
        self,
        job_id: str,
        config_id: int,
        documents: List[Any],
        incremental: bool = False
    ) -> None:
        """
        Save created documents to SQLite database.
        
        Args:
            job_id: Current job ID
            config_id: Configuration ID
            documents: List of Document objects
            incremental: Whether this is an incremental run
        """
        db_path = self._get_file_path(self.DOCUMENTS_DB)
        
        # Remove existing DB to start fresh
        if db_path.exists():
            os.remove(db_path)
        
        # Create SQLite database
        conn = self._init_sqlite_db(db_path, '''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT UNIQUE,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_doc_id ON documents(doc_id);
        ''')
        
        # Insert documents in batches
        batch_size = 1000
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            rows = []
            for doc in batch:
                content = getattr(doc, 'page_content', getattr(doc, 'content', ''))
                metadata = getattr(doc, 'metadata', {})
                doc_id = metadata.get('source_id', metadata.get('doc_id', str(i)))
                rows.append((doc_id, content, json.dumps(metadata, default=str)))
            
            conn.executemany(
                'INSERT OR REPLACE INTO documents (doc_id, content, metadata) VALUES (?, ?, ?)',
                rows
            )
            conn.commit()
        
        conn.close()
        
        # Save metadata
        metadata = CheckpointMetadata(
            job_id=job_id,
            config_id=config_id,
            phase=CheckpointPhase.DOCUMENTS,
            created_at=datetime.utcnow().isoformat(),
            total_items=len(documents),
            checksum=self._compute_checksum(len(documents)),
            incremental=incremental
        )
        self.save_metadata(metadata)
        
        logger.info(f"Documents checkpoint saved: {len(documents)} documents")
    
    def load_documents_checkpoint(self) -> Optional[List[Any]]:
        """
        Load documents from checkpoint.
        
        Returns:
            List of Document objects, or None if not found
        """
        from langchain_core.documents import Document
        
        db_path = self._get_file_path(self.DOCUMENTS_DB)
        if not db_path.exists():
            return None
        
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT doc_id, content, metadata FROM documents')
            rows = cursor.fetchall()
            
            documents = []
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                doc = Document(page_content=row['content'], metadata=metadata)
                documents.append(doc)
            
            conn.close()
            logger.info(f"Loaded documents checkpoint: {len(documents)} documents")
            return documents
        except Exception as e:
            logger.error(f"Failed to load documents checkpoint: {e}")
            return None
    
    # =========================================================================
    # Phase 3: Chunking Checkpoint
    # =========================================================================
    
    def save_chunks_checkpoint(
        self,
        job_id: str,
        config_id: int,
        child_chunks: List[Any],
        incremental: bool = False
    ) -> None:
        """
        Save child chunks to SQLite database.
        
        Args:
            job_id: Current job ID
            config_id: Configuration ID
            child_chunks: List of child Document objects
            incremental: Whether this is an incremental run
        """
        db_path = self._get_file_path(self.CHUNKS_DB)
        
        # Remove existing DB to start fresh
        if db_path.exists():
            os.remove(db_path)
        
        # Create SQLite database
        conn = self._init_sqlite_db(db_path, '''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT UNIQUE,
                parent_id TEXT,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_chunk_id ON chunks(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_parent_id ON chunks(parent_id);
        ''')
        
        # Insert chunks in batches
        batch_size = 5000
        for i in range(0, len(child_chunks), batch_size):
            batch = child_chunks[i:i + batch_size]
            rows = []
            for chunk in batch:
                content = getattr(chunk, 'page_content', getattr(chunk, 'content', ''))
                metadata = getattr(chunk, 'metadata', {})
                parent_id = metadata.get('doc_id', 'unknown')
                chunk_id = hashlib.sha256(f"{content}{parent_id}".encode()).hexdigest()
                rows.append((chunk_id, parent_id, content, json.dumps(metadata, default=str)))
            
            conn.executemany(
                'INSERT OR REPLACE INTO chunks (chunk_id, parent_id, content, metadata) VALUES (?, ?, ?, ?)',
                rows
            )
            conn.commit()
        
        conn.close()
        
        # Save metadata
        metadata = CheckpointMetadata(
            job_id=job_id,
            config_id=config_id,
            phase=CheckpointPhase.CHUNKING,
            created_at=datetime.utcnow().isoformat(),
            total_items=len(child_chunks),
            checksum=self._compute_checksum(len(child_chunks)),
            incremental=incremental
        )
        self.save_metadata(metadata)
        
        logger.info(f"Chunks checkpoint saved: {len(child_chunks)} chunks")
    
    def load_chunks_checkpoint(self) -> Optional[List[Any]]:
        """
        Load child chunks from checkpoint.
        
        Returns:
            List of Document objects, or None if not found
        """
        from langchain_core.documents import Document
        
        db_path = self._get_file_path(self.CHUNKS_DB)
        if not db_path.exists():
            return None
        
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT chunk_id, parent_id, content, metadata FROM chunks')
            rows = cursor.fetchall()
            
            chunks = []
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                doc = Document(page_content=row['content'], metadata=metadata)
                chunks.append(doc)
            
            conn.close()
            logger.info(f"Loaded chunks checkpoint: {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Failed to load chunks checkpoint: {e}")
            return None
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    def get_checkpoint_status(self) -> Dict[str, Any]:
        """
        Get current checkpoint status for the vector DB.
        
        Returns:
            Dict with checkpoint information
        """
        metadata = self.load_metadata()
        
        extraction_exists = self._get_file_path(self.EXTRACTION_FILE).exists()
        documents_exists = self._get_file_path(self.DOCUMENTS_DB).exists()
        chunks_exists = self._get_file_path(self.CHUNKS_DB).exists()
        
        return {
            "vector_db_name": self.vector_db_name,
            "checkpoint_path": str(self.checkpoint_path),
            "has_metadata": metadata is not None,
            "current_phase": metadata.phase.value if metadata else None,
            "job_id": metadata.job_id if metadata else None,
            "created_at": metadata.created_at if metadata else None,
            "total_items": metadata.total_items if metadata else None,
            "checkpoints": {
                "extraction": extraction_exists,
                "documents": documents_exists,
                "chunks": chunks_exists
            },
            "resume_phase": self.get_resume_phase().value if self.get_resume_phase() else None
        }
    
    def can_resume(self, config_id: int) -> Tuple[bool, Optional[CheckpointPhase], str]:
        """
        Check if a job can be resumed from checkpoint.
        
        Args:
            config_id: Configuration ID to verify
            
        Returns:
            Tuple of (can_resume, resume_phase, message)
        """
        metadata = self.load_metadata()
        
        if not metadata:
            return False, None, "No checkpoint found"
        
        if metadata.config_id != config_id:
            return False, None, f"Checkpoint is for config {metadata.config_id}, not {config_id}"
        
        resume_phase = self.get_resume_phase()
        if resume_phase == CheckpointPhase.COMPLETE:
            return False, None, "Previous job completed successfully"
        
        return True, resume_phase, f"Can resume from {resume_phase.value} phase"


def get_checkpoint_service(base_path: str, vector_db_name: str) -> EmbeddingCheckpointService:
    """Factory function to get a checkpoint service instance."""
    return EmbeddingCheckpointService(base_path, vector_db_name)
