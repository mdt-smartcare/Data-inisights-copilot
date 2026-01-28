/**
 * NotificationCenter component - Bell icon dropdown with notification list.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { Notification } from '../types/rag';
import {
    getNotifications,
    getUnreadNotificationCount,
    markNotificationAsRead,
    markAllNotificationsAsRead,
    dismissNotification
} from '../services/api';
import './NotificationCenter.css';

interface NotificationCenterProps {
    onNotificationClick?: (notification: Notification) => void;
}

const NOTIFICATION_ICONS: Record<string, string> = {
    embedding_started: '🚀',
    embedding_progress: '⚙️',
    embedding_complete: '✅',
    embedding_failed: '❌',
    embedding_cancelled: '⏹️',
    config_published: '📢',
    config_rolled_back: '↩️',
    schema_change_detected: '🔄',
};

const PRIORITY_COLORS: Record<string, string> = {
    low: '#94a3b8',
    medium: '#3b82f6',
    high: '#f59e0b',
    critical: '#ef4444',
};

export const NotificationCenter: React.FC<NotificationCenterProps> = ({
    onNotificationClick,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Fetch notifications and unread count
    const fetchNotifications = useCallback(async () => {
        try {
            setLoading(true);
            const [notifs, count] = await Promise.all([
                getNotifications({ limit: 20 }),
                getUnreadNotificationCount(),
            ]);
            setNotifications(notifs);
            setUnreadCount(count.count);
        } catch (e) {
            console.error('Failed to fetch notifications:', e);
        } finally {
            setLoading(false);
        }
    }, []);

    // Handle click outside to close dropdown
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isOpen]);

    // Fetch on mount and periodically
    useEffect(() => {
        fetchNotifications();
        const interval = setInterval(fetchNotifications, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, [fetchNotifications]);

    // Handle notification click
    const handleNotificationClick = async (notification: Notification) => {
        if (notification.status === 'unread') {
            try {
                await markNotificationAsRead(notification.id);
                setNotifications(prev =>
                    prev.map(n => n.id === notification.id ? { ...n, status: 'read' } : n)
                );
                setUnreadCount(prev => Math.max(0, prev - 1));
            } catch (e) {
                console.error('Failed to mark notification as read:', e);
            }
        }

        if (notification.action_url) {
            window.location.href = notification.action_url;
        }

        onNotificationClick?.(notification);
        setIsOpen(false);
    };

    // Mark all as read
    const handleMarkAllRead = async () => {
        try {
            await markAllNotificationsAsRead();
            setNotifications(prev => prev.map(n => ({ ...n, status: 'read' })));
            setUnreadCount(0);
        } catch (e) {
            console.error('Failed to mark all as read:', e);
        }
    };

    // Dismiss notification
    const handleDismiss = async (e: React.MouseEvent, notificationId: number) => {
        e.stopPropagation();
        try {
            await dismissNotification(notificationId);
            setNotifications(prev => prev.filter(n => n.id !== notificationId));
            // Update unread count if dismissed notification was unread
            const dismissed = notifications.find(n => n.id === notificationId);
            if (dismissed?.status === 'unread') {
                setUnreadCount(prev => Math.max(0, prev - 1));
            }
        } catch (e) {
            console.error('Failed to dismiss notification:', e);
        }
    };

    // Format relative time
    const formatRelativeTime = (dateString: string): string => {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    };

    return (
        <div className="notification-center" ref={dropdownRef}>
            {/* Bell icon button */}
            <button
                className="notification-center__trigger"
                onClick={() => setIsOpen(!isOpen)}
                aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
            >
                <svg
                    className="notification-center__bell-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                >
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {unreadCount > 0 && (
                    <span className="notification-center__badge">
                        {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                )}
            </button>

            {/* Dropdown */}
            {isOpen && (
                <div className="notification-center__dropdown">
                    {/* Header */}
                    <div className="notification-center__header">
                        <h3 className="notification-center__title">Notifications</h3>
                        {unreadCount > 0 && (
                            <button
                                className="notification-center__mark-all-btn"
                                onClick={handleMarkAllRead}
                            >
                                Mark all read
                            </button>
                        )}
                    </div>

                    {/* Notification list */}
                    <div className="notification-center__list">
                        {loading && notifications.length === 0 ? (
                            <div className="notification-center__loading">Loading...</div>
                        ) : notifications.length === 0 ? (
                            <div className="notification-center__empty">
                                <div className="notification-center__empty-icon">🔔</div>
                                <div className="notification-center__empty-text">No notifications</div>
                            </div>
                        ) : (
                            notifications.map(notification => (
                                <div
                                    key={notification.id}
                                    className={`notification-center__item ${notification.status === 'unread' ? 'notification-center__item--unread' : ''
                                        }`}
                                    onClick={() => handleNotificationClick(notification)}
                                >
                                    <div
                                        className="notification-center__item-icon"
                                        style={{
                                            borderColor: PRIORITY_COLORS[notification.priority] || PRIORITY_COLORS.medium
                                        }}
                                    >
                                        {NOTIFICATION_ICONS[notification.type] || '📬'}
                                    </div>
                                    <div className="notification-center__item-content">
                                        <div className="notification-center__item-title">
                                            {notification.title}
                                        </div>
                                        {notification.message && (
                                            <div className="notification-center__item-message">
                                                {notification.message}
                                            </div>
                                        )}
                                        <div className="notification-center__item-time">
                                            {formatRelativeTime(notification.created_at)}
                                        </div>
                                    </div>
                                    <button
                                        className="notification-center__item-dismiss"
                                        onClick={(e) => handleDismiss(e, notification.id)}
                                        aria-label="Dismiss notification"
                                    >
                                        ×
                                    </button>
                                </div>
                            ))
                        )}
                    </div>

                    {/* Footer */}
                    {notifications.length > 0 && (
                        <div className="notification-center__footer">
                            <a href="/notifications" className="notification-center__view-all">
                                View all notifications
                            </a>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default NotificationCenter;
