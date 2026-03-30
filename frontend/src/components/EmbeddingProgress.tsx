/**
 * EmbeddingProgress component for real-time embedding job progress display.
 * Uses WebSocket for live updates with polling fallback.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { EmbeddingJobProgress, EmbeddingJobStatus, WebSocketProgressMessage } from '../types/rag';
import { getEmbeddingProgress, cancelEmbeddingJob } from '../services/api';
import { oidcService } from '../services/oidcService';
import { API_BASE_URL } from '../config';
import { formatTimeRemaining, formatElapsedTime } from '../utils/datetime';
import './EmbeddingProgress.css';

interface EmbeddingProgressProps {
    jobId: string;
    onComplete?: (success: boolean) => void;
    onError?: (error: string) => void;
    onCancel?: () => void;
}

const STATUS_LABELS: Record<EmbeddingJobStatus, string> = {
    QUEUED: 'Queued',
    PREPARING: 'Preparing Documents',
    EMBEDDING: 'Generating Embeddings',
    VALIDATING: 'Validating',
    STORING: 'Storing Vectors',
    COMPLETED: 'Completed',
    FAILED: 'Failed',
    CANCELLED: 'Cancelled',
};

const STATUS_COLORS: Record<EmbeddingJobStatus, string> = {
    QUEUED: 'var(--color-info)',
    PREPARING: 'var(--color-info)',
    EMBEDDING: 'var(--color-primary)',
    VALIDATING: 'var(--color-warning)',
    STORING: 'var(--color-info)',
    COMPLETED: 'var(--color-success)',
    FAILED: 'var(--color-error)',
    CANCELLED: 'var(--color-warning)',
};

const PHASE_ORDER: EmbeddingJobStatus[] = [
    'QUEUED',
    'PREPARING',
    'EMBEDDING',
    'VALIDATING',
    'STORING',
    'COMPLETED',
];

export const EmbeddingProgress: React.FC<EmbeddingProgressProps> = ({
    jobId,
    onComplete,
    onError,
    onCancel,
}) => {
    const [progress, setProgress] = useState<EmbeddingJobProgress | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isCancelling, setIsCancelling] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const completedRef = useRef(false); // Guard against multiple onComplete calls

    // Client-side timer state for real-time ETA/elapsed updates
    const [clientElapsedSeconds, setClientElapsedSeconds] = useState<number | null>(null);
    const [clientEtaSeconds, setClientEtaSeconds] = useState<number | null>(null);
    const clientTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const lastBackendUpdateRef = useRef<number>(Date.now());

    // Memoize the handlers to prevent dependency churn
    const onCompleteRef = useRef(onComplete);
    const onErrorRef = useRef(onError);
    const onCancelRef = useRef(onCancel);

    useEffect(() => {
        onCompleteRef.current = onComplete;
        onErrorRef.current = onError;
        onCancelRef.current = onCancel;
    }, [onComplete, onError, onCancel]);

    // Safe wrapper that only calls onComplete once
    const triggerComplete = useCallback((success: boolean) => {
        if (completedRef.current) return;
        completedRef.current = true;
        onCompleteRef.current?.(success);
    }, []);

    const isFinalState = (status: EmbeddingJobStatus) =>
        ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status);

    // Update client-side timers when backend data arrives
    const syncWithBackendData = useCallback((data: EmbeddingJobProgress) => {
        lastBackendUpdateRef.current = Date.now();
        setClientElapsedSeconds(data.elapsed_seconds);
        setClientEtaSeconds(data.estimated_time_remaining_seconds);
    }, []);

    // Start client-side timer for real-time updates
    useEffect(() => {
        // Only run timer when job is active
        const isActive = progress && ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING'].includes(progress.status);
        
        if (isActive) {
            // Clear any existing timer
            if (clientTimerRef.current) {
                clearInterval(clientTimerRef.current);
            }

            // Start new timer that updates every second
            clientTimerRef.current = setInterval(() => {
                setClientElapsedSeconds(prev => prev !== null ? prev + 1 : null);
                setClientEtaSeconds(prev => {
                    if (prev === null || prev <= 0) return prev;
                    return Math.max(0, prev - 1);
                });
            }, 1000);

            return () => {
                if (clientTimerRef.current) {
                    clearInterval(clientTimerRef.current);
                    clientTimerRef.current = null;
                }
            };
        } else {
            // Job not active, stop timer
            if (clientTimerRef.current) {
                clearInterval(clientTimerRef.current);
                clientTimerRef.current = null;
            }
        }
    }, [progress?.status]);

    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    // Connect to WebSocket
    const connectWebSocket = useCallback(async (): Promise<boolean> => {
        // If we already have a final state, don't connect
        if (progress && isFinalState(progress.status)) return false;

        const token = await oidcService.getAccessToken();
        if (!token) {
            console.warn('No auth token for WebSocket, falling back to polling');
            return false;
        }

        // Connect directly to backend WebSocket endpoint
        const wsBaseUrl = API_BASE_URL.replace(/^http/, 'ws');
        const wsUrl = `${wsBaseUrl}/api/v1/ws/embedding-progress/${jobId}?token=${token}`;

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('WebSocket connected for job:', jobId);
                stopPolling();
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as WebSocketProgressMessage;

                    if (data.event === 'embedding_progress') {
                        const progressData: EmbeddingJobProgress = {
                            job_id: data.job_id,
                            status: data.status,
                            phase: data.phase,
                            total_documents: data.progress.total_documents,
                            processed_documents: data.progress.processed_documents,
                            failed_documents: data.progress.failed_documents,
                            progress_percentage: data.progress.percentage,
                            current_batch: data.progress.current_batch,
                            total_batches: data.progress.total_batches,
                            documents_per_second: data.performance.documents_per_second,
                            estimated_time_remaining_seconds: data.performance.estimated_time_remaining_seconds,
                            elapsed_seconds: data.performance.elapsed_seconds,
                            errors_count: data.errors.count,
                            recent_errors: data.errors.recent,
                            started_at: null,
                            completed_at: null,
                        };
                        setProgress(progressData);
                        // Sync client-side timers with backend data
                        syncWithBackendData(progressData);
                    } else if (data.event === 'job_finished') {
                        const finished = data as any;
                        if (finished.status === 'COMPLETED') {
                            triggerComplete(true);
                            ws.close();
                        } else if (finished.status === 'FAILED') {
                            onErrorRef.current?.('Job failed');
                            ws.close();
                        }
                    }
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                startPolling();
            };

            ws.onclose = () => {
                console.log('WebSocket closed');
                wsRef.current = null;
            };

            return true;
        } catch (e) {
            console.error('WebSocket connection failed:', e);
            return false;
        }
    }, [jobId, progress?.status, stopPolling, triggerComplete]); // Depend on status to prevent reconnecting if done

    // Polling fallback
    const startPolling = useCallback(() => {
        stopPolling(); // Ensure clean slate

        // If we already have a final state, don't poll
        if (progress && isFinalState(progress.status)) return;

        const poll = async () => {
            try {
                const data = await getEmbeddingProgress(jobId);
                setProgress(data);
                // Sync client-side timers with backend data
                syncWithBackendData(data);

                if (data.status === 'COMPLETED') {
                    stopPolling();
                    triggerComplete(true);
                } else if (data.status === 'FAILED') {
                    stopPolling();
                    onErrorRef.current?.(data.recent_errors?.[0] || 'Job failed');
                } else if (data.status === 'CANCELLED') {
                    stopPolling();
                    onCancelRef.current?.();
                }
            } catch (e) {
                console.error('Polling error:', e);
                // If 404, might be done or bad ID, stop polling to prevent spam
                stopPolling();
                // Don't error immediately, maybe just one fail? 
                // But for this spam issue, better to back off.
                // We will setError to visually indicate issue.
                setError('Connection lost');
            }
        };

        poll(); // Initial fetch
        pollingRef.current = setInterval(poll, 2000);
    }, [jobId, progress?.status, stopPolling, triggerComplete, syncWithBackendData]);

    // Handle cancel
    const handleCancel = async () => {
        if (isCancelling) return;

        setIsCancelling(true);
        try {
            await cancelEmbeddingJob(jobId);
            onCancelRef.current?.();
        } catch (e: any) {
            setError(e.message || 'Failed to cancel job');
        } finally {
            setIsCancelling(false);
        }
    };

    // Initialize connection
    useEffect(() => {
        // If we have a final state, stop everything
        if (progress && isFinalState(progress.status)) {
            stopPolling();
            if (wsRef.current) {
                wsRef.current.close();
            }
            return;
        }

        // Async connection with polling fallback
        (async () => {
            const wsConnected = await connectWebSocket();
            if (!wsConnected) {
                startPolling();
            }
        })();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            stopPolling();
        };
    }, [connectWebSocket, startPolling, stopPolling, progress?.status]);

    // Get current phase index for phase indicators
    const getCurrentPhaseIndex = (status: EmbeddingJobStatus): number => {
        return PHASE_ORDER.indexOf(status);
    };

    if (error) {
        return (
            <div className="embedding-progress embedding-progress--error">
                <div className="embedding-progress__error-icon">⚠️</div>
                <div className="embedding-progress__error-message">{error}</div>
            </div>
        );
    }

    if (!progress) {
        return (
            <div className="embedding-progress embedding-progress--loading">
                <div className="embedding-progress__spinner"></div>
                <div className="embedding-progress__loading-text">Connecting...</div>
            </div>
        );
    }

    const isRunning = ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING'].includes(progress.status);
    const isComplete = progress.status === 'COMPLETED';
    const isFailed = progress.status === 'FAILED';
    const currentPhaseIndex = getCurrentPhaseIndex(progress.status);

    // Fix display for completed state
    const displayPercentage = isComplete ? 100 : progress.progress_percentage;
    const displayProcessed = isComplete ? progress.total_documents : progress.processed_documents;
    const displayBatch = isComplete ? progress.total_batches : progress.current_batch;

    return (
        <div className={`embedding-progress embedding-progress--${progress.status.toLowerCase()}`}>
            {/* Header */}
            <div className="embedding-progress__header">
                <div className="embedding-progress__title">
                    <span className="embedding-progress__status-indicator" style={{ backgroundColor: STATUS_COLORS[progress.status] }}></span>
                    {STATUS_LABELS[progress.status]}
                </div>
                {isRunning && (
                    <button
                        className="embedding-progress__cancel-btn"
                        onClick={handleCancel}
                        disabled={isCancelling}
                    >
                        {isCancelling ? 'Cancelling...' : 'Cancel'}
                    </button>
                )}
            </div>

            {/* Phase description */}
            {progress.phase && (
                <div className="embedding-progress__phase">{progress.phase}</div>
            )}

            {/* Progress bar */}
            <div className="embedding-progress__bar-container">
                <div
                    className="embedding-progress__bar"
                    style={{
                        width: `${displayPercentage}%`,
                        backgroundColor: STATUS_COLORS[progress.status]
                    }}
                ></div>
                <div className="embedding-progress__percentage">
                    {displayPercentage.toFixed(1)}%
                </div>
            </div>

            {/* Stats grid */}
            <div className="embedding-progress__stats">
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Documents</div>
                    <div className="embedding-progress__stat-value">
                        {displayProcessed.toLocaleString()} / {progress.total_documents.toLocaleString()}
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Batch</div>
                    <div className="embedding-progress__stat-value">
                        {displayBatch} / {progress.total_batches}
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Speed</div>
                    <div className="embedding-progress__stat-value">
                        {progress.documents_per_second?.toFixed(1) || '--'} docs/s
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">ETA</div>
                    <div className="embedding-progress__stat-value">
                        {formatTimeRemaining(clientEtaSeconds)}
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Elapsed</div>
                    <div className="embedding-progress__stat-value">
                        {formatElapsedTime(clientElapsedSeconds)}
                    </div>
                </div>
                {progress.failed_documents > 0 && (
                    <div className="embedding-progress__stat embedding-progress__stat--error">
                        <div className="embedding-progress__stat-label">Errors</div>
                        <div className="embedding-progress__stat-value">
                            {progress.failed_documents}
                        </div>
                    </div>
                )}
            </div>

            {/* Phase indicators */}
            <div className="embedding-progress__phases">
                {PHASE_ORDER.slice(0, -1).map((phase, index) => (
                    <div
                        key={phase}
                        className={`embedding-progress__phase-step ${index < currentPhaseIndex ? 'embedding-progress__phase-step--completed' :
                            index === currentPhaseIndex ? 'embedding-progress__phase-step--active' :
                                'embedding-progress__phase-step--pending'
                            }`}
                    >
                        <div className="embedding-progress__phase-icon">
                            {index < currentPhaseIndex ? '✓' : index + 1}
                        </div>
                        <div className="embedding-progress__phase-label">
                            {STATUS_LABELS[phase]}
                        </div>
                    </div>
                ))}
            </div>

            {/* Error messages */}
            {progress.recent_errors && progress.recent_errors.length > 0 && (
                <div className="embedding-progress__errors">
                    <div className="embedding-progress__errors-title">Recent Errors:</div>
                    <ul className="embedding-progress__errors-list">
                        {progress.recent_errors.slice(0, 3).map((err, i) => (
                            <li key={i}>{err}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Completion message */}
            {isComplete && (
                <div className="embedding-progress__complete mt-4 pb-2">
                    <div className="mb-4">Embedding generation completed successfully!</div>
                    <button
                        onClick={() => triggerComplete(true)}
                        className="px-6 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-colors shadow-sm w-full md:w-auto"
                    >
                        Finish & Close
                    </button>
                </div>
            )}

            {isFailed && (
                <div className="embedding-progress__failed mt-4 pb-2">
                    <div className="mb-4">Embedding generation failed. Check the errors above.</div>
                    <button
                        onClick={() => onCancelRef.current?.()}
                        className="px-6 py-2 bg-red-600 text-white font-medium rounded-lg hover:bg-red-700 transition-colors shadow-sm w-full md:w-auto"
                    >
                        Dismiss
                    </button>
                </div>
            )}
        </div>
    );
};

export default EmbeddingProgress;
