/**
 * NotificationsContext - Provides notification state at app level
 * 
 * NOTE: Notifications are currently disabled. The backend API is not yet implemented.
 * This context returns a default empty state to prevent API calls.
 */
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import type { UseNotificationsReturn } from '../hooks/useNotifications';

// Default state - notifications disabled
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

export function NotificationsProvider({ children }: NotificationsProviderProps) {
    // Notifications disabled - always return default state
    // TODO: Enable when notification APIs are implemented in backend-modmono
    return (
        <NotificationsContext.Provider value={defaultState}>
            {children}
        </NotificationsContext.Provider>
    );
}

/**
 * Hook to access notification state from context.
 * Safe to use outside NotificationsProvider - returns default state.
 */
export function useNotificationsContext(): UseNotificationsReturn {
    return useContext(NotificationsContext);
}
