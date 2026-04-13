import React, { useState, useEffect, useCallback } from 'react';
import {
    ClockIcon,
    CheckCircleIcon,
    EyeIcon,
    PlayIcon,
    ArrowPathIcon,
    ChevronLeftIcon,
    ChevronRightIcon,
    XMarkIcon,
    CircleStackIcon,
    CpuChipIcon,
    SparklesIcon,
    AdjustmentsHorizontalIcon,
    CubeTransparentIcon,
    DocumentTextIcon,
    ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import {
    getConfigHistoryPaginated,
    getConfigById,
    activateConfig,
    type ConfigSummary,
    type ConfigHistoryResponse,
    type AgentConfig,
} from '../../../services/api';
import { formatDateTime } from '../../../utils/datetime';
import { useToast } from '../../Toast';
import ConfirmationModal from '../../ConfirmationModal';

interface ConfigHistoryTabProps {
    agentId: string;
    onRollback?: () => void;
}

export const ConfigHistoryTab: React.FC<ConfigHistoryTabProps> = ({
    agentId,
    onRollback,
}) => {
    const { success: showSuccess, error: showError } = useToast();

    // Table state
    const [historyData, setHistoryData] = useState<ConfigHistoryResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 10;

    // Modal state
    const [selectedConfig, setSelectedConfig] = useState<AgentConfig | null>(null);
    const [isLoadingDetails, setIsLoadingDetails] = useState(false);
    const [showDetailModal, setShowDetailModal] = useState(false);

    // Activate state
    const [activatingId, setActivatingId] = useState<number | null>(null);
    const [confirmActivate, setConfirmActivate] = useState<ConfigSummary | null>(null);

    const loadHistory = useCallback(async (page: number = 1) => {
        setIsLoading(true);
        setError(null);
        try {
            const result = await getConfigHistoryPaginated(agentId, page, pageSize);
            setHistoryData(result);
            setCurrentPage(page);
        } catch (e) {
            setError('Failed to load configuration history');
            console.error('Failed to load config history:', e);
        } finally {
            setIsLoading(false);
        }
    }, [agentId, pageSize]);

    useEffect(() => {
        loadHistory(1);
    }, [loadHistory]);

    const handleViewDetails = async (configId: number) => {
        setIsLoadingDetails(true);
        setShowDetailModal(true);
        try {
            const fullConfig = await getConfigById(configId);
            setSelectedConfig(fullConfig);
        } catch {
            showError('Load Failed', 'Could not load configuration details.');
            setShowDetailModal(false);
        } finally {
            setIsLoadingDetails(false);
        }
    };

    const handleActivate = async (config: ConfigSummary) => {
        if (config.status === 'draft') {
            showError('Cannot Activate', 'Draft configurations must be published first.');
            return;
        }

        setActivatingId(config.id);
        try {
            await activateConfig(config.id);
            showSuccess('Configuration Activated', `Version ${config.version} is now active.`);
            await loadHistory(currentPage);
            onRollback?.();
        } catch {
            showError('Activation Failed', 'Could not activate configuration.');
        } finally {
            setActivatingId(null);
            setConfirmActivate(null);
        }
    };

    const getStatusBadge = (status: string, isActive: boolean) => {
        if (isActive) {
            return (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                    <CheckCircleIcon className="w-3 h-3" />
                    Active
                </span>
            );
        }
        if (status === 'draft') {
            return (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
                    Draft
                </span>
            );
        }
        return (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                Published
            </span>
        );
    };

    const getEmbeddingBadge = (status: string) => {
        const statusMap: Record<string, { bg: string; text: string; label: string }> = {
            completed: { bg: 'bg-green-100', text: 'text-green-700', label: 'Ready' },
            in_progress: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Building' },
            failed: { bg: 'bg-red-100', text: 'text-red-700', label: 'Failed' },
            not_started: { bg: 'bg-gray-100', text: 'text-gray-600', label: 'Pending' },
        };
        const s = statusMap[status] || statusMap.not_started;
        return (
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${s.bg} ${s.text}`}>
                {s.label}
            </span>
        );
    };

    // Loading state
    if (isLoading && !historyData) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-3 text-gray-500">Loading configuration history...</span>
            </div>
        );
    }

    // Error state
    if (error) {
        return (
            <div className="p-6 bg-red-50 rounded-xl border border-red-200">
                <div className="flex items-center gap-3 text-red-700">
                    <ExclamationTriangleIcon className="w-6 h-6" />
                    <span className="font-medium">{error}</span>
                </div>
                <button
                    onClick={() => loadHistory(1)}
                    className="mt-3 text-sm text-red-600 hover:text-red-700 underline flex items-center gap-1"
                >
                    <ArrowPathIcon className="w-4 h-4" />
                    Retry
                </button>
            </div>
        );
    }

    // Empty state
    if (!historyData || historyData.configs.length === 0) {
        return (
            <div className="p-12 text-center bg-gray-50 rounded-xl border border-gray-200">
                <ClockIcon className="w-12 h-12 mx-auto mb-4 text-gray-400" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No Configuration History</h3>
                <p className="text-gray-500">
                    Complete the setup wizard to create your first configuration.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                        <ClockIcon className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-gray-900">Configuration History</h2>
                        <p className="text-sm text-gray-500">{historyData.total} version{historyData.total !== 1 ? 's' : ''}</p>
                    </div>
                </div>
                <button
                    onClick={() => loadHistory(currentPage)}
                    disabled={isLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                >
                    <ArrowPathIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Table */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Version
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Data Source
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    LLM
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Embedding
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Vector DB
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Created
                                </th>
                                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {historyData.configs.map((config) => (
                                <tr key={config.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-sm font-semibold text-gray-900">v{config.version}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {getStatusBadge(config.status, config.is_active)}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-sm text-gray-700">{config.data_source_name || '-'}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-sm text-gray-700">{config.llm_model_name || '-'}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-sm text-gray-700">{config.embedding_model_name || '-'}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {getEmbeddingBadge(config.embedding_status)}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <span className="text-sm text-gray-500">{formatDateTime(config.created_at)}</span>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-right">
                                        <div className="flex items-center justify-end gap-2">
                                            <button
                                                onClick={() => handleViewDetails(config.id)}
                                                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 rounded-md hover:bg-blue-100 transition-colors"
                                            >
                                                <EyeIcon className="w-3.5 h-3.5" />
                                                View
                                            </button>
                                            {!config.is_active && config.status !== 'draft' && (
                                                <button
                                                    onClick={() => setConfirmActivate(config)}
                                                    disabled={activatingId === config.id}
                                                    className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-green-600 bg-green-50 rounded-md hover:bg-green-100 transition-colors disabled:opacity-50"
                                                >
                                                    {activatingId === config.id ? (
                                                        <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
                                                    ) : (
                                                        <PlayIcon className="w-3.5 h-3.5" />
                                                    )}
                                                    Enable
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                {historyData.total_pages > 1 && (
                    <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
                        <div className="text-sm text-gray-500">
                            Page {historyData.page} of {historyData.total_pages} ({historyData.total} total)
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => loadHistory(currentPage - 1)}
                                disabled={currentPage <= 1 || isLoading}
                                className="p-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-200 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                <ChevronLeftIcon className="w-5 h-5" />
                            </button>
                            <button
                                onClick={() => loadHistory(currentPage + 1)}
                                disabled={currentPage >= historyData.total_pages || isLoading}
                                className="p-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-200 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                <ChevronRightIcon className="w-5 h-5" />
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Activate Confirmation Modal */}
            <ConfirmationModal
                show={!!confirmActivate}
                title="Enable Configuration"
                message={`Are you sure you want to enable Version ${confirmActivate?.version}? This will make it the active configuration for this agent.`}
                onConfirm={() => confirmActivate && handleActivate(confirmActivate)}
                onCancel={() => setConfirmActivate(null)}
                confirmText="Enable"
                type="info"
                isLoading={activatingId === confirmActivate?.id}
            />

            {/* Detail Modal */}
            {showDetailModal && (
                <ConfigDetailModal
                    config={selectedConfig}
                    isLoading={isLoadingDetails}
                    onClose={() => {
                        setShowDetailModal(false);
                        setSelectedConfig(null);
                    }}
                />
            )}
        </div>
    );
};

// ==========================================
// Config Detail Modal Component
// ==========================================

interface ConfigDetailModalProps {
    config: AgentConfig | null;
    isLoading: boolean;
    onClose: () => void;
}

const ConfigDetailModal: React.FC<ConfigDetailModalProps> = ({ config, isLoading, onClose }) => {
    const parseConfig = (c: unknown): Record<string, unknown> => {
        if (!c) return {};
        try {
            return typeof c === 'string' ? JSON.parse(c) : (c as Record<string, unknown>);
        } catch {
            return {};
        }
    };

    const parseSelectedColumns = (
        cols: string[] | Record<string, string[]> | undefined | null
    ): Record<string, string[]> => {
        if (!cols) return {};
        if (Array.isArray(cols)) return { file: cols };
        return cols;
    };

    if (isLoading) {
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                <div className="bg-white rounded-xl p-8 flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                    <span className="text-gray-700">Loading configuration details...</span>
                </div>
            </div>
        );
    }

    if (!config) return null;

    const llmConf = parseConfig(config.llm_config);
    const embConf = parseConfig(config.embedding_config);
    const chunkConf = parseConfig(config.chunking_config);
    const ragConf = parseConfig(config.rag_config);
    const dataDictionary = parseConfig(config.data_dictionary);
    const selectedCols = parseSelectedColumns(config.selected_columns);

    const tableCount = Object.keys(selectedCols).length;
    const columnCount = Object.values(selectedCols).flat().length;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
                    <div>
                        <h3 className="text-lg font-bold text-gray-900">
                            Configuration Version {config.version}
                        </h3>
                        <p className="text-sm text-gray-500">
                            Created {formatDateTime(config.created_at)}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                        <XMarkIcon className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    {/* Status Row */}
                    <div className="flex items-center gap-4">
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                            config.is_active
                                ? 'bg-green-100 text-green-700'
                                : config.status === 'draft'
                                ? 'bg-yellow-100 text-yellow-700'
                                : 'bg-gray-100 text-gray-600'
                        }`}>
                            {config.is_active ? 'Active' : config.status === 'draft' ? 'Draft' : 'Published'}
                        </span>
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                            config.embedding_status === 'completed'
                                ? 'bg-green-100 text-green-700'
                                : config.embedding_status === 'in_progress'
                                ? 'bg-yellow-100 text-yellow-700'
                                : config.embedding_status === 'failed'
                                ? 'bg-red-100 text-red-700'
                                : 'bg-gray-100 text-gray-600'
                        }`}>
                            Vector DB: {(config.embedding_status || 'not_started').replace('_', ' ')}
                        </span>
                    </div>

                    {/* Settings Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Data Source */}
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <CircleStackIcon className="w-5 h-5 text-indigo-600" />
                                <h4 className="font-semibold text-gray-900">Data Source</h4>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Name</span>
                                    <span className="font-medium text-gray-900">{config.data_source?.title || '-'}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Tables</span>
                                    <span className="font-medium text-gray-900">{tableCount}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Columns</span>
                                    <span className="font-medium text-gray-900">{columnCount}</span>
                                </div>
                            </div>
                        </div>

                        {/* LLM Settings */}
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <CpuChipIcon className="w-5 h-5 text-blue-600" />
                                <h4 className="font-semibold text-gray-900">LLM Settings</h4>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Model</span>
                                    <span className="font-medium text-gray-900">{String(llmConf.model || 'gpt-4o')}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Temperature</span>
                                    <span className="font-medium text-gray-900">{String(llmConf.temperature ?? 0)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Max Tokens</span>
                                    <span className="font-medium text-gray-900">{String(llmConf.maxTokens || llmConf.max_tokens || 4096)}</span>
                                </div>
                            </div>
                        </div>

                        {/* Embedding Settings */}
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <SparklesIcon className="w-5 h-5 text-purple-600" />
                                <h4 className="font-semibold text-gray-900">Embedding Settings</h4>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Model</span>
                                    <span className="font-medium text-gray-900">{String(embConf.model || 'BAAI/bge-m3')}</span>
                                </div>
                                {config.vector_collection_name && (
                                    <div className="flex justify-between">
                                        <span className="text-gray-500">Collection</span>
                                        <span className="font-medium text-gray-900 truncate max-w-[150px]" title={config.vector_collection_name}>
                                            {config.vector_collection_name}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* RAG Settings */}
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <AdjustmentsHorizontalIcon className="w-5 h-5 text-green-600" />
                                <h4 className="font-semibold text-gray-900">RAG Settings</h4>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Top-K Initial</span>
                                    <span className="font-medium text-gray-900">{String(ragConf.topKInitial || ragConf.top_k_initial || 50)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Top-K Final</span>
                                    <span className="font-medium text-gray-900">{String(ragConf.topKFinal || ragConf.top_k_final || 10)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Reranking</span>
                                    <span className="font-medium text-gray-900">
                                        {ragConf.rerankEnabled || ragConf.rerank_enabled ? 'Enabled' : 'Disabled'}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Chunking Settings */}
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <CubeTransparentIcon className="w-5 h-5 text-orange-600" />
                                <h4 className="font-semibold text-gray-900">Chunking Settings</h4>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Parent Chunk</span>
                                    <span className="font-medium text-gray-900">{String(chunkConf.parentChunkSize || chunkConf.parent_chunk_size || 512)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Parent Overlap</span>
                                    <span className="font-medium text-gray-900">{String(chunkConf.parentChunkOverlap || chunkConf.parent_chunk_overlap || 100)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Child Chunk</span>
                                    <span className="font-medium text-gray-900">{String(chunkConf.childChunkSize || chunkConf.child_chunk_size || 128)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Child Overlap</span>
                                    <span className="font-medium text-gray-900">{String(chunkConf.childChunkOverlap || chunkConf.child_chunk_overlap || 25)}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Selected Columns */}
                    {tableCount > 0 && (
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <CircleStackIcon className="w-5 h-5 text-cyan-600" />
                                <h4 className="font-semibold text-gray-900">Selected Columns ({columnCount} total)</h4>
                            </div>
                            <div className="space-y-3 max-h-48 overflow-y-auto">
                                {Object.entries(selectedCols).map(([table, columns]) => (
                                    <div key={table}>
                                        <p className="text-sm font-medium text-gray-700 mb-1">{table}</p>
                                        <div className="flex flex-wrap gap-1">
                                            {columns.map((col) => (
                                                <span
                                                    key={col}
                                                    className="px-2 py-0.5 bg-white border border-gray-200 text-gray-600 text-xs rounded"
                                                >
                                                    {col}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Data Dictionary */}
                    {Object.keys(dataDictionary).length > 0 && (
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <DocumentTextIcon className="w-5 h-5 text-amber-600" />
                                <h4 className="font-semibold text-gray-900">Data Dictionary</h4>
                            </div>
                            <div className="bg-white border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto">
                                <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                                    {JSON.stringify(dataDictionary, null, 2)}
                                </pre>
                            </div>
                        </div>
                    )}

                    {/* System Prompt */}
                    {config.system_prompt && (
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <DocumentTextIcon className="w-5 h-5 text-blue-600" />
                                <h4 className="font-semibold text-gray-900">System Prompt</h4>
                            </div>
                            <div className="bg-white border border-gray-200 rounded-lg p-3 max-h-64 overflow-y-auto">
                                <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">
                                    {config.system_prompt}
                                </pre>
                            </div>
                        </div>
                    )}

                    {/* Example Questions */}
                    {config.example_questions && config.example_questions.length > 0 && (
                        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 mb-3">
                                <DocumentTextIcon className="w-5 h-5 text-teal-600" />
                                <h4 className="font-semibold text-gray-900">Example Questions</h4>
                            </div>
                            <ul className="space-y-1">
                                {config.example_questions.map((q, i) => (
                                    <li key={i} className="text-sm text-gray-700 pl-4 relative before:content-['•'] before:absolute before:left-0 before:text-gray-400">
                                        {q}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfigHistoryTab;
