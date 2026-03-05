import type { User } from '../types';

/**
 * RBAC Permission Utilities
 * 
 * Role Hierarchy (descending privilege):
 * SUPER_ADMIN > ADMIN > USER
 */

export const ROLE_HIERARCHY = ['super_admin', 'admin', 'user'] as const;
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

/**
 * Check if user is a super admin.
 */
export const isSuperAdmin = (user: User | null): boolean => {
    return user?.role === 'super_admin';
};

/**
 * Check if user is at least an admin (includes super_admin).
 */
export const isAtLeastAdmin = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

// ============================================
// Permission Checks
// ============================================

export const canManageUsers = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canViewAllAuditLogs = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canManageConnections = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canEditConfig = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canEditPrompt = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

export const canPublishPrompt = (user: User | null): boolean => {
    // Admins can publish their own agents
    return isAtLeastAdmin(user);
};

// Admins can rollback their own agents
export const canRollback = (user: User | null): boolean => {
    return isAtLeastAdmin(user);
};

export const canExecuteQuery = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'user');
};

export const canViewConfig = (user: User | null): boolean => {
    return roleAtLeast(user?.role, 'admin');
};

// Helper for UI disabled states
export const isReadOnly = (user: User | null): boolean => {
    return !canEditPrompt(user);
};

// Role display name mapping
export const ROLE_DISPLAY_NAMES: Record<UserRole, string> = {
    super_admin: 'Super Admin',
    admin: 'Admin',
    user: 'User',
};

export const getRoleDisplayName = (role: string | undefined): string => {
    if (!role) return 'Unknown';
    return ROLE_DISPLAY_NAMES[role as UserRole] || role;
};
