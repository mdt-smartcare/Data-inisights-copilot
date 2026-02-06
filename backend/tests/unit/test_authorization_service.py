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
def editor_user():
    """Create editor user for testing."""
    user = MagicMock()
    user.id = 2
    user.username = "editor"
    user.email = "editor@test.com"
    user.role = "editor"
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
    """Tests for require_super_admin method."""
    
    def test_allows_super_admin(self, mock_db_service, super_admin_user):
        """Test that super admins pass the check."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            # Should not raise
            service.require_super_admin(super_admin_user, "test_action")
    
    def test_rejects_editor(self, mock_db_service, editor_user):
        """Test that editors are rejected."""
        from fastapi import HTTPException
        
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            with pytest.raises(HTTPException) as exc_info:
                service.require_super_admin(editor_user, "test_action")
            
            assert exc_info.value.status_code == 403
    
    def test_rejects_regular_user(self, mock_db_service, regular_user):
        """Test that regular users are rejected."""
        from fastapi import HTTPException
        
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            with pytest.raises(HTTPException) as exc_info:
                service.require_super_admin(regular_user, "test_action")
            
            assert exc_info.value.status_code == 403
            assert "SuperAdmin" in str(exc_info.value.detail)


class TestAuthorizationServiceCheckRagAccess:
    """Tests for check_rag_access method."""
    
    def test_super_admin_can_access_wizard(self, mock_db_service, super_admin_user):
        """Test super admin can access RAG wizard."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, "wizard_access") is True
    
    def test_editor_cannot_access_wizard(self, mock_db_service, editor_user):
        """Test editor cannot access RAG wizard."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(editor_user, "wizard_access") is False
    
    def test_super_admin_can_generate_embeddings(self, mock_db_service, super_admin_user):
        """Test super admin can generate embeddings."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, "embedding_generate") is True
    
    def test_editor_can_view_config(self, mock_db_service, editor_user):
        """Test editor can view configuration."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(editor_user, "config_view") is True
    
    def test_regular_user_cannot_view_config(self, mock_db_service, regular_user):
        """Test regular user cannot view configuration."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(regular_user, "config_view") is False


class TestAuthorizationServiceHelperMethods:
    """Tests for authorization helper methods."""
    
    def test_can_access_rag_wizard_super_admin(self, mock_db_service, super_admin_user):
        """Test can_access_rag_wizard for super admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_access_rag_wizard(super_admin_user) is True
    
    def test_can_access_rag_wizard_non_admin(self, mock_db_service, editor_user):
        """Test can_access_rag_wizard for non-admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_access_rag_wizard(editor_user) is False
    
    def test_can_generate_embeddings_super_admin(self, mock_db_service, super_admin_user):
        """Test can_generate_embeddings for super admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_generate_embeddings(super_admin_user) is True
    
    def test_can_publish_config_super_admin(self, mock_db_service, super_admin_user):
        """Test can_publish_config for super admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_publish_config(super_admin_user) is True
    
    def test_can_rollback_config_super_admin(self, mock_db_service, super_admin_user):
        """Test can_rollback_config for super admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_rollback_config(super_admin_user) is True
    
    def test_can_view_config_status_editor(self, mock_db_service, editor_user):
        """Test can_view_config_status for editor."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_view_config_status(editor_user) is True
    
    def test_can_view_config_status_regular_user(self, mock_db_service, regular_user):
        """Test can_view_config_status for regular user."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.can_view_config_status(regular_user) is False


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
            
            # Verify commit was called
            mock_db_service.get_connection.return_value.commit.assert_called()
    
    def test_logs_rag_action(self, mock_db_service, super_admin_user):
        """Test logging a RAG action."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            # Use mock action since we can't import the real one
            mock_action = MagicMock()
            mock_action.value = "config.published"
            
            service = AuthorizationService()
            
            _ = service.log_rag_action(
                user=super_admin_user,
                action=mock_action,
                config_id=1,
                success=True
            )
            
            # Verify database operations
            mock_cursor = mock_db_service.get_connection.return_value.cursor.return_value
            mock_cursor.execute.assert_called()
    
    def test_handles_logging_errors(self, mock_db_service, regular_user):
        """Test that logging errors don't crash the service."""
        mock_db_service.get_connection.side_effect = Exception("DB Error")
        
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            # Should not raise
            service._log_unauthorized_attempt(regular_user, "test_action")


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
    def test_super_admin_only_actions(self, action, mock_db_service, super_admin_user, editor_user):
        """Test that certain actions require super admin."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, action) is True
            assert service.check_rag_access(editor_user, action) is False
    
    @pytest.mark.parametrize("action", [
        "config_view",
        "embedding_status",
        "audit_view"
    ])
    def test_read_actions(self, action, mock_db_service, super_admin_user, editor_user, regular_user):
        """Test that read actions allow editors and above."""
        with patch('backend.services.authorization_service.get_db_service', return_value=mock_db_service):
            from backend.services.authorization_service import AuthorizationService
            
            service = AuthorizationService()
            
            assert service.check_rag_access(super_admin_user, action) is True
            assert service.check_rag_access(editor_user, action) is True
            assert service.check_rag_access(regular_user, action) is False
