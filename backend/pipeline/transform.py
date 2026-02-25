import pandas as pd
import hashlib
import json
from tqdm import tqdm
import logging
import multiprocessing
from typing import Dict, List, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
import uuid

logger = logging.getLogger(__name__)

class SimpleInMemoryStore(BaseStore[str, Document]):
    def __init__(self):
        self._dict = {}

    def mget(self, keys: List[str]) -> List[Document]:
        return [self._dict[key] for key in keys if key in self._dict]
    
    def mset(self, key_value_pairs: List[tuple[str, Document]]) -> None:
        for key, value in key_value_pairs:
            self._dict[key] = value
    
    def mdelete(self, keys: List[str]) -> None:
        for key in keys:
            if key in self._dict:
                del self._dict[key]

    def yield_keys(self) -> List[str]:
        return list(self._dict.keys())

class AdvancedDataTransformer:
    def __init__(self, config: Dict):
        self.config = config
        # Context mappings should be injected via config in the future
        self.medical_context = {}

    def _safe_format_value(self, value: Any) -> str | None:
        """
        A robust function to check if a value is valid and format it.
        """
        if isinstance(value, (list, np.ndarray, pd.Series)):
            if len(value) == 0:
                return None
            return ', '.join(map(str, value))

        if pd.isna(value):
            return None

        value_str = str(value).strip()

        if value_str.lower() in ['', 'null', 'none', 'nan', '[]', '{}']:
            return None
        
        return value_str

    def _enrich_medical_content(self, col: str, val: Any) -> str:
        """Enrich medical fields with human-readable context for better embeddings."""
        # Add readable names for medical columns
        if col in self.medical_context:
            readable_name = self.medical_context[col]
            return f"{readable_name} ({col}): {val}"
        
        # Convert boolean medical flags to descriptive text
        if col.startswith('is_') and isinstance(val, bool):
            condition = col.replace('is_', '').replace('_', ' ').title()
            return f"{condition}: {'Yes' if val else 'No'}"
        
        return f"{col}: {val}"

    def _get_row_id(self, row: pd.Series) -> str:
        """
        Smartly finds the best available ID for metadata.
        This resolves the "missing 'id' column" warnings.
        """
        # Check for common primary key names first
        if 'id' in row and pd.notna(row['id']):
            return str(row['id'])
        if 'patient_track_id' in row and pd.notna(row['patient_track_id']):
            return str(row['patient_track_id'])
        if 'user_id' in row and pd.notna(row['user_id']):
            return str(row['user_id'])
        
        # Fallback for tables without a clear ID (like mapping tables)
        # Create a stable hash of the row content to use as an ID
        return hashlib.md5(str(row.to_dict()).encode()).hexdigest()[:12]

    def create_documents_from_tables(self, table_data: Dict[str, pd.DataFrame], on_progress=None) -> List[Document]:
        """Converts raw table data into a flat list of LangChain Document objects."""
        all_docs = []
        total_tables = len(table_data)
        for i, (table_name, df) in enumerate(table_data.items()):
            if on_progress:
                on_progress(i, total_tables, table_name)
            logger.info(f"Formatting documents for table: {table_name} ({len(df)} rows)")
            
            # Vectorized row ID generation where possible
            # If 'id' exists, use it. Otherwise, fallback to content hash.
            # But the content hash depends on the row content... 
            # Let's optimize the loop.
            
            df_cols = df.columns.tolist()
            # Pre-calculate column names to skip
            cols_to_process = [c for c in df_cols if c != 'is_latest']
            
            # Use a list of dicts for faster iteration than itertuples/iterrows
            rows = df.to_dict('records')
            
            for row in tqdm(rows, desc=f"Processing {table_name}", leave=False):
                content_parts = []
                for col in cols_to_process:
                    val = row[col]
                    formatted_val = self._safe_format_value(val)
                    if formatted_val is not None:
                        content_parts.append(self._enrich_medical_content(col, formatted_val))
                
                if content_parts:
                    content = "\n".join(content_parts)
                    
                    # Optimized ID retrieval
                    source_id = str(row.get('id') or row.get('patient_track_id') or row.get('user_id') or 
                                   hashlib.md5(str(row).encode()).hexdigest()[:12])
                    
                    metadata = {
                        "source_table": table_name, 
                        "source_id": source_id,
                        "is_latest": row.get('is_latest', True)
                    }
                    all_docs.append(Document(page_content=content, metadata=metadata))

        logger.info(f"Created {len(all_docs)} initial documents from all tables.")
        return all_docs

    def perform_parent_child_chunking(self, documents: List[Document], on_progress=None):
        """
        Applies 'Small-to-Big' chunking with massive parallelization.
        """
        if on_progress:
            on_progress("Split (Parent)", 0, 100)
        
        parent_config = self.config['chunking']['parent_splitter']
        child_config = self.config['chunking']['child_splitter']
        
        num_workers = max(1, multiprocessing.cpu_count() - 1)
        logger.info(f"Starting parallel chunking using {num_workers} processes...")

        # 1. Split into Parent Documents
        batch_size = 10000 # Smaller batches for better worker utilization
        batches = [documents[i:i + batch_size] for i in range(0, len(documents), batch_size)]
        
        parent_docs = []
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_parallel_split_worker, batch, parent_config) for batch in batches]
            for future in tqdm(as_completed(futures), total=len(futures), desc="Split (Parent)"):
                parent_docs.extend(future.result())
                if on_progress:
                    on_progress("Split (Parent)", len(parent_docs), -1) # -1 means unknown total or we just update count

        # 2. Generate Stable IDs and populate Docstore
        if on_progress:
            on_progress("Indexing Parents", 0, 100)
            
        docstore = SimpleInMemoryStore()
        # Pre-creating IDs for parents (can also be parallelized if needed, but overhead usually too high)
        parent_data = []
        for doc in tqdm(parent_docs, desc="Indexing Parents"):
            meta_str = json.dumps(doc.metadata, sort_keys=True)
            stable_id = hashlib.sha256(f"{doc.page_content}{meta_str}".encode()).hexdigest()
            parent_data.append((stable_id, doc))
        
        docstore.mset(parent_data)

        # 3. Split Parent Documents into Child Chunks (Parallel)
        child_documents = []
        parent_batches = [parent_data[i:i + batch_size] for i in range(0, len(parent_data), batch_size)]
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_parallel_child_split_worker, batch, child_config) for batch in parent_batches]
            for future in tqdm(as_completed(futures), total=len(futures), desc="Split (Children)"):
                child_documents.extend(future.result())
                if on_progress:
                    on_progress("Split (Children)", len(child_documents), -1)

        logger.info(f"Parallel chunking complete. Parents: {len(parent_docs)}, Children: {len(child_documents)}")
        return child_documents, docstore

def _parallel_split_worker(docs: List[Document], config: Dict) -> List[Document]:
    """Helper for parallel parent document splitting."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=config.get('chunk_size', 800),
        chunk_overlap=config.get('chunk_overlap', 150)
    )
    return splitter.split_documents(docs)

def _parallel_child_split_worker(parent_batch: List[Tuple[str, Document]], config: Dict) -> List[Document]:
    """Helper for parallel child document splitting with parent linkage."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=config.get('chunk_size', 200),
        chunk_overlap=config.get('chunk_overlap', 50)
    )
    
    all_children = []
    for parent_id, doc in parent_batch:
        children = splitter.split_documents([doc])
        for child in children:
            child.metadata["parent_doc_id"] = parent_id
            all_children.append(child)
    return all_children