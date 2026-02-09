import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { EmbeddingProgress } from '../../components/EmbeddingProgress';
import * as api from '../../services/api';

// Mock the api module
vi.mock('../../services/api', () => ({
    getEmbeddingProgress: vi.fn(),
    cancelEmbeddingJob: vi.fn(),
}));

// Mock WebSocket
class MockWebSocket {
    url: string;
    onopen: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    readyState: number = WebSocket.CONNECTING;

    constructor(url: string) {
        this.url = url;
        // Simulate connection after a tick
        setTimeout(() => {
            this.readyState = WebSocket.OPEN;
            this.onopen?.(new Event('open'));
        }, 0);
    }

    close() {
        this.readyState = WebSocket.CLOSED;
        this.onclose?.(new CloseEvent('close'));
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    send(_data: string) { }
}

describe('EmbeddingProgress', () => {
    const mockProgress = {
        job_id: 'job-123',
        status: 'EMBEDDING' as const,
        phase: 'Processing batch 5 of 10',
        total_documents: 100,
        processed_documents: 50,
        failed_documents: 2,
        progress_percentage: 50,
        current_batch: 5,
        total_batches: 10,
        documents_per_second: 5.5,
        estimated_time_remaining_seconds: 90,
        elapsed_seconds: 60,
        errors_count: 2,
        recent_errors: ['Error processing doc-1', 'Error processing doc-2'],
        started_at: '2024-01-15T10:00:00Z',
        completed_at: null,
    };

    let originalWebSocket: typeof WebSocket;
    let originalLocalStorage: Storage;

    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers({ shouldAdvanceTime: true });

        originalWebSocket = global.WebSocket;
        global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

        originalLocalStorage = global.localStorage;
        const localStorageMock = {
            getItem: vi.fn().mockReturnValue(null), // No token = fallback to polling
            setItem: vi.fn(),
            removeItem: vi.fn(),
            clear: vi.fn(),
            length: 0,
            key: vi.fn(),
        };
        Object.defineProperty(global, 'localStorage', { value: localStorageMock, writable: true });
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.useRealTimers();
        global.WebSocket = originalWebSocket;
        Object.defineProperty(global, 'localStorage', { value: originalLocalStorage, writable: true });
    });

    it('shows loading state initially', async () => {
        vi.mocked(api.getEmbeddingProgress).mockImplementation(() => new Promise(() => { })); // Never resolves

        render(<EmbeddingProgress jobId="job-123" />);

        expect(screen.getByText('Connecting...')).toBeInTheDocument();
    });

    it('displays progress after fetching', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Generating Embeddings').length).toBeGreaterThan(0);
        });
    });

    it('displays phase description when available', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Processing batch 5 of 10')).toBeInTheDocument();
        });
    });

    it('displays progress percentage', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('50.0%')).toBeInTheDocument();
        });
    });

    it('displays document count', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('50 / 100')).toBeInTheDocument();
        });
    });

    it('displays batch progress', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('5 / 10')).toBeInTheDocument();
        });
    });

    it('displays documents per second speed', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('5.5 docs/s')).toBeInTheDocument();
        });
    });

    it('displays elapsed time', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('1:00')).toBeInTheDocument();
        });
    });

    it('displays estimated time remaining', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('1:30')).toBeInTheDocument();
        });
    });

    it('shows error count when there are failed documents', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Errors')).toBeInTheDocument();
            expect(screen.getByText('2')).toBeInTheDocument();
        });
    });

    it('displays recent errors list', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Recent Errors:')).toBeInTheDocument();
            expect(screen.getByText('Error processing doc-1')).toBeInTheDocument();
            expect(screen.getByText('Error processing doc-2')).toBeInTheDocument();
        });
    });

    it('shows cancel button when job is running', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Cancel')).toBeInTheDocument();
        });
    });

    it('calls cancelEmbeddingJob when cancel is clicked', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);
        vi.mocked(api.cancelEmbeddingJob).mockResolvedValue({ status: 'cancelled', job_id: 'job-123', message: 'Job cancelled' });
        const onCancel = vi.fn();

        render(<EmbeddingProgress jobId="job-123" onCancel={onCancel} />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Cancel')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('Cancel'));

        await waitFor(() => {
            expect(api.cancelEmbeddingJob).toHaveBeenCalledWith('job-123');
        });
    });

    it('shows cancelling state while cancel is in progress', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);
        vi.mocked(api.cancelEmbeddingJob).mockImplementation(() => new Promise(() => { }));

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Cancel')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('Cancel'));

        await waitFor(() => {
            expect(screen.getByText('Cancelling...')).toBeInTheDocument();
        });
    });

    it('shows error state when cancel fails', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);
        vi.mocked(api.cancelEmbeddingJob).mockRejectedValue(new Error('Cancel failed'));

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        fireEvent.click(screen.getByText('Cancel'));

        await waitFor(() => {
            expect(screen.getByText('Cancel failed')).toBeInTheDocument();
        });
    });

    it('shows completion message when job completes', async () => {
        const completedProgress = {
            ...mockProgress,
            status: 'COMPLETED' as const,
            progress_percentage: 100,
            processed_documents: 100,
            current_batch: 10,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(completedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Embedding generation completed successfully!')).toBeInTheDocument();
        });
    });

    it('shows failure message when job fails', async () => {
        const failedProgress = {
            ...mockProgress,
            status: 'FAILED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(failedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Embedding generation failed. Check the errors above.')).toBeInTheDocument();
        });
    });

    it('calls onComplete when job completes successfully', async () => {
        const completedProgress = {
            ...mockProgress,
            status: 'COMPLETED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(completedProgress);
        const onComplete = vi.fn();

        render(<EmbeddingProgress jobId="job-123" onComplete={onComplete} />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(onComplete).toHaveBeenCalledWith(true);
        });
    });

    it('calls onError when job fails', async () => {
        const failedProgress = {
            ...mockProgress,
            status: 'FAILED' as const,
            recent_errors: ['Critical error occurred'],
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(failedProgress);
        const onError = vi.fn();

        render(<EmbeddingProgress jobId="job-123" onError={onError} />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(onError).toHaveBeenCalledWith('Critical error occurred');
        });
    });

    it('calls onCancel when job is cancelled', async () => {
        const cancelledProgress = {
            ...mockProgress,
            status: 'CANCELLED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(cancelledProgress);
        const onCancel = vi.fn();

        render(<EmbeddingProgress jobId="job-123" onCancel={onCancel} />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(onCancel).toHaveBeenCalled();
        });
    });

    it('hides cancel button for completed jobs', async () => {
        const completedProgress = {
            ...mockProgress,
            status: 'COMPLETED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(completedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Completed')).toBeInTheDocument();
        });

        expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
    });

    it('hides cancel button for failed jobs', async () => {
        const failedProgress = {
            ...mockProgress,
            status: 'FAILED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(failedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Failed')).toBeInTheDocument();
        });

        expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
    });

    it('displays correct status labels for different statuses', async () => {
        const queuedProgress = {
            ...mockProgress,
            status: 'QUEUED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(queuedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Queued').length).toBeGreaterThan(0);
        });
    });

    it('displays preparing status', async () => {
        const preparingProgress = {
            ...mockProgress,
            status: 'PREPARING' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(preparingProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Preparing Documents').length).toBeGreaterThan(0);
        });
    });

    it('displays validating status', async () => {
        const validatingProgress = {
            ...mockProgress,
            status: 'VALIDATING' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(validatingProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Validating').length).toBeGreaterThan(0);
        });
    });

    it('displays storing status', async () => {
        const storingProgress = {
            ...mockProgress,
            status: 'STORING' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(storingProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Storing Vectors').length).toBeGreaterThan(0);
        });
    });

    it('displays cancelled status', async () => {
        const cancelledProgress = {
            ...mockProgress,
            status: 'CANCELLED' as const,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(cancelledProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Cancelled')).toBeInTheDocument();
        });
    });

    it('handles null speed gracefully', async () => {
        const progressWithNullSpeed = {
            ...mockProgress,
            documents_per_second: null,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(progressWithNullSpeed);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('-- docs/s')).toBeInTheDocument();
        });
    });

    it('handles null ETA gracefully', async () => {
        const progressWithNullEta = {
            ...mockProgress,
            estimated_time_remaining_seconds: null,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(progressWithNullEta);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('--:--')).toBeInTheDocument();
        });
    });

    it('displays error when polling fails', async () => {
        vi.mocked(api.getEmbeddingProgress).mockRejectedValue(new Error('Network error'));

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Connection lost')).toBeInTheDocument();
        });
    });

    it('shows phase indicators for progress', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(mockProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            // Check phase labels are present
            expect(screen.getAllByText('Queued').length).toBeGreaterThan(0);
            expect(screen.getAllByText('Preparing Documents').length).toBeGreaterThan(0);
        });
    });

    it('does not show errors section when no errors', async () => {
        const progressWithoutErrors = {
            ...mockProgress,
            failed_documents: 0,
            recent_errors: [],
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(progressWithoutErrors);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getAllByText('Generating Embeddings').length).toBeGreaterThan(0);
        });

        expect(screen.queryByText('Recent Errors:')).not.toBeInTheDocument();
    });

    it('handles elapsed_seconds being null', async () => {
        const progressNullElapsed = {
            ...mockProgress,
            elapsed_seconds: null,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(progressNullElapsed);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('0:00')).toBeInTheDocument();
        });
    });

    it('displays 100% progress for completed job', async () => {
        const completedProgress = {
            ...mockProgress,
            status: 'COMPLETED' as const,
            progress_percentage: 99, // Should show 100 when completed
            processed_documents: 99,
        };
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue(completedProgress);

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        await waitFor(() => {
            expect(screen.getByText('100.0%')).toBeInTheDocument();
        });
    });
});

describe('EmbeddingProgress - WebSocket', () => {
    let originalWebSocket: typeof WebSocket;
    let originalLocalStorage: Storage;
    let mockWebSocketInstance: MockWebSocket | null = null;

    class MockWebSocketWithToken {
        url: string;
        onopen: ((event: Event) => void) | null = null;
        onmessage: ((event: MessageEvent) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        onclose: ((event: CloseEvent) => void) | null = null;
        readyState: number = WebSocket.CONNECTING;

        constructor(url: string) {
            this.url = url;
            mockWebSocketInstance = this as any;
            setTimeout(() => {
                this.readyState = WebSocket.OPEN;
                this.onopen?.(new Event('open'));
            }, 0);
        }

        close() {
            this.readyState = WebSocket.CLOSED;
            this.onclose?.(new CloseEvent('close'));
        }

        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        send(_data: string) { }
    }

    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers({ shouldAdvanceTime: true });

        originalWebSocket = global.WebSocket;
        global.WebSocket = MockWebSocketWithToken as unknown as typeof WebSocket;

        originalLocalStorage = global.localStorage;
        const localStorageMock = {
            getItem: vi.fn().mockReturnValue('test-token'), // Token present = use WebSocket
            setItem: vi.fn(),
            removeItem: vi.fn(),
            clear: vi.fn(),
            length: 0,
            key: vi.fn(),
        };
        Object.defineProperty(global, 'localStorage', { value: localStorageMock, writable: true });
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.useRealTimers();
        global.WebSocket = originalWebSocket;
        Object.defineProperty(global, 'localStorage', { value: originalLocalStorage, writable: true });
        mockWebSocketInstance = null;
    });

    it('connects to WebSocket when token is available', async () => {
        vi.mocked(api.getEmbeddingProgress).mockResolvedValue({
            job_id: 'job-123',
            status: 'EMBEDDING',
            phase: 'Processing',
            total_documents: 100,
            processed_documents: 50,
            failed_documents: 0,
            progress_percentage: 50,
            current_batch: 5,
            total_batches: 10,
            documents_per_second: 5,
            estimated_time_remaining_seconds: 60,
            elapsed_seconds: 30,
            errors_count: 0,
            recent_errors: [],
            started_at: null,
            completed_at: null,
        });

        render(<EmbeddingProgress jobId="job-123" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(100);
        });

        expect(mockWebSocketInstance).not.toBeNull();
        expect(mockWebSocketInstance?.url).toContain('/ws/embedding-progress/job-123');
        expect(mockWebSocketInstance?.url).toContain('token=test-token');
    });
});
