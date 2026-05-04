import React from 'react';
import { getRoleDisplayName } from '../utils/permissions';
import { formatDateTime } from '../utils/datetime';
import Pagination from './Pagination';

/**
 * Base user type with common fields shared across all user representations
 */
export interface BaseUser {
    id: string;
    username: string;
    email?: string;
    full_name?: string;
    role: string;
    is_active: boolean;
}

/**
 * Pagination configuration for server-side pagination
 */
export interface PaginationConfig {
    /** Current page number (1-indexed) */
    page: number;
    /** Number of items per page */
    pageSize: number;
    /** Total number of items across all pages */
    totalItems: number;
    /** Total number of pages */
    totalPages: number;
    /** Callback when page changes */
    onPageChange: (page: number) => void;
}

export interface UserTableProps<T extends BaseUser> {
    /** Array of users to display */
    users: T[];
    /** Whether the table is loading */
    loading?: boolean;
    /** Field name to use for the date column (e.g., 'created_at' or 'granted_at') */
    dateField?: keyof T;
    /** Label for the date column header */
    dateColumnLabel?: string;
    /** Render function for action buttons - receives user and returns JSX */
    renderActions?: (user: T) => React.ReactNode;
    /** Empty state message */
    emptyMessage?: string;
    /** Empty state sub-message */
    emptySubMessage?: string;
    /** Custom empty state icon */
    emptyIcon?: React.ReactNode;
    /** Whether to show the super_admin role styling (red badge) */
    showSuperAdminRole?: boolean;
    /** Pagination configuration - if provided, pagination controls are shown */
    pagination?: PaginationConfig;
}

/**
 * Default empty state icon (users group)
 */
const DefaultEmptyIcon = () => (
    <svg className="w-16 h-16 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
);

/**
 * Reusable user table component for displaying lists of users with consistent styling.
 * 
 * @example
 * // System users with full action buttons
 * <UserTable
 *   users={users}
 *   loading={loading}
 *   dateField="created_at"
 *   dateColumnLabel="Created"
 *   showSuperAdminRole
 *   renderActions={(user) => (
 *     <button onClick={() => handleEdit(user)}>Edit</button>
 *   )}
 * />
 * 
 * @example
 * // Agent users with remove button only
 * <UserTable
 *   users={agentUsers}
 *   loading={loading}
 *   dateField="granted_at"
 *   dateColumnLabel="Granted"
 *   emptyMessage="No users assigned"
 *   renderActions={(user) => (
 *     <button onClick={() => handleRemove(user)}>Remove</button>
 *   )}
 * />
 */
function UserTable<T extends BaseUser>({
    users,
    loading = false,
    dateField,
    dateColumnLabel = 'Created',
    renderActions,
    emptyMessage = 'No users found',
    emptySubMessage,
    emptyIcon,
    showSuperAdminRole = false,
    pagination,
}: UserTableProps<T>) {
    
    /**
     * Get the role badge color classes
     */
    const getRoleBadgeClasses = (role: string): string => {
        if (showSuperAdminRole && role === 'super_admin') {
            return 'bg-red-100 text-red-800';
        }
        switch (role) {
            case 'admin':
                return 'bg-purple-100 text-purple-800';
            case 'user':
                return 'bg-yellow-100 text-yellow-800';
            default:
                return 'bg-gray-100 text-gray-800';
        }
    };

    /**
     * Get user initials for avatar
     */
    const getInitials = (user: T): string => {
        return (user.full_name || user.username || user.email || 'U').charAt(0).toUpperCase();
    };

    /**
     * Get display name for user
     */
    const getDisplayName = (user: T): string => {
        return user.full_name || user.username;
    };

    /**
     * Get date value from user object
     */
    const getDateValue = (user: T): string | undefined => {
        if (!dateField) return undefined;
        const value = user[dateField];
        return typeof value === 'string' ? value : undefined;
    };

    // Loading state
    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center py-16">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600"></div>
                <span className="mt-4 text-gray-600 font-medium">Loading users...</span>
            </div>
        );
    }

    // Empty state
    if (users.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                {emptyIcon || <DefaultEmptyIcon />}
                <p className="text-lg font-medium">{emptyMessage}</p>
                {emptySubMessage && (
                    <p className="text-sm text-gray-400 mt-1">{emptySubMessage}</p>
                )}
            </div>
        );
    }

    return (
        <>
        <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
                <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        User
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Role
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        {dateColumnLabel}
                    </th>
                    {renderActions && (
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Actions
                        </th>
                    )}
                </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
                {users.map((user) => (
                    <tr 
                        key={user.id} 
                        className={!user.is_active ? 'bg-gray-50 opacity-60' : ''}
                    >
                        {/* User column - Avatar + Name + Email */}
                        <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center">
                                <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-semibold">
                                    {getInitials(user)}
                                </div>
                                <div className="ml-4">
                                    <div className="text-sm font-medium text-gray-900">
                                        {getDisplayName(user)}
                                    </div>
                                    <div className="text-sm text-gray-500">
                                        {user.email || 'No email'}
                                    </div>
                                </div>
                            </div>
                        </td>

                        {/* Role column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getRoleBadgeClasses(user.role)}`}>
                                {getRoleDisplayName(user.role)}
                            </span>
                        </td>

                        {/* Status column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                {user.is_active ? 'Active' : 'Inactive'}
                            </span>
                        </td>

                        {/* Date column */}
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {formatDateTime(getDateValue(user))}
                        </td>

                        {/* Actions column */}
                        {renderActions && (
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <div className="flex items-center justify-end gap-2">
                                    {renderActions(user)}
                                </div>
                            </td>
                        )}
                    </tr>
                ))}
            </tbody>
        </table>
        </div>
        
        {/* Pagination */}
        {pagination && pagination.totalPages > 1 && (
            <Pagination
                page={pagination.page}
                totalPages={pagination.totalPages}
                totalItems={pagination.totalItems}
                pageSize={pagination.pageSize}
                onPageChange={pagination.onPageChange}
                disabled={loading}
            />
        )}
        </>
    );
}

export default UserTable;
