import React, { useState } from 'react';
import type { ExtractedDocument } from '../../services/api';

interface DocumentPreviewProps {
    documents: ExtractedDocument[];
    fileName: string;
    fileType: string;
    totalDocuments: number;
}

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({
    documents,
    fileName,
    fileType,
    totalDocuments
}) => {
    const [expandedDoc, setExpandedDoc] = useState<number | null>(null);

    return (
        <div className="max-w-4xl mx-auto">
            <h2 className="text-xl font-semibold mb-4">Review Extracted Data</h2>
            <p className="text-gray-500 text-sm mb-6">
                Review the documents extracted from <strong>{fileName}</strong>. These will be used to generate context for the AI agent.
            </p>

            {/* Summary bar */}
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex flex-wrap items-center gap-4 mb-4">
                <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700">
                        {fileType.toUpperCase()}
                    </span>
                    <span className="text-sm font-medium text-gray-900">{fileName}</span>
                </div>
                <span className="ml-auto text-sm text-gray-600">
                    <strong className="text-gray-900">{totalDocuments}</strong> document{totalDocuments !== 1 ? 's' : ''} extracted
                </span>
            </div>

            {/* Document list */}
            <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {documents.slice(0, 20).map((doc, idx) => (
                    <div key={idx} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                        <button
                            type="button"
                            onClick={() => setExpandedDoc(expandedDoc === idx ? null : idx)}
                            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50"
                        >
                            <div className="flex items-center gap-3 min-w-0">
                                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center text-xs font-semibold">
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
                                <pre className="mt-3 text-sm text-gray-800 whitespace-pre-wrap bg-gray-50 rounded-md p-3 max-h-48 overflow-y-auto font-mono leading-relaxed">
                                    {doc.page_content}
                                </pre>
                                <div className="mt-2 flex flex-wrap gap-1.5">
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
                {totalDocuments > 20 && (
                    <p className="text-xs text-center text-gray-400 pt-2">
                        Showing 20 of {totalDocuments} documents
                    </p>
                )}
            </div>
        </div>
    );
};
