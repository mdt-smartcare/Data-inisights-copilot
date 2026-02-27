import React, { useState } from 'react';
import DictionaryUploader from '../../DictionaryUploader';
import { DocumentPreview } from '../DocumentPreview';
import type { IngestionResponse } from '../../../services/api';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface DictionaryStepProps {
    dataSourceType: 'database' | 'file';
    dataDictionary: string;
    setDataDictionary: (value: string) => void;
    fileUploadResult: IngestionResponse | null;
}

export const DictionaryStep: React.FC<DictionaryStepProps> = ({
    dataSourceType,
    dataDictionary,
    setDataDictionary,
    fileUploadResult
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);
    const [showClearConfirm, setShowClearConfirm] = useState(false);

    return (
        <div className="h-full flex flex-col">
            <h2 className="text-xl font-semibold mb-2">Add Data Dictionary / Context</h2>
            <p className="text-gray-500 text-sm mb-4">
                {dataSourceType === 'database'
                    ? "Provide context to help the AI understand your data. Upload a file or paste definitions below."
                    : "Provide any additional context or instructions the AI should know about these documents."}
            </p>

            {dataSourceType === 'file' && fileUploadResult && (
                <div className="mb-4">
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <h3 className="text-sm font-semibold text-gray-700 mb-2">Reference Documents</h3>
                        <div className="max-h-40 overflow-y-auto pr-2">
                            <DocumentPreview
                                documents={fileUploadResult.documents}
                                fileName={fileUploadResult.file_name}
                                fileType={fileUploadResult.file_type}
                                totalDocuments={fileUploadResult.total_documents}
                            />
                        </div>
                    </div>
                </div>
            )}

            <div className="flex-1 flex flex-col min-h-0 border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
                {/* Toolbar */}
                <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex justify-between items-center">
                    <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Context Editor
                    </span>
                    <div className="flex items-center gap-2">
                        <DictionaryUploader
                            onUpload={(content) => setDataDictionary(dataDictionary ? dataDictionary + "\n\n" + content : content)}
                            disabled={!canEdit}
                        />
                        {dataDictionary && canEdit && (
                            <button
                                type="button"
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    setShowClearConfirm(true);
                                }}
                                className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1 rounded hover:bg-red-50"
                            >
                                Clear
                            </button>
                        )}
                    </div>
                </div>

                {/* Editor Area */}
                <textarea
                    className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none disabled:bg-gray-50 disabled:text-gray-500"
                    placeholder="# Users Table\n- role: 'admin' | 'user'\n- status: 1=active, 0=inactive..."
                    value={dataDictionary}
                    onChange={(e) => setDataDictionary(e.target.value)}
                    spellCheck={false}
                    disabled={!canEdit}
                />
            </div>

            {/* Clear Confirmation Modal */}
            {showClearConfirm && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 mx-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                                <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-gray-900">Clear Data Dictionary</h3>
                                <p className="text-sm text-gray-500">This action cannot be undone</p>
                            </div>
                        </div>
                        <p className="text-gray-600 mb-6">
                            Are you sure you want to clear all the data dictionary content? You'll need to re-enter or upload it again.
                        </p>
                        <div className="flex justify-end gap-3">
                            <button
                                type="button"
                                onClick={() => setShowClearConfirm(false)}
                                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setDataDictionary('');
                                    setShowClearConfirm(false);
                                }}
                                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium"
                            >
                                Clear Content
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DictionaryStep;
