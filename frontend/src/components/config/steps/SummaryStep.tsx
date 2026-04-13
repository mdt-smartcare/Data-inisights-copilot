import React, { useState, useEffect } from 'react';
import EmbeddingProgress from '../../EmbeddingProgress';
import { 
    CircleStackIcon, 
    ArrowPathIcon, 
    CheckCircleIcon, 
    XCircleIcon,
    ClockIcon,
    ArrowRightIcon
} from '@heroicons/react/24/outline';
import { apiClient } from '../../../services/api';

interface EmbeddingJob {
    job_id: string;
    status: 'QUEUED' | 'PREPARING' | 'EMBEDDING' | 'VALIDATING' | 'STORING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
    total_documents: number;
    processed_documents: number;
    failed_documents: number;
    started_at: string | null;
    completed_at: string | null;
    error_message: string | null;
}

interface SummaryStepProps {
    agentId?: string;
    configId?: number;
    embeddingJobId: string | null;
    onStartEmbedding: (incremental: boolean) => void;
    onEmbeddingComplete: () => void;
    onEmbeddingError: (err: string) => void;
    onEmbeddingCancel: () => void;
    onGoToDashboard: () => void;
}

export const SummaryStep: React.FC<SummaryStepProps> = ({
    agentId,
    configId,
    embeddingJobId,
    onStartEmbedding,
    onEmbeddingComplete,
    onEmbeddingError,
    onEmbeddingCancel,
    onGoToDashboard,
}) => {
    const [embeddingJobs, setEmbeddingJobs] = useState<EmbeddingJob[]>([]);
    const [isLoadingJobs, setIsLoadingJobs] = useState(false);

    // Fetch embedding job history
    useEffect(() => {
        if (configId) {
            fetchEmbeddingJobs();
        }
    }, [configId, embeddingJobId]);

    const fetchEmbeddingJobs = async () => {
        if (!configId) return;
        setIsLoadingJobs(true);
        try {
            const response = await apiClient.get(`/api/v1/embedding-jobs?config_id=${configId}&limit=5`);
            setEmbeddingJobs(response.data || []);
        } catch (error) {
            console.error('Failed to fetch embedding jobs:', error);
        } finally {
            setIsLoadingJobs(false);
        }
    };

    const getStatusBadge = (status: EmbeddingJob['status']) => {
        const statusConfig: Record<string, { bg: string; text: string; icon: typeof ClockIcon; spinning?: boolean }> = {
            QUEUED: { bg: 'bg-gray-100', text: 'text-gray-700', icon: ClockIcon },
            PREPARING: { bg: 'bg-blue-100', text: 'text-blue-700', icon: ArrowPathIcon, spinning: true },
            EMBEDDING: { bg: 'bg-blue-100', text: 'text-blue-700', icon: ArrowPathIcon, spinning: true },
            VALIDATING: { bg: 'bg-indigo-100', text: 'text-indigo-700', icon: ArrowPathIcon, spinning: true },
            STORING: { bg: 'bg-purple-100', text: 'text-purple-700', icon: ArrowPathIcon, spinning: true },
            COMPLETED: { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircleIcon },
            FAILED: { bg: 'bg-red-100', text: 'text-red-700', icon: XCircleIcon },
            CANCELLED: { bg: 'bg-orange-100', text: 'text-orange-700', icon: XCircleIcon },
        };
        const config = statusConfig[status] || statusConfig.QUEUED;
        const Icon = config.icon;
        const statusText = status || 'QUEUED';
        return (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
                <Icon className={`w-3 h-3 ${config.spinning ? 'animate-spin' : ''}`} />
                {statusText.charAt(0) + statusText.slice(1).toLowerCase()}
            </span>
        );
    };

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleString();
    };

    const hasCompletedJob = embeddingJobs.some(job => job.status === 'COMPLETED');

    return (
        <div className="h-full flex flex-col overflow-y-auto overflow-x-hidden p-2 sm:p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4 sm:mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-100 rounded-lg">
                        <CircleStackIcon className="w-5 h-5 sm:w-6 sm:h-6 text-indigo-600" />
                    </div>
                    <div>
                        <h2 className="text-lg sm:text-xl font-semibold text-gray-900">Knowledge Base</h2>
                        <p className="text-xs sm:text-sm text-gray-500">Build and manage your agent's vector database</p>
                    </div>
                </div>
                <button
                    onClick={onGoToDashboard}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    Go to Dashboard
                    <ArrowRightIcon className="w-4 h-4" />
                </button>
            </div>

            {/* Active Embedding Progress (shown when job is running) */}
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

            {/* Action Card - Build Knowledge Base */}
            {!embeddingJobId && (
                <div className={`rounded-lg p-4 sm:p-6 mb-4 sm:mb-6 border-2 ${hasCompletedJob ? 'bg-white border-gray-200' : 'bg-amber-50 border-amber-400 shadow-md'}`}>
                    <div className="flex flex-col sm:flex-row items-start gap-3 sm:gap-4">
                        <div className="flex-shrink-0">
                            {hasCompletedJob ? (
                                <div className="p-2 bg-green-100 rounded-lg">
                                    <CheckCircleIcon className="w-6 h-6 sm:w-8 sm:h-8 text-green-600" />
                                </div>
                            ) : (
                                <svg className="w-6 h-6 sm:w-8 sm:h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                            )}
                        </div>
                        <div className="flex-1 min-w-0">
                            <h3 className={`text-base sm:text-lg font-bold mb-2 ${hasCompletedJob ? 'text-gray-800' : 'text-amber-800'}`}>
                                {hasCompletedJob ? 'Knowledge Base Ready' : 'Action Required: Build Knowledge Base'}
                            </h3>
                            <p className={`text-xs sm:text-sm mb-3 sm:mb-4 ${hasCompletedJob ? 'text-gray-600' : 'text-amber-700'}`}>
                                {hasCompletedJob 
                                    ? 'Your agent is ready to answer questions. You can rebuild or update the knowledge base anytime.'
                                    : <>Your configuration is saved, but <strong>the agent cannot answer questions yet</strong>. You must create the Vector Database to enable the agent's knowledge base.</>
                                }
                            </p>
                            <div className="flex flex-col sm:flex-row flex-wrap gap-2 sm:gap-3">
                                <button
                                    onClick={() => onStartEmbedding(false)}
                                    className={`w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 rounded-lg font-semibold transition-colors shadow-md flex items-center justify-center gap-2 text-sm ${
                                        hasCompletedJob 
                                            ? 'bg-indigo-600 text-white hover:bg-indigo-700' 
                                            : 'bg-amber-600 text-white hover:bg-amber-700'
                                    }`}
                                >
                                    <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    {hasCompletedJob ? 'Rebuild Knowledge Base' : 'Create Vector DB Now'}
                                </button>
                            </div>
                            <p className="text-xs text-gray-500 mt-2 sm:mt-3">
                                Processing time depends on your data size. You can cancel anytime.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Embedding Job History */}
            <div className="bg-white rounded-lg border border-gray-200">
                <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                    <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                        <ClockIcon className="w-4 h-4 text-gray-500" />
                        Recent Embedding Jobs
                    </h3>
                    <button 
                        onClick={fetchEmbeddingJobs}
                        className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
                        title="Refresh"
                    >
                        <ArrowPathIcon className={`w-4 h-4 ${isLoadingJobs ? 'animate-spin' : ''}`} />
                    </button>
                </div>
                <div className="divide-y divide-gray-100">
                    {isLoadingJobs && embeddingJobs.length === 0 ? (
                        <div className="p-8 text-center text-gray-500">
                            <ArrowPathIcon className="w-6 h-6 animate-spin mx-auto mb-2" />
                            Loading...
                        </div>
                    ) : embeddingJobs.length === 0 ? (
                        <div className="p-8 text-center text-gray-500">
                            <CircleStackIcon className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                            <p className="text-sm font-medium">No embedding jobs yet</p>
                            <p className="text-xs mt-1">Start your first embedding job above</p>
                        </div>
                    ) : (
                        embeddingJobs.map((job) => (
                            <div key={job.job_id} className="px-4 py-3 hover:bg-gray-50 transition-colors">
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                    <div className="flex items-center gap-3">
                                        {getStatusBadge(job.status)}
                                        <span className="text-xs text-gray-500 font-mono">
                                            {job.job_id.slice(0, 8)}...
                                        </span>
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        {job.started_at ? formatDate(job.started_at) : 'Not started'}
                                    </div>
                                </div>
                                {(['COMPLETED', 'EMBEDDING', 'PREPARING', 'VALIDATING', 'STORING'].includes(job.status)) && (
                                    <div className="mt-2">
                                        <div className="flex items-center gap-4 text-xs text-gray-600">
                                            <span>
                                                <span className="font-medium">{job.processed_documents.toLocaleString()}</span>
                                                {job.total_documents > 0 && <span className="text-gray-400"> / {job.total_documents.toLocaleString()}</span>} documents
                                            </span>
                                            {job.failed_documents > 0 && (
                                                <span className="text-red-600">
                                                    {job.failed_documents.toLocaleString()} failed
                                                </span>
                                            )}
                                        </div>
                                        {(['EMBEDDING', 'PREPARING', 'VALIDATING', 'STORING'].includes(job.status)) && job.total_documents > 0 && (
                                            <div className="mt-1.5 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-blue-500 rounded-full transition-all duration-300"
                                                    style={{ width: `${Math.round((job.processed_documents / job.total_documents) * 100)}%` }}
                                                />
                                            </div>
                                        )}
                                    </div>
                                )}
                                {job.status === 'FAILED' && job.error_message && (
                                    <p className="mt-2 text-xs text-red-600 truncate" title={job.error_message}>
                                        Error: {job.error_message}
                                    </p>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
};

export default SummaryStep;
