"""
Advanced Data Transformer for RAG Embedding Pipeline.

Provides:
- Parent-Child (Small-to-Big) chunking strategy
- TabularDictionarySplitter for structured data (~50x faster than regex)
- Vectorized document creation with medical context enrichment
- In-memory docstore with pickle persistence (matching old backend's approach)
"""
import pandas as pd
import hashlib
import json
import pickle
import multiprocessing
from typing import Dict, List, Any, Tuple, Optional, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from datetime import datetime
from pathlib import Path

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CLINICAL_FLAG_PREFIXES = (
    'is_', 'has_', 'was_', 'history_of_', 'flag_', 
    'confirmed_', 'requires_', 'on_'
)

_SPLITTER_CACHE: Dict[str, Any] = {}


def _get_cached_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    cache_key = f"{chunk_size}_{chunk_overlap}"
    if cache_key not in _SPLITTER_CACHE:
        _SPLITTER_CACHE[cache_key] = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    return _SPLITTER_CACHE[cache_key]


class TabularDictionarySplitter:
    """Zero-regex splitter for structured tabular documents. ~50x faster than regex."""
    
    def __init__(self, keys_per_chunk: int = 10, chunk_overlap_keys: int = 2):
        self.keys_per_chunk = keys_per_chunk
        self.chunk_overlap_keys = chunk_overlap_keys
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        result = []
        for doc in documents:
            lines = [line for line in doc.page_content.split('\n') if line.strip()]
            if len(lines) <= self.keys_per_chunk:
                result.append(doc)
                continue
            step = max(1, self.keys_per_chunk - self.chunk_overlap_keys)
            for i in range(0, len(lines), step):
                chunk_lines = lines[i:i + self.keys_per_chunk]
                if not chunk_lines:
                    break
                result.append(Document(page_content='\n'.join(chunk_lines), metadata=dict(doc.metadata)))
                if i + self.keys_per_chunk >= len(lines):
                    break
        return result


def _get_tabular_splitter(keys_per_chunk: int = 10, chunk_overlap_keys: int = 2) -> TabularDictionarySplitter:
    cache_key = f"tabular_{keys_per_chunk}_{chunk_overlap_keys}"
    if cache_key not in _SPLITTER_CACHE:
        _SPLITTER_CACHE[cache_key] = TabularDictionarySplitter(keys_per_chunk, chunk_overlap_keys)
    return _SPLITTER_CACHE[cache_key]


class SimpleInMemoryStore(BaseStore[str, Document]):
    """In-memory document store for parent documents with pickle persistence."""
    def __init__(self):
        self._dict: Dict[str, Document] = {}

    def mget(self, keys: List[str]) -> List[Optional[Document]]:
        return [self._dict.get(key) for key in keys]
    
    def mset(self, key_value_pairs: List[Tuple[str, Document]]) -> None:
        for key, value in key_value_pairs:
            self._dict[key] = value
    
    def mdelete(self, keys: List[str]) -> None:
        for key in keys:
            self._dict.pop(key, None)

    def yield_keys(self, prefix: Optional[str] = None) -> Iterator[str]:
        for key in self._dict.keys():
            if prefix is None or key.startswith(prefix):
                yield key
    
    def __len__(self) -> int:
        return len(self._dict)
    
    def count(self) -> int:
        return len(self._dict)
    
    def save_to_pickle(self, file_path: str) -> None:
        """Save docstore to pickle file for persistence (matches old backend)."""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'wb') as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"Saved docstore to pickle: {file_path} ({len(self._dict)} docs)")
    
    @classmethod
    def load_from_pickle(cls, file_path: str) -> 'SimpleInMemoryStore':
        """Load docstore from pickle file."""
        with open(file_path, 'rb') as f:
            store = pickle.load(f)
        logger.info(f"Loaded docstore from pickle: {file_path} ({len(store._dict)} docs)")
        return store


class AdvancedDataTransformer:
    """Production-grade data transformer for RAG embedding pipeline."""
    
    def __init__(self, config: Dict, docstore_path: Optional[str] = None,
                 num_workers_override: Optional[int] = None, batch_size_override: Optional[int] = None):
        self.config = config
        self.docstore_path = docstore_path
        self.num_workers_override = num_workers_override
        self.batch_size_override = batch_size_override
        self.medical_context: Dict[str, str] = config.get('medical_context', {})
        prefixes_list = config.get('clinical_flag_prefixes', list(DEFAULT_CLINICAL_FLAG_PREFIXES))
        self.clinical_flag_prefixes: Tuple[str, ...] = tuple(prefixes_list)

    def _get_column_label(self, col: str) -> str:
        if col in self.medical_context:
            return f"{self.medical_context[col]} ({col}): "
        for prefix in self.clinical_flag_prefixes:
            if col.startswith(prefix):
                condition = col.replace(prefix, '').replace('_', ' ').title()
                prefix_label = prefix.rstrip('_').replace('_', ' ').title()
                return f"{prefix_label} {condition}: "
        return f"{col}: "

    def _generate_row_ids_vectorized(self, df: pd.DataFrame, table_name: str) -> pd.Series:
        pk_columns = ['id', 'patient_track_id', 'user_id', 'record_id']
        for pk_col in pk_columns:
            if pk_col in df.columns and df[pk_col].notna().all():
                return table_name + "_" + df[pk_col].astype(str)
        row_hashes = pd.util.hash_pandas_object(df, index=False)
        hex_hashes = row_hashes.apply(lambda h: format(h & 0xFFFFFFFFFFFFFFFF, '016x'))
        return table_name + "_" + hex_hashes

    def create_documents_from_tables(self, table_data: Dict[str, pd.DataFrame], 
                                      on_progress=None, check_cancellation=None) -> List[Document]:
        all_docs = []
        for i, (table_name, df) in enumerate(table_data.items()):
            if on_progress:
                on_progress(i, len(table_data), table_name)
            if check_cancellation and check_cancellation():
                raise Exception("Cancellation requested")
            if df.empty:
                continue
            
            cols_to_process = [c for c in df.columns.tolist() if c != 'is_latest']
            col_labels = {col: self._get_column_label(col) for col in cols_to_process}
            work_df = df[cols_to_process].copy()
            work_df = work_df.replace(['', 'null', 'none', 'nan', 'None', 'NaN', 'NULL', '[]', '{}'], pd.NA)
            
            content_series_list = []
            for col in cols_to_process:
                label = col_labels[col]
                col_data = work_df[col]
                is_clinical = any(col.startswith(p) for p in self.clinical_flag_prefixes)
                if is_clinical and col_data.dtype == 'bool':
                    formatted = col_data.map({True: 'Yes', False: 'No'}, na_action='ignore')
                else:
                    formatted = col_data.astype(str)
                content_series_list.append((label + formatted).where(col_data.notna(), None))
            
            doc_ids = self._generate_row_ids_vectorized(df, table_name)
            extraction_time = datetime.now().isoformat()
            
            for idx in range(len(df)):
                parts = [s.iloc[idx] for s in content_series_list if s.iloc[idx] is not None]
                if parts:
                    all_docs.append(Document(
                        page_content="\n".join(parts),
                        metadata={"source_table": table_name, "source_id": doc_ids.iloc[idx], "extraction_time": extraction_time}
                    ))
            logger.info(f"Generated docs for {table_name}: {len(df)} rows")
        return all_docs

    def _get_adaptive_parallelization(self, doc_count: int) -> Tuple[int, int]:
        cpu_count = multiprocessing.cpu_count()
        if self.num_workers_override and self.batch_size_override:
            return self.num_workers_override, self.batch_size_override
        if doc_count < 1000:
            return 1, doc_count
        elif doc_count < 50000:
            return min(4, max(2, cpu_count // 4)), 2000
        else:
            return max(2, cpu_count // 2), 5000

    def perform_parent_child_chunking(self, documents: List[Document], 
                                       on_progress=None, check_cancellation=None) -> Tuple[List[Document], BaseStore]:
        parent_config = self.config.get('chunking', {}).get('parent_splitter', {'chunk_size': 512, 'chunk_overlap': 100})
        child_config = self.config.get('chunking', {}).get('child_splitter', {'chunk_size': 128, 'chunk_overlap': 25})
        
        doc_count = len(documents)
        num_workers, batch_size = self._get_adaptive_parallelization(doc_count)
        
        # Stage 1: Parent splitting
        if num_workers == 1:
            splitter = _get_cached_splitter(parent_config.get('chunk_size', 512), parent_config.get('chunk_overlap', 100))
            parent_docs = splitter.split_documents(documents)
        else:
            batches = []
            for i in range(0, doc_count, batch_size):
                batches.append([(d.page_content, dict(d.metadata)) for d in documents[i:i+batch_size]])
            parent_docs = []
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(_parallel_split_worker, batch, parent_config) for batch in batches]
                for future in as_completed(futures):
                    parent_docs.extend(future.result())
        
        logger.info(f"Parent splitting complete: {len(parent_docs)} parent docs")
        
        # Stage 2: Index parents in memory
        docstore = SimpleInMemoryStore()
        parent_data = []
        for doc in parent_docs:
            meta_str = json.dumps(doc.metadata, sort_keys=True, default=str)
            stable_id = hashlib.sha256(f"{doc.page_content}{meta_str}".encode()).hexdigest()
            parent_data.append((stable_id, doc))
        docstore.mset(parent_data)
        logger.info(f"Indexed {len(parent_data)} parents in memory")
        
        # Stage 2.5: Persist docstore to pickle if path provided
        if self.docstore_path:
            docstore.save_to_pickle(self.docstore_path)
        
        # Stage 3: Child splitting
        child_tuples = _child_split_worker(parent_data, child_config)
        child_documents = [Document(page_content=c, metadata=m) for c, m in child_tuples]
        
        logger.info(f"Chunking complete: {len(parent_docs)} parents -> {len(child_documents)} children")
        return child_documents, docstore


def _parallel_split_worker(doc_tuples: List[Tuple[str, Dict]], config: Dict) -> List[Document]:
    docs = [Document(page_content=c, metadata=m) for c, m in doc_tuples]
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=config.get('chunk_size', 512),
        chunk_overlap=config.get('chunk_overlap', 100)
    )
    return splitter.split_documents(docs)


def _child_split_worker(parent_batch: List[Tuple[str, Document]], config: Dict) -> List[Tuple[str, dict]]:
    has_tabular = any(doc.metadata.get('source_table') for _, doc in parent_batch)
    if has_tabular:
        splitter = _get_tabular_splitter(config.get('chunk_size', 128) // 20, config.get('chunk_overlap', 25) // 20)
    else:
        splitter = _get_cached_splitter(config.get('chunk_size', 128), config.get('chunk_overlap', 25))
    
    all_children = []
    for parent_id, doc in parent_batch:
        for child in splitter.split_documents([doc]):
            meta = dict(child.metadata)
            meta["doc_id"] = parent_id
            all_children.append((child.page_content, meta))
    return all_children
