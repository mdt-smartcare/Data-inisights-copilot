"""
Factory / Router for the Multi-Modal Data Ingestion Engine.

Provides :class:`DocumentLoaderFactory` which inspects a file's extension
and routes it to the appropriate :class:`BaseExtractor` implementation.
New extractors can be registered at runtime via ``register()`` to satisfy
the Open/Closed Principle.
"""

from __future__ import annotations

import logging
import os
from typing import Type

from backend.pipeline.ingestion.extractors import (
    CSVExtractor,
    ExcelExtractor,
    JSONExtractor,
    PDFExtractor,
)
from backend.pipeline.ingestion.models import BaseExtractor

logger = logging.getLogger(__name__)


class DocumentLoaderFactory:
    """Registry-based factory that maps file extensions to extractors.

    The factory ships with built-in support for ``.pdf``, ``.csv``, ``.xlsx``,
    and ``.json``.  Additional formats can be added at runtime using the
    :meth:`register` class method, keeping the factory open for extension
    but closed for modification.

    Example::

        factory = DocumentLoaderFactory()
        extractor = factory.get_extractor("reports/q1.pdf")
        for doc in extractor.extract("reports/q1.pdf"):
            print(doc.page_content[:100])
    """

    _registry: dict[str, Type[BaseExtractor]] = {
        ".pdf": PDFExtractor,
        ".csv": CSVExtractor,
        ".xlsx": ExcelExtractor,
        ".json": JSONExtractor,
    }

    @classmethod
    def register(
        cls,
        extension: str,
        extractor_cls: Type[BaseExtractor],
    ) -> None:
        """Register a new extractor for the given file extension.

        Args:
            extension: File extension **including the dot** (e.g. ``".xml"``).
            extractor_cls: A concrete subclass of :class:`BaseExtractor`.

        Raises:
            TypeError: If *extractor_cls* is not a subclass of
                :class:`BaseExtractor`.
        """
        if not (isinstance(extractor_cls, type) and issubclass(extractor_cls, BaseExtractor)):
            raise TypeError(
                f"extractor_cls must be a subclass of BaseExtractor, "
                f"got {extractor_cls!r}"
            )
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        cls._registry[ext] = extractor_cls
        logger.info("Registered extractor %s for extension '%s'", extractor_cls.__name__, ext)

    @classmethod
    def get_extractor(cls, file_path: str) -> BaseExtractor:
        """Return an instantiated extractor for the given file.

        The file extension is used to look up the appropriate extractor class
        in the internal registry.

        Args:
            file_path: Path (or filename) whose extension determines the
                extractor to use.

        Returns:
            An instance of a :class:`BaseExtractor` subclass.

        Raises:
            ValueError: If the file extension is not registered.
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext not in cls._registry:
            supported = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unsupported file extension '{ext}'. "
                f"Supported extensions: {supported}"
            )

        extractor_cls = cls._registry[ext]
        logger.debug(
            "Routing '%s' (ext=%s) to %s",
            file_path,
            ext,
            extractor_cls.__name__,
        )
        return extractor_cls()

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """Return a sorted list of currently supported file extensions."""
        return sorted(cls._registry.keys())
