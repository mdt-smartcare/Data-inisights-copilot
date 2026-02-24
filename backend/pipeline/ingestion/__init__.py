"""
Multi-Modal Data Ingestion Engine for the RAG Pipeline.

Provides an extensible, Strategy-Pattern-based ingestion layer capable of
processing diverse file formats (.pdf, .csv, .xlsx, .json) and yielding
memory-efficient Document streams suitable for vectorization.
"""

from backend.pipeline.ingestion.models import Document, BaseExtractor
from backend.pipeline.ingestion.extractors import (
    PDFExtractor,
    CSVExtractor,
    ExcelExtractor,
    JSONExtractor,
)
from backend.pipeline.ingestion.factory import DocumentLoaderFactory

__all__ = [
    "Document",
    "BaseExtractor",
    "PDFExtractor",
    "CSVExtractor",
    "ExcelExtractor",
    "JSONExtractor",
    "DocumentLoaderFactory",
]
