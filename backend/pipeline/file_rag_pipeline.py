"""
File RAG Pipeline — Selective text column extraction and embedding for uploaded files.

Architecture for 6.5M Row Datasets:
1. NEVER embed structured columns (age, patient_id, blood_pressure)
2. ONLY embed unstructured text columns (doctor_notes, clinical_history)
3. Use local BGE-M3 embeddings (zero OpenAI cost, GPU-accelerated)
4. Parent-Child chunking for precise retrieval with full context

Example:
- 6.5M rows total, but only 1M rows have doctor_notes
- Generate ~1M parent chunks + ~4M child chunks
- Embed only the child chunks (4M * 1024 dims = ~16GB vectors)
- Retrieval: Search children → Return parent document IDs
"""

import asyncio
import hashlib
import logging
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple
from datetime import datetime

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


@dataclass
class FileRAGConfig:
    """Configuration for file RAG pipeline."""
    # Columns to embed (auto-detected if empty)
    text_columns: List[str] = field(default_factory=list)
    # Columns to exclude from RAG
    exclude_columns: List[str] = field(default_factory=list)
    # Parent chunk settings
    parent_chunk_size: int = 800
    parent_chunk_overlap: int = 150
    # Child chunk settings  
    child_chunk_size: int = 200
    child_chunk_overlap: int = 50
    # Embedding settings
    embedding_batch_size: int = 128
    # Processing settings
    max_rows_per_batch: int = 10000
    # Minimum text length to consider for RAG
    min_text_length: int = 50


@dataclass
class RAGDocument:
    """A document prepared for RAG embedding."""
    doc_id: str
    content: str
    metadata: Dict[str, Any]
    source_row_id: str
    source_column: str


@dataclass
class ChunkedDocument:
    """A chunked document with parent-child relationship."""
    chunk_id: str
    content: str
    parent_id: str
    metadata: Dict[str, Any]
    is_parent: bool = False


class FileRAGPipeline:
    """
    RAG pipeline for uploaded file data with selective text extraction.
    
    Key Design Decisions:
    1. Only embed unstructured text columns (detected automatically or configured)
    2. Use parent-child chunking for precise retrieval with context
    3. Stream processing for memory efficiency with large files
    4. Async embedding with local BGE-M3 (no API costs)
    
    For a 6.5M row clinical dataset:
    - Structured columns (age, gender, bmi) → SQL only (zero embedding)
    - Text columns (doctor_notes) → Parent-child RAG (~4M child chunks)
    """
    
    def __init__(
        self,
        user_id: int,
        config: Optional[FileRAGConfig] = None,
        embedding_provider: Optional[Any] = None,
    ):
        self.user_id = user_id
        self.config = config or FileRAGConfig()
        self._embedding_provider = embedding_provider
        self._parent_splitter = None
        self._child_splitter = None
        self._init_splitters()
    
    def _init_splitters(self):
        """Initialize text splitters for parent-child chunking."""
        self._parent_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=self.config.parent_chunk_size,
            chunk_overlap=self.config.parent_chunk_overlap,
        )
        self._child_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=self.config.child_chunk_size,
            chunk_overlap=self.config.child_chunk_overlap,
        )
    
    @property
    def embedding_provider(self):
        """Lazy initialization of embedding provider."""
        if self._embedding_provider is None:
            from backend.services.embedding_providers import BGEProvider
            self._embedding_provider = BGEProvider(
                model_path="./models/bge-m3",
                batch_size=self.config.embedding_batch_size,
            )
            logger.info(f"Initialized BGE-M3 provider on {self._embedding_provider._actual_device}")
        return self._embedding_provider
    
    def _generate_doc_id(self, row_id: str, column: str, content: str) -> str:
        """Generate stable document ID for a text cell."""
        # Combine row ID + column + content hash for uniqueness
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"{row_id}_{column}_{content_hash}"
    
    def _generate_chunk_id(self, parent_id: str, chunk_idx: int) -> str:
        """Generate stable chunk ID."""
        return f"{parent_id}_c{chunk_idx}"
    
    async def extract_text_documents(
        self,
        table_name: str,
        text_columns: List[str],
        id_column: str = "patient_id",
        batch_size: int = 10000,
        on_progress: Optional[callable] = None,
    ) -> AsyncIterator[List[RAGDocument]]:
        """
        Stream text documents from DuckDB table for RAG embedding.
        
        OPTIMIZED (Task 10): Uses DuckDB fetchdf() + pandas vectorized ops
        instead of row-by-row Python loops.
        
        Args:
            table_name: DuckDB table name
            text_columns: Columns to extract for RAG
            id_column: Column to use as row identifier
            batch_size: Rows per batch
            on_progress: Callback(processed_rows, total_rows)
            
        Yields:
            Batches of RAGDocument objects
        """
        import duckdb
        from backend.api.routes.ingestion import _get_user_duckdb_path
        
        db_path = _get_user_duckdb_path(self.user_id)
        if not db_path.exists():
            raise ValueError(f"No database found for user {self.user_id}")
        
        conn = duckdb.connect(str(db_path), read_only=True)
        
        try:
            # Get total row count
            total_rows = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            logger.info(f"Extracting text from {table_name}: {total_rows:,} rows, columns: {text_columns}")
            
            # Build column list for query
            columns_sql = ", ".join([id_column] + text_columns)
            
            # Stream in batches using OFFSET/LIMIT
            offset = 0
            processed = 0
            
            while offset < total_rows:
                query = f"""
                    SELECT {columns_sql}
                    FROM {table_name}
                    LIMIT {batch_size}
                    OFFSET {offset}
                """
                
                # OPTIMIZATION: Use fetchdf() instead of fetchall() + row-by-row loop
                df = conn.execute(query).fetchdf()
                if df.empty:
                    break
                
                # Single timestamp for entire batch (not per-row datetime.now())
                batch_timestamp = datetime.now().isoformat()
                
                # Process each text column using vectorized pandas operations
                batch_docs = []
                for col in text_columns:
                    if col not in df.columns:
                        continue
                    
                    # Vectorized null/length filtering
                    col_series = df[col].astype(str).str.strip()
                    valid_mask = (
                        df[col].notna() & 
                        (col_series != '') & 
                        (col_series != 'None') &
                        (col_series != 'nan') &
                        (col_series.str.len() >= self.config.min_text_length)
                    )
                    
                    valid_df = df[valid_mask]
                    if valid_df.empty:
                        continue
                    
                    # Vectorized row ID generation
                    row_ids = valid_df[id_column].astype(str).fillna(
                        "row_" + pd.Series(range(offset, offset + len(valid_df))).astype(str).values
                    )
                    valid_texts = col_series[valid_mask]
                    
                    # Vectorized doc_id: row_id + column + content_hash (first 8 chars)
                    content_hashes = valid_texts.apply(
                        lambda x: hashlib.sha256(x.encode()).hexdigest()[:8]
                    )
                    doc_ids = row_ids + "_" + col + "_" + content_hashes
                    
                    # Build RAGDocuments from vectorized results
                    for row_id, text, doc_id in zip(row_ids.values, valid_texts.values, doc_ids.values):
                        batch_docs.append(RAGDocument(
                            doc_id=doc_id,
                            content=text,
                            metadata={
                                "source_table": table_name,
                                "source_column": col,
                                "row_id": row_id,
                                "extraction_time": batch_timestamp,
                            },
                            source_row_id=row_id,
                            source_column=col,
                        ))
                
                processed += len(df)
                offset += batch_size
                
                if on_progress:
                    on_progress(processed, total_rows)
                
                if batch_docs:
                    yield batch_docs
                
                # Allow other async tasks to run
                await asyncio.sleep(0)
            
            logger.info(f"Text extraction complete: {processed:,} rows processed")
            
        finally:
            conn.close()
    
    def create_parent_child_chunks(
        self,
        documents: List[RAGDocument],
    ) -> Tuple[List[ChunkedDocument], List[ChunkedDocument]]:
        """
        Apply parent-child chunking to documents.
        
        OPTIMIZED (Task 11): Batches documents for splitter calls instead of
        calling split_documents([single_doc]) per document.
        
        Args:
            documents: Source documents to chunk
            
        Returns:
            Tuple of (parent_chunks, child_chunks)
        """
        parent_chunks = []
        child_chunks = []
        
        # OPTIMIZATION: Batch documents for splitter calls
        # Convert all RAGDocuments to LangChain Documents once, then split in bulk
        SPLIT_BATCH_SIZE = 200
        
        for batch_start in range(0, len(documents), SPLIT_BATCH_SIZE):
            batch = documents[batch_start:batch_start + SPLIT_BATCH_SIZE]
            
            # Build LangChain documents for this batch with tracking metadata
            lc_docs = []
            for doc in batch:
                lc_doc = Document(
                    page_content=doc.content,
                    metadata={**doc.metadata, "_rag_doc_id": doc.doc_id},
                )
                lc_docs.append(lc_doc)
            
            # Batch split into parent chunks
            parent_docs = self._parent_splitter.split_documents(lc_docs)
            
            # Group parent docs by their original RAG doc ID
            parent_groups = {}
            for parent_doc in parent_docs:
                rag_doc_id = parent_doc.metadata.get("_rag_doc_id", "unknown")
                if rag_doc_id not in parent_groups:
                    parent_groups[rag_doc_id] = []
                parent_groups[rag_doc_id].append(parent_doc)
            
            # Process parent chunks and create children
            for rag_doc_id, parent_doc_list in parent_groups.items():
                for p_idx, parent_doc in enumerate(parent_doc_list):
                    parent_id = f"{rag_doc_id}_p{p_idx}"
                    
                    # Clean up tracking metadata before storing
                    clean_metadata = {k: v for k, v in parent_doc.metadata.items() if k != "_rag_doc_id"}
                    
                    parent_chunk = ChunkedDocument(
                        chunk_id=parent_id,
                        content=parent_doc.page_content,
                        parent_id=parent_id,
                        metadata={
                            **clean_metadata,
                            "chunk_type": "parent",
                            "parent_idx": p_idx,
                            "original_doc_id": rag_doc_id,
                        },
                        is_parent=True,
                    )
                    parent_chunks.append(parent_chunk)
                    
                    # Split this parent into child chunks
                    child_docs = self._child_splitter.split_documents([parent_doc])
                    
                    for c_idx, child_doc in enumerate(child_docs):
                        child_id = self._generate_chunk_id(parent_id, c_idx)
                        child_chunk = ChunkedDocument(
                            chunk_id=child_id,
                            content=child_doc.page_content,
                            parent_id=parent_id,
                            metadata={
                                **{k: v for k, v in child_doc.metadata.items() if k != "_rag_doc_id"},
                                "chunk_type": "child",
                                "child_idx": c_idx,
                                "parent_id": parent_id,
                                "original_doc_id": rag_doc_id,
                            },
                            is_parent=False,
                        )
                        child_chunks.append(child_chunk)
        
        return parent_chunks, child_chunks
    
    async def embed_chunks(
        self,
        chunks: List[ChunkedDocument],
        batch_size: int = 128,
        on_progress: Optional[callable] = None,
    ) -> List[Tuple[str, List[float]]]:
        """
        Embed chunks using local BGE-M3 model.
        
        Args:
            chunks: Chunks to embed
            batch_size: Embedding batch size
            on_progress: Callback(processed, total)
            
        Returns:
            List of (chunk_id, embedding_vector) tuples
        """
        if not chunks:
            return []
        
        results = []
        total = len(chunks)
        
        logger.info(f"Embedding {total:,} chunks with BGE-M3...")
        
        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.content for c in batch]
            
            # Use async embedding (runs in executor for BGE)
            embeddings = await self.embedding_provider.aembed_documents(texts)
            
            for chunk, embedding in zip(batch, embeddings):
                results.append((chunk.chunk_id, embedding))
            
            if on_progress:
                on_progress(len(results), total)
            
            # Allow other async tasks to run
            await asyncio.sleep(0)
        
        logger.info(f"Embedding complete: {len(results):,} vectors")
        return results
    
    async def process_table_for_rag(
        self,
        table_name: str,
        text_columns: List[str],
        id_column: str = "patient_id",
        on_progress: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline: Extract text → Chunk → Embed → Store.
        
        This is the main entry point for RAG processing of uploaded files.
        
        Args:
            table_name: DuckDB table name
            text_columns: Columns to process for RAG
            id_column: Row identifier column
            on_progress: Callback(phase, current, total, message)
            
        Returns:
            Processing statistics
        """
        stats = {
            "table_name": table_name,
            "text_columns": text_columns,
            "total_documents": 0,
            "parent_chunks": 0,
            "child_chunks": 0,
            "embeddings_created": 0,
            "processing_time_seconds": 0,
            "status": "processing",
        }
        
        start_time = datetime.now()
        
        try:
            all_parent_chunks = []
            all_child_chunks = []
            
            # Phase 1: Extract text documents
            if on_progress:
                on_progress("extraction", 0, 100, "Extracting text from database...")
            
            async for doc_batch in self.extract_text_documents(
                table_name=table_name,
                text_columns=text_columns,
                id_column=id_column,
                on_progress=lambda curr, total: on_progress("extraction", curr, total, f"Extracted {curr:,}/{total:,} rows") if on_progress else None,
            ):
                stats["total_documents"] += len(doc_batch)
                
                # Phase 2: Create parent-child chunks
                parent_chunks, child_chunks = self.create_parent_child_chunks(doc_batch)
                all_parent_chunks.extend(parent_chunks)
                all_child_chunks.extend(child_chunks)
            
            stats["parent_chunks"] = len(all_parent_chunks)
            stats["child_chunks"] = len(all_child_chunks)
            
            logger.info(
                f"Chunking complete: {stats['total_documents']:,} docs → "
                f"{stats['parent_chunks']:,} parents + {stats['child_chunks']:,} children"
            )
            
            # Phase 3: Embed child chunks (parents are retrieved via child.parent_id)
            if on_progress:
                on_progress("embedding", 0, len(all_child_chunks), "Embedding child chunks...")
            
            embeddings = await self.embed_chunks(
                chunks=all_child_chunks,
                on_progress=lambda curr, total: on_progress("embedding", curr, total, f"Embedded {curr:,}/{total:,} chunks") if on_progress else None,
            )
            
            stats["embeddings_created"] = len(embeddings)
            
            # Phase 4: Store in vector database
            if on_progress:
                on_progress("storing", 0, 100, "Storing vectors and parent documents...")
            
            await self._store_rag_data(
                table_name=table_name,
                parent_chunks=all_parent_chunks,
                child_chunks=all_child_chunks,
                embeddings=embeddings,
            )
            
            stats["status"] = "success"
            
        except Exception as e:
            logger.error(f"RAG processing failed: {e}")
            stats["status"] = "error"
            stats["error"] = str(e)
            raise
        
        finally:
            stats["processing_time_seconds"] = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"RAG processing complete: {stats}")
        return stats
    
    async def _store_rag_data(
        self,
        table_name: str,
        parent_chunks: List[ChunkedDocument],
        child_chunks: List[ChunkedDocument],
        embeddings: List[Tuple[str, List[float]]],
    ):
        """
        Store parent documents and child embeddings for RAG retrieval.
        
        Storage Strategy:
        - Parent documents: SQLite docstore (for context retrieval)
        - Child embeddings: ChromaDB collection (for vector search)
        """
        from backend.pipeline.docstore import SQLiteDocStore
        
        # Get storage paths
        from backend.api.routes.ingestion import _get_user_data_dir
        user_dir = _get_user_data_dir(self.user_id)
        
        # Store parent documents in SQLite docstore
        docstore_path = user_dir / f"{table_name}_parents.db"
        docstore = SQLiteDocStore(str(docstore_path))
        
        parent_data = [
            (chunk.chunk_id, Document(page_content=chunk.content, metadata=chunk.metadata))
            for chunk in parent_chunks
        ]
        docstore.mset(parent_data)
        logger.info(f"Stored {len(parent_data)} parent documents in {docstore_path}")
        
        # Store child embeddings in ChromaDB
        try:
            import chromadb
            from chromadb.config import Settings
            
            chroma_path = user_dir / "chroma_db"
            chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
            
            collection_name = f"file_rag_{table_name}"
            
            # Delete existing collection if exists
            try:
                chroma_client.delete_collection(collection_name)
            except Exception:
                pass
            
            collection = chroma_client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            
            # Build embedding lookup
            embedding_map = {chunk_id: emb for chunk_id, emb in embeddings}
            
            # Batch insert to ChromaDB
            batch_size = 1000
            for i in range(0, len(child_chunks), batch_size):
                batch = child_chunks[i:i + batch_size]
                
                ids = [c.chunk_id for c in batch]
                documents = [c.content for c in batch]
                metadatas = [c.metadata for c in batch]
                embs = [embedding_map[c.chunk_id] for c in batch]
                
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embs,
                )
            
            logger.info(f"Stored {len(child_chunks)} child embeddings in ChromaDB collection: {collection_name}")
            
        except ImportError:
            logger.warning("ChromaDB not installed, skipping vector storage")
    
    async def semantic_search(
        self,
        query: str,
        table_name: str,
        top_k: int = 10,
        return_parents: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search against embedded text columns.
        
        Search Flow:
        1. Embed query using BGE-M3
        2. Search child chunks in ChromaDB
        3. Retrieve parent documents for full context
        
        Args:
            query: Search query
            table_name: Table to search
            top_k: Number of results
            return_parents: Whether to return parent documents (full context)
            
        Returns:
            List of search results with scores and context
        """
        import chromadb
        from chromadb.config import Settings
        from backend.pipeline.docstore import SQLiteDocStore
        from backend.api.routes.ingestion import _get_user_data_dir
        
        user_dir = _get_user_data_dir(self.user_id)
        
        # Embed query
        query_embedding = await self.embedding_provider.aembed_query(query)
        
        # Search ChromaDB
        chroma_path = user_dir / "chroma_db"
        chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
        
        collection_name = f"file_rag_{table_name}"
        collection = chroma_client.get_collection(collection_name)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        
        # Process results
        search_results = []
        seen_parents = set()
        
        if return_parents:
            # Load parent docstore
            docstore_path = user_dir / f"{table_name}_parents.db"
            docstore = SQLiteDocStore(str(docstore_path))
        
        for i in range(len(results["ids"][0])):
            chunk_id = results["ids"][0][i]
            child_content = results["documents"][0][i]
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            
            # Convert distance to similarity score (ChromaDB uses L2 by default)
            # For cosine distance: similarity = 1 - distance
            similarity = 1 - distance
            
            result = {
                "chunk_id": chunk_id,
                "child_content": child_content,
                "similarity_score": round(similarity, 4),
                "metadata": metadata,
            }
            
            # Get parent document for full context
            if return_parents and "parent_id" in metadata:
                parent_id = metadata["parent_id"]
                if parent_id not in seen_parents:
                    parent_docs = docstore.mget([parent_id])
                    if parent_docs and parent_docs[0]:
                        result["parent_content"] = parent_docs[0].page_content
                        result["parent_id"] = parent_id
                    seen_parents.add(parent_id)
            
            # Include source row info for SQL join capability
            if "row_id" in metadata:
                result["source_row_id"] = metadata["row_id"]
            if "source_column" in metadata:
                result["source_column"] = metadata["source_column"]
            
            search_results.append(result)
        
        return search_results


# Convenience function
def get_file_rag_pipeline(
    user_id: int,
    config: Optional[FileRAGConfig] = None,
) -> FileRAGPipeline:
    """Get a FileRAGPipeline instance for a user."""
    return FileRAGPipeline(user_id, config)
