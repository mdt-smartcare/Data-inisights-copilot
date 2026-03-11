/**
 * NotificationsContext - Provides notification state at app level
 * 
 * This context holds the WebSocket connection and notification state,
 * ensuring the connection persists across page navigations.
 */
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { useNotifications } from '../hooks/useNotifications';
import type { UseNotificationsReturn } from '../hooks/useNotifications';
import { useAuth } from './AuthContext';

// Default state when user is not authenticated
const defaultState: UseNotificationsReturn = {
    notifications: [],
    unreadCount: 0,
    isLoading: false,
    isConnected: false,
    error: null,
    markAsRead: async () => {},
    markAllAsRead: async () => {},
    dismiss: async () => {},
    refresh: async () => {}
};

const NotificationsContext = createContext<UseNotificationsReturn>(defaultState);

interface NotificationsProviderProps {
    children: ReactNode;
}

// Internal component that uses the hook when authenticated
function AuthenticatedNotifications({ children }: { children: ReactNode }) {
    const notificationsState = useNotifications({
        unreadOnly: true,
        limit: 20,
        enableWebSocket: true,
        pollingInterval: 30000
    });

    return (
        <NotificationsContext.Provider value={notificationsState}>
            {children}
        </NotificationsContext.Provider>
    );
}

export function NotificationsProvider({ children }: NotificationsProviderProps) {
    const { isAuthenticated, isLoading } = useAuth();

    // Don't initialize notifications until auth is resolved and user is authenticated
    if (isLoading || !isAuthenticated) {
        return (
            <NotificationsContext.Provider value={defaultState}>
                {children}
            </NotificationsContext.Provider>
        );
    }

    return (
        <AuthenticatedNotifications>
            {children}
        </AuthenticatedNotifications>
    );
}

/**
 * Hook to access notification state from context.
 * Safe to use outside NotificationsProvider - returns default state.
 */
export function useNotificationsContext(): UseNotificationsReturn {
    return useContext(NotificationsContext);
}
