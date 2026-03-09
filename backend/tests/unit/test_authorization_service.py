"""
Unit tests for backend/services/authorization_service.py

Tests RBAC enforcement for RAG operations.
"""
import pytest
from unittest.mock import MagicMock, patch
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_db_service():
    """Create mock database service."""
    mock = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock.get_connection.return_value = mock_conn
    return mock


@pytest.fixture
def super_admin_user():
    """Create super admin user for testing."""
    user = MagicMock()
    user.id = 1
    user.username = "superadmin"
    user.email = "superadmin@test.com"
    user.role = "super_admin"
    return user

@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    user = MagicMock()
    user.id = 2
    user.username = "admin"
    user.email = "admin@test.com"
    user.role = "admin"
    return user


@pytest.fixture
def regular_user():
    """Create regular user for testing."""
    user = MagicMock()
    user.id = 3
    user.username = "user"
    user.email = "user@test.com"
    user.role = "user"
    return user


class TestAuthorizationServiceRequireSuperAdmin:
    """Tests for require_super_admin method (now mapped to require_admin)."""
    
    def test_allows_super_admin(self, mock_db_service, super_admin_user):
        """Test that super admins pass the check."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            # Should not raise
            service.require_super_admin(super_admin_user, "test_action")

    def test_allows_admin(self, mock_db_service, admin_user):
        """Test that admins pass the check."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            # Should not raise
            service.require_super_admin(admin_user, "test_action")
    
    def test_rejects_regular_user(self, mock_db_service, regular_user):
        """Test that regular users are rejected."""
        from fastapi import HTTPException
        
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            with pytest.raises(HTTPException) as exc_info:
                service.require_super_admin(regular_user, "test_action")
            
            assert exc_info.value.status_code == 403

class TestAuthorizationServiceCheckRagAccess:
    """Tests for check_rag_access method."""
    
    def test_super_admin_can_access_wizard(self, mock_db_service, super_admin_user):
        """Test super admin can access RAG wizard."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, "wizard_access") is True
    
    def test_admin_can_access_wizard(self, mock_db_service, admin_user):
        """Test admin can access RAG wizard."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(admin_user, "wizard_access") is True
    
    def test_regular_user_cannot_access_wizard(self, mock_db_service, regular_user):
        """Test regular user cannot access RAG wizard."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(regular_user, "wizard_access") is False

class TestAuthorizationServiceAuditLogging:
    """Tests for audit logging methods."""
    
    def test_logs_unauthorized_attempt(self, mock_db_service, regular_user):
        """Test that unauthorized attempts are logged."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            service._log_unauthorized_attempt(regular_user, "test_action")
            
            # Verify insert was called
            mock_cursor = mock_db_service.get_connection.return_value.cursor.return_value
            mock_cursor.execute.assert_called()
    
    def test_logs_rag_action(self, mock_db_service, admin_user):
        """Test logging a RAG action."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            # Use mock action
            mock_action = MagicMock()
            mock_action.value = "config_published"
            
            service = AuthorizationService()
            
            _ = service.log_rag_action(
                user=admin_user,
                action=mock_action,
                config_id=1,
                success=True
            )
            
            # Verify database operations
            mock_cursor = mock_db_service.get_connection.return_value.cursor.return_value
            mock_cursor.execute.assert_called()

class TestRoleChecksForAllActions:
    """Comprehensive tests for all RAG actions."""
    
    @pytest.mark.parametrize("action", [
        "wizard_access",
        "schema_select",
        "dictionary_upload",
        "embedding_generate",
        "config_publish",
        "config_rollback",
        "embedding_cancel"
    ])
    def test_admin_required_actions(self, action, mock_db_service, super_admin_user, admin_user, regular_user):
        """Test that certain actions require at least admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, action) is True
            assert service.check_rag_access(admin_user, action) is True
            assert service.check_rag_access(regular_user, action) is False
    
    @pytest.mark.parametrize("action", [
        "config_view",
        "embedding_status",
        "audit_view"
    ])
    def test_read_actions_admin_required(self, action, mock_db_service, super_admin_user, admin_user, regular_user):
        """Test that read actions require at least admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, action) is True
            assert service.check_rag_access(admin_user, action) is True
            assert service.check_rag_access(regular_user, action) is False
