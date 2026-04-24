import React, { useState } from 'react';
import type { Agent } from '../types/agent';
import { updateAgent, handleApiError } from '../services/api';
import { useToast } from './Toast';
import { PencilIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { formatDate } from '../utils/datetime';

interface AgentDetailsCardProps {
    agent: Agent;
    canEdit?: boolean;
    onAgentUpdate?: () => void;
}

/**
 * Reusable card component for displaying and editing agent details (name & description).
 * Used in both OverviewTab (configured agents) and AgentDashboardPage (unconfigured agents).
 */
const AgentDetailsCard: React.FC<AgentDetailsCardProps> = ({
    agent,
    canEdit = false,
    onAgentUpdate
}) => {
    const { success: showSuccess, error: showError } = useToast();

    // Edit state
    const [isEditing, setIsEditing] = useState(false);
    const [editName, setEditName] = useState(agent.name || '');
    const [editDescription, setEditDescription] = useState(agent.description || '');
    const [isSaving, setIsSaving] = useState(false);

    const handleStartEdit = () => {
        setEditName(agent.name || '');
        setEditDescription(agent.description || '');
        setIsEditing(true);
    };

    const handleCancelEdit = () => {
        setIsEditing(false);
        setEditName(agent.name || '');
        setEditDescription(agent.description || '');
    };

    const handleSaveEdit = async () => {
        if (!editName.trim()) return;

        setIsSaving(true);
        try {
            await updateAgent(agent.id, {
                name: editName.trim(),
                description: editDescription.trim() || undefined
            });
            showSuccess('Agent Updated', 'Agent details have been updated successfully.');
            setIsEditing(false);
            onAgentUpdate?.();
        } catch (err) {
            showError('Update Failed', handleApiError(err));
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-slate-50 rounded-lg flex items-center justify-center">
                        <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-base font-semibold text-gray-900">Agent Details</h3>
                        <p className="text-xs text-gray-500">Basic information</p>
                    </div>
                </div>
                {canEdit && !isEditing && (
                    <button
                        onClick={handleStartEdit}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                        <PencilIcon className="w-4 h-4" />
                        Edit
                    </button>
                )}
            </div>

            {isEditing ? (
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Agent Name <span className="text-red-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                            placeholder="Enter agent name"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Description
                        </label>
                        <textarea
                            value={editDescription}
                            onChange={(e) => setEditDescription(e.target.value)}
                            rows={2}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none text-sm"
                            placeholder="Enter agent description (optional)"
                        />
                    </div>
                    <div className="flex justify-end gap-2">
                        <button
                            onClick={handleCancelEdit}
                            disabled={isSaving}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
                        >
                            <XMarkIcon className="w-4 h-4" />
                            Cancel
                        </button>
                        <button
                            onClick={handleSaveEdit}
                            disabled={isSaving || !editName.trim()}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                        >
                            {isSaving ? (
                                <>
                                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                    Saving...
                                </>
                            ) : (
                                <>
                                    <CheckIcon className="w-4 h-4" />
                                    Save
                                </>
                            )}
                        </button>
                    </div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <p className="text-xs font-medium text-gray-500 uppercase mb-1">Name</p>
                        <p className="text-sm font-semibold text-gray-900">{agent.name}</p>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-gray-500 uppercase mb-1">Created</p>
                        <p className="text-sm text-gray-700">
                            {agent.created_at ? formatDate(agent.created_at) : 'Unknown'}
                        </p>
                    </div>
                    <div className="md:col-span-2">
                        <p className="text-xs font-medium text-gray-500 uppercase mb-1">Description</p>
                        <p className="text-sm text-gray-700">{agent.description || <span className="text-gray-400 italic">No description</span>}</p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AgentDetailsCard;
