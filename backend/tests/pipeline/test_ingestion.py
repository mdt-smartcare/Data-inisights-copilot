"""
Unit tests for the Multi-Modal Data Ingestion Engine.

Tests cover:
- Document dataclass creation and defaults
- Each concrete extractor (PDF, CSV, Excel, JSON) yielding Document streams
- DocumentLoaderFactory routing and registration
- Error handling for corrupted/missing/unsupported files
"""

import csv
import json
import os

import pytest

# Set test environment variables FIRST before any imports
os.environ.setdefault("OPENAI_API_KEY", "test-key-123")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-long-for-jwt-signing")

from backend.pipeline.ingestion.models import BaseExtractor, Document
from backend.pipeline.ingestion.extractors import (
    CSVExtractor,
    ExcelExtractor,
    JSONExtractor,
    PDFExtractor,
)
from backend.pipeline.ingestion.factory import DocumentLoaderFactory


# =========================================================================
# Document Model Tests
# =========================================================================


class TestDocument:
    """Tests for the Document dataclass."""

    def test_create_with_content_only(self):
        doc = Document(page_content="hello")
        assert doc.page_content == "hello"
        assert doc.metadata == {}

    def test_create_with_metadata(self):
        doc = Document(page_content="hello", metadata={"source": "test.csv"})
        assert doc.metadata["source"] == "test.csv"

    def test_repr_short_content(self):
        doc = Document(page_content="short")
        assert "short" in repr(doc)

    def test_repr_long_content_truncated(self):
        doc = Document(page_content="x" * 200)
        r = repr(doc)
        assert "..." in r
        assert len(r) < 250


# =========================================================================
# CSV Extractor Tests
# =========================================================================


class TestCSVExtractor:
    """Tests for CSVExtractor."""

    def test_extracts_rows_as_documents(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n")

        extractor = CSVExtractor()
        docs = list(extractor.extract(str(csv_file)))

        assert len(docs) == 2
        assert "Alice" in docs[0].page_content
        assert docs[0].metadata["file_type"] == "csv"
        assert docs[0].metadata["row_number"] == 1
        assert "name" in docs[0].metadata["columns"]

    def test_skips_empty_rows(self, tmp_path):
        """Rows where all values are empty should be skipped."""
        csv_file = tmp_path / "sparse.csv"
        # DictReader returns empty strings for blank cells
        csv_file.write_text("a,b\n,\nfoo,bar\n")

        docs = list(CSVExtractor().extract(str(csv_file)))
        assert len(docs) == 1
        assert "foo" in docs[0].page_content

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            list(CSVExtractor().extract("/nonexistent/file.csv"))

    def test_encoding_error_raises_value_error(self, tmp_path):
        bad_file = tmp_path / "bad.csv"
        bad_file.write_bytes(b"\xff\xfe" + "name\n".encode("utf-16-le"))

        with pytest.raises(ValueError, match="Cannot decode CSV"):
            list(CSVExtractor(encoding="ascii").extract(str(bad_file)))


# =========================================================================
# JSON Extractor Tests
# =========================================================================


class TestJSONExtractor:
    """Tests for JSONExtractor."""

    def test_array_of_objects(self, tmp_path):
        json_file = tmp_path / "data.json"
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        json_file.write_text(json.dumps(data))

        docs = list(JSONExtractor().extract(str(json_file)))
        assert len(docs) == 2
        assert "Alice" in docs[0].page_content
        assert docs[0].metadata["item_index"] == 0

    def test_single_object(self, tmp_path):
        json_file = tmp_path / "single.json"
        json_file.write_text(json.dumps({"key": "value", "count": 42}))

        docs = list(JSONExtractor().extract(str(json_file)))
        assert len(docs) == 1
        assert "key: value" in docs[0].page_content

    def test_nested_flattening(self, tmp_path):
        json_file = tmp_path / "nested.json"
        data = {"user": {"name": "Alice", "address": {"city": "NYC"}}}
        json_file.write_text(json.dumps(data))

        docs = list(JSONExtractor().extract(str(json_file)))
        assert len(docs) == 1
        assert "user.name: Alice" in docs[0].page_content
        assert "user.address.city: NYC" in docs[0].page_content

    def test_list_values_joined(self, tmp_path):
        json_file = tmp_path / "lists.json"
        data = {"tags": ["a", "b", "c"]}
        json_file.write_text(json.dumps(data))

        docs = list(JSONExtractor().extract(str(json_file)))
        assert "a, b, c" in docs[0].page_content

    def test_invalid_json_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")

        with pytest.raises(ValueError, match="Cannot parse JSON"):
            list(JSONExtractor().extract(str(bad_file)))

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            list(JSONExtractor().extract("/nonexistent/file.json"))


# =========================================================================
# Excel Extractor Tests
# =========================================================================


class TestExcelExtractor:
    """Tests for ExcelExtractor."""

    def _create_xlsx(self, path, sheets_data: dict):
        """Helper to create an .xlsx file with openpyxl."""
        from openpyxl import Workbook

        wb = Workbook()
        first = True
        for sheet_name, rows in sheets_data.items():
            if first:
                ws = wb.active
                ws.title = sheet_name
                first = False
            else:
                ws = wb.create_sheet(title=sheet_name)
            for row in rows:
                ws.append(row)
        wb.save(path)

    def test_extracts_rows_from_single_sheet(self, tmp_path):
        xlsx_file = tmp_path / "data.xlsx"
        self._create_xlsx(str(xlsx_file), {
            "Sheet1": [
                ["name", "age"],
                ["Alice", 30],
                ["Bob", 25],
            ]
        })

        docs = list(ExcelExtractor().extract(str(xlsx_file)))
        assert len(docs) == 2
        assert "Alice" in docs[0].page_content
        assert docs[0].metadata["sheet_name"] == "Sheet1"
        assert docs[0].metadata["file_type"] == "xlsx"

    def test_handles_multiple_sheets(self, tmp_path):
        xlsx_file = tmp_path / "multi.xlsx"
        self._create_xlsx(str(xlsx_file), {
            "Users": [["name"], ["Alice"]],
            "Orders": [["item"], ["Widget"]],
        })

        docs = list(ExcelExtractor().extract(str(xlsx_file)))
        assert len(docs) == 2
        sheet_names = {d.metadata["sheet_name"] for d in docs}
        assert sheet_names == {"Users", "Orders"}

    def test_skips_empty_rows(self, tmp_path):
        xlsx_file = tmp_path / "sparse.xlsx"
        self._create_xlsx(str(xlsx_file), {
            "Data": [
                ["col_a"],
                [None],
                ["value"],
            ]
        })

        docs = list(ExcelExtractor().extract(str(xlsx_file)))
        assert len(docs) == 1
        assert "value" in docs[0].page_content

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            list(ExcelExtractor().extract("/nonexistent/file.xlsx"))

    def test_corrupted_file_raises(self, tmp_path):
        bad_file = tmp_path / "bad.xlsx"
        bad_file.write_text("not an excel file")

        with pytest.raises(ValueError, match="Cannot parse Excel"):
            list(ExcelExtractor().extract(str(bad_file)))


# =========================================================================
# PDF Extractor Tests
# =========================================================================


class TestPDFExtractor:
    """Tests for PDFExtractor."""

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            list(PDFExtractor().extract("/nonexistent/file.pdf"))

    def test_corrupted_file_raises(self, tmp_path):
        bad_file = tmp_path / "bad.pdf"
        bad_file.write_text("not a real pdf")

        with pytest.raises(ValueError, match="Cannot parse PDF"):
            list(PDFExtractor().extract(str(bad_file)))

    def test_extract_returns_generator(self, tmp_path):
        """Verify that extract() returns a generator type."""
        import types

        # Create a minimal (but invalid-content) PDF to verify generator
        # interface without needing a real PDF with extractable text.
        pdf_path = tmp_path / "empty.pdf"
        # Minimal valid PDF structure (no text content)
        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Resources<<>>>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n219\n%%EOF"
        )
        pdf_path.write_bytes(pdf_content)

        extractor = PDFExtractor()
        result = extractor.extract(str(pdf_path))
        assert isinstance(result, types.GeneratorType)
        # Blank page → may yield 0 docs (no text), which is correct
        docs = list(result)
        assert isinstance(docs, list)


# =========================================================================
# DocumentLoaderFactory Tests
# =========================================================================


class TestDocumentLoaderFactory:
    """Tests for DocumentLoaderFactory."""

    def test_get_extractor_pdf(self):
        ext = DocumentLoaderFactory.get_extractor("report.pdf")
        assert isinstance(ext, PDFExtractor)

    def test_get_extractor_csv(self):
        ext = DocumentLoaderFactory.get_extractor("data.csv")
        assert isinstance(ext, CSVExtractor)

    def test_get_extractor_xlsx(self):
        ext = DocumentLoaderFactory.get_extractor("sheet.xlsx")
        assert isinstance(ext, ExcelExtractor)

    def test_get_extractor_json(self):
        ext = DocumentLoaderFactory.get_extractor("config.json")
        assert isinstance(ext, JSONExtractor)

    def test_case_insensitive_extension(self):
        ext = DocumentLoaderFactory.get_extractor("FILE.PDF")
        assert isinstance(ext, PDFExtractor)

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file extension"):
            DocumentLoaderFactory.get_extractor("file.docx")

    def test_supported_extensions_returns_list(self):
        extensions = DocumentLoaderFactory.supported_extensions()
        assert ".pdf" in extensions
        assert ".csv" in extensions
        assert ".xlsx" in extensions
        assert ".json" in extensions

    def test_register_custom_extractor(self):
        """Test that a custom extractor can be registered and retrieved."""

        class MarkdownExtractor(BaseExtractor):
            def extract(self, file_path):
                yield Document(page_content="md content", metadata={})

        DocumentLoaderFactory.register(".md", MarkdownExtractor)
        ext = DocumentLoaderFactory.get_extractor("readme.md")
        assert isinstance(ext, MarkdownExtractor)

        # Clean up registry
        del DocumentLoaderFactory._registry[".md"]

    def test_register_non_extractor_raises(self):
        with pytest.raises(TypeError, match="subclass of BaseExtractor"):
            DocumentLoaderFactory.register(".txt", str)  # type: ignore


# =========================================================================
# Integration: Factory → Extractor → Documents
# =========================================================================


class TestIngestionIntegration:
    """End-to-end tests routing through the factory to extractors."""

    def test_csv_through_factory(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("x,y\n1,2\n3,4\n")

        extractor = DocumentLoaderFactory.get_extractor(str(csv_file))
        docs = list(extractor.extract(str(csv_file)))
        assert len(docs) == 2
        assert all(isinstance(d, Document) for d in docs)

    def test_json_through_factory(self, tmp_path):
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps([{"a": 1}, {"b": 2}]))

        extractor = DocumentLoaderFactory.get_extractor(str(json_file))
        docs = list(extractor.extract(str(json_file)))
        assert len(docs) == 2

    def test_generator_is_lazy(self, tmp_path):
        """Verify that extract() returns a generator, not a list."""
        csv_file = tmp_path / "lazy.csv"
        csv_file.write_text("col\nval\n")

        import types

        extractor = CSVExtractor()
        result = extractor.extract(str(csv_file))
        assert isinstance(result, types.GeneratorType)
