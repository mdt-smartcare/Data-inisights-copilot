"""
Core models for the Multi-Modal Data Ingestion Engine.

Defines the standard Document container and the abstract BaseExtractor
interface that all concrete extractors must implement.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """A lightweight, framework-agnostic document container.

    Attributes:
        page_content: The textual content of the document chunk.
        metadata: Arbitrary key-value metadata (source, page number, etc.).
    """

    page_content: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        snippet = (
            self.page_content[:80] + "..."
            if len(self.page_content) > 80
            else self.page_content
        )
        return f"Document(page_content='{snippet}', metadata={self.metadata})"


class BaseExtractor(ABC):
    """Abstract base class for all file-format extractors.

    Concrete subclasses must implement the ``extract`` method, which yields
    a stream of :class:`Document` objects for memory-efficient processing.
    """

    @abstractmethod
    def extract(self, file_path: str) -> Generator[Document, None, None]:
        """Extract documents from the given file.

        Args:
            file_path: Absolute or relative path to the file to ingest.

        Yields:
            Document: One document per logical chunk (page, row, object, etc.).

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            ValueError: If the file cannot be parsed at all.
        """
        ...  # pragma: no cover
