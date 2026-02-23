import React, { useState, useEffect } from 'react';
import type { Agent } from '../../types/agent';
import { getAgents, createAgent, assignUserToAgent, revokeUserAccess, getUsers, handleApiError } from '../../services/api'; // Ensure getUsers exists or add it
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../Toast';
import Alert from '../Alert';
import { PlusIcon, UserGroupIcon, Cog6ToothIcon, TrashIcon } from '@heroicons/react/24/outline'; // Adjust icons as needed

// Helper to fetch users if not already available in api.ts
// If getUsers is not in api.ts, we might need to add it or use a local fetch.
// For now, I'll assume I need to fetch users for the assignment modal.
// I'll check api.ts again or just implement a simple fetch here if needed, but reusing api is better.
// Actually, in the previous `api.ts` view, I didn't see `getUsers`. `UsersPage` likely uses it.
// Let's assume for now I should use `apiClient` directly if `getUsers` is missing, or add it.
// Wait, `UsersPage` was in the file list. Let's assume `getUsers` is in `api.ts` or `usersService.ts`?
// The `api.ts` file had `getUserProfile` but not `getUsers` (list).
// I will implement a local fetchUsers in the component for now to avoid switching context again, using apiClient.
import { apiClient } from '../../services/api';

interface AgentsTabProps {
    onSelectAgent: (agent: Agent) => void;
}

const AgentsTab: React.FC<AgentsTabProps> = ({ onSelectAgent }) => {
    const { user } = useAuth();
    const { success, error: showError } = useToast();
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Create Modal State
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newAgentData, setNewAgentData] = useState({ name: '', description: '', type: 'sql' });
    const [creating, setCreating] = useState(false);

    // User Assignment Modal State
    const [showUserModal, setShowUserModal] = useState(false);
    const [selectedAgentForUsers, setSelectedAgentForUsers] = useState<Agent | null>(null);
    const [users, setUsers] = useState<any[]>([]); // User type
    const [loadingUsers, setLoadingUsers] = useState(false);
    const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
    const [assigning, setAssigning] = useState(false);

    useEffect(() => {
        loadAgents();
    }, []);

    const loadAgents = async () => {
        setLoading(true);
        try {
            const data = await getAgents();
            setAgents(data);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    const handleCreateAgent = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreating(true);
        try {
            const newAgent = await createAgent(newAgentData);
            setAgents([...agents, newAgent]);
            success('Agent Created', `${newAgent.name} has been created.`);
            setShowCreateModal(false);
            setNewAgentData({ name: '', description: '', type: 'sql' });
        } catch (err) {
            showError('Failed to create agent', handleApiError(err));
        } finally {
            setCreating(false);
        }
    };

    const openUserModal = async (agent: Agent, e: React.MouseEvent) => {
        e.stopPropagation(); // Prevent selecting the agent
        setSelectedAgentForUsers(agent);
        setShowUserModal(true);
        loadUsers();
    };

    const loadUsers = async () => {
        setLoadingUsers(true);
        try {
            // Fetch users - assuming an endpoint exists or using generic one
            const response = await apiClient.get('/api/v1/users'); // Use direct call if method missing
            setUsers(response.data);
        } catch (err) {
            console.error("Failed to load users", err);
            // Don't block UI, just empty list
        } finally {
            setLoadingUsers(false);
        }
    };

    const handleAssignUser = async () => {
        if (!selectedAgentForUsers || !selectedUserId) return;
        setAssigning(true);
        try {
            await assignUserToAgent(selectedAgentForUsers.id, selectedUserId, 'viewer'); // Default to viewer
            success('User Assigned', 'User has been granted access.');
            // Reload agents to update user_role if needed, logic might vary
        } catch (err) {
            showError('Failed to assign user', handleApiError(err));
        } finally {
            setAssigning(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-gray-50">
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
                    <p className="text-gray-500 text-sm mt-1">Manage AI agents and their configurations.</p>
                </div>
                {user?.role === 'super_admin' && (
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm font-medium"
                    >
                        <PlusIcon className="w-5 h-5" />
                        New Agent
                    </button>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-6">
                {error && <Alert type="error" message={error} className="mb-6" />}

                {loading ? (
                    <div className="flex justify-center items-center h-64">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                ) : agents.length === 0 ? (
                    <div className="text-center py-20 bg-white rounded-lg border border-gray-200 border-dashed">
                        <UserGroupIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                        <h3 className="text-lg font-medium text-gray-900">No Agents Found</h3>
                        <p className="text-gray-500 mt-2">Get started by creating your first agent.</p>
                        {user?.role === 'super_admin' && (
                            <button
                                onClick={() => setShowCreateModal(true)}
                                className="mt-6 px-4 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 font-medium"
                            >
                                Create Agent
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {agents.map((agent) => (
                            <div
                                key={agent.id}
                                onClick={() => onSelectAgent(agent)}
                                className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group flex flex-col"
                            >
                                <div className="p-6 flex-1">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${agent.type === 'sql' ? 'bg-indigo-50 text-indigo-600' : 'bg-orange-50 text-orange-600'}`}>
                                                {agent.type === 'sql' ? (
                                                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                                                    </svg>
                                                ) : (
                                                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                                    </svg>
                                                )}
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-900 text-lg">{agent.name}</h3>
                                                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide bg-gray-100 px-2 py-0.5 rounded">
                                                    {agent.type}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    <p className="text-gray-600 text-sm line-clamp-2 mb-4">
                                        {agent.description || "No description provided."}
                                    </p>
                                </div>
                                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 rounded-b-xl flex justify-between items-center">
                                    <span className="text-xs text-gray-500">
                                        {/* You could show role or status here */}
                                        Role: {agent.user_role || 'Viewer'}
                                    </span>
                                    <div className="flex gap-2">
                                        {user?.role === 'super_admin' && (
                                            <button
                                                onClick={(e) => openUserModal(agent, e)}
                                                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                                                title="Manage Users"
                                            >
                                                <UserGroupIcon className="w-5 h-5" />
                                            </button>
                                        )}
                                        <button className="flex items-center text-blue-600 text-sm font-medium hover:underline">
                                            Configure <Cog6ToothIcon className="w-4 h-4 ml-1" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Create Agent Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
                        <div className="p-6 border-b border-gray-200">
                            <h2 className="text-xl font-semibold text-gray-900">Create New Agent</h2>
                        </div>
                        <form onSubmit={handleCreateAgent} className="p-6">
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Agent Name</label>
                                    <input
                                        type="text"
                                        required
                                        value={newAgentData.name}
                                        onChange={(e) => setNewAgentData({ ...newAgentData, name: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        placeholder="e.g., Sales Analyst"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                                    <textarea
                                        value={newAgentData.description}
                                        onChange={(e) => setNewAgentData({ ...newAgentData, description: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        rows={3}
                                        placeholder="What does this agent do?"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                                    <select
                                        value={newAgentData.type}
                                        onChange={(e) => setNewAgentData({ ...newAgentData, type: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="sql">SQL (Structured Data)</option>
                                        {/* <option value="rag">RAG (Documents) - Coming Soon</option> */}
                                    </select>
                                </div>
                            </div>
                            <div className="mt-6 flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateModal(false)}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={creating}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                                >
                                    {creating ? 'Creating...' : 'Create Agent'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* User Assignment Modal */}
            {showUserModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
                        <div className="p-6 border-b border-gray-200">
                            <h2 className="text-xl font-semibold text-gray-900">Manage Users</h2>
                            <p className="text-sm text-gray-500">Assign users to {selectedAgentForUsers?.name}</p>
                        </div>
                        <div className="p-6">
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 mb-1">Select User to Assign</label>
                                {loadingUsers ? (
                                    <div className="text-center py-2 text-gray-500">Loading users...</div>
                                ) : (
                                    <select
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        onChange={(e) => setSelectedUserId(Number(e.target.value))}
                                        value={selectedUserId || ''}
                                    >
                                        <option value="">Select a user...</option>
                                        {users.map(u => (
                                            <option key={u.id} value={u.id}>{u.username} ({u.role})</option>
                                        ))}
                                    </select>
                                )}
                            </div>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowUserModal(false)}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
                                >
                                    Done
                                </button>
                                <button
                                    type="button"
                                    onClick={handleAssignUser}
                                    disabled={assigning || !selectedUserId}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                                >
                                    {assigning ? 'Assigning...' : 'Assign User'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AgentsTab;
