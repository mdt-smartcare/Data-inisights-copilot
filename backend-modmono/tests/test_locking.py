import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from app.modules.agents.service import AgentConfigService
from app.core.utils.exceptions import AppException

@pytest.mark.asyncio
async def test_upsert_data_source_lock_published():
    """Test that you cannot change data source for a published agent."""
    # Setup
    mock_db = AsyncMock()
    service = AgentConfigService(mock_db)
    
    agent_id = uuid4()
    old_ds_id = uuid4()
    new_ds_id = uuid4()
    
    # Mock agent and source exist
    service.agents.get_by_id = AsyncMock(return_value=Mock(id=agent_id))
    service.sources.get_by_id = AsyncMock(return_value=Mock(id=new_ds_id))
    
    # Mock history with a published config
    published_config = Mock(status="published", data_source_id=old_ds_id)
    service.configs.get_config_history = AsyncMock(return_value=[published_config])
    
    # Execution & Verification: Should raise AppException
    with pytest.raises(AppException) as excinfo:
        await service.upsert_data_source_step(agent_id, new_ds_id)
    
    assert "Data source cannot be changed" in str(excinfo.value.message)
    assert excinfo.value.status_code == 400

@pytest.mark.asyncio
async def test_upsert_data_source_lock_draft_only():
    """Test that you CAN change data source if only drafts exist."""
    # Setup
    mock_db = AsyncMock()
    service = AgentConfigService(mock_db)
    
    agent_id = uuid4()
    old_ds_id = uuid4()
    new_ds_id = uuid4()
    
    # Mock agent and source exist
    service.agents.get_by_id = AsyncMock(return_value=Mock(id=agent_id))
    service.sources.get_by_id = AsyncMock(return_value=Mock(id=new_ds_id))
    
    # Mock history with only a draft config
    draft_config = Mock(status="draft", data_source_id=old_ds_id)
    service.configs.get_config_history = AsyncMock(return_value=[draft_config])
    
    # Mock create_draft
    service.configs.create_draft = AsyncMock(return_value=Mock())
    service._to_response = MagicMock()
    
    # Execution
    await service.upsert_data_source_step(agent_id, new_ds_id)
    
    # Verification: create_draft should be called with the new ds id
    service.configs.create_draft.assert_called_once_with(
        agent_id=agent_id,
        data_source_id=new_ds_id
    )

@pytest.mark.asyncio
async def test_upsert_data_source_same_ds_published():
    """Test that you CAN use the same data source even if published."""
    # Setup
    mock_db = AsyncMock()
    service = AgentConfigService(mock_db)
    
    agent_id = uuid4()
    ds_id = uuid4()
    
    # Mock agent and source exist
    service.agents.get_by_id = AsyncMock(return_value=Mock(id=agent_id))
    service.sources.get_by_id = AsyncMock(return_value=Mock(id=ds_id))
    
    # Mock history with a published config using the SAME ds_id
    published_config = Mock(status="published", data_source_id=ds_id)
    service.configs.get_config_history = AsyncMock(return_value=[published_config])
    
    # Mock create_draft
    service.configs.create_draft = AsyncMock(return_value=Mock())
    service._to_response = MagicMock()
    
    # Execution
    await service.upsert_data_source_step(agent_id, ds_id)
    
    # Verification: Success (no exception)
    service.configs.create_draft.assert_called_once()
