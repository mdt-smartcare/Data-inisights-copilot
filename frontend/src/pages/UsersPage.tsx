import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canManageUsers, getRoleDisplayName, ROLE_HIERARCHY, isSuperAdmin } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import ConfirmationModal from '../components/ConfirmationModal';
import { APP_CONFIG, CONFIRMATION_MESSAGES } from '../config';
import { apiClient, getAgents, getAllAgents, getUserAgents, bulkAssignAgents, revokeUserAccess, handleApiError } from '../services/api';
import type { Agent } from '../types';
import { formatDateTime } from '../utils/datetime';

interface UserData {
    id: string;
    username: string;
    email?: string;
    full_name?: string;
    role: string;
    is_active: boolean;
    created_at?: string;
}

const UsersPage: React.FC = () => {
    const { user } = useAuth();
    const [users, setUsers] = useState<UserData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Role Change Modal State (shows role buttons directly)
    const [roleChangeModal, setRoleChangeModal] = useState<{ show: boolean; user: UserData | null; saving: boolean }>({ show: false, user: null, saving: false });

    // Deactivate Modal State
    const [deactivateConfirm, setDeactivateConfirm] = useState<{ show: boolean; user: UserData | null }>({ show: false, user: null });
    // Activate Modal State
    const [activateConfirm, setActivateConfirm] = useState<{ show: boolean; user: UserData | null }>({ show: false, user: null });
    // Role Change Confirmation Modal State
    const [roleChangeConfirm, setRoleChangeConfirm] = useState<{ show: boolean; user: UserData | null; newRole: string }>({ show: false, user: null, newRole: '' });

    // Agent Assignment State
    const [agentModalUser, setAgentModalUser] = useState<UserData | null>(null);
    const [allAgents, setAllAgents] = useState<Agent[]>([]);
    const [userAgents, setUserAgents] = useState<Agent[]>([]);
    const [loadingAgents, setLoadingAgents] = useState(false);
    const [selectedAgentRoles, setSelectedAgentRoles] = useState<Record<string, 'admin' | 'user'>>({}); // Per-agent role map (agent IDs are UUIDs)
    const [assigning, setAssigning] = useState(false);

    // Helper to get selected agent IDs
    const selectedAgentIds = Object.keys(selectedAgentRoles); // Already strings (agent IDs are UUIDs)

    const hasAccess = canManageUsers(user);
    const currentUserIsSuperAdmin = isSuperAdmin(user);

    useEffect(() => {
        if (hasAccess) {
            loadUsers();
        }
    }, [hasAccess]);

    const loadUsers = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await apiClient.get('/api/v1/users');
            // Handle wrapped response: { success, data: { items } }
            const users = res.data?.data?.items || res.data?.items || (Array.isArray(res.data) ? res.data : []);
            setUsers(users);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (u: UserData) => {
        setRoleChangeModal({ show: true, user: u, saving: false });
    };

    const handleRoleSelect = (newRole: string) => {
        if (!roleChangeModal.user || newRole === roleChangeModal.user.role) return;
        // Show confirmation
        setRoleChangeConfirm({ show: true, user: roleChangeModal.user, newRole });
    };

    const confirmRoleChange = async () => {
        if (!roleChangeConfirm.user) return;
        setRoleChangeModal(m => ({ ...m, saving: true }));
        try {
            await apiClient.patch(`/api/v1/users/${roleChangeConfirm.user.id}`, { role: roleChangeConfirm.newRole });
            setRoleChangeConfirm({ show: false, user: null, newRole: '' });
            setRoleChangeModal({ show: false, user: null, saving: false });
            loadUsers();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to update user role');
            setRoleChangeConfirm({ show: false, user: null, newRole: '' });
            setRoleChangeModal(m => ({ ...m, saving: false }));
        }
    };

    const handleDeactivate = (u: UserData) => {
        setDeactivateConfirm({ show: true, user: u });
    };

    const confirmDeactivate = async () => {
        if (!deactivateConfirm.user) return;
        try {
            await apiClient.post(`/api/v1/users/${deactivateConfirm.user.id}/deactivate`);
            setDeactivateConfirm({ show: false, user: null });
            loadUsers();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to deactivate user');
        }
    };

    const handleActivate = (u: UserData) => {
        setActivateConfirm({ show: true, user: u });
    };

    const confirmActivate = async () => {
        if (!activateConfirm.user) return;
        try {
            await apiClient.post(`/api/v1/users/${activateConfirm.user.id}/activate`);
            setActivateConfirm({ show: false, user: null });
            loadUsers();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to activate user');
        }
    };

    // Agent assignment handlers
    const handleOpenAgentModal = async (u: UserData) => {
        setAgentModalUser(u);
        setLoadingAgents(true);
        setSelectedAgentRoles({}); // Reset selections
        try {
            // Super admin can see all agents, admin can only see agents they can configure
            const agentsPromise = currentUserIsSuperAdmin ? getAllAgents() : getAgents();
            const [agents, userAgentsResponse] = await Promise.all([
                agentsPromise,
                getUserAgents(u.id)
            ]);
            // For admins, filter to only agents they can configure (user_role === 'admin')
            const configurableAgents = currentUserIsSuperAdmin 
                ? agents 
                : agents.filter(a => a.user_role === 'admin');
            setAllAgents(configurableAgents);
            setUserAgents(userAgentsResponse.agents || []);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoadingAgents(false);
        }
    };

    const handleAssignAgents = async () => {
        if (!agentModalUser || selectedAgentIds.length === 0) return;
        setAssigning(true);
        try {
            // If target user has 'user' role, force all assignments to 'user' per-agent role
            // (user-role users cannot have configure access)
            if (agentModalUser.role === 'user') {
                await bulkAssignAgents(agentModalUser.id, selectedAgentIds, 'user');
            } else {
                // Group agents by role and make separate calls for admin-role targets
                const adminAgentIds = selectedAgentIds.filter(id => selectedAgentRoles[id] === 'admin');
                const chatAgentIds = selectedAgentIds.filter(id => selectedAgentRoles[id] === 'user');
                
                if (adminAgentIds.length > 0) {
                    await bulkAssignAgents(agentModalUser.id, adminAgentIds, 'admin');
                }
                if (chatAgentIds.length > 0) {
                    await bulkAssignAgents(agentModalUser.id, chatAgentIds, 'user');
                }
            }
            
            const userAgentsResponse = await getUserAgents(agentModalUser.id);
            setUserAgents(userAgentsResponse.agents || []);
            setSelectedAgentRoles({});
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setAssigning(false);
        }
    };

    const toggleAgentSelection = (agentId: string) => {
        setSelectedAgentRoles(prev => {
            if (prev[agentId] !== undefined) {
                // Remove from selection
                const { [agentId]: _, ...rest } = prev;
                return rest;
            } else {
                // Add with default role 'user'
                return { ...prev, [agentId]: 'user' };
            }
        });
    };

    const setAgentRole = (agentId: string, role: 'admin' | 'user') => {
        setSelectedAgentRoles(prev => ({
            ...prev,
            [agentId]: role
        }));
    };

    const handleRevokeAgent = async (agentId: string) => {
        if (!agentModalUser) return;
        try {
            await revokeUserAccess(agentId, agentModalUser.id);
            const userAgentsResponse = await getUserAgents(agentModalUser.id);
            setUserAgents(userAgentsResponse.agents || []);
        } catch (err) {
            setError(handleApiError(err));
        }
    };

    const getAvailableAgents = () => {
        const assignedIds = new Set(userAgents.map(a => a.id));
        return allAgents.filter(a => !assignedIds.has(a.id));
    };

    /**
     * Determine if the current user can assign agents to a target user.
     * - Super admin can assign agents to admins and users (not other super_admins or self)
     * - Admin can assign agents to admins and users (not super_admins or self)
     */
    const canAssignAgents = (targetUser: UserData): boolean => {
        // Never show for self
        if (targetUser.username === user?.username) return false;
        // Cannot assign agents to super_admins
        return targetUser.role !== 'super_admin';
    };

    /**
     * Determine if the current user can edit role or deactivate a target user.
     * Only super admin can edit/deactivate (and only for admins and users, not other super_admins)
     */
    const canEditOrDeactivate = (targetUser: UserData): boolean => {
        // Only super admin can edit/deactivate
        if (!currentUserIsSuperAdmin) return false;
        // Never show for self
        if (targetUser.username === user?.username) return false;
        // Cannot edit/deactivate other super_admins
        return targetUser.role !== 'super_admin';
    };

    /**
     * Get the available roles that the current user can assign.
     * - Super admin can assign: super_admin, admin, user
     * - Admin can assign: admin, user (cannot promote to super_admin)
     */
    const getAssignableRoles = (): string[] => {
        if (currentUserIsSuperAdmin) {
            return ROLE_HIERARCHY.filter(r => r !== 'super_admin'); // Can promote to admin but not another super_admin
        }
        // Admin can only assign admin or user roles
        return ['admin', 'user'];
    };

    // Access check AFTER all hooks
    if (!hasAccess) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
                        <p className="text-gray-500">You don't have permission to access this page.</p>
                        <p className="text-sm text-gray-400 mt-2">Only Super Admin can manage users.</p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="max-w-6xl mx-auto py-8 px-4">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">User Management</h1>
                            <p className="text-gray-500 mt-1">Manage user accounts and roles</p>
                        </div>
                        <div className="flex items-center gap-3">
                            <RefreshButton
                                onClick={loadUsers}
                                isLoading={loading}
                            />
                        </div>
                    </div>

                    {error && (
                        <Alert
                            type="error"
                            message={error}
                            onDismiss={() => setError(null)}
                        />
                    )}

                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600"></div>
                            <span className="mt-4 text-gray-600 font-medium">Loading users...</span>
                            <span className="mt-1 text-sm text-gray-400">Please wait</span>
                        </div>
                    ) : (
                        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Role</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {users.map((u) => (
                                        <tr key={u.id} className={!u.is_active ? 'bg-gray-50 opacity-60' : ''}>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="flex items-center">
                                                    <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-semibold">
                                                        {(u.full_name || u.username || u.email || 'U').charAt(0).toUpperCase()}
                                                    </div>
                                                    <div className="ml-4">
                                                        <div className="text-sm font-medium text-gray-900">{u.full_name || u.username}</div>
                                                        <div className="text-sm text-gray-500">{u.email || 'No email'}</div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium 
                                            ${u.role === 'super_admin' ? 'bg-red-100 text-red-800' : ''}
                                            ${u.role === 'admin' ? 'bg-purple-100 text-purple-800' : ''}
                                            ${u.role === 'user' ? 'bg-yellow-100 text-yellow-800' : ''}
                                          
                                        `}>
                                                    {getRoleDisplayName(u.role)}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                                    {u.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {formatDateTime(u.created_at)}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                <div className="flex items-center justify-end gap-2">
                                                    {u.is_active ? (
                                                        <>
                                                            {/* Agents button - super admin and admin can assign agents to admins/users */}
                                                            {canAssignAgents(u) && (
                                                                <button 
                                                                    onClick={() => handleOpenAgentModal(u)} 
                                                                    className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 transition-colors"
                                                                >
                                                                    Agents
                                                                </button>
                                                            )}
                                                            {/* Change Role button - super admin only */}
                                                            {canEditOrDeactivate(u) && (
                                                                <button 
                                                                    onClick={() => handleEdit(u)} 
                                                                    className="px-3 py-1.5 text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-colors"
                                                                >
                                                                    Change Role
                                                                </button>
                                                            )}
                                                            {/* Deactivate button - super admin only */}
                                                            {canEditOrDeactivate(u) && (
                                                                <button 
                                                                    onClick={() => handleDeactivate(u)} 
                                                                    className="px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
                                                                >
                                                                    Deactivate
                                                                </button>
                                                            )}
                                                        </>
                                                    ) : (
                                                        /* Activate button - super admin only */
                                                        canEditOrDeactivate(u) && (
                                                            <button 
                                                                onClick={() => handleActivate(u)} 
                                                                className="px-3 py-1.5 text-sm font-medium text-green-700 bg-green-50 border border-green-200 rounded-md hover:bg-green-100 transition-colors"
                                                            >
                                                                Activate
                                                            </button>
                                                        )
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Change Role Modal - Role Selection with Buttons */}
                    {roleChangeModal.show && roleChangeModal.user && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                            <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6" style={{ maxWidth: '28rem' }}>
                                <h3 className="text-lg font-semibold mb-2">Change Role</h3>
                                <p className="text-gray-600 mb-4">Select a new role for <span className="font-medium">{roleChangeModal.user.full_name || roleChangeModal.user.username}</span></p>
                                <p className="text-sm text-gray-500 mb-4">Current role: <span className="font-medium text-blue-600">{getRoleDisplayName(roleChangeModal.user.role)}</span></p>

                                <div className="space-y-2">
                                    {getAssignableRoles().map(r => (
                                        <button
                                            key={r}
                                            onClick={() => handleRoleSelect(r)}
                                            disabled={r === roleChangeModal.user?.role || roleChangeModal.saving}
                                            className={`w-full px-4 py-3 text-left rounded-lg border transition-colors ${
                                                r === roleChangeModal.user?.role
                                                    ? 'bg-blue-50 border-blue-300 text-blue-700 cursor-default'
                                                    : 'border-gray-200 hover:bg-gray-50 hover:border-gray-300'
                                            }`}
                                        >
                                            <span className="font-medium">{getRoleDisplayName(r)}</span>
                                            {r === roleChangeModal.user?.role && (
                                                <span className="ml-2 text-xs text-blue-600">(current)</span>
                                            )}
                                        </button>
                                    ))}
                                </div>

                                <div className="mt-6 flex justify-end">
                                    <button
                                        onClick={() => setRoleChangeModal({ show: false, user: null, saving: false })}
                                        className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                                        disabled={roleChangeModal.saving}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Deactivate Confirmation Modal */}
                    <ConfirmationModal
                        show={deactivateConfirm.show}
                        title="Deactivate User"
                        message={deactivateConfirm.user ? `Are you sure you want to deactivate ${deactivateConfirm.user.full_name || deactivateConfirm.user.username}? They will no longer be able to log in or access the system.` : CONFIRMATION_MESSAGES.DEACTIVATE_USER}
                        confirmText="Deactivate"
                        onConfirm={confirmDeactivate}
                        onCancel={() => setDeactivateConfirm({ show: false, user: null })}
                        type="danger"
                    />

                    {/* Activate Confirmation Modal */}
                    <ConfirmationModal
                        show={activateConfirm.show}
                        title="Activate User"
                        message={activateConfirm.user ? `Are you sure you want to activate ${activateConfirm.user.full_name || activateConfirm.user.username}? They will be able to log in again.` : 'Are you sure you want to activate this user?'}
                        confirmText="Activate"
                        onConfirm={confirmActivate}
                        onCancel={() => setActivateConfirm({ show: false, user: null })}
                        type="info"
                    />

                    {/* Role Change Confirmation Modal */}
                    <ConfirmationModal
                        show={roleChangeConfirm.show}
                        title="Confirm Role Change"
                        message={roleChangeConfirm.user ? 
                            `Are you sure you want to change ${roleChangeConfirm.user.full_name || roleChangeConfirm.user.username}'s role from "${getRoleDisplayName(roleChangeConfirm.user.role)}" to "${getRoleDisplayName(roleChangeConfirm.newRole)}"?${roleChangeConfirm.user.role === 'admin' && roleChangeConfirm.newRole === 'user' ? '\n\nThis will also revoke their admin access to all agents they manage.' : ''}` 
                            : 'Are you sure you want to change this user\'s role?'}
                        confirmText="Change Role"
                        onConfirm={confirmRoleChange}
                        onCancel={() => setRoleChangeConfirm({ show: false, user: null, newRole: '' })}
                        type="warning"
                    />

                    {/* Agent Assignment Modal */}
                    {agentModalUser && (
                        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden" style={{ maxWidth: '42rem' }}>
                                {/* Header */}
                                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-indigo-50 to-blue-50">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center">
                                            <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                            </svg>
                                        </div>
                                        <div>
                                            <h3 className="text-lg font-semibold text-gray-900">Manage Agent Access</h3>
                                            <p className="text-sm text-gray-500">Configure agents for <span className="font-medium text-indigo-600">{agentModalUser.full_name || agentModalUser.username}</span></p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setAgentModalUser(null)}
                                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                                        aria-label="Close modal"
                                    >
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                        </svg>
                                    </button>
                                </div>

                                {/* Body */}
                                <div className="flex-1 overflow-y-auto px-6 py-5">
                                    {loadingAgents ? (
                                        <div className="flex flex-col items-center justify-center py-12">
                                            <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-200 border-t-indigo-600"></div>
                                            <p className="mt-3 text-sm text-gray-500">Loading agents...</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-6">
                                            {/* Assigned Agents Section */}
                                            <div>
                                                <div className="flex items-center justify-between mb-3">
                                                    <h4 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Assigned Agents</h4>
                                                    <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                                                        {userAgents.length} agent{userAgents.length !== 1 ? 's' : ''}
                                                    </span>
                                                </div>
                                                {userAgents.length === 0 ? (
                                                    <div className="flex flex-col items-center justify-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                                                        <svg className="w-10 h-10 text-gray-300 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                                                        </svg>
                                                        <p className="text-sm text-gray-500">No agents assigned yet</p>
                                                        <p className="text-xs text-gray-400 mt-1">Assign agents from the section below</p>
                                                    </div>
                                                ) : (
                                                    <div className="grid gap-2 max-h-48 overflow-y-auto pr-1">
                                                        {userAgents.map(agent => (
                                                            <div 
                                                                key={agent.id} 
                                                                className="group flex items-center justify-between bg-white px-4 py-3 rounded-lg border border-gray-200 hover:border-gray-300 hover:shadow-sm transition-all"
                                                            >
                                                                <div className="flex items-center gap-3 min-w-0">
                                                                    <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                                                        <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                                                        </svg>
                                                                    </div>
                                                                    <div className="min-w-0">
                                                                        <div className="flex items-center gap-2">
                                                                            <span className="font-medium text-gray-900 truncate">{agent.name}</span>
                                                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                                                                agent.user_role === 'admin' 
                                                                                    ? 'bg-purple-100 text-purple-700 ring-1 ring-purple-200' 
                                                                                    : 'bg-amber-100 text-amber-700 ring-1 ring-amber-200'
                                                                            }`}>
                                                                                {agent.user_role === 'admin' ? '⚙️ Configure' : '💬 Chat'}
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <button
                                                                    onClick={() => handleRevokeAgent(agent.id)}
                                                                    className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-all"
                                                                    title="Remove access"
                                                                >
                                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                                    </svg>
                                                                </button>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>

                                            {/* Divider */}
                                            <div className="relative">
                                                <div className="absolute inset-0 flex items-center">
                                                    <div className="w-full border-t border-gray-200"></div>
                                                </div>
                                                <div className="relative flex justify-center">
                                                    <span className="px-3 bg-white text-xs font-medium text-gray-400 uppercase tracking-wider">Add New</span>
                                                </div>
                                            </div>

                                            {/* Available Agents Section */}
                                            <div>
                                                <div className="flex items-center justify-between mb-3">
                                                    <h4 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Available Agents</h4>
                                                    <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                                                        {getAvailableAgents().length} available
                                                    </span>
                                                </div>
                                                {getAvailableAgents().length === 0 ? (
                                                    <div className="flex flex-col items-center justify-center py-8 bg-green-50 rounded-lg border border-green-200">
                                                        <svg className="w-10 h-10 text-green-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                        </svg>
                                                        <p className="text-sm text-green-700 font-medium">All agents assigned!</p>
                                                        <p className="text-xs text-green-600 mt-1">This user has access to all available agents</p>
                                                    </div>
                                                ) : (
                                                    <>
                                                        <div className="grid gap-2 max-h-60 overflow-y-auto pr-1">
                                                            {getAvailableAgents().map(agent => {
                                                                const isSelected = selectedAgentRoles[agent.id] !== undefined;
                                                                const agentRole = selectedAgentRoles[agent.id] || 'user';
                                                                return (
                                                                    <div 
                                                                        key={agent.id} 
                                                                        className={`flex items-center gap-3 px-4 py-3 rounded-lg border-2 transition-all ${
                                                                            isSelected 
                                                                                ? 'border-indigo-500 bg-indigo-50 shadow-sm' 
                                                                                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                                                                        }`}
                                                                    >
                                                                        {/* Checkbox */}
                                                                        <label className="flex items-center gap-3 cursor-pointer flex-1 min-w-0">
                                                                            <input
                                                                                type="checkbox"
                                                                                checked={isSelected}
                                                                                onChange={() => toggleAgentSelection(agent.id)}
                                                                                className="sr-only"
                                                                            />
                                                                            <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                                                                                isSelected 
                                                                                    ? 'bg-indigo-600 border-indigo-600' 
                                                                                    : 'border-gray-300 bg-white'
                                                                            }`}>
                                                                                {isSelected && (
                                                                                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                                                                    </svg>
                                                                                )}
                                                                            </div>
                                                                            <div className="min-w-0 flex-1">
                                                                                <span className={`block text-sm font-medium truncate ${isSelected ? 'text-indigo-900' : 'text-gray-900'}`}>
                                                                                    {agent.name}
                                                                                </span>
                                                                            </div>
                                                                        </label>

                                                                        {/* Inline role selector - shown when selected (super admin only AND target is admin role) */}
                                                                        {isSelected && currentUserIsSuperAdmin && agentModalUser?.role === 'admin' && (
                                                                            <div className="flex-shrink-0 inline-flex rounded-md overflow-hidden border border-indigo-300 shadow-sm">
                                                                                <button
                                                                                    type="button"
                                                                                    onClick={(e) => { e.stopPropagation(); setAgentRole(agent.id, 'user'); }}
                                                                                    className={`px-2 py-1 text-xs font-medium transition-colors ${
                                                                                        agentRole === 'user'
                                                                                            ? 'bg-indigo-600 text-white'
                                                                                            : 'bg-white text-indigo-700 hover:bg-indigo-100'
                                                                                    }`}
                                                                                    title="Chat access only"
                                                                                >
                                                                                    💬 Chat
                                                                                </button>
                                                                                <button
                                                                                    type="button"
                                                                                    onClick={(e) => { e.stopPropagation(); setAgentRole(agent.id, 'admin'); }}
                                                                                    className={`px-2 py-1 text-xs font-medium transition-colors border-l border-indigo-300 ${
                                                                                        agentRole === 'admin'
                                                                                            ? 'bg-indigo-600 text-white'
                                                                                            : 'bg-white text-indigo-700 hover:bg-indigo-100'
                                                                                    }`}
                                                                                    title="Configure access"
                                                                                >
                                                                                    ⚙️ Config
                                                                                </button>
                                                                            </div>
                                                                        )}

                                                                        {/* Show role badge for super admin assigning to user-role target */}
                                                                        {isSelected && currentUserIsSuperAdmin && agentModalUser?.role === 'user' && (
                                                                            <span className="flex-shrink-0 inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-indigo-100 text-indigo-700">
                                                                                💬 Chat
                                                                            </span>
                                                                        )}

                                                                        {/* Show role badge for non-super admins when selected */}
                                                                        {isSelected && !currentUserIsSuperAdmin && (
                                                                            <span className="flex-shrink-0 inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-amber-100 text-amber-700">
                                                                                💬 Chat
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>

                                                        {/* Selection Summary */}
                                                        {selectedAgentIds.length > 0 && (
                                                            <div className="mt-3 px-3 py-2 bg-indigo-50 rounded-lg border border-indigo-100">
                                                                <span className="text-sm font-medium text-indigo-900">
                                                                    {selectedAgentIds.length} agent{selectedAgentIds.length !== 1 ? 's' : ''} selected
                                                                </span>
                                                                {currentUserIsSuperAdmin && agentModalUser?.role === 'admin' && (
                                                                    <span className="text-xs text-indigo-600 ml-2">
                                                                        ({selectedAgentIds.filter(id => selectedAgentRoles[id] === 'admin').length} configure, {selectedAgentIds.filter(id => selectedAgentRoles[id] === 'user').length} chat)
                                                                    </span>
                                                                )}
                                                                {currentUserIsSuperAdmin && agentModalUser?.role === 'user' && (
                                                                    <span className="text-xs text-indigo-600 ml-2">
                                                                        (all chat-only)
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Footer */}
                                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
                                    <button
                                        onClick={() => setAgentModalUser(null)}
                                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                                    >
                                        Close
                                    </button>
                                    {getAvailableAgents().length > 0 && (
                                        <button
                                            onClick={handleAssignAgents}
                                            disabled={selectedAgentIds.length === 0 || assigning}
                                            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                        >
                                            {assigning ? (
                                                <>
                                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                                    Assigning...
                                                </>
                                            ) : (
                                                <>
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                                    </svg>
                                                    Assign {selectedAgentIds.length > 0 ? `(${selectedAgentIds.length})` : 'Selected'}
                                                </>
                                            )}
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default UsersPage;
