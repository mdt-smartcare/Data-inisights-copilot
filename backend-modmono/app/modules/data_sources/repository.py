"""
Repository for data source data access operations.
"""
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.data_sources.models import DataSourceModel


class DataSourceRepository:
    """Repository for data source CRUD operations."""
    
    def __init__(self, session: AsyncSession):
        self.db = session
    
    async def create(self, data: Dict[str, Any], created_by: Optional[UUID] = None) -> DataSourceModel:
        """Create a new data source."""
        source = DataSourceModel(**data, created_by=created_by)
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)
        return source
    
    async def get_by_id(self, source_id: UUID) -> Optional[DataSourceModel]:
        """Get data source by ID."""
        query = select(DataSourceModel).where(DataSourceModel.id == source_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_title(self, title: str) -> Optional[DataSourceModel]:
        """Get data source by title."""
        query = select(DataSourceModel).where(DataSourceModel.title == title)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def update(self, source_id: UUID, data: Dict[str, Any]) -> Optional[DataSourceModel]:
        """Update a data source."""
        source = await self.get_by_id(source_id)
        if not source:
            return None
        
        for key, value in data.items():
            if hasattr(source, key) and value is not None:
                setattr(source, key, value)
        
        await self.db.flush()
        await self.db.refresh(source)
        return source
    
    async def delete(self, source_id: UUID) -> bool:
        """Delete a data source."""
        source = await self.get_by_id(source_id)
        if not source:
            return False
        
        await self.db.delete(source)
        await self.db.flush()
        return True
    
    async def search(
        self,
        query: Optional[str] = None,
        source_type: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[DataSourceModel], int]:
        """Search data sources with filters."""
        filters = []
        
        if query:
            filters.append(
                or_(
                    DataSourceModel.title.ilike(f"%{query}%"),
                    DataSourceModel.description.ilike(f"%{query}%"),
                )
            )
        
        if source_type:
            filters.append(DataSourceModel.source_type == source_type)
        
        if created_by:
            filters.append(DataSourceModel.created_by == created_by)
        
        base_query = select(DataSourceModel)
        if filters:
            base_query = base_query.where(and_(*filters))
        
        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()
        
        # Results
        stmt = base_query.offset(skip).limit(limit).order_by(DataSourceModel.created_at.desc())
        result = await self.db.execute(stmt)
        
        return list(result.scalars().all()), total
    
    async def get_by_type(
        self,
        source_type: str,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[DataSourceModel], int]:
        """Get data sources by type."""
        return await self.search(source_type=source_type, skip=skip, limit=limit)
