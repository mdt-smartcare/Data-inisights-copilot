"""
Document generator for schema-driven embeddings.
Generates embedding documents from database schema and data dictionary.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import json

from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingDocument:
    """Represents a document to be embedded."""
    document_id: str
    document_type: str  # table, column, relationship
    content: str
    source_table: Optional[str] = None
    source_column: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmbeddingDocumentGenerator:
    """
    Generates embedding documents from schema and data dictionary.
    
    Document types:
    - Table-level: Overview of table with all columns
    - Column-level: Individual column with type and description
    - Relationship: Foreign key relationships between tables
    """
    
    def __init__(self):
        # Dictionary descriptions keyed by table.column or table
        self.dictionary: Dict[str, str] = {}
    
    def load_data_dictionary(self, dictionary_content: str) -> None:
        """
        Parse and load data dictionary content.
        
        Args:
            dictionary_content: Raw data dictionary text or JSON
        """
        self.dictionary = {}
        
        if not dictionary_content:
            return
        
        # Try to parse as JSON first
        try:
            data = json.loads(dictionary_content)
            if isinstance(data, dict):
                self._load_json_dictionary(data)
                return
        except json.JSONDecodeError:
            pass
        
        # Parse as text format (table.column: description)
        self._load_text_dictionary(dictionary_content)
    
    def _load_json_dictionary(self, data: Dict[str, Any]) -> None:
        """Load dictionary from JSON format."""
        for table_name, table_info in data.items():
            if isinstance(table_info, str):
                self.dictionary[table_name] = table_info
            elif isinstance(table_info, dict):
                # Table-level description
                if 'description' in table_info:
                    self.dictionary[table_name] = table_info['description']
                
                # Column descriptions
                columns = table_info.get('columns', {})
                for col_name, col_info in columns.items():
                    key = f"{table_name}.{col_name}"
                    if isinstance(col_info, str):
                        self.dictionary[key] = col_info
                    elif isinstance(col_info, dict) and 'description' in col_info:
                        self.dictionary[key] = col_info['description']
    
    def _load_text_dictionary(self, content: str) -> None:
        """Load dictionary from text format."""
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse "table.column: description" or "table: description"
            if ':' in line:
                key, description = line.split(':', 1)
                self.dictionary[key.strip()] = description.strip()
    
    def generate_table_documents(self, schema: Dict[str, Any]) -> List[EmbeddingDocument]:
        """
        Generate table-level embedding documents.
        
        Args:
            schema: Database schema dict with tables and columns
            
        Returns:
            List of table-level EmbeddingDocument objects
        """
        documents = []
        
        tables = schema.get('tables', {})
        if not isinstance(tables, dict):
            tables = {t: {} for t in tables} if isinstance(tables, list) else {}
        
        for table_name, table_info in tables.items():
            # Get table description from dictionary
            table_desc = self.dictionary.get(table_name, f"Table storing {table_name} data")
            
            # Get columns
            columns = self._get_columns(table_info)
            column_list = ', '.join(columns) if columns else 'various fields'
            
            # Build content
            content = f"The {table_name} table contains {table_desc.lower() if table_desc else 'data'}. "
            content += f"This table includes the following columns: {column_list}."
            
            # Add relationship info if available
            relationships = self._get_table_relationships(table_name, schema)
            if relationships:
                content += f" Related to: {', '.join(relationships)}."
            
            documents.append(EmbeddingDocument(
                document_id=f"table:{table_name}",
                document_type="table",
                content=content,
                source_table=table_name,
                metadata={
                    "column_count": len(columns),
                    "relationships": relationships
                }
            ))
        
        logger.info(f"Generated {len(documents)} table documents")
        return documents
    
    def generate_column_documents(self, schema: Dict[str, Any]) -> List[EmbeddingDocument]:
        """
        Generate column-level embedding documents.
        
        Args:
            schema: Database schema dict with tables and columns
            
        Returns:
            List of column-level EmbeddingDocument objects
        """
        documents = []
        
        tables = schema.get('tables', {})
        if not isinstance(tables, dict):
            return documents
        
        for table_name, table_info in tables.items():
            columns = table_info.get('columns', {})
            if not isinstance(columns, dict):
                continue
            
            for col_name, col_info in columns.items():
                # Get column info
                col_type = col_info.get('type', 'unknown') if isinstance(col_info, dict) else str(col_info)
                nullable = col_info.get('nullable', True) if isinstance(col_info, dict) else True
                is_pk = col_info.get('primary_key', False) if isinstance(col_info, dict) else False
                is_fk = col_info.get('foreign_key') if isinstance(col_info, dict) else None
                
                # Get description from dictionary
                dict_key = f"{table_name}.{col_name}"
                col_desc = self.dictionary.get(dict_key, "")
                
                # Build content
                content = f"{col_name} column in {table_name} table. "
                content += f"Type: {col_type}. "
                
                if col_desc:
                    content += f"Description: {col_desc}. "
                
                if is_pk:
                    content += "This is the primary key. "
                
                if not nullable:
                    content += "This field is required. "
                
                if is_fk:
                    content += f"References: {is_fk}. "
                
                documents.append(EmbeddingDocument(
                    document_id=f"column:{table_name}.{col_name}",
                    document_type="column",
                    content=content.strip(),
                    source_table=table_name,
                    source_column=col_name,
                    metadata={
                        "type": col_type,
                        "nullable": nullable,
                        "primary_key": is_pk,
                        "foreign_key": is_fk
                    }
                ))
        
        logger.info(f"Generated {len(documents)} column documents")
        return documents
    
    def generate_relationship_documents(self, schema: Dict[str, Any]) -> List[EmbeddingDocument]:
        """
        Generate relationship-level embedding documents.
        
        Args:
            schema: Database schema dict with tables and relationships
            
        Returns:
            List of relationship EmbeddingDocument objects
        """
        documents = []
        seen_relationships = set()
        
        tables = schema.get('tables', {})
        if not isinstance(tables, dict):
            return documents
        
        for table_name, table_info in tables.items():
            columns = table_info.get('columns', {})
            if not isinstance(columns, dict):
                continue
            
            for col_name, col_info in columns.items():
                if not isinstance(col_info, dict):
                    continue
                
                fk = col_info.get('foreign_key')
                if not fk:
                    continue
                
                # Parse foreign key reference (format: "other_table.column" or just "other_table")
                if '.' in fk:
                    ref_table, ref_col = fk.split('.', 1)
                else:
                    ref_table = fk
                    ref_col = 'id'
                
                # Create unique relationship ID
                rel_key = tuple(sorted([table_name, ref_table]))
                if rel_key in seen_relationships:
                    continue
                seen_relationships.add(rel_key)
                
                # Determine relationship type (usually one-to-many from ref to source)
                rel_type = "one-to-many"
                
                # Build content
                content = f"{table_name} table connects to {ref_table} table through {col_name} foreign key. "
                content += f"Relationship: {rel_type}. "
                content += f"The {col_name} column in {table_name} references {ref_col} in {ref_table}. "
                content += f"Used for joining {table_name} and {ref_table} data."
                
                documents.append(EmbeddingDocument(
                    document_id=f"relationship:{table_name}-{ref_table}",
                    document_type="relationship",
                    content=content,
                    source_table=table_name,
                    metadata={
                        "from_table": table_name,
                        "from_column": col_name,
                        "to_table": ref_table,
                        "to_column": ref_col,
                        "relationship_type": rel_type
                    }
                ))
        
        logger.info(f"Generated {len(documents)} relationship documents")
        return documents
    
    def generate_all(
        self,
        schema: Dict[str, Any],
        dictionary_content: Optional[str] = None
    ) -> List[EmbeddingDocument]:
        """
        Generate all embedding documents from schema and dictionary.
        
        Args:
            schema: Database schema dict
            dictionary_content: Optional data dictionary content
            
        Returns:
            List of all EmbeddingDocument objects
        """
        if dictionary_content:
            self.load_data_dictionary(dictionary_content)
        
        documents = []
        
        # Generate all document types
        documents.extend(self.generate_table_documents(schema))
        documents.extend(self.generate_column_documents(schema))
        documents.extend(self.generate_relationship_documents(schema))
        
        logger.info(
            f"Generated {len(documents)} total documents: "
            f"{sum(1 for d in documents if d.document_type == 'table')} tables, "
            f"{sum(1 for d in documents if d.document_type == 'column')} columns, "
            f"{sum(1 for d in documents if d.document_type == 'relationship')} relationships"
        )
        
        return documents
    
    def _get_columns(self, table_info: Any) -> List[str]:
        """Extract column names from table info."""
        if isinstance(table_info, dict):
            columns = table_info.get('columns', {})
            if isinstance(columns, dict):
                return list(columns.keys())
            elif isinstance(columns, list):
                return columns
        elif isinstance(table_info, list):
            return table_info
        return []
    
    def _get_table_relationships(
        self,
        table_name: str,
        schema: Dict[str, Any]
    ) -> List[str]:
        """Get list of related tables for a given table."""
        relationships = []
        
        tables = schema.get('tables', {})
        if not isinstance(tables, dict):
            return relationships
        
        # Check this table's foreign keys
        table_info = tables.get(table_name, {})
        columns = table_info.get('columns', {})
        if isinstance(columns, dict):
            for col_name, col_info in columns.items():
                if isinstance(col_info, dict) and col_info.get('foreign_key'):
                    fk = col_info['foreign_key']
                    ref_table = fk.split('.')[0] if '.' in fk else fk
                    if ref_table not in relationships:
                        relationships.append(f"{ref_table} via {col_name}")
        
        # Check other tables referencing this table
        for other_table, other_info in tables.items():
            if other_table == table_name:
                continue
            
            other_cols = other_info.get('columns', {})
            if isinstance(other_cols, dict):
                for col_name, col_info in other_cols.items():
                    if isinstance(col_info, dict):
                        fk = col_info.get('foreign_key', '')
                        if table_name in fk:
                            relationships.append(f"{other_table} via {col_name}")
        
        return relationships


def get_document_generator() -> EmbeddingDocumentGenerator:
    """Get a new document generator instance."""
    return EmbeddingDocumentGenerator()
