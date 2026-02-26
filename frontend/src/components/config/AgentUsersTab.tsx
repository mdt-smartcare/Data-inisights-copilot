import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../Toast';
import Alert from '../Alert';
import ConfirmationModal from '../ConfirmationModal';
import { getAgentUsers, assignUserToAgent, revokeUserAccess, handleApiError } from '../../services/api';
import type { AgentUser, SearchUser } from '../../services/api';
import { getRoleDisplayName } from '../../utils/permissions';
import UserSearchInput from './UserSearchInput';

interface AgentUsersTabProps {
    agentId: number;
    agentName: string;
}

const AgentUsersTab: React.FC<AgentUsersTabProps> = ({ agentId, agentName }) => {
    const { user } = useAuth();
    const { success, error: showError } = useToast();
    
    // Users assigned to this agent
    const [agentUsers, setAgentUsers] = useState<AgentUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    // Selected users to add (chips)
    const [selectedUsers, setSelectedUsers] = useState<SearchUser[]>([]);
    const [assigning, setAssigning] = useState(false);
    
    // Remove confirmation modal
    const [removeConfirm, setRemoveConfirm] = useState<{ show: boolean; user: AgentUser | null }>({ show: false, user: null });
    const [removing, setRemoving] = useState(false);

    const loadAgentUsers = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await getAgentUsers(agentId);
            setAgentUsers(response.users);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    }, [agentId]);

    useEffect(() => {
        loadAgentUsers();
    }, [loadAgentUsers]);

    const handleAssignUsers = async () => {
        if (selectedUsers.length === 0) return;
        setAssigning(true);
        
        let successCount = 0;
        let failCount = 0;
        
        try {
            // Assign all selected users
            for (const userToAdd of selectedUsers) {
                try {
                    await assignUserToAgent(agentId, userToAdd.id, 'user');
                    successCount++;
                } catch (err) {
                    console.error(`Failed to assign user ${userToAdd.username}:`, err);
                    failCount++;
                }
            }
            
            if (successCount > 0) {
                success(
                    'Users Added', 
                    `${successCount} user${successCount > 1 ? 's' : ''} ${successCount > 1 ? 'have' : 'has'} been granted access to this agent.${failCount > 0 ? ` (${failCount} failed)` : ''}`
                );
            }
            
            if (failCount > 0 && successCount === 0) {
                showError('Failed to add users', 'Could not assign any users to this agent.');
            }
            
            setSelectedUsers([]);
            await loadAgentUsers();
        } catch (err) {
            showError('Failed to add users', handleApiError(err));
        } finally {
            setAssigning(false);
        }
    };

    const handleRemoveClick = (agentUser: AgentUser) => {
        setRemoveConfirm({ show: true, user: agentUser });
    };

    const confirmRemove = async () => {
        if (!removeConfirm.user) return;
        setRemoving(true);
        try {
            await revokeUserAccess(agentId, removeConfirm.user.id);
            success('User Removed', `${removeConfirm.user.username} has been removed from this agent.`);
            setRemoveConfirm({ show: false, user: null });
            await loadAgentUsers();
        } catch (err) {
            showError('Failed to remove user', handleApiError(err));
        } finally {
            setRemoving(false);
        }
    };

    // Get IDs of users already assigned to exclude from search
    const excludeUserIds = agentUsers.map(u => u.id);

    return (
        <div className="space-y-6">
            {/* Add User Section */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Add Users to Agent</h3>
                <div className="space-y-4">
                    <UserSearchInput
                        selectedUsers={selectedUsers}
                        onSelectionChange={setSelectedUsers}
                        excludeUserIds={excludeUserIds}
                        disabled={assigning}
                    />
                    <div className="flex justify-end">
                        <button
                            onClick={handleAssignUsers}
                            disabled={assigning || selectedUsers.length === 0}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
                        >
                            {assigning ? 'Adding...' : `Add ${selectedUsers.length > 0 ? selectedUsers.length : ''} User${selectedUsers.length !== 1 ? 's' : ''}`}
                        </button>
                    </div>
                </div>
            </div>

            {/* Users Table */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900">Assigned Users</h3>
                    <p className="text-sm text-gray-500 mt-1">
                        Users who have access to {agentName}
                    </p>
                </div>

                {error && (
                    <div className="p-4">
                        <Alert
                            type="error"
                            message={error}
                            onDismiss={() => setError(null)}
                        />
                    </div>
                )}

                {loading ? (
                    <div className="flex flex-col items-center justify-center py-16">
                        <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600"></div>
                        <span className="mt-4 text-gray-600 font-medium">Loading users...</span>
                    </div>
                ) : agentUsers.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                        <svg className="w-16 h-16 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                        </svg>
                        <p className="text-lg font-medium">No users assigned</p>
                        <p className="text-sm text-gray-400 mt-1">Add users using the form above</p>
                    </div>
                ) : (
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
                            {agentUsers.map((agentUser) => (
                                <tr key={agentUser.id} className={!agentUser.is_active ? 'bg-gray-50 opacity-60' : ''}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center">
                                            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-semibold">
                                                {agentUser.username.charAt(0).toUpperCase()}
                                            </div>
                                            <div className="ml-4">
                                                <div className="text-sm font-medium text-gray-900">{agentUser.username}</div>
                                                <div className="text-sm text-gray-500">{agentUser.email || 'No email'}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium 
                                            ${agentUser.user_role === 'admin' ? 'bg-purple-100 text-purple-800' : ''}
                                            ${agentUser.user_role === 'user' ? 'bg-yellow-100 text-yellow-800' : ''}
                                        `}>
                                            {getRoleDisplayName(agentUser.user_role)}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${agentUser.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                            {agentUser.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {agentUser.created_at ? new Date(agentUser.created_at).toLocaleDateString() : '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        {agentUser.username !== user?.username && (
                                            <button 
                                                onClick={() => handleRemoveClick(agentUser)} 
                                                className="px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
                                            >
                                                Remove
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Remove Confirmation Modal */}
            <ConfirmationModal
                show={removeConfirm.show}
                title="Remove User Access"
                message={`Are you sure you want to remove ${removeConfirm.user?.username} from ${agentName}? They will no longer be able to access this agent.`}
                onConfirm={confirmRemove}
                onCancel={() => setRemoveConfirm({ show: false, user: null })}
                confirmText="Remove"
                cancelText="Cancel"
                type="danger"
                isLoading={removing}
            />
        </div>
    );
};

export default AgentUsersTab;
