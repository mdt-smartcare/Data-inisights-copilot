import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ChatHeader from '../components/chat/ChatHeader';
import { getNotifications, markNotificationAsRead, dismissNotification, markAllNotificationsAsRead } from '../services/api';
import type { Notification } from '../types/rag';
import { useToast } from '../components/Toast';

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

export default function NotificationsPage() {
    const navigate = useNavigate();
    const { success, error } = useToast();
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [filter, setFilter] = useState<string>('all');

    const fetchNotifications = useCallback(async () => {
        try {
            setIsLoading(true);
            const params: any = { limit: 100 };
            if (filter !== 'all') {
                params.status_filter = filter;
            }
            const data = await getNotifications(params);
            setNotifications(data);
        } catch (err) {
            console.error('Failed to fetch notifications', err);
            error('Failed to load notifications');
        } finally {
            setIsLoading(false);
        }
    }, [filter, error]);

    useEffect(() => {
        fetchNotifications();
    }, [fetchNotifications]);

    const handleMarkAsRead = async (id: number) => {
        try {
            await markNotificationAsRead(id);
            setNotifications(prev => prev.map(n => n.id === id ? { ...n, status: 'read' } : n));
        } catch (err) {
            error('Failed to mark as read');
        }
    };

    const handleDismiss = async (id: number) => {
        try {
            await dismissNotification(id);
            setNotifications(prev => prev.filter(n => n.id !== id));
            success('Notification dismissed');
        } catch (err) {
            error('Failed to dismiss notification');
        }
    };

    const handleMarkAllRead = async () => {
        try {
            await markAllNotificationsAsRead();
            setNotifications(prev => prev.map(n => ({ ...n, status: 'read' })));
            success('All notifications marked as read');
        } catch (err) {
            error('Failed to mark all as read');
        }
    };

    const formatTime = (dateString: string) => {
        const date = new Date(dateString);
        return date.toLocaleString();
    };

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title="All Notifications" />

            <main className="flex-1 overflow-y-auto p-4 md:p-8">
                <div className="max-w-4xl mx-auto">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-4">
                            <h2 className="text-2xl font-bold text-gray-900">Notifications</h2>
                            <div className="flex bg-white rounded-lg p-1 shadow-sm border border-gray-200">
                                {['all', 'unread', 'read'].map((f) => (
                                    <button
                                        key={f}
                                        onClick={() => setFilter(f)}
                                        className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${filter === f
                                            ? 'bg-blue-100 text-blue-700'
                                            : 'text-gray-600 hover:bg-gray-100'
                                            }`}
                                    >
                                        {f.charAt(0).toUpperCase() + f.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <button
                            onClick={handleMarkAllRead}
                            className="text-sm font-medium text-blue-600 hover:text-blue-700"
                        >
                            Mark all as read
                        </button>
                    </div>

                    {isLoading ? (
                        <div className="flex justify-center py-12">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        </div>
                    ) : notifications.length === 0 ? (
                        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
                            <div className="text-4xl mb-4">📭</div>
                            <h3 className="text-lg font-medium text-gray-900 mb-1">No notifications found</h3>
                            <p className="text-gray-500">You're all caught up!</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {notifications.map((notification) => (
                                <div
                                    key={notification.id}
                                    className={`bg-white rounded-xl border p-4 shadow-sm transition-all hover:shadow-md ${notification.status === 'unread' ? 'border-blue-200 bg-blue-50/30' : 'border-gray-200'
                                        }`}
                                >
                                    <div className="flex gap-4">
                                        <div
                                            className="w-12 h-12 rounded-full border-2 flex items-center justify-center text-xl shrink-0"
                                            style={{ borderColor: PRIORITY_COLORS[notification.priority] || '#3b82f6', backgroundColor: 'white' }}
                                        >
                                            {NOTIFICATION_ICONS[notification.type] || '📬'}
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-start justify-between gap-2">
                                                <h4 className="text-base font-semibold text-gray-900 truncate">
                                                    {notification.title}
                                                </h4>
                                                <span className="text-xs text-gray-500 whitespace-nowrap">
                                                    {formatTime(notification.created_at)}
                                                </span>
                                            </div>

                                            <p className="text-sm text-gray-600 mt-1 mb-3">
                                                {notification.message}
                                            </p>

                                            <div className="flex items-center gap-4">
                                                {notification.action_url && (
                                                    <button
                                                        onClick={() => navigate(notification.action_url!)}
                                                        className="text-xs font-semibold text-blue-600 hover:text-blue-700 bg-blue-50 px-3 py-1.5 rounded-lg transition-colors"
                                                    >
                                                        {notification.action_label || 'View Details'}
                                                    </button>
                                                )}

                                                {notification.status === 'unread' && (
                                                    <button
                                                        onClick={() => handleMarkAsRead(notification.id)}
                                                        className="text-xs font-medium text-gray-500 hover:text-gray-700"
                                                    >
                                                        Mark as read
                                                    </button>
                                                )}

                                                <button
                                                    onClick={() => handleDismiss(notification.id)}
                                                    className="text-xs font-medium text-gray-400 hover:text-red-500"
                                                >
                                                    Dismiss
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
