/**
 * useNotifications hook - Manages notifications with WebSocket real-time updates.
 *
 * Features:
 * - WebSocket connection for instant notification delivery
 * - Automatic reconnection with exponential backoff
 * - Fallback to polling if WebSocket fails
 * - Cross-tab synchronization (read/dismiss events)
 * - Only shows unread notifications in dropdown
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import type {
    Notification,
    WebSocketNotificationMessage
} from '../types/rag';
import {
    getNotifications,
    getUnreadNotificationCount,
    markNotificationAsRead,
    markAllNotificationsAsRead,
    dismissNotification as dismissNotificationApi
} from '../services/api';
import { oidcService } from '../services/oidcService';

interface UseNotificationsOptions {
    /** Only fetch unread notifications (for dropdown). Default: true */
    unreadOnly?: boolean;
    /** Maximum notifications to fetch. Default: 20 */
    limit?: number;
    /** Enable WebSocket connection. Default: true */
    enableWebSocket?: boolean;
    /** Polling interval in ms when WebSocket is unavailable. Default: 30000 (30s) */
    pollingInterval?: number;
}

export interface UseNotificationsReturn {
    notifications: Notification[];
    unreadCount: number;
    isLoading: boolean;
    isConnected: boolean;
    error: string | null;
    markAsRead: (notificationId: number) => Promise<void>;
    markAllAsRead: () => Promise<void>;
    dismiss: (notificationId: number) => Promise<void>;
    refresh: () => Promise<void>;
}

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
    const {
        unreadOnly = true,
        limit = 20,
        enableWebSocket = true,
        pollingInterval = 30000
    } = options;

    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const wsRef = useRef<WebSocket | null>(null);
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const reconnectAttempts = useRef(0);
    const maxReconnectAttempts = 5;
    const isConnectingRef = useRef(false); // Guard against StrictMode double-mount
    
    // Ref to track current notifications for use in callbacks without causing re-renders
    const notificationsRef = useRef<Notification[]>([]);
    notificationsRef.current = notifications;
    
    // Refs for stable function references
    const optionsRef = useRef({ limit, unreadOnly, pollingInterval, enableWebSocket });
    optionsRef.current = { limit, unreadOnly, pollingInterval, enableWebSocket };

    // Fetch notifications from API
    const fetchNotifications = useCallback(async () => {
        try {
            const { limit: lim, unreadOnly: unread } = optionsRef.current;
            const params: { limit: number; status_filter?: string } = { limit: lim };
            if (unread) {
                params.status_filter = 'unread';
            }

            const [notifs, countResult] = await Promise.all([
                getNotifications(params),
                getUnreadNotificationCount()
            ]);

            setNotifications(notifs);
            setUnreadCount(countResult.count);
            setError(null);
        } catch (e) {
            console.error('Failed to fetch notifications:', e);
            setError('Failed to load notifications');
        } finally {
            setIsLoading(false);
        }
    }, []); // No dependencies - uses refs

    // Stop polling
    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    // Start polling fallback
    const startPolling = useCallback(() => {
        stopPolling();
        pollingRef.current = setInterval(fetchNotifications, optionsRef.current.pollingInterval);
    }, [fetchNotifications, stopPolling]);

    // Handle incoming WebSocket message
    const handleWebSocketMessage = useCallback((event: MessageEvent) => {
        try {
            const data = JSON.parse(event.data) as WebSocketNotificationMessage;
            const { limit: lim, unreadOnly: unread } = optionsRef.current;

            switch (data.event) {
                case 'new_notification': {
                    const newNotif = data.notification;
                    // Add to list if showing unread only and notification is unread
                    // Or add to list if showing all notifications
                    if (!unread || newNotif.status === 'unread') {
                        setNotifications(prev => [newNotif, ...prev].slice(0, lim));
                    }
                    if (newNotif.status === 'unread') {
                        setUnreadCount(prev => prev + 1);
                    }
                    break;
                }

                case 'notification_read': {
                    const readId = data.notification_id;
                    if (unread) {
                        // Remove from list when showing unread only
                        setNotifications(prev => prev.filter(n => n.id !== readId));
                    } else {
                        // Update status when showing all
                        setNotifications(prev =>
                            prev.map(n => n.id === readId ? { ...n, status: 'read' as const } : n)
                        );
                    }
                    setUnreadCount(prev => Math.max(0, prev - 1));
                    break;
                }

                case 'notification_dismissed': {
                    const dismissedId = data.notification_id;
                    // Use ref to check if notification was unread without adding to dependencies
                    const dismissed = notificationsRef.current.find(n => n.id === dismissedId);
                    setNotifications(prev => prev.filter(n => n.id !== dismissedId));
                    if (dismissed?.status === 'unread') {
                        setUnreadCount(prev => Math.max(0, prev - 1));
                    }
                    break;
                }

                case 'all_read': {
                    if (unread) {
                        // Clear all when showing unread only
                        setNotifications([]);
                    } else {
                        // Update all to read when showing all
                        setNotifications(prev => prev.map(n => ({ ...n, status: 'read' as const })));
                    }
                    setUnreadCount(0);
                    break;
                }

                case 'connected':
                    console.log('Notification WebSocket connected');
                    break;

                case 'heartbeat':
                case 'pong':
                    // Keep-alive messages, no action needed
                    break;

                default:
                    console.debug('Unknown WebSocket event:', data);
            }
        } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
        }
    }, []); // No dependencies - uses refs

    // Connect to WebSocket
    const connectWebSocket = useCallback(async () => {
        // Guard against duplicate connections (React StrictMode, rapid re-renders)
        if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.OPEN) {
            return false;
        }
        isConnectingRef.current = true;
        
        const token = await oidcService.getAccessToken();
        
        if (!token) {
            console.warn('No auth token for WebSocket, falling back to polling');
            isConnectingRef.current = false;
            startPolling();
            return false;
        }

        // Use same-origin WebSocket connection (proxied by NGINX in production)
        // Token in query string is acceptable for WebSocket (not logged in browser history)
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws/notifications?token=${encodeURIComponent(token)}`;

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('Notification WebSocket connected');
                isConnectingRef.current = false;
                setIsConnected(true);
                setError(null);
                stopPolling();
                reconnectAttempts.current = 0;
            };

            ws.onmessage = handleWebSocketMessage;

            ws.onerror = (event) => {
                console.error('Notification WebSocket error:', event);
                setIsConnected(false);
            };

            ws.onclose = (event) => {
                console.log('Notification WebSocket closed:', event.code, event.reason);
                setIsConnected(false);
                wsRef.current = null;
                isConnectingRef.current = false; // Allow reconnection

                // Don't retry on authentication errors - fall back to polling
                if (event.code === 4001) {
                    console.warn('WebSocket auth failed, falling back to polling');
                    startPolling();
                    return;
                }

                // Attempt reconnection with exponential backoff for other errors
                if (reconnectAttempts.current < maxReconnectAttempts) {
                    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
                    reconnectAttempts.current++;
                    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`);
                    
                    reconnectTimeoutRef.current = setTimeout(() => {
                        connectWebSocket().catch(() => startPolling());
                    }, delay);
                } else {
                    console.warn('Max reconnection attempts reached, falling back to polling');
                    startPolling();
                }
            };

            return true;
        } catch (e) {
            console.error('Failed to create WebSocket:', e);
            isConnectingRef.current = false;
            startPolling();
            return false;
        }
    }, [handleWebSocketMessage, startPolling, stopPolling]);

    // Mark notification as read
    const markAsRead = useCallback(async (notificationId: number) => {
        try {
            await markNotificationAsRead(notificationId);
            // Optimistic update (WebSocket will also send event, but this is faster)
            const { unreadOnly: unread } = optionsRef.current;
            if (unread) {
                setNotifications(prev => prev.filter(n => n.id !== notificationId));
            } else {
                setNotifications(prev =>
                    prev.map(n => n.id === notificationId ? { ...n, status: 'read' as const } : n)
                );
            }
            setUnreadCount(prev => Math.max(0, prev - 1));
        } catch (e) {
            console.error('Failed to mark notification as read:', e);
            throw e;
        }
    }, []); // No dependencies - uses refs

    // Mark all notifications as read
    const markAllAsRead = useCallback(async () => {
        try {
            await markAllNotificationsAsRead();
            // Optimistic update
            const { unreadOnly: unread } = optionsRef.current;
            if (unread) {
                setNotifications([]);
            } else {
                setNotifications(prev => prev.map(n => ({ ...n, status: 'read' as const })));
            }
            setUnreadCount(0);
        } catch (e) {
            console.error('Failed to mark all as read:', e);
            throw e;
        }
    }, []); // No dependencies - uses refs

    // Dismiss notification
    const dismiss = useCallback(async (notificationId: number) => {
        try {
            // Use ref to find notification without adding to dependencies
            const notification = notificationsRef.current.find(n => n.id === notificationId);
            
            await dismissNotificationApi(notificationId);
            
            // Optimistic update
            setNotifications(prev => prev.filter(n => n.id !== notificationId));
            if (notification?.status === 'unread') {
                setUnreadCount(prev => Math.max(0, prev - 1));
            }
        } catch (e) {
            console.error('Failed to dismiss notification:', e);
            throw e;
        }
    }, []);

    // Setup WebSocket connection and initial fetch - runs once on mount
    useEffect(() => {
        // Initial fetch
        fetchNotifications();

        // Setup WebSocket or polling
        if (optionsRef.current.enableWebSocket) {
            // connectWebSocket is now async
            connectWebSocket().catch(err => {
                console.error('WebSocket connection error:', err);
                startPolling();
            });
        } else {
            startPolling();
        }

        // Cleanup
        return () => {
            stopPolling();
            isConnectingRef.current = false;
            
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
            
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Empty deps - run only once on mount, callbacks use refs

    return {
        notifications,
        unreadCount,
        isLoading,
        isConnected,
        error,
        markAsRead,
        markAllAsRead,
        dismiss,
        refresh: fetchNotifications
    };
}

export default useNotifications;
