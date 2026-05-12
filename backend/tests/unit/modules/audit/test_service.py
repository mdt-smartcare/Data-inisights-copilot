"""Tests for audit module service layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime


class TestAuditService:
    """Tests for AuditService."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_repository(self):
        """Mock AuditLogRepository."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_log_audit_event(self, mock_db, mock_repository):
        """Test logging an audit event."""
        with patch('app.modules.audit.service.AuditLogRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.create.return_value = 1
            
            from app.modules.audit.service import AuditService
            from app.modules.audit.schemas import AuditAction
            
            service = AuditService(mock_db)
            service.repository = mock_repository
            
            log_id = await service.log(
                action=AuditAction.AGENT_CREATED,
                actor_id=str(uuid4()),
                actor_username="testuser",
                actor_role="admin",
                resource_type="agent",
                resource_id=str(uuid4()),
                resource_name="Test Agent",
                details={"key": "value"},
                ip_address="127.0.0.1"
            )
            
            assert log_id == 1
            mock_repository.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_audit_event_with_string_action(self, mock_db, mock_repository):
        """Test logging with string action instead of enum."""
        with patch('app.modules.audit.service.AuditLogRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.create.return_value = 2
            
            from app.modules.audit.service import AuditService
            
            service = AuditService(mock_db)
            service.repository = mock_repository
            
            log_id = await service.log(
                action="custom.action",
                actor_username="testuser"
            )
            
            assert log_id == 2
    
    @pytest.mark.asyncio
    async def test_get_logs_with_filters(self, mock_db, mock_repository):
        """Test querying audit logs with filters."""
        from app.modules.audit.schemas import AuditLogResponse
        
        # Create properly typed mock logs that pass Pydantic validation
        sample_log = AuditLogResponse(
            id=1,
            action="agent.created",
            actor_id=str(uuid4()),
            actor_username="admin",
            actor_role="admin",
            resource_type="agent",
            resource_id=str(uuid4()),
            resource_name="Test Agent",
            details={"key": "value"},
            ip_address="127.0.0.1",
            user_agent="test-agent",
            timestamp=datetime.utcnow()
        )
        
        with patch('app.modules.audit.service.AuditLogRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            # Return proper AuditLogResponse objects
            mock_repository.get_logs.return_value = [sample_log]
            mock_repository.get_log_count.return_value = 1
            
            from app.modules.audit.service import AuditService
            
            service = AuditService(mock_db)
            service.repository = mock_repository
            
            result = await service.get_logs(
                actor_username="admin",
                action="agent.created",
                limit=10
            )
            
            assert result.total == 1
            assert len(result.logs) == 1
            mock_repository.get_logs.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_logs_empty(self, mock_db, mock_repository):
        """Test audit log query returns empty list."""
        with patch('app.modules.audit.service.AuditLogRepository') as MockRepo:
            MockRepo.return_value = mock_repository
            mock_repository.get_logs.return_value = []
            mock_repository.get_log_count.return_value = 0
            
            from app.modules.audit.service import AuditService
            
            service = AuditService(mock_db)
            service.repository = mock_repository
            
            result = await service.get_logs(limit=10, offset=20)
            
            assert result.total == 0
            assert len(result.logs) == 0


class TestAuditAction:
    """Tests for AuditAction enum."""
    
    def test_audit_actions_defined(self):
        """Test that essential audit actions are defined."""
        from app.modules.audit.schemas import AuditAction
        
        # Check essential actions exist
        assert hasattr(AuditAction, 'AGENT_CREATED')
        assert hasattr(AuditAction, 'CONFIG_ACTIVATED')
        assert hasattr(AuditAction, 'DATASOURCE_CREATED')
    
    def test_audit_action_values_are_strings(self):
        """Test that audit action values are strings."""
        from app.modules.audit.schemas import AuditAction
        
        for action in AuditAction:
            assert isinstance(action.value, str)


class TestAuditLogSchemas:
    """Tests for audit log schemas."""
    
    def test_audit_log_create_schema(self):
        """Test AuditLogCreate schema validation."""
        from app.modules.audit.schemas import AuditLogCreate
        
        log = AuditLogCreate(
            action="test.action",
            actor_id="user-123",
            actor_username="testuser",
            resource_type="agent",
            resource_id="agent-456"
        )
        
        assert log.action == "test.action"
        assert log.actor_username == "testuser"
    
    def test_audit_log_create_with_details(self):
        """Test AuditLogCreate with details dictionary."""
        from app.modules.audit.schemas import AuditLogCreate
        
        details = {
            "old_value": "foo",
            "new_value": "bar",
            "changed_fields": ["title", "description"]
        }
        
        log = AuditLogCreate(
            action="config.updated",
            details=details
        )
        
        assert log.details == details
        assert log.details["old_value"] == "foo"
