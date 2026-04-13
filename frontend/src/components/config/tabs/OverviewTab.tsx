import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ActiveConfig, ModelInfo } from '../../../contexts/AgentContext';
import type { Agent } from '../../../types/agent';
import { updateAgent, deleteAgent, handleApiError } from '../../../services/api';
import { useToast } from '../../Toast';
import ConfirmationModal from '../../ConfirmationModal';
import { CircleStackIcon, SparklesIcon, AdjustmentsHorizontalIcon, PencilIcon, TrashIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { formatDate } from '../../../utils/datetime';

interface OverviewTabProps {
    activeConfig: ActiveConfig;
    connectionName: string;
    agent?: Agent;
    canEdit?: boolean;
    onAgentUpdate?: () => void;
}

// Helper to format model display
const ModelDisplay: React.FC<{ label: string; model?: ModelInfo; fallback?: string }> = ({ label, model, fallback }) => (
    <div className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0">
        <span className="text-sm text-gray-500">{label}</span>
        <span className="text-sm font-medium text-gray-900">
            {model ? (
                <span className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded">{model.provider_name}</span>
                    {model.display_name}
                </span>
            ) : fallback || 'Not configured'}
        </span>
    </div>
);

export const OverviewTab: React.FC<OverviewTabProps> = ({
    activeConfig,
    connectionName,
    agent,
    canEdit = false,
    onAgentUpdate
}) => {
    const navigate = useNavigate();
    const { success: showSuccess, error: showError } = useToast();

    // Schema is now parsed directly from activeConfig.schema_selection

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

    const llmConf = parseConfig(activeConfig.llm_config);
    const embConf = parseConfig(activeConfig.embedding_config);
    const chunkConf = parseConfig(activeConfig.chunking_config);
    const retConf = parseConfig(activeConfig.retriever_config);

    // Build fileInfo from activeConfig for file-based data sources
    const fileInfo = activeConfig.data_source_type === 'file' && activeConfig.ingestion_file_name
        ? { name: activeConfig.ingestion_file_name, type: activeConfig.ingestion_file_type || 'unknown' }
        : undefined;

    // Parse schema from schema_selection (works for both file and database sources)
    // schema_selection contains the selected_columns from agent config
    let schema: Record<string, string[]> = {};
    if (activeConfig.schema_selection) {
        try {
            const parsed = typeof activeConfig.schema_selection === 'string'
                ? JSON.parse(activeConfig.schema_selection)
                : activeConfig.schema_selection;
            if (typeof parsed === 'object' && parsed !== null && Object.keys(parsed).length > 0) {
                schema = parsed;
            }
        } catch {
            schema = {};
        }
    }

    // Helper to mask sensitive info in DB URL
    const maskDbUrl = (url?: string) => {
        if (!url) return '';
        try {
            // Simple regex to mask password in common DB URIs
            // e.g., postgresql://user:password@host:port/db -> postgresql://user:****@host:port/db
            return url.replace(/:\/\/([^:]+):([^@]+)@/, '://$1:****@');
        } catch {
            return url;
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">


            {/* Main Content Grid */}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* Agent Details Section - At top */}
                {agent && (
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
                )}
                {/* Data Source Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
                            <CircleStackIcon className="w-5 h-5 text-indigo-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">Data Source</h3>
                            <p className="text-xs text-gray-500">Connected knowledge source</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Type</span>
                            <span className="text-sm font-medium text-gray-900 capitalize">{activeConfig.data_source_type || 'Database'}</span>
                        </div>
                        {activeConfig.data_source_type === 'database' ? (
                            <>
                                <div className="flex justify-between py-2 border-b border-gray-100">
                                    <span className="text-sm text-gray-500">Connection</span>
                                    <span className="text-sm font-medium text-gray-900">{connectionName || 'Not set'}</span>
                                </div>
                                {activeConfig.db_url && (
                                    <div className="flex flex-col py-2 border-b border-gray-100">
                                        <span className="text-sm text-gray-500 mb-1">Endpoint</span>
                                        <span className="text-xs font-mono text-gray-600 break-all bg-gray-50 p-2 rounded-md border border-gray-100">
                                            {maskDbUrl(activeConfig.db_url)}
                                        </span>
                                    </div>
                                )}
                            </>
                        ) : (
                            <div className="flex justify-between py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-500">File</span>
                                <span className="text-sm font-medium text-gray-900">{fileInfo?.name || 'Not set'}</span>
                            </div>
                        )}
                        <div className="flex justify-between py-2">
                            <span className="text-sm text-gray-500">Tables/Columns</span>
                            <span className="text-sm font-medium text-gray-900">
                                {Object.keys(schema).length} tables, {Object.values(schema).flat().length} columns
                            </span>
                        </div>
                    </div>
                </div>

                {/* AI Models Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center">
                            <SparklesIcon className="w-5 h-5 text-purple-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">AI Models</h3>
                            <p className="text-xs text-gray-500">Intelligence configuration</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <ModelDisplay
                            label="LLM"
                            model={activeConfig.llm_model}
                            fallback={llmConf.model}
                        />
                        <ModelDisplay
                            label="Embedding"
                            model={activeConfig.embedding_model}
                            fallback={embConf.model}
                        />
                        <ModelDisplay
                            label="Reranker"
                            model={activeConfig.reranker_model}
                            fallback={retConf.rerankerModel || retConf.reranker_model}
                        />
                    </div>
                </div>

                {/* RAG Settings Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center">
                            <AdjustmentsHorizontalIcon className="w-5 h-5 text-green-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">RAG Settings</h3>
                            <p className="text-xs text-gray-500">Retrieval configuration</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Top K (Initial)</span>
                            <span className="text-sm font-medium text-gray-900">{retConf.topKInitial || retConf.top_k_initial || 50}</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Top K (Final)</span>
                            <span className="text-sm font-medium text-gray-900">{retConf.topKFinal || retConf.top_k_final || 10}</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Reranking</span>
                            {(() => {
                                const isEnabled = activeConfig.reranker_model || activeConfig.reranker_model_id || retConf.rerankEnabled || retConf.rerank_enabled;
                                return (
                                    <span className={`text-sm font-medium ${isEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                                        {isEnabled ? 'Enabled' : 'Disabled'}
                                    </span>
                                );
                            })()}
                        </div>
                        <div className="flex justify-between py-2">
                            <span className="text-sm text-gray-500">Hybrid Weights</span>
                            <span className="text-sm font-medium text-gray-900">
                                {(retConf.hybridWeights || retConf.hybrid_weights || [0.75, 0.25]).join(' / ')}
                            </span>
                        </div>
                    </div>
                </div>

            </div>

            {/* Danger Zone - Delete Agent */}
            {agent && canEdit && (
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

export default OverviewTab;
