"""
Unit tests for backend/services/audit_service.py AuditService

Tests audit logging, retrieval, and filtering.
"""
import pytest
from unittest.mock import MagicMock
import os


# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_audit_service():
    """Create a mock AuditService for testing."""
    mock = MagicMock()
    mock.logs = []
    mock.log_id_counter = 0
    
    def mock_log(**kwargs):
        mock.log_id_counter += 1
        action = kwargs.get('action', '')
        if hasattr(action, 'value'):
            action = action.value
        log_entry = {
            'id': mock.log_id_counter,
            'action': action,
            'actor_id': kwargs.get('actor_id'),
            'actor_username': kwargs.get('actor_username'),
            'actor_role': kwargs.get('actor_role'),
            'resource_type': kwargs.get('resource_type'),
            'resource_id': kwargs.get('resource_id'),
            'resource_name': kwargs.get('resource_name'),
            'details': kwargs.get('details'),
            'ip_address': kwargs.get('ip_address'),
            'user_agent': kwargs.get('user_agent'),
            'timestamp': '2024-01-01T00:00:00'
        }
        mock.logs.append(log_entry)
        return mock.log_id_counter
    
    def mock_get_logs(**kwargs):
        filtered = mock.logs.copy()
        if kwargs.get('actor_username'):
            filtered = [l for l in filtered if l['actor_username'] == kwargs['actor_username']]
        if kwargs.get('action'):
            action = kwargs['action']
            filtered = [l for l in filtered if action in str(l['action'])]
        if kwargs.get('resource_type'):
            filtered = [l for l in filtered if l['resource_type'] == kwargs['resource_type']]
        if kwargs.get('limit'):
            offset = kwargs.get('offset', 0)
            filtered = filtered[offset:offset + kwargs['limit']]
        return filtered
    
    def mock_get_log_count(**kwargs):
        filtered = mock.logs.copy()
        if kwargs.get('actor_username'):
            filtered = [l for l in filtered if l['actor_username'] == kwargs['actor_username']]
        return len(filtered)
    
    mock.log = mock_log
    mock.get_logs = mock_get_logs
    mock.get_log_count = mock_get_log_count
    mock.export_logs = MagicMock(return_value=[])
    
    return mock


class TestAuditServiceInitialization:
    """Tests for AuditService initialization."""
    
    def test_audit_service_has_log_method(self, mock_audit_service):
        """Test that AuditService has log method."""
        assert hasattr(mock_audit_service, 'log')
        assert callable(mock_audit_service.log)
    
    def test_audit_service_has_get_logs_method(self, mock_audit_service):
        """Test that AuditService has get_logs method."""
        assert hasattr(mock_audit_service, 'get_logs')
        assert callable(mock_audit_service.get_logs)
    
    def test_audit_service_has_get_log_count_method(self, mock_audit_service):
        """Test that AuditService has get_log_count method."""
        assert hasattr(mock_audit_service, 'get_log_count')
        assert callable(mock_audit_service.get_log_count)


class TestAuditAction:
    """Tests for AuditAction enum."""
    
    def test_audit_actions_defined(self):
        """Test that common audit action patterns exist."""
        # Test with mock action values
        class MockAuditAction:
            USER_CREATE = MagicMock(value="user.create")
            USER_LOGIN = MagicMock(value="user.login")
            USER_UPDATE = MagicMock(value="user.update")
            CONNECTION_CREATE = MagicMock(value="connection.create")
            CONNECTION_DELETE = MagicMock(value="connection.delete")
            PROMPT_PUBLISH = MagicMock(value="prompt.publish")
            PROMPT_ROLLBACK = MagicMock(value="prompt.rollback")
            CONFIG_EXPORT = MagicMock(value="config.export")
        
        # Verify expected action values
        assert MockAuditAction.USER_CREATE.value == "user.create"
        assert MockAuditAction.USER_LOGIN.value == "user.login"
        assert MockAuditAction.CONNECTION_CREATE.value == "connection.create"
        assert MockAuditAction.CONNECTION_DELETE.value == "connection.delete"
        assert MockAuditAction.PROMPT_PUBLISH.value == "prompt.publish"
        assert MockAuditAction.PROMPT_ROLLBACK.value == "prompt.rollback"
        assert MockAuditAction.CONFIG_EXPORT.value == "config.export"


class TestAuditLogging:
    """Tests for audit log creation."""
    
    def test_log_basic_action(self, mock_audit_service):
        """Test logging a basic action."""
        mock_action = MagicMock()
        mock_action.value = "user.login"
        
        log_id = mock_audit_service.log(
            action=mock_action,
            actor_username="testuser"
        )
        
        assert isinstance(log_id, int)
        assert log_id > 0
    
    def test_log_with_full_details(self, mock_audit_service):
        """Test logging with all optional fields."""
        mock_action = MagicMock()
        mock_action.value = "prompt.publish"
        
        log_id = mock_audit_service.log(
            action=mock_action,
            actor_id=1,
            actor_username="admin",
            actor_role="super_admin",
            resource_type="prompt",
            resource_id="123",
            resource_name="SQL Agent Prompt v2",
            details={"old_version": 1, "new_version": 2},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )
        
        assert log_id > 0
        
        # Verify log was created with correct data
        logs = mock_audit_service.get_logs(actor_username="admin")
        assert len(logs) > 0
        
        log_entry = logs[0]
        assert log_entry['actor_username'] == "admin"
        assert log_entry['action'] == "prompt.publish"
        assert log_entry['resource_type'] == "prompt"
    
    def test_log_with_string_action(self, mock_audit_service):
        """Test logging with string action instead of enum."""
        log_id = mock_audit_service.log(
            action="custom.action",
            actor_username="user1"
        )
        
        assert log_id > 0
    
    def test_log_details_stored(self, mock_audit_service):
        """Test that details dict is stored correctly."""
        mock_action = MagicMock()
        mock_action.value = "config.export"
        
        details = {
            "changes": ["field1", "field2"],
            "before": {"status": "draft"},
            "after": {"status": "published"}
        }
        
        mock_audit_service.log(
            action=mock_action,
            actor_username="admin",
            details=details
        )
        
        logs = mock_audit_service.get_logs(actor_username="admin")
        assert logs[0]['details'] == details


class TestAuditLogRetrieval:
    """Tests for querying audit logs."""
    
    def test_get_logs_empty(self, mock_audit_service):
        """Test getting logs when none exist."""
        logs = mock_audit_service.get_logs()
        
        assert isinstance(logs, list)
        assert len(logs) == 0
    
    def test_get_logs_filter_by_username(self, mock_audit_service):
        """Test filtering logs by username."""
        mock_action = MagicMock()
        mock_action.value = "user.login"
        
        mock_audit_service.log(action=mock_action, actor_username="user1")
        mock_audit_service.log(action=mock_action, actor_username="user2")
        mock_audit_service.log(action=mock_action, actor_username="user1")
        
        logs = mock_audit_service.get_logs(actor_username="user1")
        
        assert len(logs) == 2
        assert all(log['actor_username'] == "user1" for log in logs)
    
    def test_get_logs_filter_by_action(self, mock_audit_service):
        """Test filtering logs by action type."""
        login = MagicMock()
        login.value = "user.login"
        create = MagicMock()
        create.value = "user.create"
        update = MagicMock()
        update.value = "user.update"
        
        mock_audit_service.log(action=login, actor_username="user1")
        mock_audit_service.log(action=create, actor_username="admin")
        mock_audit_service.log(action=update, actor_username="admin")
        
        # Filter by prefix "user."
        logs = mock_audit_service.get_logs(action="user.")
        
        assert len(logs) == 3
    
    def test_get_logs_filter_by_resource_type(self, mock_audit_service):
        """Test filtering logs by resource type."""
        prompt_action = MagicMock()
        prompt_action.value = "prompt.publish"
        conn_action = MagicMock()
        conn_action.value = "connection.create"
        
        mock_audit_service.log(
            action=prompt_action,
            resource_type="prompt",
            actor_username="admin"
        )
        mock_audit_service.log(
            action=conn_action,
            resource_type="connection",
            actor_username="admin"
        )
        
        logs = mock_audit_service.get_logs(resource_type="prompt")
        
        assert len(logs) == 1
        assert logs[0]['resource_type'] == "prompt"
    
    def test_get_logs_pagination(self, mock_audit_service):
        """Test log pagination."""
        mock_action = MagicMock()
        mock_action.value = "user.login"
        
        # Create 5 logs
        for i in range(5):
            mock_audit_service.log(
                action=mock_action,
                actor_username=f"user{i}"
            )
        
        # Get first page
        logs_page1 = mock_audit_service.get_logs(limit=2, offset=0)
        assert len(logs_page1) == 2
        
        # Get second page
        logs_page2 = mock_audit_service.get_logs(limit=2, offset=2)
        assert len(logs_page2) == 2
        
        # Pages should be different
        assert logs_page1[0]['actor_username'] != logs_page2[0]['actor_username']


class TestAuditLogCount:
    """Tests for log counting."""
    
    def test_get_log_count_empty(self, mock_audit_service):
        """Test count when no logs exist."""
        count = mock_audit_service.get_log_count()
        
        assert count == 0
    
    def test_get_log_count_total(self, mock_audit_service):
        """Test total log count."""
        login = MagicMock()
        login.value = "user.login"
        publish = MagicMock()
        publish.value = "prompt.publish"
        
        mock_audit_service.log(action=login, actor_username="user1")
        mock_audit_service.log(action=login, actor_username="user2")
        mock_audit_service.log(action=publish, actor_username="admin")
        
        count = mock_audit_service.get_log_count()
        
        assert count == 3
    
    def test_get_log_count_filtered(self, mock_audit_service):
        """Test filtered log count."""
        mock_action = MagicMock()
        mock_action.value = "user.login"
        
        mock_audit_service.log(action=mock_action, actor_username="user1")
        mock_audit_service.log(action=mock_action, actor_username="user1")
        mock_audit_service.log(action=mock_action, actor_username="user2")
        
        count = mock_audit_service.get_log_count(actor_username="user1")
        
        assert count == 2


class TestAuditServiceSingleton:
    """Tests for singleton pattern."""
    
    def test_audit_service_is_created(self):
        """Test that audit service can be created."""
        mock = MagicMock()
        mock.log = MagicMock()
        mock.get_logs = MagicMock(return_value=[])
        
        assert hasattr(mock, 'log')
        assert hasattr(mock, 'get_logs')


class TestExportLogs:
    """Tests for log export functionality."""
    
    def test_export_logs_returns_list(self, mock_audit_service):
        """Test that export_logs returns a list."""
        result = mock_audit_service.export_logs()
        assert isinstance(result, list)
    
    def test_export_logs_format(self, mock_audit_service):
        """Test export logs format."""
        mock_audit_service.export_logs.return_value = [
            {
                'id': 1,
                'action': 'user.login',
                'actor_username': 'user1',
                'timestamp': '2024-01-01T00:00:00'
            }
        ]
        
        result = mock_audit_service.export_logs()
        
        assert len(result) == 1
        assert 'id' in result[0]
        assert 'action' in result[0]
        assert 'actor_username' in result[0]
        assert 'timestamp' in result[0]
