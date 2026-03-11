import React, { useState, useCallback, useRef } from 'react';
import { uploadForIngestion, handleApiError } from '../services/api';
import type { IngestionResponse } from '../services/api';

const ACCEPTED_EXTENSIONS = '.pdf,.csv,.xlsx,.json';
const FILE_TYPE_COLORS: Record<string, string> = {
    pdf: 'bg-red-100 text-red-700',
    csv: 'bg-green-100 text-green-700',
    xlsx: 'bg-blue-100 text-blue-700',
    json: 'bg-amber-100 text-amber-700',
};

interface FileUploadSourceProps {
    /** Called when extraction completes — parent receives the full result */
    onExtractionComplete: (result: IngestionResponse) => void;
    /** If true, prevent interaction */
    disabled?: boolean;
}

/**
 * File upload data source component for the agent config wizard.
 * Provides drag-and-drop / click-to-browse upload of .pdf/.csv/.xlsx/.json
 * and shows extraction results.
 */
const FileUploadSource: React.FC<FileUploadSourceProps> = ({
    onExtractionComplete,
    disabled = false,
}) => {
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<IngestionResponse | null>(null);
    const [expandedDoc, setExpandedDoc] = useState<number | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFile = useCallback(async (file: File) => {
        setError(null);
        setResult(null);
        setIsUploading(true);
        setExpandedDoc(null);

        try {
            const response = await uploadForIngestion(file);
            setResult(response);
            onExtractionComplete(response);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setIsUploading(false);
        }
    }, [onExtractionComplete]);

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
                onClick={() => !isUploading && !disabled && fileInputRef.current?.click()}
                className={`relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200
          ${isDragging
                        ? 'border-blue-500 bg-blue-50 scale-[1.01]'
                        : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50'
                    }
          ${isUploading || disabled ? 'opacity-60 pointer-events-none' : ''}
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
                        <p className="text-sm font-medium text-blue-600">Processing file…</p>
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
                            <p className="text-xs text-gray-400 mt-1">.pdf, .csv, .xlsx, .json</p>
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

            {/* Results */}
            {result && (
                <div className="space-y-3">
                    {/* Summary */}
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
                            <strong className="text-gray-900">{result.total_documents}</strong> document{result.total_documents !== 1 ? 's' : ''} extracted
                        </span>
                    </div>

                    {/* Document Preview (collapsible, max 5 shown) */}
                    <details className="group">
                        <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:text-blue-800 select-none">
                            Preview extracted documents ({Math.min(result.documents.length, 5)} of {result.total_documents})
                        </summary>
                        <div className="mt-2 space-y-2">
                            {result.documents.slice(0, 5).map((doc, idx) => (
                                <div
                                    key={idx}
                                    className="bg-white rounded-lg border border-gray-200 overflow-hidden"
                                >
                                    <button
                                        type="button"
                                        onClick={() => setExpandedDoc(expandedDoc === idx ? null : idx)}
                                        className="w-full flex items-center justify-between px-3 py-2 text-left"
                                    >
                                        <div className="flex items-center gap-2 min-w-0">
                                            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-100 text-gray-600 flex items-center justify-center text-xs font-semibold">
                                                {idx + 1}
                                            </span>
                                            <span className="text-sm text-gray-700 truncate">
                                                {doc.page_content.slice(0, 100)}{doc.page_content.length > 100 ? '…' : ''}
                                            </span>
                                        </div>
                                        <svg
                                            className={`w-4 h-4 text-gray-400 flex-shrink-0 ml-2 transition-transform ${expandedDoc === idx ? 'rotate-180' : ''}`}
                                            fill="none" stroke="currentColor" viewBox="0 0 24 24"
                                        >
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </button>

                                    {expandedDoc === idx && (
                                        <div className="px-3 pb-3 border-t border-gray-100">
                                            <pre className="mt-2 text-xs text-gray-800 whitespace-pre-wrap bg-gray-50 rounded p-2 max-h-40 overflow-y-auto font-mono">
                                                {doc.page_content}
                                            </pre>
                                            <div className="mt-2 flex flex-wrap gap-1">
                                                {Object.entries(doc.metadata).map(([key, value]) => (
                                                    <span key={key} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 text-xs text-gray-600">
                                                        <span className="font-medium text-gray-800">{key}:</span>
                                                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </details>
                </div>
            )}
        </div>
    );
};

export default FileUploadSource;
