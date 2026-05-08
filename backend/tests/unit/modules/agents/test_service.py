"""Tests for agents module service layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4
from datetime import datetime


class TestAgentService:
    """Tests for AgentService."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_agent_repo(self):
        """Mock AgentRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_user_agent_repo(self):
        """Mock UserAgentRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def sample_agent(self):
        """Sample agent data."""
        return MagicMock(
            id=uuid4(),
            title="Test Agent",
            description="A test agent",
            created_by=uuid4(),
            created_at=datetime.utcnow(),
            is_active=True
        )
    
    @pytest.mark.asyncio
    async def test_create_agent_success(self, mock_db, mock_agent_repo, mock_user_agent_repo, sample_agent):
        """Test successful agent creation."""
        from app.modules.agents.schemas import AgentCreate
        
        with patch('app.modules.agents.service.AgentRepository') as MockAgentRepo, \
             patch('app.modules.agents.service.UserAgentRepository') as MockUserAgentRepo:
            
            MockAgentRepo.return_value = mock_agent_repo
            MockUserAgentRepo.return_value = mock_user_agent_repo
            mock_agent_repo.get_by_title.return_value = None  # No existing agent
            mock_agent_repo.create.return_value = sample_agent
            
            from app.modules.agents.service import AgentService
            service = AgentService(mock_db)
            service.agents = mock_agent_repo
            service.user_agents = mock_user_agent_repo
            
            data = AgentCreate(title="Test Agent", description="A test agent")
            creator_id = uuid4()
            
            result = await service.create_agent(data, creator_id)
            
            assert result.id == sample_agent.id
            mock_agent_repo.create.assert_called_once()
            mock_user_agent_repo.grant_access.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_agent_duplicate_title_raises_error(self, mock_db, mock_agent_repo, sample_agent):
        """Test that creating agent with duplicate title raises error."""
        from app.modules.agents.schemas import AgentCreate
        from app.core.utils.exceptions import AppException
        
        with patch('app.modules.agents.service.AgentRepository') as MockAgentRepo:
            MockAgentRepo.return_value = mock_agent_repo
            mock_agent_repo.get_by_title.return_value = sample_agent  # Existing agent
            
            from app.modules.agents.service import AgentService
            service = AgentService(mock_db)
            service.agents = mock_agent_repo
            
            data = AgentCreate(title="Test Agent", description="Duplicate")
            
            with pytest.raises(AppException) as exc_info:
                await service.create_agent(data, uuid4())
            
            assert exc_info.value.status_code == 409
    
    @pytest.mark.asyncio
    async def test_get_agent_by_id(self, mock_db, mock_agent_repo, sample_agent):
        """Test getting agent by ID."""
        with patch('app.modules.agents.service.AgentRepository') as MockAgentRepo:
            MockAgentRepo.return_value = mock_agent_repo
            mock_agent_repo.get_by_id.return_value = sample_agent
            
            from app.modules.agents.service import AgentService
            service = AgentService(mock_db)
            service.agents = mock_agent_repo
            
            result = await service.get_agent(sample_agent.id)
            
            assert result.id == sample_agent.id
            mock_agent_repo.get_by_id.assert_called_once_with(sample_agent.id)
    
    @pytest.mark.asyncio
    async def test_get_agent_returns_none_for_missing(self, mock_db, mock_agent_repo):
        """Test get_agent returns None for non-existent agent."""
        with patch('app.modules.agents.service.AgentRepository') as MockAgentRepo:
            MockAgentRepo.return_value = mock_agent_repo
            mock_agent_repo.get_by_id.return_value = None
            
            from app.modules.agents.service import AgentService
            service = AgentService(mock_db)
            service.agents = mock_agent_repo
            
            result = await service.get_agent(uuid4())
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_agent(self, mock_db, mock_agent_repo):
        """Test agent deletion."""
        with patch('app.modules.agents.service.AgentRepository') as MockAgentRepo:
            MockAgentRepo.return_value = mock_agent_repo
            mock_agent_repo.delete.return_value = True
            
            from app.modules.agents.service import AgentService
            service = AgentService(mock_db)
            service.agents = mock_agent_repo
            
            result = await service.delete_agent(uuid4())
            
            assert result is True
            mock_agent_repo.delete.assert_called_once()


class TestUserAgentService:
    """Tests for UserAgentService (RBAC)."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_user_agent_repo(self):
        """Mock UserAgentRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_agent_repo(self):
        """Mock AgentRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_user_repo(self):
        """Mock UserRepository."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_revoke_access(self, mock_db, mock_user_agent_repo):
        """Test revoking user access from agent."""
        with patch('app.modules.agents.service.UserAgentRepository') as MockRepo:
            MockRepo.return_value = mock_user_agent_repo
            mock_user_agent_repo.revoke_access.return_value = True
            
            from app.modules.agents.service import UserAgentService
            service = UserAgentService(mock_db)
            service.user_agents = mock_user_agent_repo
            
            result = await service.revoke_access(uuid4(), uuid4())
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_has_access_super_admin_always_true(self, mock_db, mock_user_agent_repo):
        """Test that super admin always has access."""
        from app.modules.agents.service import UserAgentService
        
        with patch('app.modules.agents.service.UserAgentRepository') as MockRepo:
            MockRepo.return_value = mock_user_agent_repo
            
            service = UserAgentService(mock_db)
            service.user_agents = mock_user_agent_repo
            
            # Super admin should have access without even checking repo
            result = await service.has_access(
                uuid4(), uuid4(), 
                min_role="admin",
                user_role="super_admin"
            )
            
            assert result is True
            # Repository should not be called for super admin
            mock_user_agent_repo.has_access.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_has_access_regular_user_checks_repo(self, mock_db, mock_user_agent_repo):
        """Test that regular users' access is checked via repository."""
        from app.modules.agents.service import UserAgentService
        
        with patch('app.modules.agents.service.UserAgentRepository') as MockRepo:
            MockRepo.return_value = mock_user_agent_repo
            mock_user_agent_repo.has_access.return_value = True
            
            service = UserAgentService(mock_db)
            service.user_agents = mock_user_agent_repo
            
            result = await service.has_access(
                uuid4(), uuid4(),
                min_role="editor",
                user_role="user"
            )
            
            assert result is True
            mock_user_agent_repo.has_access.assert_called_once()


class TestAgentConfigService:
    """Tests for AgentConfigService."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_config_repo(self):
        """Mock AgentConfigRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def sample_config(self):
        """Sample config data as MagicMock."""
        config = MagicMock()
        config.id = 1
        config.agent_id = uuid4()
        config.version = 1
        config.is_active = True
        config.data_source_id = uuid4()
        config.embedding_status = "completed"
        config.created_at = datetime.utcnow()
        return config
    
    @pytest.mark.asyncio
    async def test_get_config_by_id(self, mock_db, mock_config_repo, sample_config):
        """Test getting config by ID."""
        with patch('app.modules.agents.service.AgentConfigRepository') as MockRepo:
            MockRepo.return_value = mock_config_repo
            mock_config_repo.get_by_id.return_value = sample_config
            
            from app.modules.agents.service import AgentConfigService
            service = AgentConfigService(mock_db)
            service.configs = mock_config_repo
            
            # Mock the _to_response_with_models method
            with patch.object(service, '_to_response_with_models', new_callable=AsyncMock) as mock_response:
                mock_response.return_value = MagicMock(id=sample_config.id, is_active=True)
                
                result = await service.get_config(sample_config.id)
                
                assert result.id == sample_config.id
                mock_config_repo.get_by_id.assert_called_once_with(sample_config.id)
    
    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_missing(self, mock_db, mock_config_repo):
        """Test get_config returns None for non-existent config."""
        with patch('app.modules.agents.service.AgentConfigRepository') as MockRepo:
            MockRepo.return_value = mock_config_repo
            mock_config_repo.get_by_id.return_value = None
            
            from app.modules.agents.service import AgentConfigService
            service = AgentConfigService(mock_db)
            service.configs = mock_config_repo
            
            result = await service.get_config(9999)
            
            assert result is None
