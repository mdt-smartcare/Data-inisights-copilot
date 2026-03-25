import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CommandLineIcon, PencilIcon, TrashIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import type { ActiveConfig } from '../../../contexts/AgentContext';
import type { Agent } from '../../../types/agent';
import { updateAgent, deleteAgent, handleApiError } from '../../../services/api';
import { useToast } from '../../Toast';
import ConfirmationModal from '../../ConfirmationModal';
import { useSystemSettings } from '../../../contexts/SystemSettingsContext';
import { formatDate } from '../../../utils/datetime';

interface SettingsTabProps {
    activeConfig?: ActiveConfig | null;
    agent?: Agent;
    canEdit?: boolean;
    onAgentUpdate?: () => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
    activeConfig,
    agent,
    canEdit = false,
    onAgentUpdate
}) => {
    const navigate = useNavigate();
    const { success: showSuccess, error: showError } = useToast();
    const { advancedSettings } = useSystemSettings();
    
    // Edit state
    const [isEditing, setIsEditing] = useState(false);
    const [editName, setEditName] = useState(agent?.name || '');
    const [editDescription, setEditDescription] = useState(agent?.description || '');
    const [isSaving, setIsSaving] = useState(false);
    
    // Delete state
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);

    const parseConfig = (config: string | undefined | null) => {
        if (!config) return {};
        try {
            return typeof config === 'string' ? JSON.parse(config) : config;
        } catch {
            return {};
        }
    };

    const llmConf = activeConfig ? parseConfig(activeConfig.llm_config) : {};
    const embConf = activeConfig ? parseConfig(activeConfig.embedding_config) : {};
    const chunkConf = activeConfig ? parseConfig(activeConfig.chunking_config) : {};
    const retConf = activeConfig ? parseConfig(activeConfig.retriever_config) : {};

    const handleStartEdit = () => {
        setEditName(agent?.name || '');
        setEditDescription(agent?.description || '');
        setIsEditing(true);
    };

    const handleCancelEdit = () => {
        setIsEditing(false);
        setEditName(agent?.name || '');
        setEditDescription(agent?.description || '');
    };

    const handleSaveEdit = async () => {
        if (!agent || !editName.trim()) return;
        
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

    const handleDeleteConfirm = async () => {
        if (!agent) return;
        
        setIsDeleting(true);
        try {
            await deleteAgent(agent.id);
            showSuccess('Agent Deleted', `Agent "${agent.name}" has been permanently deleted.`);
            setShowDeleteModal(false);
            navigate('/agents');
        } catch (err) {
            showError('Delete Failed', handleApiError(err));
            setIsDeleting(false);
        }
    };

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Agent Details Section */}
            {agent && (
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                                <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-gray-900">Agent Details</h3>
                                <p className="text-sm text-gray-500">Basic agent information</p>
                            </div>
                        </div>
                        {canEdit && !isEditing && (
                            <button
                                onClick={handleStartEdit}
                                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
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
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
                                    rows={3}
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                                    placeholder="Enter agent description (optional)"
                                />
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    onClick={handleCancelEdit}
                                    disabled={isSaving}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
                                >
                                    <XMarkIcon className="w-4 h-4" />
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSaveEdit}
                                    disabled={isSaving || !editName.trim()}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
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
                                            Save Changes
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-4">
                            <div className="p-4 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Name</p>
                                <p className="text-base font-semibold text-gray-900">{agent.name}</p>
                            </div>
                            <div className="p-4 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Description</p>
                                <p className="text-sm text-gray-700">{agent.description || <span className="text-gray-400 italic">No description provided</span>}</p>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="p-4 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Type</p>
                                    <p className="text-sm font-medium text-gray-700">{agent.type}</p>
                                </div>
                                <div className="p-4 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Created</p>
                                    <p className="text-sm font-medium text-gray-700">
                                        {agent.created_at ? formatDate(agent.created_at) : 'Unknown'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Config Specs - Only show when activeConfig exists */}
            {activeConfig && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* LLM Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-indigo-50 rounded-xl flex items-center justify-center">
                            <CommandLineIcon className="w-6 h-6 text-indigo-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Logic Engine (LLM)</h3>
                            <p className="text-sm text-gray-500">Core reasoning configuration</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Model Name</p>
                                <p className="text-sm font-mono font-bold text-gray-700">{llmConf.model || 'gpt-4o'}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Temperature</p>
                                <p className="text-sm font-semibold text-gray-700">{llmConf.temperature ?? 0.0}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Max Tokens</p>
                                <p className="text-sm font-semibold text-gray-700">{llmConf.maxTokens || 4096}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Embedding Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-emerald-50 rounded-xl flex items-center justify-center">
                            <svg className="w-6 h-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Knowledge Engine</h3>
                            <p className="text-sm text-gray-500">Vectorization & Chunking</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Embedding Model</p>
                                <p className="text-sm font-mono font-bold text-gray-700">{embConf.model || 'BAAI/bge-m3'}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Parent Size</p>
                                <p className="text-sm font-semibold text-gray-700">{chunkConf.parentChunkSize || advancedSettings.chunking.parentChunkSize} chars</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Child Size</p>
                                <p className="text-sm font-semibold text-gray-700">{chunkConf.childChunkSize || advancedSettings.chunking.childChunkSize} chars</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Retriever Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md col-span-1 md:col-span-2">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-purple-50 rounded-xl flex items-center justify-center">
                            <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Retrieval Strategy</h3>
                            <p className="text-sm text-gray-500">Search weights and reranking</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            {retConf.hybridWeights && (
                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Semantic Weight</p>
                                    <p className="text-sm font-bold text-purple-700">{(retConf.hybridWeights[0] * 100).toFixed(0)}%</p>
                                </div>
                            )}
                            {retConf.hybridWeights && (
                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Keyword Weight</p>
                                    <p className="text-sm font-bold text-purple-700">{(retConf.hybridWeights[1] * 100).toFixed(0)}%</p>
                                </div>
                            )}
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Top-K Final</p>
                                <p className="text-sm font-bold text-gray-700">{retConf.topKFinal || 10}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Reranking</p>
                                <p className={`text-sm font-bold ${retConf.rerankEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                                    {retConf.rerankEnabled ? 'Enabled' : 'Disabled'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            )}

            {/* Danger Zone - Delete Agent */}
            {agent && canEdit && (
                <div className="bg-white p-8 rounded-2xl border-2 border-red-200 shadow-sm">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-red-50 rounded-xl flex items-center justify-center">
                            <TrashIcon className="w-6 h-6 text-red-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-red-900">Danger Zone</h3>
                            <p className="text-sm text-red-600">Irreversible actions</p>
                        </div>
                    </div>
                    <div className="p-4 bg-red-50 rounded-lg border border-red-100">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                            <div>
                                <h4 className="font-semibold text-gray-900">Delete this agent</h4>
                                <p className="text-sm text-gray-600 mt-1">
                                    This will permanently delete the agent and all associated configurations, prompts, user assignments, and vector data.
                                    This action cannot be undone.
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
            )}

            {/* Delete Confirmation Modal */}
            <ConfirmationModal
                show={showDeleteModal}
                title="Delete Agent"
                message={`Are you sure you want to delete "${agent?.name}"? This will permanently delete all associated configurations, prompts, user assignments, and vector data. This action cannot be undone.`}
                onConfirm={handleDeleteConfirm}
                onCancel={() => setShowDeleteModal(false)}
                confirmText="Delete Agent"
                type="danger"
                isLoading={isDeleting}
            />
        </div>
    );
};

export default SettingsTab;
