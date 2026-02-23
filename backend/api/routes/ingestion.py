"""
Ingestion API route — File upload endpoint for testing the multi-modal
data ingestion engine from the browser UI.
"""

import os
import tempfile
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from backend.pipeline.ingestion.factory import DocumentLoaderFactory
from backend.api.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ExtractedDocument(BaseModel):
    """A single extracted document preview."""
    page_content: str
    metadata: Dict[str, Any]


class IngestionResponse(BaseModel):
    """Response from the file upload / extraction endpoint."""
    status: str
    file_name: str
    file_type: str
    total_documents: int
    documents: List[ExtractedDocument]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = DocumentLoaderFactory.supported_extensions()
MAX_PREVIEW_DOCS = 50
MAX_CONTENT_LENGTH = 500  # chars per document preview


@router.post("/upload", response_model=IngestionResponse)
async def upload_and_extract(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a file and extract documents using the ingestion engine.

    Accepts ``.pdf``, ``.csv``, ``.xlsx``, and ``.json`` files.
    Returns up to 50 extracted document previews.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    # Validate extension
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # Save uploaded file to a temp location
    tmp_dir = tempfile.mkdtemp(prefix="ingestion_")
    tmp_path = os.path.join(tmp_dir, file.filename)

    try:
        # Write uploaded bytes to temp file
        contents = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(contents)

        logger.info(
            "Ingestion upload: file='%s', size=%d bytes, user='%s'",
            file.filename,
            len(contents),
            current_user.get("username", "unknown"),
        )

        # Run extraction
        extractor = DocumentLoaderFactory.get_extractor(tmp_path)
        documents: List[ExtractedDocument] = []
        total = 0

        for doc in extractor.extract(tmp_path):
            total += 1
            if len(documents) < MAX_PREVIEW_DOCS:
                preview = doc.page_content[:MAX_CONTENT_LENGTH]
                if len(doc.page_content) > MAX_CONTENT_LENGTH:
                    preview += "…"
                documents.append(
                    ExtractedDocument(
                        page_content=preview,
                        metadata=doc.metadata,
                    )
                )

        logger.info(
            "Ingestion complete: file='%s', documents=%d",
            file.filename,
            total,
        )

        return IngestionResponse(
            status="success",
            file_name=file.filename,
            file_type=ext.lstrip("."),
            total_documents=total,
            documents=documents,
        )

    except ValueError as exc:
        logger.error("Ingestion failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error during ingestion of '%s': %s", file.filename, exc)
        raise HTTPException(status_code=500, detail="Internal error during file processing.")
    finally:
        # Cleanup temp file
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass
