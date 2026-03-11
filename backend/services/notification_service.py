"""
Core notification service for multi-channel delivery routing.
Routes notifications to appropriate channels based on user preferences.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json

from backend.models.rag_models import (
    NotificationType, NotificationPriority, NotificationStatus,
    Notification, NotificationCreate, NotificationPreferences
)
from backend.models.schemas import User
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service

logger = get_logger(__name__)


class NotificationService:
    """
    Core service for creating and routing notifications.
    
    Responsibilities:
    - Create notification records
    - Check user preferences
    - Route to appropriate delivery channels
    - Track notification status
    """
    
    def __init__(self):
        self.db = get_db_service()
        
        # Channel services will be injected/created as needed
        self._in_app_service = None
        self._email_service = None
        self._webhook_service = None
    
    async def create_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None,
        channels: Optional[List[str]] = None
    ) -> int:
        """
        Create a new notification and route to appropriate channels.
        
        Args:
            user_id: Target user ID
            notification_type: Type of notification
            title: Notification title
            message: Optional message body
            priority: Notification priority
            action_url: URL for action button
            action_label: Action button label
            related_entity_type: Related entity type (e.g., 'embedding_job')
            related_entity_id: Related entity ID
            channels: Override channel list (default: check user preferences)
            
        Returns:
            Notification ID
        """
        # Get user preferences to determine channels
        if channels is None:
            preferences = self.get_user_preferences(user_id)
            channels = self._get_enabled_channels(preferences, notification_type)
        
        # Create notification record
        notification_id = self._create_notification_record(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            action_url=action_url,
            action_label=action_label,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            channels=channels
        )
        
        # Route to channels
        await self._route_to_channels(notification_id, channels, user_id)
        
        logger.info(f"Created notification {notification_id} for user {user_id}: {title}")
        return notification_id
    
    def _create_notification_record(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: Optional[str],
        priority: NotificationPriority,
        action_url: Optional[str],
        action_label: Optional[str],
        related_entity_type: Optional[str],
        related_entity_id: Optional[int],
        channels: List[str]
    ) -> int:
        """Create notification record in database."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            channels_json = json.dumps(channels)
            
            cursor.execute("""
                INSERT INTO notifications 
                (user_id, type, priority, title, message, action_url, action_label,
                 related_entity_type, related_entity_id, channels, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                notification_type.value if isinstance(notification_type, NotificationType) else notification_type,
                priority.value if isinstance(priority, NotificationPriority) else priority,
                title,
                message,
                action_url,
                action_label,
                related_entity_type,
                related_entity_id,
                channels_json,
                NotificationStatus.UNREAD.value,
                datetime.now(timezone.utc).isoformat()
            ))
            
            conn.commit()
            return cursor.lastrowid
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create notification: {e}")
            raise
        finally:
            conn.close()
    
    async def _route_to_channels(
        self,
        notification_id: int,
        channels: List[str],
        user_id: int
    ) -> None:
        """Route notification to specified channels."""
        notification = self.get_notification(notification_id)
        if not notification:
            return
        
        preferences = self.get_user_preferences(user_id)
        
        for channel in channels:
            try:
                if channel == "in_app":
                    await self._deliver_in_app(notification, user_id)
                elif channel == "email":
                    await self._deliver_email(notification, user_id, preferences)
                elif channel == "webhook":
                    await self._deliver_webhook(notification, preferences)
                    
                # Log successful delivery
                self._log_delivery(notification_id, channel, "sent")
                
            except Exception as e:
                logger.error(f"Failed to deliver notification to {channel}: {e}")
                self._log_delivery(notification_id, channel, "failed", str(e))
    
    async def _deliver_in_app(self, notification: Notification, user_id: int) -> None:
        """Deliver notification via in-app channel using WebSocket."""
        try:
            # Import here to avoid circular imports
            from backend.api.websocket.notifications import get_notification_ws_manager
            
            # Convert notification to dict for WebSocket transmission
            notification_data = {
                "id": notification.id,
                "user_id": notification.user_id,
                "type": notification.type.value if hasattr(notification.type, 'value') else notification.type,
                "priority": notification.priority.value if hasattr(notification.priority, 'value') else notification.priority,
                "title": notification.title,
                "message": notification.message,
                "action_url": notification.action_url,
                "action_label": notification.action_label,
                "status": notification.status.value if hasattr(notification.status, 'value') else notification.status,
                "related_entity_type": notification.related_entity_type,
                "related_entity_id": notification.related_entity_id,
                "channels": notification.channels,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "created_at": notification.created_at.isoformat() if notification.created_at else None
            }
            
            # Push via WebSocket
            ws_manager = get_notification_ws_manager()
            sent_count = await ws_manager.send_to_user(str(user_id), notification_data)
            
            if sent_count > 0:
                logger.debug(f"In-app notification pushed to {sent_count} connections for user {user_id}")
            else:
                logger.debug(f"In-app notification ready for user {user_id} (no active WebSocket connections)")
                
        except Exception as e:
            # Don't fail the notification creation if WebSocket push fails
            # The notification is still in DB and will be fetched on next poll
            logger.warning(f"Failed to push notification via WebSocket: {e}")
    
    async def _deliver_email(
        self,
        notification: Notification,
        user_id: int,
        preferences: NotificationPreferences
    ) -> None:
        """Deliver notification via email."""
        # Email delivery would be handled by EmailNotificationService
        # For now, just log
        logger.info(f"Email notification queued for user {user_id}: {notification.title}")
    
    async def _deliver_webhook(
        self,
        notification: Notification,
        preferences: NotificationPreferences
    ) -> None:
        """Deliver notification via webhook."""
        if not preferences.webhook_url:
            logger.warning("Webhook notification requested but no URL configured")
            return
        
        # Webhook delivery would be handled by WebhookNotificationService
        logger.info(f"Webhook notification queued to {preferences.webhook_url}")
    
    def _log_delivery(
        self,
        notification_id: int,
        channel: str,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Log notification delivery attempt."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO notification_delivery_log 
                (notification_id, channel, status, error_message)
                VALUES (?, ?, ?, ?)
            """, (notification_id, channel, status, error_message))
            
            conn.commit()
        except Exception as e:
            logger.debug(f"Failed to log delivery: {e}")
        finally:
            conn.close()
    
    def _get_enabled_channels(
        self,
        preferences: NotificationPreferences,
        notification_type: NotificationType
    ) -> List[str]:
        """Get list of enabled channels for a notification type."""
        channels = []
        
        # Check if notification type is enabled in preferences
        type_enabled = preferences.notification_types.get(
            notification_type.value if isinstance(notification_type, NotificationType) else notification_type,
            True  # Default to enabled
        )
        
        if not type_enabled:
            return channels
        
        # Check quiet hours
        if preferences.quiet_hours_enabled and self._is_quiet_hours(preferences):
            # During quiet hours, only critical notifications and in-app
            channels.append("in_app")
            return channels
        
        if preferences.in_app_enabled:
            channels.append("in_app")
        
        if preferences.email_enabled:
            channels.append("email")
        
        if preferences.webhook_enabled and preferences.webhook_url:
            channels.append("webhook")
        
        return channels if channels else ["in_app"]  # Always default to in-app
    
    def _is_quiet_hours(self, preferences: NotificationPreferences) -> bool:
        """Check if current time is within quiet hours."""
        if not preferences.quiet_hours_start or not preferences.quiet_hours_end:
            return False
        
        try:
            now = datetime.now(timezone.utc).strftime("%H:%M")
            start = preferences.quiet_hours_start
            end = preferences.quiet_hours_end
            
            if start <= end:
                return start <= now <= end
            else:
                # Quiet hours span midnight
                return now >= start or now <= end
        except:
            return False
    
    def get_notification(self, notification_id: int) -> Optional[Notification]:
        """Get a notification by ID."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            data = dict(row)
            data['channels'] = json.loads(data.get('channels', '["in_app"]'))
            
            return Notification(
                id=data['id'],
                user_id=data['user_id'],
                type=NotificationType(data['type']),
                priority=NotificationPriority(data['priority']),
                title=data['title'],
                message=data.get('message'),
                action_url=data.get('action_url'),
                action_label=data.get('action_label'),
                status=NotificationStatus(data['status']),
                related_entity_type=data.get('related_entity_type'),
                related_entity_id=data.get('related_entity_id'),
                channels=data['channels'],
                read_at=datetime.fromisoformat(data['read_at']) if data.get('read_at') else None,
                created_at=datetime.fromisoformat(data['created_at'])
            )
        except Exception as e:
            logger.error(f"Failed to get notification: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_notifications(
        self,
        user_id: int,
        status: Optional[NotificationStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """Get notifications for a user."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT id FROM notifications WHERE user_id = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            notification_ids = [row['id'] for row in cursor.fetchall()]
            
        finally:
            conn.close()
        
        return [self.get_notification(nid) for nid in notification_ids if self.get_notification(nid)]
    
    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND status = ?",
                (user_id, NotificationStatus.UNREAD.value)
            )
            return cursor.fetchone()['count']
        finally:
            conn.close()
    
    def get_notification_count(
        self, 
        user_id: int, 
        status: Optional[NotificationStatus] = None
    ) -> int:
        """Get total count of notifications for a user, optionally filtered by status."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT COUNT(*) as count FROM notifications WHERE user_id = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            cursor.execute(query, params)
            return cursor.fetchone()['count']
        finally:
            conn.close()
    
    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE notifications 
                SET status = ?, read_at = ?
                WHERE id = ? AND user_id = ?
            """, (
                NotificationStatus.READ.value,
                datetime.now(timezone.utc).isoformat(),
                notification_id,
                user_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to mark notification as read: {e}")
            return False
        finally:
            conn.close()
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all user's notifications as read."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE notifications 
                SET status = ?, read_at = ?
                WHERE user_id = ? AND status = ?
            """, (
                NotificationStatus.READ.value,
                datetime.now(timezone.utc).isoformat(),
                user_id,
                NotificationStatus.UNREAD.value
            ))
            
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
    
    def dismiss_notification(self, notification_id: int, user_id: int) -> bool:
        """Dismiss a notification."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE notifications 
                SET status = ?, dismissed_at = ?
                WHERE id = ? AND user_id = ?
            """, (
                NotificationStatus.DISMISSED.value,
                datetime.now(timezone.utc).isoformat(),
                notification_id,
                user_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_user_preferences(self, user_id: int) -> NotificationPreferences:
        """Get notification preferences for a user."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM notification_preferences WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                # Return defaults if no preferences set
                return NotificationPreferences()
            
            data = dict(row)
            
            return NotificationPreferences(
                in_app_enabled=bool(data.get('in_app_enabled', 1)),
                email_enabled=bool(data.get('email_enabled', 1)),
                webhook_enabled=bool(data.get('webhook_enabled', 0)),
                webhook_url=data.get('webhook_url'),
                webhook_format=data.get('webhook_format', 'slack'),
                notification_types=json.loads(data.get('notification_types', '{}')),
                quiet_hours_enabled=bool(data.get('quiet_hours_enabled', 0)),
                quiet_hours_start=data.get('quiet_hours_start'),
                quiet_hours_end=data.get('quiet_hours_end'),
                quiet_hours_timezone=data.get('quiet_hours_timezone', 'UTC')
            )
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return NotificationPreferences()
        finally:
            conn.close()
    
    def update_user_preferences(
        self,
        user_id: int,
        preferences: Dict[str, Any]
    ) -> bool:
        """Update notification preferences for a user."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if preferences exist
            cursor.execute(
                "SELECT id FROM notification_preferences WHERE user_id = ?",
                (user_id,)
            )
            exists = cursor.fetchone() is not None
            
            # Convert notification_types to JSON if present
            if 'notification_types' in preferences:
                preferences['notification_types'] = json.dumps(preferences['notification_types'])
            
            # Convert booleans to integers
            for key in ['in_app_enabled', 'email_enabled', 'webhook_enabled', 'quiet_hours_enabled']:
                if key in preferences:
                    preferences[key] = 1 if preferences[key] else 0
            
            if exists:
                # Update
                fields = [f"{k} = ?" for k in preferences.keys()]
                values = list(preferences.values()) + [datetime.now(timezone.utc).isoformat(), user_id]
                
                cursor.execute(
                    f"UPDATE notification_preferences SET {', '.join(fields)}, updated_at = ? WHERE user_id = ?",
                    values
                )
            else:
                # Insert
                preferences['user_id'] = user_id
                fields = list(preferences.keys())
                placeholders = ['?' for _ in fields]
                
                cursor.execute(
                    f"INSERT INTO notification_preferences ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                    list(preferences.values())
                )
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update preferences: {e}")
            return False
        finally:
            conn.close()
    
    async def broadcast_notification_read(self, notification_id: int, user_id: int) -> None:
        """Broadcast notification_read event to all user's WebSocket connections."""
        try:
            from backend.api.websocket.notifications import get_notification_ws_manager
            ws_manager = get_notification_ws_manager()
            await ws_manager.broadcast_to_user(
                str(user_id), 
                "notification_read", 
                {"notification_id": notification_id}
            )
        except Exception as e:
            logger.debug(f"Failed to broadcast notification_read: {e}")
    
    async def broadcast_all_read(self, user_id: int) -> None:
        """Broadcast all_read event to all user's WebSocket connections."""
        try:
            from backend.api.websocket.notifications import get_notification_ws_manager
            ws_manager = get_notification_ws_manager()
            await ws_manager.broadcast_to_user(str(user_id), "all_read")
        except Exception as e:
            logger.debug(f"Failed to broadcast all_read: {e}")
    
    async def broadcast_notification_dismissed(self, notification_id: int, user_id: int) -> None:
        """Broadcast notification_dismissed event to all user's WebSocket connections."""
        try:
            from backend.api.websocket.notifications import get_notification_ws_manager
            ws_manager = get_notification_ws_manager()
            await ws_manager.broadcast_to_user(
                str(user_id), 
                "notification_dismissed", 
                {"notification_id": notification_id}
            )
        except Exception as e:
            logger.debug(f"Failed to broadcast notification_dismissed: {e}")


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create the notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
