import pandas as pd
import hashlib
import json
from tqdm import tqdm
import logging
from typing import Dict, List, Any
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
        # Medical domain mappings for better semantic understanding
        self.medical_context = {
            'is_htn_diagnosis': 'Hypertension',
            'is_diabetes_diagnosis': 'Diabetes',
            'cvd_risk_level': 'Cardiovascular Disease Risk',
            'bmi': 'Body Mass Index',
            'avg_systolic': 'Systolic Blood Pressure',
            'avg_diastolic': 'Diastolic Blood Pressure',
            'glucose_value': 'Blood Glucose Level',
            'phq9_score': 'Depression Screening (PHQ-9)',
            'gad7_score': 'Anxiety Screening (GAD-7)',
        }

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

    def create_documents_from_tables(self, table_data: Dict[str, pd.DataFrame]) -> List[Document]:
        """Converts raw table data into a flat list of LangChain Document objects."""
        all_docs = []
        for table_name, df in tqdm(table_data.items(), desc="Formatting documents from tables"):
            
            # --- NEW LOGIC START: Metadata Enrichment for Deduplication ---
            # Default to True for tables that don't need deduplication
            df = df.copy()  # Avoid modifying the original dataframe
            df['is_latest'] = True 
            
            if table_name == 'patient_tracker' and 'patient_track_id' in df.columns and 'updated_at' in df.columns:
                # Sort by patient and time, then mark the last one as latest
                df = df.sort_values(['patient_track_id', 'updated_at'])
                df['is_latest'] = ~df.duplicated(subset=['patient_track_id'], keep='last')
                
            elif table_name == 'screening_log' and 'screening_id' in df.columns and 'updated_at' in df.columns:
                # Sort by screening_id and time (dashboard logic)
                df = df.sort_values(['screening_id', 'updated_at'])
                df['is_latest'] = ~df.duplicated(subset=['screening_id'], keep='last')
            # --- NEW LOGIC END ---

            for _, row in df.iterrows():
                content_parts = []
                for col, val in row.items():
                    # Skip the temp 'is_latest' column in the text content
                    if col == 'is_latest':
                        continue
                        
                    formatted_val = self._safe_format_value(val)
                    if formatted_val is not None:
                        enriched_content = self._enrich_medical_content(col, formatted_val)
                        content_parts.append(enriched_content)
                
                if content_parts:
                    content = "\n".join(content_parts)
                    source_id = self._get_row_id(row)
                    
                    # Add the new flag to metadata
                    metadata = {
                        "source_table": table_name, 
                        "source_id": source_id,
                        "is_latest": row['is_latest']  # <--- Vital for RAG filtering
                    }
                    all_docs.append(Document(page_content=content, metadata=metadata))

        logger.info(f"Created {len(all_docs)} initial documents from all tables.")
        return all_docs

    def perform_parent_child_chunking(self, documents: List[Document]):
        """
        Applies the 'Small-to-Big' chunking strategy manually.
        """
        parent_splitter_config = self.config['chunking']['parent_splitter']
        child_splitter_config = self.config['chunking']['child_splitter']

        parent_splitter = RecursiveCharacterTextSplitter(**parent_splitter_config)
        child_splitter = RecursiveCharacterTextSplitter(**child_splitter_config)
        
        docstore = SimpleInMemoryStore()
        child_documents = []
        
        logger.info("Applying parent-child chunking to all documents...")
        
        parent_docs = parent_splitter.split_documents(documents)
        parent_doc_ids = [str(uuid.uuid4()) for _ in parent_docs]
        docstore.mset(list(zip(parent_doc_ids, parent_docs)))

        for i, doc in enumerate(tqdm(parent_docs, desc="Splitting into child documents")):
            _id = parent_doc_ids[i]
            sub_docs = child_splitter.split_documents([doc])
            for _doc in sub_docs:
                _doc.metadata["doc_id"] = _id
                child_documents.append(_doc)

        logger.info(f"Chunking complete. Created {len(child_documents)} child documents.")
        return child_documents, docstore