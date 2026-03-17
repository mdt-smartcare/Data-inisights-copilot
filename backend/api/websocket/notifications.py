"""
WebSocket endpoint for real-time notification delivery.
"""
import asyncio
import json
from typing import Dict, Set, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.core.security import decode_keycloak_token
from backend.sqliteDb.db import get_db_service

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()


class NotificationConnectionManager:
    """
    Manages WebSocket connections for real-time notification delivery.
    
    Maps user_id -> set of websocket connections (supports multiple tabs).
    """
    
    def __init__(self):
        # user_id (str) -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Accept a new WebSocket connection for a user."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"Notification WebSocket connected for user {user_id}")
    
    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"Notification WebSocket disconnected for user {user_id}")
    
    async def send_to_user(self, user_id: str, notification_data: dict) -> int:
        """
        Send notification to all connections for a user.
        
        Args:
            user_id: Target user ID
            notification_data: Notification data to send
            
        Returns:
            Number of connections that received the message
        """
        if user_id not in self.active_connections:
            return 0
        
        message = json.dumps({
            "event": "new_notification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notification": notification_data
        })
        
        sent_count = 0
        dead_connections = set()
        
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_text(message)
                sent_count += 1
            except Exception as e:
                logger.debug(f"Failed to send notification to WebSocket: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[user_id].discard(conn)
        
        if dead_connections:
            logger.debug(f"Cleaned up {len(dead_connections)} dead connections for user {user_id}")
        
        return sent_count
    
    async def broadcast_to_user(
        self, 
        user_id: str, 
        event: str, 
        data: Optional[dict] = None
    ) -> int:
        """
        Broadcast a generic event to all connections for a user.
        
        Useful for notification_read, notification_dismissed events.
        
        Args:
            user_id: Target user ID
            event: Event name
            data: Optional event data
            
        Returns:
            Number of connections that received the message
        """
        if user_id not in self.active_connections:
            return 0
        
        message = json.dumps({
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {})
        })
        
        sent_count = 0
        dead_connections = set()
        
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_text(message)
                sent_count += 1
            except Exception as e:
                logger.debug(f"Failed to broadcast to WebSocket: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[user_id].discard(conn)
        
        return sent_count
    
    def get_connection_count(self, user_id: str) -> int:
        """Get number of active connections for a user."""
        return len(self.active_connections.get(user_id, set()))
    
    def get_total_connections(self) -> int:
        """Get total number of active connections across all users."""
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager - singleton instance
_notification_manager: Optional[NotificationConnectionManager] = None


def get_notification_ws_manager() -> NotificationConnectionManager:
    """Get the global notification WebSocket connection manager."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationConnectionManager()
    return _notification_manager


async def verify_token(token: str) -> Optional[dict]:
    """
    Verify Keycloak JWT token for WebSocket authentication.
    
    Returns:
        Decoded token payload if valid, None otherwise.
        user_id is the DATABASE user ID (not Keycloak sub).
    """
    try:
        # Use Keycloak token verification
        if settings.oidc_issuer_url and settings.oidc_client_id:
            logger.debug("WebSocket: Verifying token with Keycloak")
            payload = await decode_keycloak_token(
                token=token,
                issuer_url=settings.oidc_issuer_url,
                client_id=settings.oidc_client_id
            )
            # Extract user info from Keycloak token
            username = payload.get("preferred_username") or payload.get("email")
            external_id = payload.get("sub")  # Keycloak uses 'sub' for user ID
            if not external_id:
                logger.warning("WebSocket: Token missing 'sub' claim")
                return None
            
            # Look up database user ID from external_id (Keycloak sub)
            db_service = get_db_service()
            user_data = db_service.get_user_by_external_id(external_id)
            if not user_data:
                logger.warning(f"WebSocket: No database user found for external_id {external_id} (username: {username})")
                return None
            
            # Return database user ID (what notifications use)
            return {"username": username, "user_id": user_data['id'], "external_id": external_id}
        else:
            # Fallback: no OIDC configured, reject
            logger.warning("WebSocket: OIDC not configured, authentication not available")
            return None
    except Exception as e:
        logger.warning(f"WebSocket: Token verification failed - {type(e).__name__}: {str(e)}")
        return None


@router.websocket("/notifications")
async def notifications_websocket(
    websocket: WebSocket,
    token: str = Query(None)
):
    """
    WebSocket endpoint for real-time notification delivery.
    
    Connect to this endpoint to receive instant notifications when they are created.
    
    Authentication:
        Pass JWT token as query parameter: ?token=<jwt_token>
    
    Messages Received:
        - new_notification: New notification created
          {
              "event": "new_notification",
              "timestamp": "2026-03-09T12:00:00Z",
              "notification": {...}
          }
        
        - notification_read: Notification marked as read (from another tab)
        - notification_dismissed: Notification dismissed
        - all_read: All notifications marked as read
        - pong: Response to ping
        - heartbeat: Server keep-alive (every 30s)
    
    Messages to Send:
        - ping: Keep-alive ping {"action": "ping"}
    """
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"WebSocket connection attempt from {client_host}")
    
    # Verify authentication before accepting connection
    if not token:
        logger.warning(f"WebSocket connection rejected from {client_host}: No token provided")
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    token_data = await verify_token(token)
    if not token_data:
        logger.warning(f"WebSocket connection rejected from {client_host}: Invalid token")
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    user_id = str(token_data.get("user_id", token_data.get("username")))
    
    manager = get_notification_ws_manager()
    await manager.connect(websocket, user_id)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "event": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Keep connection alive
        while True:
            try:
                # Wait for client messages (ping or close)
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30 second heartbeat
                )
                
                # Handle client commands
                try:
                    data = json.loads(message)
                    if data.get("action") == "ping":
                        await websocket.send_json({"event": "pong"})
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Send periodic ping to keep connection alive
                try:
                    await websocket.send_json({
                        "event": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except Exception:
                    # Connection is dead
                    break
                    
    except WebSocketDisconnect:
        logger.info(f"Notification WebSocket client disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"Notification WebSocket error for user {user_id}: {e}")
    finally:
        manager.disconnect(websocket, user_id)
