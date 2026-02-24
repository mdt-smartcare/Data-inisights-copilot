import type { User } from '../types';

/**
 * RBAC Permission Utilities
 * 
 * Role Hierarchy (descending privilege):
 * SUPER_ADMIN > EDITOR > USER > VIEWER
 */

export const ROLE_HIERARCHY = ['admin', 'user'] as const;
export type UserRole = typeof ROLE_HIERARCHY[number];

/**
 * Check if user's role is at least the required level.
 */
export const roleAtLeast = (userRole: string | undefined, requiredRole: UserRole): boolean => {
    if (!userRole) return false;
    const userIdx = ROLE_HIERARCHY.indexOf(userRole as UserRole);
    const reqIdx = ROLE_HIERARCHY.indexOf(requiredRole);
    if (userIdx === -1 || reqIdx === -1) return false;
    return userIdx <= reqIdx;
};

// ============================================
// Permission Checks
// ============================================

export const canManageUsers = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canViewAllAuditLogs = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canManageConnections = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canEditConfig = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canEditPrompt = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canPublishPrompt = (user: User | null): boolean => {
    // Only Super Admin can publish
    return user?.role === 'admin';
};

// Only Super Admin can rollback
export const canRollback = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canExecuteQuery = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'user');
};

// Editor+ can view history/config/insights
export const canViewHistory = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canViewConfig = (user: User | null): boolean => {
    return user?.role === 'admin';
};

export const canViewInsights = (user: User | null): boolean => {
    return user?.role === 'admin';
};

// Helper for UI disabled states
export const isReadOnly = (user: User | null): boolean => {
    return !canEditPrompt(user);
};

// Role display name mapping
export const ROLE_DISPLAY_NAMES: Record<UserRole, string> = {
    admin: 'Admin',
    user: 'User',
};

export const getRoleDisplayName = (role: string | undefined): string => {
    if (!role) return 'Unknown';
    return ROLE_DISPLAY_NAMES[role as UserRole] || role;
};
