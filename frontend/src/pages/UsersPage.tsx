import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canManageUsers, getRoleDisplayName, ROLE_HIERARCHY } from '../utils/permissions';

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

    const handleDeactivate = async (u: UserData) => {
        if (!window.confirm(`Deactivate user "${u.username}"?`)) return;
        try {
            const token = getAuthToken();
            const res = await fetch(`/api/v1/users/${u.id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to deactivate user');
            loadUsers();
        } catch (err: any) {
            setError(err.message || 'Failed to deactivate user');
        }
    };

    // Access check AFTER all hooks
    if (!hasAccess) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
                    <p className="text-gray-500">You don't have permission to access this page.</p>
                    <p className="text-sm text-gray-400 mt-2">Only Super Admin can manage users.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-6xl mx-auto py-8 px-4">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">User Management</h1>
                    <p className="text-gray-500 mt-1">Manage user accounts and roles</p>
                </div>
                <button
                    onClick={loadUsers}
                    className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                >
                    Refresh
                </button>
            </div>

            {error && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
                    <span>{error}</span>
                    <button onClick={() => setError(null)} className="text-red-500">&times;</button>
                </div>
            )}

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading users...</span>
                </div>
            ) : (
                <div className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
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
                                            ${u.role === 'admin' ? 'bg-blue-100 text-blue-800' : ''}
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
                                <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                                <select
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
        </div>
    );
};

export default UsersPage;
