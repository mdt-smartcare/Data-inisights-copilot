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
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

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

    // Connect to WebSocket
    const connectWebSocket = useCallback(() => {
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
                // Stop polling if we have WebSocket
                if (pollingRef.current) {
                    clearInterval(pollingRef.current);
                    pollingRef.current = null;
                }
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
                            onComplete?.(true);
                        } else if (finished.status === 'FAILED') {
                            onError?.('Job failed');
                        }
                    }
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                // Fall back to polling
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
    }, [jobId, onComplete, onError]);

    // Polling fallback
    const startPolling = useCallback(() => {
        if (pollingRef.current) return;

        const poll = async () => {
            try {
                const data = await getEmbeddingProgress(jobId);
                setProgress(data);

                if (data.status === 'COMPLETED') {
                    onComplete?.(true);
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current);
                        pollingRef.current = null;
                    }
                } else if (data.status === 'FAILED') {
                    onError?.(data.recent_errors?.[0] || 'Job failed');
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current);
                        pollingRef.current = null;
                    }
                } else if (data.status === 'CANCELLED') {
                    onCancel?.();
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current);
                        pollingRef.current = null;
                    }
                }
            } catch (e) {
                console.error('Polling error:', e);
                setError('Failed to fetch progress');
            }
        };

        poll(); // Initial fetch
        pollingRef.current = setInterval(poll, 2000);
    }, [jobId, onComplete, onError, onCancel]);

    // Handle cancel
    const handleCancel = async () => {
        if (isCancelling) return;

        setIsCancelling(true);
        try {
            await cancelEmbeddingJob(jobId);
            onCancel?.();
        } catch (e: any) {
            setError(e.message || 'Failed to cancel job');
        } finally {
            setIsCancelling(false);
        }
    };

    // Initialize connection
    useEffect(() => {
        const wsConnected = connectWebSocket();
        if (!wsConnected) {
            startPolling();
        }

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
            }
        };
    }, [connectWebSocket, startPolling]);

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
                        width: `${progress.progress_percentage}%`,
                        backgroundColor: STATUS_COLORS[progress.status]
                    }}
                ></div>
                <div className="embedding-progress__percentage">
                    {progress.progress_percentage.toFixed(1)}%
                </div>
            </div>

            {/* Stats grid */}
            <div className="embedding-progress__stats">
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Documents</div>
                    <div className="embedding-progress__stat-value">
                        {progress.processed_documents.toLocaleString()} / {progress.total_documents.toLocaleString()}
                    </div>
                </div>
                <div className="embedding-progress__stat">
                    <div className="embedding-progress__stat-label">Batch</div>
                    <div className="embedding-progress__stat-value">
                        {progress.current_batch} / {progress.total_batches}
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
                    ✅ Embedding generation completed successfully!
                </div>
            )}

            {isFailed && (
                <div className="embedding-progress__failed">
                    ❌ Embedding generation failed. Check the errors above.
                </div>
            )}
        </div>
    );
};

export default EmbeddingProgress;
