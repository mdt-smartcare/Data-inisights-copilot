/**
 * EmbeddingProgress component for real-time embedding job progress display.
 * Uses WebSocket for live updates with polling fallback.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { EmbeddingJobProgress, EmbeddingJobStatus, WebSocketProgressMessage } from '../types/rag';
import { getEmbeddingProgress, cancelEmbeddingJob } from '../services/api';
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

    // Memoize the handlers to prevent dependency churn
    const onCompleteRef = useRef(onComplete);
    const onErrorRef = useRef(onError);
    const onCancelRef = useRef(onCancel);

    useEffect(() => {
        onCompleteRef.current = onComplete;
        onErrorRef.current = onError;
        onCancelRef.current = onCancel;
    }, [onComplete, onError, onCancel]);

    const isFinalState = (status: EmbeddingJobStatus) =>
        ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status);

    // Format time remaining
    const formatTimeRemaining = (seconds: number | null): string => {
        if (seconds === null || seconds < 0) return '--:--';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    // Format elapsed time
    const formatElapsed = (seconds: number | null): string => {
        if (seconds === null) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    // Connect to WebSocket
    const connectWebSocket = useCallback(() => {
        // If we already have a final state, don't connect
        if (progress && isFinalState(progress.status)) return false;

        const token = localStorage.getItem('auth_token');
        if (!token) {
            console.warn('No auth token for WebSocket, falling back to polling');
            return false;
        }

        const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/embedding-progress/${jobId}?token=${token}`;

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
                        setProgress({
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
                        });
                    } else if (data.event === 'job_finished') {
                        const finished = data as any;
                        if (finished.status === 'COMPLETED') {
                            onCompleteRef.current?.(true);
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
    }, [jobId, progress?.status, stopPolling]); // Depend on status to prevent reconnecting if done

    // Polling fallback
    const startPolling = useCallback(() => {
        stopPolling(); // Ensure clean slate

        // If we already have a final state, don't poll
        if (progress && isFinalState(progress.status)) return;

        const poll = async () => {
            try {
                const data = await getEmbeddingProgress(jobId);
                setProgress(data);

                if (data.status === 'COMPLETED') {
                    stopPolling();
                    onCompleteRef.current?.(true);
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
    }, [jobId, progress?.status, stopPolling]);

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

        const wsConnected = connectWebSocket();
        if (!wsConnected) {
            startPolling();
        }

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
                        {formatTimeRemaining(progress.estimated_time_remaining_seconds)}
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Elapsed</div>
                    <div className="embedding-progress__stat-value">
                        {formatElapsed(progress.elapsed_seconds)}
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
                <div className="embedding-progress__complete">
                    Embedding generation completed successfully!
                </div>
            )}

            {isFailed && (
                <div className="embedding-progress__failed">
                    Embedding generation failed. Check the errors above.
                </div>
            )}
        </div>
    );
};

export default EmbeddingProgress;
