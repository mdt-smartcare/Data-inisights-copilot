import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canManageUsers, getRoleDisplayName, ROLE_HIERARCHY } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';

const getAuthToken = (): string | null => localStorage.getItem('auth_token');

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
    const [editForm, setEditForm] = useState({ role: '', is_active: true });

    // Add User State
    const [addingUser, setAddingUser] = useState(false);
    const [newUserForm, setNewUserForm] = useState({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: 'user'
    });

    // Deactivate Modal State
    const [deactivateConfirm, setDeactivateConfirm] = useState<{ show: boolean; user: UserData | null }>({ show: false, user: null });

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
            const token = getAuthToken();
            const res = await fetch('/api/v1/users', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load users');
            const data = await res.json();
            setUsers(data);
        } catch (err: any) {
            setError(err.message || 'Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (u: UserData) => {
        setEditingUser(u);
        setEditForm({ role: u.role, is_active: u.is_active });
    };

    const handleSave = async () => {
        if (!editingUser) return;
        try {
            const token = getAuthToken();
            const res = await fetch(`/api/v1/users/${editingUser.id}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(editForm)
            });
            if (!res.ok) throw new Error('Failed to update user');
            setEditingUser(null);
            loadUsers();
        } catch (err: any) {
            setError(err.message || 'Failed to update user');
        }
    };

    const handleCreateUser = async () => {
        if (!newUserForm.username || !newUserForm.password) {
            setError('Username and password are required');
            return;
        }

        try {
            const token = getAuthToken();
            const res = await fetch('/api/v1/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(newUserForm)
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || 'Failed to create user');
            }

            setAddingUser(false);
            setNewUserForm({
                username: '',
                email: '',
                password: '',
                full_name: '',
                role: 'user'
            });
            loadUsers();
        } catch (err: any) {
            setError(err.message || 'Failed to create user');
        }
    };

    const handleDeactivate = (u: UserData) => {
        setDeactivateConfirm({ show: true, user: u });
    };

    const confirmDeactivate = async () => {
        if (!deactivateConfirm.user) return;
        try {
            const token = getAuthToken();
            const res = await fetch(`/api/v1/users/${deactivateConfirm.user.id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to deactivate user');
            setDeactivateConfirm({ show: false, user: null });
            loadUsers();
        } catch (err: any) {
            setError(err.message || 'Failed to deactivate user');
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
                            <button
                                onClick={() => setAddingUser(true)}
                                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm hover:shadow-md transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                </svg>
                                Add User
                            </button>
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
                                            ${u.role === 'super_admin' ? 'bg-purple-100 text-purple-800' : ''}
                                            ${u.role === 'editor' ? 'bg-green-100 text-green-800' : ''}
                                            ${u.role === 'user' ? 'bg-yellow-100 text-yellow-800' : ''}
                                            ${u.role === 'viewer' ? 'bg-gray-100 text-gray-800' : ''}
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
                                                    <>
                                                        <button onClick={() => handleEdit(u)} className="text-blue-600 hover:text-blue-900 mr-4">Edit</button>
                                                        {u.is_active && (
                                                            <button onClick={() => handleDeactivate(u)} className="text-red-600 hover:text-red-900">Deactivate</button>
                                                        )}
                                                    </>
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
                                    <div className="flex items-center">
                                        <input
                                            type="checkbox"
                                            id="is_active"
                                            checked={editForm.is_active}
                                            onChange={(e) => setEditForm(f => ({ ...f, is_active: e.target.checked }))}
                                            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                        />
                                        <label htmlFor="is_active" className="ml-2 block text-sm text-gray-900">Active</label>
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
                    {/* Add User Modal */}
                    {addingUser && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                            <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                                <h3 className="text-lg font-semibold mb-4">Add New User</h3>

                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Username *</label>
                                        <input
                                            type="text"
                                            value={newUserForm.username}
                                            onChange={(e) => setNewUserForm(f => ({ ...f, username: e.target.value }))}
                                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                                            placeholder="jdoe"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                                        <input
                                            type="email"
                                            value={newUserForm.email}
                                            onChange={(e) => setNewUserForm(f => ({ ...f, email: e.target.value }))}
                                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                                            placeholder="john@example.com"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                                        <input
                                            type="text"
                                            value={newUserForm.full_name}
                                            onChange={(e) => setNewUserForm(f => ({ ...f, full_name: e.target.value }))}
                                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                                            placeholder="John Doe"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Password *</label>
                                        <input
                                            type="password"
                                            value={newUserForm.password}
                                            onChange={(e) => setNewUserForm(f => ({ ...f, password: e.target.value }))}
                                            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                                            placeholder="********"
                                        />
                                    </div>
                                    <div>
                                        <label htmlFor="new-role-select" className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                        <select
                                            id="new-role-select"
                                            value={newUserForm.role}
                                            onChange={(e) => setNewUserForm(f => ({ ...f, role: e.target.value }))}
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
                                        onClick={() => setAddingUser(false)}
                                        className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleCreateUser}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                                    >
                                        Create User
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Deactivate Confirmation Modal */}
                    {deactivateConfirm.show && deactivateConfirm.user && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                            <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                                        <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                        </svg>
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-semibold text-gray-900">Deactivate User</h3>
                                        <p className="text-sm text-gray-500">This action can be undone later</p>
                                    </div>
                                </div>
                                <p className="text-gray-600 mb-6">
                                    Are you sure you want to deactivate <strong>{deactivateConfirm.user.username}</strong>?
                                    They will no longer be able to log in to the system.
                                </p>
                                <div className="flex justify-end gap-3">
                                    <button
                                        type="button"
                                        onClick={() => setDeactivateConfirm({ show: false, user: null })}
                                        className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="button"
                                        onClick={confirmDeactivate}
                                        className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium"
                                    >
                                        Yes, Deactivate
                                    </button>
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
