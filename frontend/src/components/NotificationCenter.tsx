/**
 * NotificationCenter component - Bell icon dropdown with notification list.
 * 
 * Uses NotificationsContext for real-time notification delivery via WebSocket.
 * Shows only unread notifications in the dropdown.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Notification } from '../types/rag';
import { useNotificationsContext } from '../contexts/NotificationsContext';
import { formatRelativeTime } from '../utils/datetime';
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
    const dropdownRef = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();

    // Use the notifications context - WebSocket connection lives at app level
    const {
        notifications,
        unreadCount,
        isLoading,
        isConnected,
        markAsRead,
        markAllAsRead,
        dismiss
    } = useNotificationsContext();

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

    // Handle notification click
    const handleNotificationClick = async (notification: Notification) => {
        if (notification.status === 'unread') {
            try {
                await markAsRead(notification.id);
            } catch (e) {
                console.error('Failed to mark notification as read:', e);
            }
        }

        if (notification.action_url) {
            navigate(notification.action_url);
        }

        onNotificationClick?.(notification);
        setIsOpen(false);
    };

    // Mark all as read
    const handleMarkAllRead = async () => {
        try {
            await markAllAsRead();
        } catch (e) {
            console.error('Failed to mark all as read:', e);
        }
    };

    // Dismiss notification
    const handleDismiss = async (e: React.MouseEvent, notificationId: number) => {
        e.stopPropagation();
        try {
            await dismiss(notificationId);
        } catch (e) {
            console.error('Failed to dismiss notification:', e);
        }
    };

    // Using centralized formatRelativeTime utility

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
                {/* Connection indicator (optional - subtle dot) */}
                {isConnected && (
                    <span 
                        className="notification-center__connected-indicator"
                        title="Real-time updates enabled"
                    />
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
                        {isLoading && notifications.length === 0 ? (
                            <div className="notification-center__loading">Loading...</div>
                        ) : notifications.length === 0 ? (
                            <div className="notification-center__empty">
                                <div className="notification-center__empty-icon">✓</div>
                                <div className="notification-center__empty-text">All caught up!</div>
                            </div>
                        ) : (
                            notifications.map(notification => (
                                <div
                                    key={notification.id}
                                    className="notification-center__item notification-center__item--unread"
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
                    <div className="notification-center__footer">
                        <Link to="/notifications" className="notification-center__view-all" onClick={() => setIsOpen(false)}>
                            View all notifications
                        </Link>
                    </div>
                </div>
            )}
        </div>
    );
};

export default NotificationCenter;
