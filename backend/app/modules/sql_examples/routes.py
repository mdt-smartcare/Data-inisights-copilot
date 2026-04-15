"""
Training Management API Routes.

Provides REST API endpoints for managing SQL training examples used in few-shot learning.
Enables continuous improvement of NL2SQL accuracy without redeployment.

Security:
- Admin-only access for modifications
- PII pattern detection and rejection
- Rate limiting on bulk uploads
- Audit logging for all changes

Usage:
    POST /api/v1/training/examples - Add a new training example
    GET /api/v1/training/examples - List examples with pagination
    GET /api/v1/training/examples/search - Search similar examples
    DELETE /api/v1/training/examples/{example_id} - Delete an example
    POST /api/v1/training/bulk - Bulk upload examples
    GET /api/v1/training/stats - Get training statistics
"""
import re
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from pydantic import BaseModel, Field, field_validator

from app.core.utils.logging import get_logger
from app.core.models.common import BaseResponse, PaginatedResponse
from app.core.auth.permissions import require_admin, get_current_user
from app.core.models.auth import Role
from app.modules.users.schemas import User
from app.modules.sql_examples.store import get_sql_examples_store, SQLExamplesStore

logger = get_logger(__name__)

router = APIRouter(prefix="/training", tags=["Training"])


# ============================================
# Rate Limiting State (in-memory for simplicity)
# ============================================

_bulk_upload_timestamps: Dict[str, List[datetime]] = defaultdict(list)
BULK_UPLOAD_LIMIT = 5  # Max uploads per window
BULK_UPLOAD_WINDOW = timedelta(hours=1)


def check_bulk_rate_limit(user_id: str) -> bool:
    """Check if user is within bulk upload rate limit."""
    now = datetime.utcnow()
    window_start = now - BULK_UPLOAD_WINDOW
    
    # Clean old timestamps
    _bulk_upload_timestamps[user_id] = [
        ts for ts in _bulk_upload_timestamps[user_id] if ts > window_start
    ]
    
    # Check limit
    if len(_bulk_upload_timestamps[user_id]) >= BULK_UPLOAD_LIMIT:
        return False
    
    # Record this upload
    _bulk_upload_timestamps[user_id].append(now)
    return True


# ============================================
# PII Detection Patterns
# ============================================

PII_PATTERNS = [
    # Names (common patterns)
    r"\b(John|Jane|Smith|Johnson|Williams|Brown|Jones|Davis|Miller)\b",
    # SSN patterns
    r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    # Phone numbers
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    # Email addresses
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    # Credit card patterns
    r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    # MRN/Patient ID patterns (common formats)
    r"\bMRN[-:\s]?\d{6,10}\b",
    r"\bPATIENT[-_]?ID[-:\s]?\d+\b",
    # Date of birth with specific dates
    r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/\d{4}\b",
    # Specific addresses
    r"\b\d+\s+[A-Za-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr)\b",
]

COMPILED_PII_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PII_PATTERNS]


def contains_pii(text: str) -> bool:
    """Check if text contains potential PII patterns."""
    for pattern in COMPILED_PII_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_for_logging(text: str, max_length: int = 50) -> str:
    """Sanitize text for logging (truncate and remove potential PII)."""
    truncated = text[:max_length] + "..." if len(text) > max_length else text
    # Replace any numbers longer than 5 digits
    sanitized = re.sub(r'\d{6,}', '[REDACTED]', truncated)
    return sanitized


# ============================================
# Allowed Categories
# ============================================

ALLOWED_CATEGORIES = [
    "general",
    "aggregation",
    "temporal",
    "comparison",
    "blood_pressure",
    "medications",
    "lab_results",
    "demographics",
    "encounters",
    "diagnoses",
    "procedures",
    "window_functions",
    "cte_patterns",
    "joins",
    "subqueries",
    "date_functions",
    "streak_detection",
    "statistical",
]


# ============================================
# Pydantic Models (Request/Response)
# ============================================

class TrainingExampleCreate(BaseModel):
    """Request model for creating a training example."""
    question: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Natural language question"
    )
    sql: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Corresponding SQL query"
    )
    category: Optional[str] = Field(
        default="general",
        description="Category for filtering"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        max_length=10,
        description="Tags for additional filtering"
    )
    description: Optional[str] = Field(
        default="",
        max_length=500,
        description="Description of what this example demonstrates"
    )
    
    @field_validator('question')
    @classmethod
    def validate_question(cls, v: str) -> str:
        if contains_pii(v):
            raise ValueError("Question contains potential PII patterns. Use generic placeholders instead.")
        return v.strip()
    
    @field_validator('sql')
    @classmethod
    def validate_sql(cls, v: str) -> str:
        # Check for PII in SQL
        if contains_pii(v):
            raise ValueError("SQL contains potential PII patterns. Use generic placeholders instead.")
        
        # Basic SQL syntax validation
        sql_upper = v.upper().strip()
        valid_starts = ['SELECT', 'WITH', '--']
        if not any(sql_upper.startswith(start) for start in valid_starts):
            raise ValueError("SQL must start with SELECT, WITH, or a comment")
        
        # Check for dangerous keywords
        dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE']
        for keyword in dangerous_keywords:
            # Match whole words only
            if re.search(rf'\b{keyword}\b', sql_upper):
                raise ValueError(f"SQL cannot contain {keyword} statements for safety")
        
        return v.strip()
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v and v not in ALLOWED_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(ALLOWED_CATEGORIES)}")
        return v or "general"
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v:
            # Sanitize tags
            return [tag.strip().lower() for tag in v if tag.strip()]
        return v


class TrainingExampleResponse(BaseModel):
    """Response model for a training example."""
    id: str = Field(description="Unique identifier (SHA256 hash)")
    question: str
    sql: str
    category: str
    tags: List[str]
    description: str
    score: Optional[float] = Field(default=None, description="Similarity score (for search results)")
    
    model_config = {"from_attributes": True}


class TrainingExamplesList(BaseModel):
    """Response model for listing training examples."""
    items: List[TrainingExampleResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class TrainingStats(BaseModel):
    """Statistics about the training data."""
    total_examples: int
    categories: Dict[str, int]
    health_status: str
    backend: str
    embedding_model: str


class BulkUploadResult(BaseModel):
    """Result of a bulk upload operation."""
    uploaded: int
    skipped: int
    errors: List[str]


# ============================================
# Helper Functions
# ============================================

def generate_example_id(question: str, sql: str) -> str:
    """Generate deterministic ID for an example."""
    content = f"{question.strip().lower()}|{sql.strip()}"
    return hashlib.sha256(content.encode()).hexdigest()


# ============================================
# API Endpoints
# ============================================

@router.post(
    "/examples",
    response_model=BaseResponse[TrainingExampleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a new training example",
    description="Add a new Q&A training example for few-shot learning. Admin only."
)
async def add_training_example(
    example: TrainingExampleCreate,
    current_user: User = Depends(require_admin)
) -> BaseResponse[TrainingExampleResponse]:
    """
    Add a new SQL training example.
    
    The example will be embedded and stored in the vector database for
    similarity-based retrieval during SQL generation.
    
    Security:
    - Admin only
    - PII patterns are rejected
    - Dangerous SQL keywords are rejected
    """
    try:
        store = get_sql_examples_store()
        
        # Add the example
        success = await store.add_example(
            question=example.question,
            sql=example.sql,
            category=example.category,
            tags=example.tags,
            description=example.description or ""
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add training example"
            )
        
        # Generate ID for response
        example_id = generate_example_id(example.question, example.sql)
        
        # Log the action (without sensitive content)
        logger.info(
            "Training example added",
            user_id=str(current_user.id),
            user_email=current_user.email,
            example_id=example_id[:12],
            category=example.category
        )
        
        response = TrainingExampleResponse(
            id=example_id,
            question=example.question,
            sql=example.sql,
            category=example.category,
            tags=example.tags or [],
            description=example.description or ""
        )
        
        return BaseResponse.ok(data=response, message="Training example added successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add training example: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add training example: {str(e)}"
        )


@router.get(
    "/examples",
    response_model=BaseResponse[TrainingExamplesList],
    summary="List training examples",
    description="List all training examples with pagination. Admin only."
)
async def list_training_examples(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    current_user: User = Depends(require_admin)
) -> BaseResponse[TrainingExamplesList]:
    """
    List training examples with optional category filter.
    
    Returns paginated results. Use the search endpoint for similarity-based retrieval.
    """
    try:
        store = get_sql_examples_store()
        
        # Get total count
        total = await store.get_example_count()
        
        # For listing, we'll use a generic search with high top_k
        # In a production system, you'd want direct pagination support in the store
        if total == 0:
            return BaseResponse.ok(data=TrainingExamplesList(
                items=[],
                total=0,
                page=page,
                limit=limit,
                has_more=False
            ))
        
        # Search with a generic query to get examples
        # This is a workaround - ideally the store would support direct listing
        examples = await store.get_similar_examples(
            question="general data query",  # Generic query
            top_k=min(total, 1000),  # Get up to 1000
            category_filter=category,
            min_score=0.0  # Accept all
        )
        
        # Apply pagination manually
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated = examples[start_idx:end_idx]
        
        items = [
            TrainingExampleResponse(
                id=generate_example_id(ex["question"], ex["sql"]),
                question=ex["question"],
                sql=ex["sql"],
                category=ex["category"],
                tags=ex["tags"],
                description=ex["description"],
                score=ex.get("score")
            )
            for ex in paginated
        ]
        
        return BaseResponse.ok(data=TrainingExamplesList(
            items=items,
            total=len(examples),
            page=page,
            limit=limit,
            has_more=end_idx < len(examples)
        ))
        
    except Exception as e:
        logger.error(f"Failed to list training examples: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list training examples: {str(e)}"
        )


@router.get(
    "/examples/search",
    response_model=BaseResponse[List[TrainingExampleResponse]],
    summary="Search similar examples",
    description="Search for training examples similar to a given question."
)
async def search_training_examples(
    question: str = Query(..., min_length=5, description="Question to search for"),
    top_k: int = Query(default=5, ge=1, le=20, description="Number of results"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    min_score: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimum similarity score"),
    current_user: User = Depends(get_current_user)
) -> BaseResponse[List[TrainingExampleResponse]]:
    """
    Search for similar training examples using vector similarity.
    
    This endpoint is useful for:
    - Finding relevant examples for a new question
    - Checking if a similar example already exists
    - Debugging few-shot retrieval
    """
    try:
        # Validate category if provided
        if category and category not in ALLOWED_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Must be one of: {', '.join(ALLOWED_CATEGORIES)}"
            )
        
        store = get_sql_examples_store()
        
        examples = await store.get_similar_examples(
            question=question,
            top_k=top_k,
            category_filter=category,
            min_score=min_score
        )
        
        items = [
            TrainingExampleResponse(
                id=generate_example_id(ex["question"], ex["sql"]),
                question=ex["question"],
                sql=ex["sql"],
                category=ex["category"],
                tags=ex["tags"],
                description=ex["description"],
                score=ex.get("score")
            )
            for ex in examples
        ]
        
        return BaseResponse.ok(data=items)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search training examples: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search training examples: {str(e)}"
        )


@router.delete(
    "/examples/{example_id}",
    response_model=BaseResponse[Dict[str, str]],
    summary="Delete a training example",
    description="Delete a training example by ID. Admin only."
)
async def delete_training_example(
    example_id: str,
    current_user: User = Depends(require_admin)
) -> BaseResponse[Dict[str, str]]:
    """
    Delete a training example by its ID.
    
    Note: The example_id is the SHA256 hash of the question+sql content.
    You can get this from the list or search endpoints.
    """
    try:
        store = get_sql_examples_store()
        
        # The store's delete_example method needs question+sql, but we have the ID
        # We need to find the example first or add a delete_by_id method
        # For now, we'll use the vector store's delete_by_source_ids directly
        
        await store._vector_store.delete_by_source_ids([example_id])
        
        # Log the action
        logger.info(
            "Training example deleted",
            user_id=str(current_user.id),
            user_email=current_user.email,
            example_id=example_id[:12]
        )
        
        return BaseResponse.ok(
            data={"deleted_id": example_id},
            message="Training example deleted successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to delete training example: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete training example: {str(e)}"
        )


@router.post(
    "/bulk",
    response_model=BaseResponse[BulkUploadResult],
    summary="Bulk upload training examples",
    description="Upload multiple training examples from a JSON file. Admin only. Rate limited."
)
async def bulk_upload_examples(
    file: UploadFile = File(..., description="JSON file with training examples"),
    current_user: User = Depends(require_admin)
) -> BaseResponse[BulkUploadResult]:
    """
    Bulk upload training examples from a JSON file.
    
    Expected JSON format:
    ```json
    {
        "examples": [
            {
                "question": "...",
                "sql": "...",
                "category": "...",
                "tags": ["..."],
                "description": "..."
            }
        ]
    }
    ```
    
    Or a simple list:
    ```json
    [
        {"question": "...", "sql": "..."}
    ]
    ```
    
    Rate limited to 5 uploads per hour per user.
    """
    try:
        # Check rate limit
        if not check_bulk_rate_limit(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {BULK_UPLOAD_LIMIT} bulk uploads per hour."
            )
        
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a JSON file"
            )
        
        # Read and parse file
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File too large. Maximum size is 10MB."
            )
        
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON: {str(e)}"
            )
        
        # Extract examples list
        if isinstance(data, list):
            examples_raw = data
        elif isinstance(data, dict):
            examples_raw = data.get('examples', data.get('training_examples', []))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid format. Expected a list or object with 'examples' key."
            )
        
        if not examples_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No examples found in file"
            )
        
        if len(examples_raw) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many examples. Maximum 500 per upload."
            )
        
        # Validate and prepare examples
        valid_examples = []
        errors = []
        skipped = 0
        
        for i, ex in enumerate(examples_raw):
            try:
                # Validate using Pydantic model
                validated = TrainingExampleCreate(
                    question=ex.get('question', ''),
                    sql=ex.get('sql', ''),
                    category=ex.get('category', 'general'),
                    tags=ex.get('tags'),
                    description=ex.get('description', '')
                )
                valid_examples.append({
                    "question": validated.question,
                    "sql": validated.sql,
                    "category": validated.category,
                    "tags": validated.tags or [],
                    "description": validated.description or ""
                })
            except Exception as e:
                errors.append(f"Example {i+1}: {str(e)}")
                skipped += 1
        
        if not valid_examples:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid examples found. Errors: {'; '.join(errors[:5])}"
            )
        
        # Bulk add to store
        store = get_sql_examples_store()
        uploaded = await store.add_examples_batch(valid_examples)
        
        # Log the action
        logger.info(
            "Bulk training examples uploaded",
            user_id=str(current_user.id),
            user_email=current_user.email,
            uploaded=uploaded,
            skipped=skipped,
            filename=file.filename
        )
        
        result = BulkUploadResult(
            uploaded=uploaded,
            skipped=skipped,
            errors=errors[:10]  # Limit errors in response
        )
        
        return BaseResponse.ok(
            data=result,
            message=f"Uploaded {uploaded} examples, skipped {skipped}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk upload training examples: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk upload: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=BaseResponse[TrainingStats],
    summary="Get training statistics",
    description="Get statistics about the training data store."
)
async def get_training_stats(
    current_user: User = Depends(get_current_user)
) -> BaseResponse[TrainingStats]:
    """
    Get statistics about the training data.
    
    Returns:
    - Total example count
    - Examples per category
    - Store health status
    - Backend information
    """
    try:
        store = get_sql_examples_store()
        
        # Get health info
        health = await store.health_check()
        
        # Get example count
        total = health.get("example_count", 0)
        
        # Get category breakdown (approximation via search)
        categories = {}
        for category in ALLOWED_CATEGORIES:
            try:
                examples = await store.get_similar_examples(
                    question="query",
                    top_k=1000,
                    category_filter=category,
                    min_score=0.0
                )
                if examples:
                    categories[category] = len(examples)
            except Exception:
                pass
        
        stats = TrainingStats(
            total_examples=total,
            categories=categories,
            health_status="healthy" if health.get("healthy") else "unhealthy",
            backend=health.get("backend", "unknown"),
            embedding_model=health.get("embedding_model", "unknown")
        )
        
        return BaseResponse.ok(data=stats)
        
    except Exception as e:
        logger.error(f"Failed to get training stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get training stats: {str(e)}"
        )


@router.get(
    "/categories",
    response_model=BaseResponse[List[str]],
    summary="Get allowed categories",
    description="Get list of allowed category values."
)
async def get_allowed_categories(
    current_user: User = Depends(get_current_user)
) -> BaseResponse[List[str]]:
    """Get list of allowed category values for training examples."""
    return BaseResponse.ok(data=ALLOWED_CATEGORIES)
