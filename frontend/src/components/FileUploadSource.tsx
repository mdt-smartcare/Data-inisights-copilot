import React, { useState, useCallback, useRef, useEffect } from 'react';
import { uploadForIngestion, handleApiError, getFileSqlTableSchema, getFileSqlTableStatus } from '../services/api';
import type { IngestionResponse } from '../services/api';

const ACCEPTED_EXTENSIONS = '.csv,.xlsx';
const FILE_TYPE_COLORS: Record<string, string> = {
    csv: 'bg-green-100 text-green-700',
    xlsx: 'bg-blue-100 text-blue-700',
};

interface FileUploadSourceProps {
    /** Called when upload completes — parent receives the full result */
    onExtractionComplete: (result: IngestionResponse) => void;
    /** If true, prevent interaction */
    disabled?: boolean;
    /** Pre-populate with an existing result (for edit mode) */
    initialResult?: IngestionResponse | null;
}

/**
 * File upload data source component for the agent config wizard.
 * Provides drag-and-drop / click-to-browse upload of .csv/.xlsx
 * and shows a success summary when extraction completes.
 *
 * For large files (≥10MB), polls for background processing completion
 * to fetch column information once ready.
 */
const FileUploadSource: React.FC<FileUploadSourceProps> = ({
    onExtractionComplete,
    disabled = false,
    initialResult = null,
}) => {
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [isPolling, setIsPolling] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<IngestionResponse | null>(initialResult);
    const [pollingMessage, setPollingMessage] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Update result if initialResult changes (e.g., when loading existing config)
    useEffect(() => {
        if (initialResult) {
            setResult(initialResult);
        }
    }, [initialResult]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (pollingIntervalRef.current) {
                clearInterval(pollingIntervalRef.current);
            }
        };
    }, []);

    // Poll for background processing status
    const pollForCompletion = useCallback(async (tableName: string, initialResult: IngestionResponse) => {
        setIsPolling(true);
        setPollingMessage('Processing large file in background...');
        
        const poll = async () => {
            try {
                const status = await getFileSqlTableStatus(tableName);
                
                if (status.ready) {
                    // Processing complete - fetch column details
                    if (pollingIntervalRef.current) {
                        clearInterval(pollingIntervalRef.current);
                        pollingIntervalRef.current = null;
                    }
                    
                    try {
                        const schema = await getFileSqlTableSchema(tableName);
                        const columnDetails = schema.schema.map((col: { column_name: string; data_type: string }) => ({
                            name: col.column_name,
                            type: col.data_type,
                        }));
                        const columns = schema.schema.map((col: { column_name: string }) => col.column_name);
                        
                        // Update result with column information
                        const updatedResult: IngestionResponse = {
                            ...initialResult,
                            columns,
                            column_details: columnDetails,
                            row_count: status.row_count || initialResult.row_count,
                            processing_mode: 'complete',
                        };
                        
                        setResult(updatedResult);
                        setIsPolling(false);
                        setPollingMessage(null);
                        onExtractionComplete(updatedResult);
                    } catch (schemaErr) {
                        console.error('Failed to fetch schema:', schemaErr);
                        setError('File processed but failed to fetch column information. Please try again.');
                        setIsPolling(false);
                    }
                } else if (status.status === 'error') {
                    if (pollingIntervalRef.current) {
                        clearInterval(pollingIntervalRef.current);
                        pollingIntervalRef.current = null;
                    }
                    setError(status.error || 'Background processing failed');
                    setIsPolling(false);
                } else {
                    setPollingMessage(`Processing... ${status.status || 'Please wait'}`);
                }
            } catch (err) {
                console.error('Polling error:', err);
                // Continue polling on transient errors
            }
        };
        
        // Start polling every 2 seconds
        pollingIntervalRef.current = setInterval(poll, 2000);
        // Also poll immediately
        poll();
    }, [onExtractionComplete]);

    const handleFile = useCallback(async (file: File) => {
        setError(null);
        setResult(null);
        setIsUploading(true);
        setIsPolling(false);
        setPollingMessage(null);

        try {
            const response = await uploadForIngestion(file);
            setResult(response);
            
            // Check if background processing is needed
            if (response.processing_mode === 'background' && response.table_name) {
                // Start polling for completion
                pollForCompletion(response.table_name, response);
            } else {
                // Sync processing complete - columns should be available
                onExtractionComplete(response);
            }
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setIsUploading(false);
        }
    }, [onExtractionComplete, pollForCompletion]);

    const onDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
    }, [handleFile]);

    const onDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const onDragLeave = useCallback(() => setIsDragging(false), []);

    const onFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) handleFile(file);
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, [handleFile]);

    const typeColor = (type: string) => FILE_TYPE_COLORS[type] || 'bg-gray-100 text-gray-700';

    return (
        <div className="space-y-4">
            {/* Drop Zone */}
            <div
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onClick={() => !isUploading && !isPolling && !disabled && fileInputRef.current?.click()}
                className={`relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200
          ${isDragging
                        ? 'border-blue-500 bg-blue-50 scale-[1.01]'
                        : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50'
                    }
          ${isUploading || isPolling || disabled ? 'opacity-60 pointer-events-none' : ''}
        `}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    accept={ACCEPTED_EXTENSIONS}
                    onChange={onFileSelect}
                />

                {isUploading ? (
                    <div className="flex flex-col items-center gap-3">
                        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                        <p className="text-sm font-medium text-blue-600">Uploading file…</p>
                    </div>
                ) : isPolling ? (
                    <div className="flex flex-col items-center gap-3">
                        <div className="w-10 h-10 border-4 border-amber-500 border-t-transparent rounded-full animate-spin" />
                        <p className="text-sm font-medium text-amber-600">{pollingMessage || 'Processing large file...'}</p>
                        <p className="text-xs text-gray-500">This may take a minute for large datasets</p>
                    </div>
                ) : (
                    <div className="flex flex-col items-center gap-3">
                        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                            />
                        </svg>
                        <div>
                            <p className="text-sm font-medium text-gray-700">
                                Drag & drop a file here, or <span className="text-blue-600 underline">browse</span>
                            </p>
                            <p className="text-xs text-gray-400 mt-1">.csv, .xlsx</p>
                        </div>
                    </div>
                )}
            </div>

            {/* Error */}
            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                    <svg className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd"
                            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                            clipRule="evenodd"
                        />
                    </svg>
                    <div>
                        <p className="text-sm font-medium text-red-800">Upload failed</p>
                        <p className="text-sm text-red-600 mt-0.5">{error}</p>
                    </div>
                </div>
            )}

            {/* Upload Success Summary */}
            {result && !isPolling && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex flex-wrap items-center gap-4">
                    <div className="flex items-center gap-2">
                        <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${typeColor(result.file_type)}`}>
                            {result.file_type.toUpperCase()}
                        </span>
                        <span className="text-sm font-medium text-gray-900">{result.file_name}</span>
                    </div>
                    <span className="ml-auto text-sm text-gray-600">
                        {result.row_count ? (
                            <><strong className="text-gray-900">{result.row_count.toLocaleString()}</strong> rows</>
                        ) : (
                            <><strong className="text-gray-900">{result.total_documents.toLocaleString()}</strong> document{result.total_documents !== 1 ? 's' : ''} extracted</>
                        )}
                        {result.columns && (
                            <span className="text-gray-400 ml-2">• {result.columns.length} column{result.columns.length !== 1 ? 's' : ''} detected</span>
                        )}
                    </span>
                </div>
            )}

            {/* Polling in progress summary */}
            {result && isPolling && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex flex-wrap items-center gap-4">
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${typeColor(result.file_type)}`}>
                            {result.file_type.toUpperCase()}
                        </span>
                        <span className="text-sm font-medium text-gray-900">{result.file_name}</span>
                    </div>
                    <span className="ml-auto text-sm text-amber-700">
                        Processing {result.row_count ? `~${result.row_count.toLocaleString()} rows` : 'large file'}...
                    </span>
                </div>
            )}
        </div>
    );
};

export default FileUploadSource;
