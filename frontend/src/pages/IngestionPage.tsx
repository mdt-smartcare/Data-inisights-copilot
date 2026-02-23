import React, { useState, useCallback, useRef } from 'react';
import ChatHeader from '../components/chat/ChatHeader';
import { uploadForIngestion, handleApiError } from '../services/api';
import type { IngestionResponse } from '../services/api';

const ACCEPTED_EXTENSIONS = '.pdf,.csv,.xlsx,.json';
const FILE_TYPE_COLORS: Record<string, string> = {
    pdf: 'bg-red-100 text-red-700',
    csv: 'bg-green-100 text-green-700',
    xlsx: 'bg-blue-100 text-blue-700',
    json: 'bg-amber-100 text-amber-700',
};

export default function IngestionPage() {
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
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setIsUploading(false);
        }
    }, []);

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
        <div className="min-h-screen bg-gray-50">
            <ChatHeader title="Data Insights AI-Copilot" />

            <div className="max-w-5xl mx-auto px-4 py-8">
                {/* Page Title */}
                <div className="mb-6">
                    <h2 className="text-2xl font-bold text-gray-900">Ingestion Engine</h2>
                    <p className="text-sm text-gray-500 mt-1">
                        Upload a file to test the multi-modal data extraction pipeline. Supported formats: PDF, CSV, Excel, JSON.
                    </p>
                </div>

                {/* Drop Zone */}
                <div
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onClick={() => !isUploading && fileInputRef.current?.click()}
                    className={`relative border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all duration-200
            ${isDragging
                            ? 'border-blue-500 bg-blue-50 scale-[1.01]'
                            : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50'
                        }
            ${isUploading ? 'opacity-60 pointer-events-none' : ''}
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
                            <svg className="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                        <svg className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd"
                                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                clipRule="evenodd"
                            />
                        </svg>
                        <div>
                            <p className="text-sm font-medium text-red-800">Extraction failed</p>
                            <p className="text-sm text-red-600 mt-0.5">{error}</p>
                        </div>
                    </div>
                )}

                {/* Results */}
                {result && (
                    <div className="mt-6 space-y-4">
                        {/* Summary Bar */}
                        <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap items-center gap-4">
                            <div className="flex items-center gap-2">
                                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${typeColor(result.file_type)}`}>
                                    {result.file_type.toUpperCase()}
                                </span>
                                <span className="text-sm font-medium text-gray-900">{result.file_name}</span>
                            </div>
                            <div className="ml-auto flex items-center gap-4 text-sm text-gray-500">
                                <span>
                                    <strong className="text-gray-900">{result.total_documents}</strong> document{result.total_documents !== 1 ? 's' : ''} extracted
                                </span>
                                {result.total_documents > result.documents.length && (
                                    <span className="text-xs text-amber-600">
                                        (showing first {result.documents.length})
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Document List */}
                        <div className="space-y-2">
                            {result.documents.map((doc, idx) => (
                                <div
                                    key={idx}
                                    className="bg-white rounded-lg border border-gray-200 overflow-hidden transition-shadow hover:shadow-sm"
                                >
                                    <button
                                        onClick={() => setExpandedDoc(expandedDoc === idx ? null : idx)}
                                        className="w-full flex items-center justify-between px-4 py-3 text-left"
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-100 text-gray-600 flex items-center justify-center text-xs font-semibold">
                                                {idx + 1}
                                            </span>
                                            <span className="text-sm text-gray-700 truncate">
                                                {doc.page_content.slice(0, 120)}{doc.page_content.length > 120 ? '…' : ''}
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
                                        <div className="px-4 pb-4 border-t border-gray-100">
                                            {/* Content */}
                                            <div className="mt-3">
                                                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Content</h4>
                                                <pre className="text-sm text-gray-800 whitespace-pre-wrap bg-gray-50 rounded-md p-3 max-h-60 overflow-y-auto font-mono leading-relaxed">
                                                    {doc.page_content}
                                                </pre>
                                            </div>
                                            {/* Metadata */}
                                            <div className="mt-3">
                                                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Metadata</h4>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {Object.entries(doc.metadata).map(([key, value]) => (
                                                        <span key={key} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 text-xs text-gray-600">
                                                            <span className="font-medium text-gray-800">{key}:</span>
                                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
