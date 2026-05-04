import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../Toast';
import Alert from '../Alert';
import ConfirmationModal from '../ConfirmationModal';
import UserTable from '../UserTable';
import SearchInput from '../SearchInput';
import { getAgentUsers, assignUserToAgent, revokeUserAccess, handleApiError } from '../../services/api';
import type { AgentUser, SearchUser } from '../../services/api';
import UserSearchInput from './UserSearchInput';

interface AgentUsersTabProps {
    agentId: string;
    agentName: string;
}

const AgentUsersTab: React.FC<AgentUsersTabProps> = ({ agentId, agentName }) => {
    const { user } = useAuth();
    const { success, error: showError } = useToast();
    
    // Users assigned to this agent
    const [agentUsers, setAgentUsers] = useState<AgentUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    // Pagination state
    const [page, setPage] = useState(1);
    const [pageSize] = useState(10);
    const [totalItems, setTotalItems] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    
    // Search state
    const [search, setSearch] = useState('');
    
    // Selected users to add (chips)
    const [selectedUsers, setSelectedUsers] = useState<SearchUser[]>([]);
    const [assigning, setAssigning] = useState(false);
    
    // Remove confirmation modal
    const [removeConfirm, setRemoveConfirm] = useState<{ show: boolean; user: AgentUser | null }>({ show: false, user: null });
    const [removing, setRemoving] = useState(false);

    const loadAgentUsers = useCallback(async (currentPage: number, currentSearch?: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await getAgentUsers(agentId, currentPage, pageSize, currentSearch);
            setAgentUsers(response.users || []);
            setTotalItems(response.total);
            setTotalPages(response.pages);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    }, [agentId, pageSize]);

    useEffect(() => {
        loadAgentUsers(page, search);
    }, [loadAgentUsers, page, search]);

    const handlePageChange = (newPage: number) => {
        setPage(newPage);
    };

    const handleSearchChange = (value: string) => {
        setSearch(value);
        setPage(1); // Reset to first page on search
    };

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
            await loadAgentUsers(page, search);
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
            await loadAgentUsers(page, search);
        } catch (err) {
            showError('Failed to remove user', handleApiError(err));
        } finally {
            setRemoving(false);
        }
    };

    // Get IDs of users already assigned to exclude from search
    const excludeUserIds: string[] = agentUsers.map(u => u.id);

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
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                        <div>
                            <h3 className="text-lg font-semibold text-gray-900">Assigned Users</h3>
                            <p className="text-sm text-gray-500 mt-1">
                                Users who have access to {agentName}
                            </p>
                        </div>
                        <SearchInput
                            value={search}
                            onChange={handleSearchChange}
                            placeholder="Search assigned users..."
                            className="sm:w-64"
                        />
                    </div>
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

                <UserTable
                    users={agentUsers}
                    loading={loading}
                    dateField="granted_at"
                    dateColumnLabel="Granted"
                    pagination={{
                        page,
                        pageSize,
                        totalItems,
                        totalPages,
                        onPageChange: handlePageChange,
                    }}
                    emptyMessage={search ? `No users found matching "${search}"` : "No users assigned"}
                    emptySubMessage={search ? "Try adjusting your search terms" : "Add users using the form above"}
                    renderActions={(agentUser) => (
                        agentUser.username !== user?.username ? (
                            <button 
                                onClick={() => handleRemoveClick(agentUser)} 
                                className="px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
                            >
                                Remove
                            </button>
                        ) : null
                    )}
                />
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
