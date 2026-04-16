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
    
    async def get_by_id(self, source_id: UUID) -> Optional[Any]:
        """Get data source by ID with dependency info."""
        from app.modules.agents.models import AgentConfigModel, AgentModel
        
        stmt = (
            select(
                DataSourceModel,
                func.count(AgentConfigModel.id).label("dependent_config_count"),
                func.array_agg(AgentModel.title.distinct()).label("dependent_agents")
            )
            .outerjoin(AgentConfigModel, AgentConfigModel.data_source_id == DataSourceModel.id)
            .outerjoin(AgentModel, AgentModel.id == AgentConfigModel.agent_id)
            .where(DataSourceModel.id == source_id)
            .group_by(DataSourceModel.id)
        )
        
        result = await self.db.execute(stmt)
        row = result.first()
        
        if not row:
            return None
            
        source, count, agents = row
        source.dependent_config_count = count
        source.dependent_agents = [a for a in agents if a is not None] if agents else []
        
        return source
    
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
    ) -> Tuple[List[Any], int]:
        """Search data sources with filters and dependency info."""
        from app.modules.agents.models import AgentConfigModel, AgentModel
        
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
        
        # Base query for count
        count_stmt = select(func.count(DataSourceModel.id))
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        
        total = (await self.db.execute(count_stmt)).scalar_one()
        
        # Main query with joins for dependency info
        # Note: postgresql array_agg returns NULL if no rows, or [NULL] if join matches but no title
        # We use coalesce and array_remove to handle these cases if needed, 
        # but here we'll just handle it in Python for simplicity.
        stmt = (
            select(
                DataSourceModel,
                func.count(AgentConfigModel.id).label("dependent_config_count"),
                func.array_agg(AgentModel.title.distinct()).label("dependent_agents")
            )
            .outerjoin(AgentConfigModel, AgentConfigModel.data_source_id == DataSourceModel.id)
            .outerjoin(AgentModel, AgentModel.id == AgentConfigModel.agent_id)
        )
        
        if filters:
            stmt = stmt.where(and_(*filters))
            
        stmt = (
            stmt.group_by(DataSourceModel.id)
            .offset(skip)
            .limit(limit)
            .order_by(DataSourceModel.created_at.desc())
        )
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        processed_sources = []
        for source, count, agents in rows:
            # Clean up agents list (filter out None)
            source.dependent_config_count = count
            source.dependent_agents = [a for a in agents if a is not None] if agents else []
            processed_sources.append(source)
        
        return processed_sources, total
    
    async def get_by_type(
        self,
        source_type: str,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[DataSourceModel], int]:
        """Get data sources by type."""
        return await self.search(source_type=source_type, skip=skip, limit=limit)
