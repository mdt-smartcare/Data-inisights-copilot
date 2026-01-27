import type { User } from '../types';

/**
 * RBAC Permission Utilities
 */

// Role Hierarchy/Definitions (for reference)
// ADMIN: Super Admin
// EDITOR: Editor
// USER: User
// VIEWER: Viewer

export const canManageConnections = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canEditPrompt = (user: User | null): boolean => {
    return user?.role === 'admin' || user?.role === 'editor';
};

export const canExecuteQuery = (user: User | null): boolean => {
    return user?.role === 'admin' || user?.role === 'editor' || user?.role === 'user';
};

export const canViewHistory = (user: User | null): boolean => {
    // All roles can view history/config (read-only for some)
    return !!user;
};

// Helper for UI disabled states
export const isReadOnly = (user: User | null): boolean => {
    return !canEditPrompt(user);
};
