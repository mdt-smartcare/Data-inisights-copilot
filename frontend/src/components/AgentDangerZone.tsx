import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Agent } from '../types/agent';
import { deleteAgent, handleApiError } from '../services/api';
import { useToast } from './Toast';
import ConfirmationModal from './ConfirmationModal';
import { TrashIcon } from '@heroicons/react/24/outline';

interface AgentDangerZoneProps {
    agent: Agent;
    /** Optional redirect path after deletion. Defaults to '/agents' */
    redirectPath?: string;
    /** Optional callback after successful deletion (called before redirect) */
    onDeleted?: () => void;
}

/**
 * Reusable danger zone component for deleting an agent.
 * Includes the delete button and confirmation modal.
 * Used in both OverviewTab (configured agents) and AgentDashboardPage (unconfigured agents).
 */
const AgentDangerZone: React.FC<AgentDangerZoneProps> = ({
    agent,
    redirectPath = '/agents',
    onDeleted
}) => {
    const navigate = useNavigate();
    const { success: showSuccess, error: showError } = useToast();

    // Delete state
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);

    const handleDeleteConfirm = async () => {
        setIsDeleting(true);
        try {
            await deleteAgent(agent.id);
            showSuccess('Agent Deleted', `Agent "${agent.name}" has been permanently deleted.`);
            setShowDeleteModal(false);
            onDeleted?.();
            navigate(redirectPath);
        } catch (err) {
            showError('Delete Failed', handleApiError(err));
            setIsDeleting(false);
        }
    };

    return (
        <>
            <div className="bg-white p-6 rounded-xl border-2 border-red-200">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-red-50 rounded-lg flex items-center justify-center">
                        <TrashIcon className="w-5 h-5 text-red-600" />
                    </div>
                    <div>
                        <h3 className="text-base font-semibold text-red-900">Danger Zone</h3>
                        <p className="text-xs text-red-600">Irreversible actions</p>
                    </div>
                </div>
                <div className="p-4 bg-red-50 rounded-lg border border-red-100">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div>
                            <h4 className="font-medium text-gray-900 text-sm">Delete this agent</h4>
                            <p className="text-xs text-gray-600 mt-0.5">
                                Permanently delete the agent and all associated data.
                            </p>
                        </div>
                        <button
                            onClick={() => setShowDeleteModal(true)}
                            className="flex-shrink-0 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                        >
                            Delete Agent
                        </button>
                    </div>
                </div>
            </div>

            {/* Delete Confirmation Modal */}
            <ConfirmationModal
                show={showDeleteModal}
                title="Delete Agent"
                message={`Are you sure you want to delete "${agent.name}"? This will permanently delete all associated configurations, prompts, user assignments, and vector data. This action cannot be undone.`}
                onConfirm={handleDeleteConfirm}
                onCancel={() => setShowDeleteModal(false)}
                confirmText="Delete Agent"
                type="danger"
                isLoading={isDeleting}
            />
        </>
    );
};

export default AgentDangerZone;
