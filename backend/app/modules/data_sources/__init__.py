"""
Data Sources module: Database connections and file uploads.

Provides unified management for:
- Database connections (PostgreSQL, MySQL, SQLite, etc.)
- File-based sources (CSV, Excel, PDF, JSON)
- DuckDB integration for file querying
- File ingestion and processing

Module structure:
- models.py: DataSourceModel ORM
- repository.py: Data access layer
- service.py: Business logic
- schemas.py: Pydantic request/response models
- routes.py: API endpoints
- utils.py: DuckDB and schema normalization utilities
"""
from app.modules.data_sources.models import DataSourceModel
from app.modules.data_sources.routes import router
from app.modules.data_sources.service import DataSourceService

__all__ = [
    "DataSourceModel",
    "DataSourceService",
    "router",
]
