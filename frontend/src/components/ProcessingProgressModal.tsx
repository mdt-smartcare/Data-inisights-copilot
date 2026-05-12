/**
 * ProcessingProgressModal - Shows DuckDB processing progress via long polling
 */
import { useEffect, useState, useRef } from 'react';
import { getProcessingProgress } from '../services/api';

interface ProcessingProgress {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  error?: string;
  row_count?: number;
}

interface ProcessingProgressModalProps {
  isOpen: boolean;
  onClose: () => void;
  dataSourceId: string;
  dataSourceTitle: string;
  onComplete?: () => void;
}

export default function ProcessingProgressModal({
  isOpen,
  onClose,
  dataSourceId,
  dataSourceTitle,
  onComplete,
}: ProcessingProgressModalProps) {
  const [status, setStatus] = useState<'pending' | 'processing' | 'completed' | 'failed'>('pending');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [rowCount, setRowCount] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  
  const abortControllerRef = useRef<AbortController | null>(null);
  const onCompleteRef = useRef(onComplete);
  
  // Keep onComplete ref updated
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    if (!isOpen || !dataSourceId) return;

    // Create abort controller for this effect instance
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    
    // Reset state when opening
    setLoading(true);
    setStatus('pending');
    setProgress(0);
    setError(null);
    
    let currentStatus: string | undefined;
    let currentProgress: number | undefined;

    const longPoll = async () => {
      while (!abortController.signal.aborted) {
        try {
          const result: ProcessingProgress = await getProcessingProgress(
            dataSourceId,
            currentStatus,
            currentProgress,
            30, // 30 second timeout
            abortController.signal // Pass signal to cancel request
          );
          
          // Check if aborted after await
          if (abortController.signal.aborted) break;
          
          // Update state
          setStatus(result.status);
          setProgress(result.progress);
          setError(result.error || null);
          setRowCount(result.row_count);
          setLoading(false);
          
          // Update known values for next poll
          currentStatus = result.status;
          currentProgress = result.progress;
          
          // Check if processing is complete
          if (result.status === 'completed' || result.status === 'failed') {
            if (onCompleteRef.current && !abortController.signal.aborted) {
              // Give user time to see the final status
              setTimeout(() => {
                if (!abortController.signal.aborted) onCompleteRef.current?.();
              }, 1500);
            }
            break;
          }
        } catch (err: any) {
          // Ignore abort errors
          if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') {
            break;
          }
          console.error('Failed to fetch processing progress:', err);
          setLoading(false);
          // On error, wait a bit before retrying
          if (!abortController.signal.aborted) {
            await new Promise(resolve => setTimeout(resolve, 2000));
          }
        }
      }
    };
    
    // Start long polling
    longPoll();

    return () => {
      abortController.abort();
    };
  }, [isOpen, dataSourceId]); // Removed onComplete from deps

  if (!isOpen) return null;

  const getStatusColor = (s: string) => {
    switch (s) {
      case 'pending':
        return 'text-yellow-600';
      case 'processing':
        return 'text-blue-600';
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  const getProgressBarColor = (s: string) => {
    switch (s) {
      case 'completed':
        return 'bg-green-500';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-blue-500';
    }
  };

  const getMessage = () => {
    switch (status) {
      case 'pending':
        return 'Waiting to start processing...';
      case 'processing':
        if (progress < 20) return 'Starting file processing...';
        if (progress < 85) return 'Converting and processing file data...';
        return 'Registering table in database...';
      case 'completed':
        return 'Processing completed successfully!';
      case 'failed':
        return 'Processing failed.';
      default:
        return 'Unknown status';
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">Processing Progress</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-600 truncate" title={dataSourceTitle}>
              {dataSourceTitle}
            </p>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
              Loading status...
            </div>
          ) : (
            <div className="space-y-4">
              {/* Status */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-700">Status:</span>
                <span className={`text-sm font-medium capitalize ${getStatusColor(status)}`}>
                  {status}
                </span>
                {(status === 'pending' || status === 'processing') && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                )}
                {status === 'completed' && (
                  <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {status === 'failed' && (
                  <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
              </div>

              {/* Progress Bar */}
              <div>
                <div className="flex justify-between text-sm text-gray-600 mb-1">
                  <span>Progress</span>
                  <span>{progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all duration-300 ${getProgressBarColor(status)}`}
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
              </div>

              {/* Message */}
              <p className="text-sm text-gray-600">
                {getMessage()}
              </p>

              {/* Row Count (when completed) */}
              {status === 'completed' && rowCount !== undefined && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-sm text-green-800">
                    <strong>{rowCount.toLocaleString()}</strong> rows processed successfully
                  </p>
                </div>
              )}

              {/* Error Message */}
              {status === 'failed' && error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}
            </div>
          )}

          {/* Close Button */}
          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              {status === 'completed' || status === 'failed' ? 'Close' : 'Close (Processing continues)'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
