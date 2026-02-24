import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canManageUsers, getRoleDisplayName, ROLE_HIERARCHY } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import ConfirmationModal from '../components/ConfirmationModal';
import { APP_CONFIG, CONFIRMATION_MESSAGES } from '../config';
import { apiClient } from '../services/api';

interface UserData {
    id: number;
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
    const [editingUser, setEditingUser] = useState<UserData | null>(null);
    const [editForm, setEditForm] = useState({ role: '' });

    // Deactivate Modal State
    const [deactivateConfirm, setDeactivateConfirm] = useState<{ show: boolean; user: UserData | null }>({ show: false, user: null });
    // Activate Modal State
    const [activateConfirm, setActivateConfirm] = useState<{ show: boolean; user: UserData | null }>({ show: false, user: null });

    const hasAccess = canManageUsers(user);

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

            setUsers(res.data || []);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (u: UserData) => {
        setEditingUser(u);
        setEditForm({ role: u.role });
    };

    const handleSave = async () => {
        if (!editingUser) return;
        try {
            await apiClient.patch(`/api/v1/users/${editingUser.id}`, editForm);
            setEditingUser(null);
            loadUsers();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to update user');
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
                                                        {u.username.charAt(0).toUpperCase()}
                                                    </div>
                                                    <div className="ml-4">
                                                        <div className="text-sm font-medium text-gray-900">{u.username}</div>
                                                        <div className="text-sm text-gray-500">{u.email || 'No email'}</div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium 
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
                                                {u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                {u.username !== user?.username && (
                                                    <div className="flex items-center justify-end gap-2">
                                                        {u.is_active ? (
                                                            <>
                                                                <button 
                                                                    onClick={() => handleEdit(u)} 
                                                                    className="px-3 py-1.5 text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-colors"
                                                                >
                                                                    Edit
                                                                </button>
                                                                <button 
                                                                    onClick={() => handleDeactivate(u)} 
                                                                    className="px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
                                                                >
                                                                    Deactivate
                                                                </button>
                                                            </>
                                                        ) : (
                                                            <button 
                                                                onClick={() => handleActivate(u)} 
                                                                className="px-3 py-1.5 text-sm font-medium text-green-700 bg-green-50 border border-green-200 rounded-md hover:bg-green-100 transition-colors"
                                                            >
                                                                Activate
                                                            </button>
                                                        )}
                                                    </div>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Edit Modal */}
                    {editingUser && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                            <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                                <h3 className="text-lg font-semibold mb-4">Edit User: {editingUser.username}</h3>

                                <div className="space-y-4">
                                    <div>
                                        <label htmlFor="edit-role-select" className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                        <select
                                            id="edit-role-select"
                                            value={editForm.role}
                                            onChange={(e) => setEditForm(f => ({ ...f, role: e.target.value }))}
                                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                                        >
                                            {ROLE_HIERARCHY.map(r => (
                                                <option key={r} value={r}>{getRoleDisplayName(r)}</option>
                                            ))}
                                        </select>
                                    </div>

                                </div>

                                <div className="mt-6 flex justify-end gap-3">
                                    <button
                                        onClick={() => setEditingUser(null)}
                                        className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleSave}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                                    >
                                        Save Changes
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Deactivate Confirmation Modal */}
                    <ConfirmationModal
                        show={deactivateConfirm.show}
                        title="Deactivate User"
                        message={deactivateConfirm.user ? `Are you sure you want to deactivate ${deactivateConfirm.user.username}? ${CONFIRMATION_MESSAGES.DEACTIVATE_USER}` : CONFIRMATION_MESSAGES.DEACTIVATE_USER}
                        confirmText="Deactivate"
                        onConfirm={confirmDeactivate}
                        onCancel={() => setDeactivateConfirm({ show: false, user: null })}
                        type="danger"
                    />

                    {/* Activate Confirmation Modal */}
                    <ConfirmationModal
                        show={activateConfirm.show}
                        title="Activate User"
                        message={activateConfirm.user ? `Are you sure you want to activate ${activateConfirm.user.username}? They will be able to log in again.` : 'Are you sure you want to activate this user?'}
                        confirmText="Activate"
                        onConfirm={confirmActivate}
                        onCancel={() => setActivateConfirm({ show: false, user: null })}
                        type="info"
                    />
                </div>
            </div>
        </div>
    );
};

export default UsersPage;
