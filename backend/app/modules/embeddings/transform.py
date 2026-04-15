"""
Advanced Data Transformer for RAG Embedding Pipeline.

Provides:
- Vectorized document creation with medical context enrichment
- In-memory docstore with pickle persistence (matching old backend's approach)

Note: Character/token-based chunking has been removed as part of Phase 1 cleanup.
Database schemas are now processed without chunking.
"""
import pandas as pd
import hashlib
import json
import pickle
from typing import Dict, List, Any, Tuple, Optional, Iterator
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from datetime import datetime
from pathlib import Path

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CLINICAL_FLAG_PREFIXES = (
    'is_', 'has_', 'was_', 'history_of_', 'flag_', 
    'confirmed_', 'requires_', 'on_'
)


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

    def store_documents(self, documents: List[Document]) -> 'SimpleInMemoryStore':
        """
        Store documents in docstore without chunking.
        
        Each document is stored as-is with a stable ID based on content hash.
        
        Args:
            documents: List of documents to store
            
        Returns:
            SimpleInMemoryStore containing the documents
        """
        docstore = SimpleInMemoryStore()
        doc_data = []
        
        for doc in documents:
            meta_str = json.dumps(doc.metadata, sort_keys=True, default=str)
            stable_id = hashlib.sha256(f"{doc.page_content}{meta_str}".encode()).hexdigest()
            doc_data.append((stable_id, doc))
        
        docstore.mset(doc_data)
        logger.info(f"Stored {len(doc_data)} documents in docstore")
        
        # Persist docstore to pickle if path provided
        if self.docstore_path:
            docstore.save_to_pickle(self.docstore_path)
        
        return docstore
