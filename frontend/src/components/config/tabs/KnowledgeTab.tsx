import React, { useState } from 'react';
import EmbeddingProgress from '../../EmbeddingProgress';
import EmbeddingSettingsModal from '../../EmbeddingSettingsModal';
import ScheduleSelector from '../../ScheduleSelector';
import { CheckCircleIcon, ExclamationTriangleIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import type { ActiveConfig, VectorDbStatus } from '../../../contexts/AgentContext';

interface KnowledgeTabProps {
    activeConfig: ActiveConfig;
    vectorDbStatus: VectorDbStatus | null;
    embeddingJobId: string | null;
    onStartEmbedding: (incremental: boolean, settings?: any) => void;
    onEmbeddingComplete: () => void;
    onEmbeddingError: (err: string) => void;
    onEmbeddingCancel: () => void;
}

export const KnowledgeTab: React.FC<KnowledgeTabProps> = ({
    activeConfig,
    vectorDbStatus,
    embeddingJobId,
    onStartEmbedding,
    onEmbeddingComplete,
    onEmbeddingError,
    onEmbeddingCancel
}) => {
    const [showSettingsModal, setShowSettingsModal] = useState(false);

    // Get vector DB name from config
    const getVectorDbName = () => {
        try {
            const embConf = activeConfig.embedding_config
                ? (typeof activeConfig.embedding_config === 'string'
                    ? JSON.parse(activeConfig.embedding_config)
                    : activeConfig.embedding_config)
                : {};
            return embConf.vectorDbName ||
                (activeConfig.data_source_type === 'database' && activeConfig.connection_id
                    ? `db_connection_${activeConfig.connection_id}_data`
                    : 'default_vector_db');
        } catch {
            return 'default_vector_db';
        }
    };

    // Get chunking config from activeConfig for default settings
    const getChunkingConfig = () => {
        try {
            const chunkConf = activeConfig.chunking_config
                ? (typeof activeConfig.chunking_config === 'string'
                    ? JSON.parse(activeConfig.chunking_config)
                    : activeConfig.chunking_config)
                : {};
            return {
                parent_chunk_size: chunkConf.parentChunkSize || 800,
                parent_chunk_overlap: chunkConf.parentChunkOverlap || 150,
                child_chunk_size: chunkConf.childChunkSize || 200,
                child_chunk_overlap: chunkConf.childChunkOverlap || 50,
            };
        } catch {
            return {
                parent_chunk_size: 800,
                parent_chunk_overlap: 150,
                child_chunk_size: 200,
                child_chunk_overlap: 50,
            };
        }
    };

    // Get complete default settings for the modal
    const getDefaultSettings = () => ({
        batch_size: 128,  // Optimized for GPU
        max_concurrent: 5,
        chunking: getChunkingConfig(),
        parallelization: {
            num_workers: undefined,
            chunking_batch_size: undefined,
            delta_check_batch_size: 50000,
        },
        medical_context_config: {
            medical_context: {},
            clinical_flag_prefixes: ['is_', 'has_', 'was_', 'history_of_', 'confirmed_', 'requires_', 'on_'],
            use_yaml_defaults: true,
        },
        max_consecutive_failures: 5,
        retry_attempts: 3,
    });

    const handleEmbeddingConfirm = (settings: any, incremental: boolean) => {
        onStartEmbedding(incremental, settings);
        setShowSettingsModal(false);
    };

    return (
        <div className="space-y-8">
            {/* Embedding Settings Modal */}
            <EmbeddingSettingsModal
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
                        onComplete={onEmbeddingComplete}
                        onError={onEmbeddingError}
                        onCancel={onEmbeddingCancel}
                    />
                ) : (
                    <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8">
                            <div className="max-w-xl">
                                <h3 className="text-lg font-semibold text-gray-900">Manage Knowledge Base</h3>
                                <p className="text-gray-500 mt-2">
                                    Keep your agent's vector representations up-to-date with your latest data. Update manually or set an automatic sync schedule below.
                                </p>
                            </div>
                            <div className="flex gap-3">
                                <button
                                    onClick={() => setShowSettingsModal(true)}
                                    className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-semibold shadow-sm transition-all hover:scale-105 active:scale-95 flex items-center gap-2"
                                >
                                    <Cog6ToothIcon className="w-4 h-4" />
                                    Update Knowledge
                                </button>
                                <button
                                    onClick={() => {
                                        if (window.confirm('Are you sure you want to rebuild the vector database? This will delete all existing knowledge and re-index everything from scratch. This may take a long time and consume LLM tokens.')) {
                                            onStartEmbedding(false);
                                        }
                                    }}
                                    className="px-6 py-2.5 bg-white border border-red-200 text-red-600 rounded-lg hover:bg-red-50 font-semibold transition-all hover:border-red-300"
                                >
                                    Rebuild DB
                                </button>
                            </div>
                        </div>

                        {/* Vector DB Stats Card */}
                        {vectorDbStatus && (
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8 border-t border-gray-100">
                                <div className="p-4 bg-blue-50/50 rounded-xl border border-blue-100">
                                    <p className="text-xs text-blue-600 font-bold uppercase tracking-wider mb-2">Stored Documents</p>
                                    <div className="flex items-end gap-2">
                                        <p className="text-3xl font-bold text-gray-900">{vectorDbStatus.total_documents_indexed.toLocaleString()}</p>
                                        <p className="text-sm text-gray-500 font-medium mb-1">Items</p>
                                    </div>
                                </div>

                                <div className="p-4 bg-purple-50/50 rounded-xl border border-purple-100">
                                    <p className="text-xs text-purple-600 font-bold uppercase tracking-wider mb-2">Vector Embeddings</p>
                                    <div className="flex items-end gap-2">
                                        <p className="text-3xl font-bold text-gray-900">{vectorDbStatus.total_vectors.toLocaleString()}</p>
                                        <p className="text-sm text-gray-500 font-medium mb-1">Vectors</p>
                                    </div>
                                </div>

                                <div className="p-4 bg-green-50/50 rounded-xl border border-green-100">
                                    <p className="text-xs text-green-600 font-bold uppercase tracking-wider mb-2">Last Synchronized</p>
                                    <div className="flex items-center gap-2 mt-2">
                                        <CheckCircleIcon className="w-6 h-6 text-green-600" />
                                        <p className="text-base font-semibold text-gray-900">
                                            {vectorDbStatus.last_updated_at
                                                ? new Date(vectorDbStatus.last_updated_at + 'Z').toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
                                                : 'Never run'}
                                        </p>
                                    </div>
                                </div>

                                {/* Enhanced Metadata Fields */}
                                <div className="col-span-1 md:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-2">
                                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Embedding Model</p>
                                        <p className="text-sm font-medium text-gray-800 truncate" title={vectorDbStatus.embedding_model || 'N/A'}>
                                            {vectorDbStatus.embedding_model || 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">LLM Model</p>
                                        <p className="text-sm font-medium text-gray-800">
                                            {vectorDbStatus.llm || 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Last Full Sync</p>
                                        <p className="text-sm font-medium text-gray-800">
                                            {vectorDbStatus.last_full_run ? new Date(vectorDbStatus.last_full_run + 'Z').toLocaleDateString() : 'N/A'}
                                        </p>
                                    </div>
                                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                        <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Version</p>
                                        <p className="text-sm font-medium text-gray-800">
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

                                {/* Schedule Selector */}
                                <div className="col-span-1 md:col-span-3 mt-4 pt-6 border-t border-gray-100">
                                    <ScheduleSelector vectorDbName={getVectorDbName()} />
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
