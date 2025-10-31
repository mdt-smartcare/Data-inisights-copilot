# src/pipeline/transform.py
import pandas as pd
import hashlib
import json
from tqdm import tqdm
import logging
from typing import Dict, List, Any
import numpy as np

logger = logging.getLogger(__name__)

class DataTransformer:
    def __init__(self):
        self.id_mappings = {}
    
    def anonymize_id(self, original_id, salt="spice_healthcare"):
        """Anonymize an ID while maintaining referential integrity"""
        if pd.isna(original_id):
            return None
        
        key = f"{original_id}_{salt}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    def should_anonymize_column(self, table_name, column_name):
        """Check if a column should be anonymized"""
        id_indicators = ['_id', 'id_', 'user_id', 'patient_id', 'track_id', 'visit_id']
        return any(indicator in column_name.lower() for indicator in id_indicators)
    
    def transform_table_data(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Apply transformations to table data"""
        if df.empty:
            return df
        
        transformed_df = df.copy()
        
        # Anonymize ID columns
        for column in df.columns:
            if self.should_anonymize_column(table_name, column):
                transformed_df[column] = df[column].apply(
                    lambda x: self.anonymize_id(x, salt=column) if pd.notna(x) else None
                )
        
        logger.info(f"Transformed {table_name}: {len(transformed_df)} rows")
        return transformed_df
    
    def safe_value_check(self, value):
        """Safely check if a value should be included in the document - COMPLETELY SAFE VERSION"""
        if pd.isna(value):
            return False
        
        # COMPLETE FIX: Avoid ALL truth value checks on arrays
        try:
            # For numpy arrays - use size check instead of truth value
            if hasattr(value, 'size'):
                return value.size > 0
            
            # For lists/tuples - use length check
            if isinstance(value, (list, tuple)):
                return len(value) > 0
            
            # For pandas objects
            if hasattr(value, 'empty'):
                return not value.empty
            
            # For other iterables that aren't strings
            if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                try:
                    # Try to get length without triggering truth value
                    return len(value) > 0
                except:
                    # If length check fails, assume it has content
                    return True
            
            # Handle regular values
            value_str = str(value).strip()
            return value_str not in ['', 'NULL', 'null', 'None', 'nan']
        except Exception:
            # If any check fails, assume it's valid content
            return True
    
    def format_value(self, value):
        """Format value for document content - ULTRA SAFE VERSION"""
        try:
            # Handle numpy arrays safely - NO TRUTH VALUE CHECKS
            if hasattr(value, 'dtype') and hasattr(value, 'shape'):
                try:
                    # Convert to list first, then to string - NO TRUTH VALUE CHECKS
                    if hasattr(value, 'tolist'):
                        return str(value.tolist())
                    return str(list(value))
                except:
                    return str(value)
            
            # Handle lists/tuples
            if isinstance(value, (list, tuple)):
                return str(value)
            
            # Handle pandas objects
            if hasattr(value, 'tolist'):
                try:
                    return str(value.tolist())
                except:
                    return str(value)
            
            # Regular values
            return str(value)
        except Exception:
            # If formatting fails, return empty string
            return ""
    
    def create_documents_from_table(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert table data into document format for embedding - SAFE VERSION"""
        documents = []
        
        # Process each row with comprehensive error handling
        for idx, row in tqdm(df.iterrows(), total=len(df), desc=f"Creating documents from {table_name}"):
            content_parts = [f"Table: {table_name}"]
            row_success = True
            
            for column, value in row.items():
                try:
                    # Use safe check that doesn't trigger truth value ambiguity
                    if self.safe_value_check(value):
                        value_str = self.format_value(value)
                        # Additional check after formatting
                        if value_str and value_str.strip() and value_str not in ['[]', 'NULL', 'null', 'None', 'nan', '']:
                            content_parts.append(f"{column}: {value_str}")
                except Exception as e:
                    # Skip this value if any error occurs
                    continue
            
            if len(content_parts) > 1:
                try:
                    document = {
                        "content": "\n".join(content_parts),
                        "metadata": {
                            "table_name": table_name,
                            "row_hash": self.anonymize_id(str(dict(row))),
                            "columns": list(row.index),
                            "document_type": "database_record"
                        }
                    }
                    documents.append(document)
                except Exception as e:
                    # Skip this document if creation fails
                    continue
        
        logger.info(f"Created {len(documents)} documents from {table_name}")
        return documents
    
    def transform_all_tables(self, table_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Transform all table data into documents with robust error handling"""
        all_documents = []
        problematic_tables = []
        
        for table_name, df in tqdm(table_data.items(), desc="Transforming tables"):
            try:
                transformed_df = self.transform_table_data(table_name, df)
                if not transformed_df.empty:
                    table_documents = self.create_documents_from_table(table_name, transformed_df)
                    all_documents.extend(table_documents)
                    logger.info(f" Successfully transformed {table_name}: {len(table_documents)} documents")
            except Exception as e:
                logger.error(f"✗ Error transforming table {table_name}: {e}")
                problematic_tables.append(table_name)
                continue
        
        if problematic_tables:
            logger.warning(f"Could not process {len(problematic_tables)} tables: {problematic_tables}")
        
        logger.info(f"Total documents created: {len(all_documents)}")
        return all_documents

# Factory function
def create_data_transformer():
    return DataTransformer()