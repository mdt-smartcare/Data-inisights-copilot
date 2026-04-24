import React, { useState, useEffect, useCallback } from 'react';
import EmbeddingProgress from '../../EmbeddingProgress';
import EmbeddingSettingsModal from '../../EmbeddingSettingsModal';
import type { EmbeddingSettings } from '../../EmbeddingSettingsModal';
import { CheckCircleIcon, ExclamationTriangleIcon, Cog6ToothIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import type { VectorDbStatus } from '../../../contexts/AgentContext';
import { useSystemSettings } from '../../../contexts/SystemSettingsContext';
import { useToast } from '../../Toast';
import { formatDateTime } from '../../../utils/datetime';
import {
    startEmbeddingJob,
    getVectorDbStatusByConfig,
    listEmbeddingJobs,
    handleApiError
} from '../../../services/api';

interface KnowledgeTabProps {
    configId: number | undefined;
}

export const KnowledgeTab: React.FC<KnowledgeTabProps> = ({ configId }) => {
    const { success: showSuccess, error: showError } = useToast();
    const { getEmbeddingModalDefaults } = useSystemSettings();

    // Internal state - KnowledgeTab owns its domain
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [vectorDbStatus, setVectorDbStatus] = useState<VectorDbStatus | null>(null);
    const [isLoadingStatus, setIsLoadingStatus] = useState(true);
    const [showSettingsModal, setShowSettingsModal] = useState(false);

    // Load vector DB status
    const loadVectorDbStatus = useCallback(async () => {
        if (!configId) return;
        setIsLoadingStatus(true);
        try {
            const status = await getVectorDbStatusByConfig(configId);
            setVectorDbStatus(status);
        } catch (err) {
            console.log('Could not fetch vector DB status:', err);
            setVectorDbStatus(null);
        } finally {
            setIsLoadingStatus(false);
        }
    }, [configId]);

    // Check for running embedding jobs
    const checkForRunningJob = useCallback(async () => {
        if (!configId) return;
        try {
            const jobs = await listEmbeddingJobs({ config_id: configId, limit: 1 });
            if (jobs.length > 0) {
                const latestJob = jobs[0];
                const activeStatuses = ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING'];
                if (activeStatuses.includes(latestJob.status)) {
                    setEmbeddingJobId(latestJob.job_id);
                }
            }
        } catch (err) {
            console.error('Failed to check for running jobs:', err);
        }
    }, [configId]);

    useEffect(() => {
        loadVectorDbStatus();
        checkForRunningJob();
    }, [loadVectorDbStatus, checkForRunningJob]);

    // Get default settings for the modal (excluding chunking - backend uses agent_config)
    const getDefaultSettings = () => {
        const systemDefaults = getEmbeddingModalDefaults();
        return {
            batch_size: systemDefaults.batch_size,
            max_concurrent: systemDefaults.max_concurrent,
            parallelization: systemDefaults.parallelization,
            medical_context_config: {
                medical_context: {},
                clinical_flag_prefixes: ['is_', 'has_', 'was_', 'history_of_', 'confirmed_', 'requires_', 'on_'],
                use_yaml_defaults: true,
            },
            max_consecutive_failures: systemDefaults.max_consecutive_failures,
            retry_attempts: systemDefaults.retry_attempts,
        };
    };

    // Start embedding job - all logic contained here
    const handleStartEmbedding = async (incremental: boolean, settings?: EmbeddingSettings) => {
        if (!configId) return;
        try {
            const batchSize = settings?.batch_size || 50;
            const maxConcurrent = settings?.max_concurrent || 5;

            const result = await startEmbeddingJob({
                config_id: configId,
                batch_size: batchSize,
                max_concurrent: maxConcurrent,
                incremental: incremental,
                parallelization: settings?.parallelization,
                medical_context_config: settings?.medical_context_config,
                max_consecutive_failures: settings?.max_consecutive_failures,
                retry_attempts: settings?.retry_attempts,
            });
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };

    // Embedding callbacks - all handled internally
    const handleEmbeddingComplete = async () => {
        showSuccess('Embeddings Generated', 'Knowledge base updated successfully');
        setEmbeddingJobId(null);
        await loadVectorDbStatus(); // Refresh status
    };

    const handleEmbeddingError = (err: string) => {
        showError('Embedding Failed', err);
        setEmbeddingJobId(null);
    };

    const handleEmbeddingCancel = () => {
        showError('Job Cancelled', 'Embedding generation cancelled');
        setEmbeddingJobId(null);
    };

    const handleEmbeddingConfirm = (settings: EmbeddingSettings, incremental: boolean) => {
        handleStartEmbedding(incremental, settings);
        setShowSettingsModal(false);
    };

    // Show loading state while fetching initial status
    if (isLoadingStatus && !embeddingJobId) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                <span className="ml-3 text-gray-500">Loading knowledge base status...</span>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Embedding Settings Modal */}
            <EmbeddingSettingsModal
                key={showSettingsModal ? 'open' : 'closed'}
                isOpen={showSettingsModal}
                onClose={() => setShowSettingsModal(false)}
                onConfirm={handleEmbeddingConfirm}
                defaultSettings={getDefaultSettings()}
            />

            {/* Embedding Section */}
            <div>
                <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                    <svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                    Knowledge Base Management
                </h2>
                {embeddingJobId ? (
                    <EmbeddingProgress
                        jobId={embeddingJobId}
                        onComplete={handleEmbeddingComplete}
                        onError={handleEmbeddingError}
                        onCancel={handleEmbeddingCancel}
                    />
                ) : (
                    <div className="bg-white p-4 sm:p-8 rounded-xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                        <div className="flex flex-col gap-4 sm:gap-6 mb-6 sm:mb-8">
                            <div className="max-w-xl">
                                <h3 className="text-base sm:text-lg font-semibold text-gray-900">Manage Knowledge Base</h3>
                                <p className="text-sm text-gray-500 mt-2">
                                    Keep your agent's vector representations up-to-date with your latest data. Update manually or set an automatic sync schedule below.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2 sm:gap-3">
                                <button
                                    onClick={() => handleStartEmbedding(true)}
                                    className="flex-1 sm:flex-none px-4 sm:px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-semibold shadow-sm transition-all hover:scale-105 active:scale-95 flex items-center justify-center gap-2 text-sm sm:text-base"
                                    title="Quick incremental sync - only processes new or changed data"
                                >
                                    <ArrowPathIcon className="w-4 h-4" />
                                    <span>Sync Now</span>
                                </button>
                                <button
                                    onClick={() => setShowSettingsModal(true)}
                                    className="px-3 sm:px-4 py-2.5 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-semibold transition-all flex items-center justify-center gap-2 text-sm sm:text-base"
                                    title="Configure batch size, chunking, parallelization, and more"
                                >
                                    <Cog6ToothIcon className="w-4 h-4" />
                                    <span className="hidden sm:inline">Advanced</span>
                                </button>
                                <button
                                    onClick={() => {
                                        if (window.confirm('Are you sure you want to rebuild the vector database? This will delete all existing knowledge and re-index everything from scratch. This may take a long time and consume LLM tokens.')) {
                                            handleStartEmbedding(false);
                                        }
                                    }}
                                    className="px-3 sm:px-6 py-2.5 bg-white border border-red-200 text-red-600 rounded-lg hover:bg-red-50 font-semibold transition-all hover:border-red-300 text-sm sm:text-base"
                                >
                                    <span className="sm:hidden">Rebuild</span>
                                    <span className="hidden sm:inline">Rebuild DB</span>
                                </button>
                            </div>
                        </div>

                        {/* Vector DB Stats Card - Show empty state if no vectorDbStatus */}
                        {vectorDbStatus ? (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-6 pt-6 sm:pt-8 border-t border-gray-100">
                                <div className="p-3 sm:p-4 bg-blue-50/50 rounded-xl border border-blue-100">
                                    <p className="text-xs text-blue-600 font-bold uppercase tracking-wider mb-2">Stored Documents</p>
                                    <div className="flex items-end gap-2">
                                        <p className="text-2xl sm:text-3xl font-bold text-gray-900">{vectorDbStatus.total_documents_indexed.toLocaleString()}</p>
                                        <p className="text-sm text-gray-500 font-medium mb-1">Items</p>
                                    </div>
                                </div>

                                <div className="p-3 sm:p-4 bg-purple-50/50 rounded-xl border border-purple-100">
                                    <p className="text-xs text-purple-600 font-bold uppercase tracking-wider mb-2">Vector Embeddings</p>
                                    <div className="flex items-end gap-2">
                                        <p className="text-2xl sm:text-3xl font-bold text-gray-900">{vectorDbStatus.total_vectors.toLocaleString()}</p>
                                        <p className="text-sm text-gray-500 font-medium mb-1">Vectors</p>
                                    </div>
                                </div>

                                <div className="p-3 sm:p-4 bg-green-50/50 rounded-xl border border-green-100 sm:col-span-2 md:col-span-1">
                                    <p className="text-xs text-green-600 font-bold uppercase tracking-wider mb-2">Last Synchronized</p>
                                    <div className="flex items-center gap-2 mt-2">
                                        <CheckCircleIcon className="w-5 h-5 sm:w-6 sm:h-6 text-green-600" />
                                        <p className="text-sm sm:text-base font-semibold text-gray-900">
                                            {vectorDbStatus.last_updated_at
                                                ? formatDateTime(vectorDbStatus.last_updated_at)
                                                : 'Never run'}
                                        </p>
                                    </div>
                                </div>

                                {/* Enhanced Metadata Fields */}
                                <div className="col-span-1 sm:col-span-2 md:col-span-3 grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mt-2">
                                    <div className="p-2 sm:p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Vector Database</p>
                                        <p className="text-xs sm:text-sm font-medium text-gray-800 capitalize flex items-center gap-1.5">
                                            {vectorDbStatus.vector_db_type === 'qdrant' && (
                                                <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                                            )}
                                            {vectorDbStatus.vector_db_type === 'chroma' && (
                                                <span className="w-2 h-2 rounded-full bg-orange-500"></span>
                                            )}
                                            {vectorDbStatus.vector_db_type || 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-2 sm:p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Embedding Model</p>
                                        <p className="text-xs sm:text-sm font-medium text-gray-800 truncate" title={vectorDbStatus.embedding_model || 'N/A'}>
                                            {vectorDbStatus.embedding_model || 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-2 sm:p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">LLM Model</p>
                                        <p className="text-xs sm:text-sm font-medium text-gray-800 truncate">
                                            {vectorDbStatus.llm || 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-2 sm:p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Last Full Sync</p>
                                        <p className="text-xs sm:text-sm font-medium text-gray-800">
                                            {vectorDbStatus.last_full_run ? formatDateTime(vectorDbStatus.last_full_run) : 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-2 sm:p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Version</p>
                                        <p className="text-xs sm:text-sm font-medium text-gray-800">
                                            {vectorDbStatus.version}
                                        </p>
                                    </div>
                                </div>

                                {/* Diagnostics Alert */}
                                {vectorDbStatus.diagnostics && vectorDbStatus.diagnostics.length > 0 && (
                                    <div className="col-span-1 md:col-span-3 mt-4">
                                        <div className="p-4 bg-amber-50 rounded-xl border border-amber-100">
                                            <div className="flex items-center gap-2 mb-2 text-amber-800">
                                                <ExclamationTriangleIcon className="w-5 h-5" />
                                                <span className="font-bold text-sm">System Diagnostics</span>
                                            </div>
                                            <ul className="space-y-1">
                                                {vectorDbStatus.diagnostics.map((diag, i) => (
                                                    <li key={i} className={`text-sm ${diag.level === 'error' ? 'text-red-700' : 'text-amber-700'} flex items-start gap-2`}>
                                                        <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                                                        {diag.message}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>
                                )}

                                {/* Schedule Selector - Disabled until backend API is implemented
                                   Backend routes for /api/v1/vector-db/schedule/* are not yet available.
                                   See: migrations/001_initial_schema.sql for vector_db_schedules table schema */}
                                {/* <div className="col-span-1 md:col-span-3 mt-4 pt-6 border-t border-gray-100">
                                    <ScheduleSelector vectorDbName={getVectorDbName()} />
                                </div> */}
                            </div>
                        ) : (
                            <div className="pt-6 sm:pt-8 border-t border-gray-100">
                                <div className="flex flex-col items-center justify-center text-center p-8 bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
                                    <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
                                        <svg className="w-8 h-8 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                                        </svg>
                                    </div>
                                    <h3 className="text-lg font-semibold text-gray-900 mb-2">No Knowledge Base Yet</h3>
                                    <p className="text-sm text-gray-500 max-w-md mb-4">
                                        This agent doesn't have a vector database yet. Click "Sync Now" or "Rebuild DB" above to create embeddings from your data source.
                                    </p>
                                    <div className="flex items-center gap-2 text-xs text-gray-400">
                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                        <span>First sync may take several minutes depending on data size</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default KnowledgeTab;
