import React, { useState } from 'react';
import ConfigSummary from '../../ConfigSummary';
import EmbeddingProgress from '../../EmbeddingProgress';
import EmbeddingSettingsModal from '../../EmbeddingSettingsModal';
import { CheckCircleIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import type { AdvancedSettings, PromptVersion } from '../../../contexts/AgentContext';
import type { IngestionResponse } from '../../../services/api';

interface SummaryStepProps {
    connectionId: number | null;
    connectionName: string;
    dataSourceType: 'database' | 'file';
    fileUploadResult: IngestionResponse | null;
    selectedSchema: Record<string, string[]>;
    dataDictionary: string;
    history: PromptVersion[];
    advancedSettings: AdvancedSettings;
    embeddingJobId: string | null;
    onStartEmbedding: (incremental: boolean, settings?: any) => void;
    onEmbeddingComplete: () => void;
    onEmbeddingError: (err: string) => void;
    onEmbeddingCancel: () => void;
    onGoToDashboard: () => void;
}

export const SummaryStep: React.FC<SummaryStepProps> = ({
    connectionId,
    connectionName,
    dataSourceType,
    fileUploadResult,
    selectedSchema,
    dataDictionary,
    history,
    advancedSettings,
    embeddingJobId,
    onStartEmbedding,
    onEmbeddingComplete,
    onEmbeddingError,
    onEmbeddingCancel,
    onGoToDashboard
}) => {
    const [showSettingsModal, setShowSettingsModal] = useState(false);
    const activeVersion = history.find(p => p.is_active);

    // Get default settings for the modal from advancedSettings
    const getDefaultSettings = () => ({
        batch_size: 128,
        max_concurrent: 5,
        chunking: {
            parent_chunk_size: advancedSettings.chunking.parentChunkSize,
            parent_chunk_overlap: advancedSettings.chunking.parentChunkOverlap,
            child_chunk_size: advancedSettings.chunking.childChunkSize,
            child_chunk_overlap: advancedSettings.chunking.childChunkOverlap,
        },
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
        <div className="h-full flex flex-col overflow-y-auto overflow-x-hidden p-2 sm:p-6">
            {/* Embedding Settings Modal */}
            <EmbeddingSettingsModal
                isOpen={showSettingsModal}
                onClose={() => setShowSettingsModal(false)}
                onConfirm={handleEmbeddingConfirm}
                defaultSettings={getDefaultSettings()}
            />

            <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Configuration Summary</h2>

            {/* Success Banner */}
            <div className="bg-green-50 p-3 sm:p-4 rounded-md mb-3 sm:mb-4 border border-green-200 flex flex-col sm:flex-row items-start sm:items-center gap-3">
                <div className="flex items-center gap-3 flex-1">
                    <div className="flex-shrink-0">
                        <CheckCircleIcon className="w-5 h-5 sm:w-6 sm:h-6 text-green-600" />
                    </div>
                    <div className="min-w-0">
                        <h3 className="font-bold text-green-900 text-sm sm:text-base">Configuration Published!</h3>
                        <p className="text-xs sm:text-sm text-green-700">Your agent configuration has been saved successfully.</p>
                    </div>
                </div>
                <button
                    onClick={onGoToDashboard}
                    className="w-full sm:w-auto px-3 sm:px-4 py-2 bg-white text-green-700 border border-green-300 rounded font-medium shadow-sm hover:bg-green-50 text-sm"
                >
                    Go to Dashboard
                </button>
            </div>

            {/* PROMINENT: Vector DB Required Warning */}
            {!embeddingJobId && (
                <div className="bg-amber-50 border-2 border-amber-400 rounded-lg p-4 sm:p-6 mb-4 sm:mb-6 shadow-md">
                    <div className="flex flex-col sm:flex-row items-start gap-3 sm:gap-4">
                        <div className="flex-shrink-0">
                            <svg className="w-6 h-6 sm:w-8 sm:h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                        </div>
                        <div className="flex-1 min-w-0">
                            <h3 className="text-base sm:text-lg font-bold text-amber-800 mb-2">
                                Action Required: Build Knowledge Base
                            </h3>
                            <p className="text-xs sm:text-sm text-amber-700 mb-3 sm:mb-4">
                                Your configuration is saved, but <strong>the agent cannot answer questions yet</strong>.
                                You must create the Vector Database to enable the agent's knowledge base.
                            </p>
                            <div className="flex flex-col sm:flex-row flex-wrap gap-2 sm:gap-3">
                                <button
                                    onClick={() => onStartEmbedding(false)}
                                    className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-semibold transition-colors shadow-md flex items-center justify-center gap-2 text-sm"
                                >
                                    <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    Create Vector DB Now
                                </button>
                                <button
                                    onClick={() => setShowSettingsModal(true)}
                                    className="w-full sm:w-auto px-4 py-2.5 sm:py-3 bg-white border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50 font-semibold transition-all flex items-center justify-center gap-2 text-sm"
                                    title="Configure batch size, chunking, parallelization, and more"
                                >
                                    <Cog6ToothIcon className="w-4 h-4 sm:w-5 sm:h-5" />
                                    Advanced Settings
                                </button>
                            </div>
                            <p className="text-xs text-amber-600 mt-2 sm:mt-3">
                                This may take a few minutes depending on your data size.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Embedding Progress (shown when job is running) */}
            {embeddingJobId && (
                <div className="mb-4 sm:mb-6">
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 sm:p-4 mb-3 sm:mb-4">
                        <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2 text-sm sm:text-base">
                            <svg className="animate-spin h-4 w-4 sm:h-5 sm:w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Building Knowledge Base...
                        </h3>
                        <p className="text-xs sm:text-sm text-blue-700">Your agent will be ready to answer questions once this completes.</p>
                    </div>
                    <EmbeddingProgress
                        jobId={embeddingJobId}
                        onComplete={onEmbeddingComplete}
                        onError={onEmbeddingError}
                        onCancel={onEmbeddingCancel}
                    />
                </div>
            )}

            <ConfigSummary
                connectionId={connectionId}
                connectionName={connectionName}
                dataSourceType={dataSourceType}
                fileInfo={fileUploadResult ? { name: fileUploadResult.file_name, type: fileUploadResult.file_type } : undefined}
                schema={selectedSchema}
                dataDictionary={dataDictionary}
                activePromptVersion={typeof activeVersion?.version === 'number' ? activeVersion.version : null}
                totalPromptVersions={history.length}
                lastUpdatedBy={activeVersion?.created_by_username}
                settings={advancedSettings}
            />

            {/* Additional Options (smaller, secondary) */}
            {!embeddingJobId && (
                <div className="mt-4 sm:mt-6 pt-4 sm:pt-6 border-t border-gray-200">
                    <h3 className="text-xs sm:text-sm font-medium text-gray-500 mb-2 sm:mb-3">Additional Options</h3>
                    <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
                        <button
                            onClick={() => onStartEmbedding(true)}
                            className="px-3 sm:px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium transition-colors text-xs sm:text-sm"
                            title="Only process new or changed data"
                        >
                            Incremental Update
                        </button>
                        <button
                            onClick={onGoToDashboard}
                            className="px-3 sm:px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium transition-colors text-xs sm:text-sm"
                        >
                            Skip for Now (Go to Dashboard)
                        </button>
                    </div>
                    <p className="text-[10px] sm:text-xs text-gray-400 mt-2">
                        You can always create or update the vector database later from the Dashboard.
                    </p>
                </div>
            )}
        </div>
    );
};

export default SummaryStep;
