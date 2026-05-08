"""Tests for users module service layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime


class TestUserService:
    """Tests for UserService."""
    
    @pytest.fixture
    def mock_repository(self):
        """Mock UserRepository."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def sample_user_mock(self):
        """Sample user as MagicMock to avoid schema validation."""
        user = MagicMock()
        user.id = uuid4()
        user.username = "testuser"
        user.email = "test@example.com"
        user.full_name = "Test User"
        user.role = "user"
        user.is_active = True
        user.created_at = datetime.utcnow()
        return user
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_returns_user(self, mock_db, mock_repository, sample_user_mock):
        """Test that get_user returns the correct user."""
        with patch('app.modules.users.service.UserRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.get_by_id.return_value = sample_user_mock
            
            from app.modules.users.service import UserService
            service = UserService(mock_db)
            service.repository = mock_repository
            
            result = await service.get_user(str(sample_user_mock.id))
            
            assert result.id == sample_user_mock.id
            assert result.username == sample_user_mock.username
            mock_repository.get_by_id.assert_called_once_with(str(sample_user_mock.id))
    
    @pytest.mark.asyncio
    async def test_get_user_raises_not_found_for_missing(self, mock_db, mock_repository):
        """Test that get_user raises ResourceNotFoundError for non-existent user."""
        from app.core.utils.exceptions import ResourceNotFoundError
        
        with patch('app.modules.users.service.UserRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.get_by_id.return_value = None
            
            from app.modules.users.service import UserService
            service = UserService(mock_db)
            service.repository = mock_repository
            
            with pytest.raises(ResourceNotFoundError):
                await service.get_user("nonexistent-id")
    
    @pytest.mark.asyncio
    async def test_get_user_by_username_returns_user(self, mock_db, mock_repository, sample_user_mock):
        """Test getting user by username."""
        with patch('app.modules.users.service.UserRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.get_by_username.return_value = sample_user_mock
            
            from app.modules.users.service import UserService
            service = UserService(mock_db)
            service.repository = mock_repository
            
            result = await service.get_user_by_username("testuser")
            
            assert result.username == "testuser"
            mock_repository.get_by_username.assert_called_once_with("testuser")
    
    @pytest.mark.asyncio
    async def test_get_user_by_username_returns_none_for_missing(self, mock_db, mock_repository):
        """Test that get_user_by_username returns None for non-existent user."""
        with patch('app.modules.users.service.UserRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.get_by_username.return_value = None
            
            from app.modules.users.service import UserService
            service = UserService(mock_db)
            service.repository = mock_repository
            
            result = await service.get_user_by_username("nonexistent")
            
            assert result is None


class TestUserSchemaValidation:
    """Tests for user schema validation."""
    
    def test_user_create_requires_username(self):
        """Test that UserCreate requires username."""
        from app.modules.users.schemas import UserCreate
        
        with pytest.raises(ValueError):
            UserCreate(external_id="ext-123")  # Missing username
    
    def test_user_create_requires_external_id(self):
        """Test that UserCreate requires external_id for OIDC."""
        from app.modules.users.schemas import UserCreate
        
        with pytest.raises(ValueError):
            UserCreate(username="testuser")  # Missing external_id
    
    def test_user_create_valid(self):
        """Test valid UserCreate with required fields."""
        from app.modules.users.schemas import UserCreate
        
        user = UserCreate(
            username="testuser",
            external_id="oidc-sub-123",
            email="test@example.com",
            full_name="Test User"
        )
        assert user.username == "testuser"
        assert user.external_id == "oidc-sub-123"
    
    def test_user_create_default_role(self):
        """Test UserCreate has default role of 'user'."""
        from app.modules.users.schemas import UserCreate
        
        user = UserCreate(
            username="testuser",
            external_id="oidc-sub-123"
        )
        assert user.role == "user"
    
    def test_user_update_partial(self):
        """Test UserUpdate allows partial updates."""
        from app.modules.users.schemas import UserUpdate
        
        update = UserUpdate(full_name="New Name")
        assert update.full_name == "New Name"
        assert update.email is None
        assert update.role is None
