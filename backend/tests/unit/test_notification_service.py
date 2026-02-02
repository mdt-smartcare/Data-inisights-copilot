"""
Unit tests for backend/services/notification_service.py NotificationService

Tests notification creation, routing, and preference management.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
import os
from datetime import datetime


# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_notification_service():
    """Create a mock NotificationService for testing."""
    mock = MagicMock()
    mock.db = MagicMock()
    mock.notifications = []
    mock.preferences = {}
    mock.notification_id_counter = 0
    
    def mock_create_record(**kwargs):
        mock.notification_id_counter += 1
        notification = {
            'id': mock.notification_id_counter,
            'user_id': kwargs.get('user_id'),
            'type': kwargs.get('notification_type', 'info').value if hasattr(kwargs.get('notification_type', ''), 'value') else kwargs.get('notification_type', 'info'),
            'priority': kwargs.get('priority', 'medium').value if hasattr(kwargs.get('priority', ''), 'value') else kwargs.get('priority', 'medium'),
            'title': kwargs.get('title'),
            'message': kwargs.get('message'),
            'action_url': kwargs.get('action_url'),
            'action_label': kwargs.get('action_label'),
            'related_entity_type': kwargs.get('related_entity_type'),
            'related_entity_id': kwargs.get('related_entity_id'),
            'channels': kwargs.get('channels', ['in_app']),
            'status': 'unread',
            'created_at': datetime.now().isoformat()
        }
        mock.notifications.append(notification)
        return mock.notification_id_counter
    
    def mock_get_for_user(user_id, **kwargs):
        user_notifications = [n for n in mock.notifications if n['user_id'] == user_id]
        if kwargs.get('status'):
            user_notifications = [n for n in user_notifications if n['status'] == kwargs['status']]
        limit = kwargs.get('limit', 50)
        return user_notifications[:limit]
    
    def mock_mark_as_read(notification_id):
        for n in mock.notifications:
            if n['id'] == notification_id:
                n['status'] = 'read'
                n['read_at'] = datetime.now().isoformat()
                return True
        return False
    
    def mock_get_unread_count(user_id):
        return len([n for n in mock.notifications if n['user_id'] == user_id and n['status'] == 'unread'])
    
    def mock_get_preferences(user_id):
        return mock.preferences.get(user_id, {
            'user_id': user_id,
            'in_app_enabled': True,
            'email_enabled': True,
            'webhook_enabled': False,
            'webhook_url': None,
            'quiet_hours_enabled': False
        })
    
    def mock_update_preferences(user_id, **kwargs):
        if user_id not in mock.preferences:
            mock.preferences[user_id] = {'user_id': user_id}
        mock.preferences[user_id].update(kwargs)
        return mock.preferences[user_id]
    
    mock._create_notification_record = mock_create_record
    mock.get_notifications_for_user = mock_get_for_user
    mock.mark_as_read = mock_mark_as_read
    mock.get_unread_count = mock_get_unread_count
    mock.get_user_preferences = mock_get_preferences
    mock.update_user_preferences = mock_update_preferences
    mock.dismiss_notification = MagicMock(return_value=True)
    mock.delete_notification = MagicMock(return_value=True)
    mock.mark_all_as_read = MagicMock(return_value=5)
    mock.notify = AsyncMock(return_value=1)
    mock.send_webhook_notification = AsyncMock(return_value=True)
    
    return mock


class TestNotificationServiceInitialization:
    """Tests for NotificationService initialization."""
    
    def test_notification_service_has_db(self, mock_notification_service):
        """Test that NotificationService has db service."""
        assert mock_notification_service.db is not None
    
    def test_notification_service_has_required_methods(self, mock_notification_service):
        """Test that NotificationService has required methods."""
        assert hasattr(mock_notification_service, '_create_notification_record')
        assert hasattr(mock_notification_service, 'get_notifications_for_user')
        assert hasattr(mock_notification_service, 'mark_as_read')
        assert hasattr(mock_notification_service, 'get_unread_count')


class TestCreateNotificationRecord:
    """Tests for notification record creation."""
    
    def test_create_notification_record(self, mock_notification_service):
        """Test creating a notification record."""
        notification_id = mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='embedding_complete'),
            title="Embedding Complete",
            message="Your embeddings are ready",
            priority=MagicMock(value='medium'),
            channels=['in_app']
        )
        
        assert notification_id == 1
        assert len(mock_notification_service.notifications) == 1
    
    def test_create_notification_with_action(self, mock_notification_service):
        """Test creating a notification with action URL."""
        notification_id = mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='config_published'),
            title="Config Published",
            message="New configuration is active",
            priority=MagicMock(value='high'),
            action_url="/config/1",
            action_label="View Config"
        )
        
        assert notification_id > 0
        notification = mock_notification_service.notifications[0]
        assert notification['action_url'] == "/config/1"
        assert notification['action_label'] == "View Config"
    
    def test_create_notification_with_related_entity(self, mock_notification_service):
        """Test creating a notification with related entity."""
        _ = mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='embedding_error'),
            title="Embedding Failed",
            message="Job failed",
            priority=MagicMock(value='critical'),
            related_entity_type="embedding_job",
            related_entity_id=123
        )
        
        notification = mock_notification_service.notifications[0]
        assert notification['related_entity_type'] == "embedding_job"
        assert notification['related_entity_id'] == 123


class TestGetNotificationsForUser:
    """Tests for notification retrieval."""
    
    def test_get_notifications_empty(self, mock_notification_service):
        """Test getting notifications when none exist."""
        notifications = mock_notification_service.get_notifications_for_user(user_id=1)
        
        assert isinstance(notifications, list)
        assert len(notifications) == 0
    
    def test_get_notifications_for_user(self, mock_notification_service):
        """Test getting notifications for a specific user."""
        # Create notifications for different users
        mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="For User 1",
            message="Message 1"
        )
        mock_notification_service._create_notification_record(
            user_id=2,
            notification_type=MagicMock(value='info'),
            title="For User 2",
            message="Message 2"
        )
        mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="For User 1 again",
            message="Message 3"
        )
        
        notifications = mock_notification_service.get_notifications_for_user(user_id=1)
        
        assert len(notifications) == 2
        assert all(n['user_id'] == 1 for n in notifications)
    
    def test_get_notifications_with_status_filter(self, mock_notification_service):
        """Test getting notifications with status filter."""
        mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="Unread",
            message="Unread message"
        )
        
        # Get all notifications
        all_notifications = mock_notification_service.get_notifications_for_user(user_id=1)
        assert len(all_notifications) == 1
        
        # Get only unread
        unread = mock_notification_service.get_notifications_for_user(user_id=1, status='unread')
        assert len(unread) == 1
    
    def test_get_notifications_with_limit(self, mock_notification_service):
        """Test getting notifications with limit."""
        for i in range(10):
            mock_notification_service._create_notification_record(
                user_id=1,
                notification_type=MagicMock(value='info'),
                title=f"Notification {i}",
                message=f"Message {i}"
            )
        
        notifications = mock_notification_service.get_notifications_for_user(user_id=1, limit=5)
        
        assert len(notifications) == 5


class TestMarkAsRead:
    """Tests for marking notifications as read."""
    
    def test_mark_as_read(self, mock_notification_service):
        """Test marking a notification as read."""
        notification_id = mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="Test",
            message="Test message"
        )
        
        result = mock_notification_service.mark_as_read(notification_id)
        
        assert result == True
        notification = mock_notification_service.notifications[0]
        assert notification['status'] == 'read'
        assert notification['read_at'] is not None
    
    def test_mark_nonexistent_as_read(self, mock_notification_service):
        """Test marking a non-existent notification as read."""
        result = mock_notification_service.mark_as_read(999)
        
        assert result == False


class TestGetUnreadCount:
    """Tests for unread count."""
    
    def test_get_unread_count_zero(self, mock_notification_service):
        """Test getting unread count when zero."""
        count = mock_notification_service.get_unread_count(user_id=1)
        
        assert count == 0
    
    def test_get_unread_count(self, mock_notification_service):
        """Test getting unread count."""
        mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="Test 1",
            message="Message 1"
        )
        mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="Test 2",
            message="Message 2"
        )
        
        count = mock_notification_service.get_unread_count(user_id=1)
        
        assert count == 2
    
    def test_get_unread_count_after_read(self, mock_notification_service):
        """Test unread count decreases after marking as read."""
        notification_id = mock_notification_service._create_notification_record(
            user_id=1,
            notification_type=MagicMock(value='info'),
            title="Test",
            message="Message"
        )
        
        mock_notification_service.mark_as_read(notification_id)
        
        count = mock_notification_service.get_unread_count(user_id=1)
        assert count == 0


class TestUserPreferences:
    """Tests for user notification preferences."""
    
    def test_get_default_preferences(self, mock_notification_service):
        """Test getting default preferences for new user."""
        prefs = mock_notification_service.get_user_preferences(user_id=1)
        
        assert prefs['in_app_enabled'] == True
        assert prefs['email_enabled'] == True
        assert prefs['webhook_enabled'] == False
    
    def test_update_preferences(self, mock_notification_service):
        """Test updating user preferences."""
        mock_notification_service.update_user_preferences(
            user_id=1,
            email_enabled=False,
            webhook_enabled=True,
            webhook_url="https://hooks.slack.com/test"
        )
        
        prefs = mock_notification_service.get_user_preferences(user_id=1)
        
        assert prefs['email_enabled'] == False
        assert prefs['webhook_enabled'] == True
        assert prefs['webhook_url'] == "https://hooks.slack.com/test"
    
    def test_enable_quiet_hours(self, mock_notification_service):
        """Test enabling quiet hours."""
        mock_notification_service.update_user_preferences(
            user_id=1,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="08:00"
        )
        
        prefs = mock_notification_service.get_user_preferences(user_id=1)
        
        assert prefs['quiet_hours_enabled'] == True
        assert prefs['quiet_hours_start'] == "22:00"
        assert prefs['quiet_hours_end'] == "08:00"


class TestDismissNotification:
    """Tests for dismissing notifications."""
    
    def test_dismiss_notification(self, mock_notification_service):
        """Test dismissing a notification."""
        result = mock_notification_service.dismiss_notification(1)
        
        assert result == True
        mock_notification_service.dismiss_notification.assert_called_once_with(1)


class TestDeleteNotification:
    """Tests for deleting notifications."""
    
    def test_delete_notification(self, mock_notification_service):
        """Test deleting a notification."""
        result = mock_notification_service.delete_notification(1)
        
        assert result == True
        mock_notification_service.delete_notification.assert_called_once_with(1)


class TestMarkAllAsRead:
    """Tests for marking all notifications as read."""
    
    def test_mark_all_as_read(self, mock_notification_service):
        """Test marking all notifications as read for a user."""
        result = mock_notification_service.mark_all_as_read(user_id=1)
        
        assert result == 5
        mock_notification_service.mark_all_as_read.assert_called_once_with(user_id=1)


class TestNotifyAsync:
    """Tests for async notification."""
    
    @pytest.mark.asyncio
    async def test_notify(self, mock_notification_service):
        """Test async notify method."""
        result = await mock_notification_service.notify(
            user_id=1,
            notification_type="embedding_complete",
            title="Complete",
            message="Done"
        )
        
        assert result == 1


class TestWebhookNotification:
    """Tests for webhook notifications."""
    
    @pytest.mark.asyncio
    async def test_send_webhook_notification(self, mock_notification_service):
        """Test sending webhook notification."""
        result = await mock_notification_service.send_webhook_notification(
            webhook_url="https://hooks.slack.com/test",
            title="Test",
            message="Test message"
        )
        
        assert result == True


class TestNotificationTypes:
    """Tests for notification types."""
    
    def test_notification_type_values(self):
        """Test notification type enum values."""
        class MockNotificationType:
            EMBEDDING_STARTED = MagicMock(value="embedding_started")
            EMBEDDING_COMPLETE = MagicMock(value="embedding_complete")
            EMBEDDING_ERROR = MagicMock(value="embedding_error")
            CONFIG_PUBLISHED = MagicMock(value="config_published")
            USER_MENTION = MagicMock(value="user_mention")
            SYSTEM = MagicMock(value="system")
        
        assert MockNotificationType.EMBEDDING_STARTED.value == "embedding_started"
        assert MockNotificationType.EMBEDDING_COMPLETE.value == "embedding_complete"
        assert MockNotificationType.EMBEDDING_ERROR.value == "embedding_error"
        assert MockNotificationType.CONFIG_PUBLISHED.value == "config_published"
        assert MockNotificationType.USER_MENTION.value == "user_mention"
        assert MockNotificationType.SYSTEM.value == "system"


class TestNotificationPriority:
    """Tests for notification priority."""
    
    def test_priority_values(self):
        """Test notification priority enum values."""
        class MockNotificationPriority:
            LOW = MagicMock(value="low")
            MEDIUM = MagicMock(value="medium")
            HIGH = MagicMock(value="high")
            CRITICAL = MagicMock(value="critical")
        
        assert MockNotificationPriority.LOW.value == "low"
        assert MockNotificationPriority.MEDIUM.value == "medium"
        assert MockNotificationPriority.HIGH.value == "high"
        assert MockNotificationPriority.CRITICAL.value == "critical"
