import React, { useState } from 'react';
import DictionaryUploader from '../../DictionaryUploader';
import { DocumentPreview } from '../DocumentPreview';
import type { IngestionResponse, DataSourceSchemaResponse } from '../../../services/api';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface DictionaryStepProps {
    dataSourceType: 'database' | 'file';
    dataDictionary: string;
    setDataDictionary: (value: string) => void;
    fileUploadResult: IngestionResponse | null;
    schema: DataSourceSchemaResponse | null;
    selectedSchema: Record<string, string[]>;
}

export const DictionaryStep: React.FC<DictionaryStepProps> = ({
    dataSourceType,
    dataDictionary,
    setDataDictionary,
    fileUploadResult,
    schema,
    selectedSchema
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);
    const [showClearConfirm, setShowClearConfirm] = useState(false);

    // Filter schema to only show selected tables and columns
    const schemaDetails = React.useMemo(() => {
        if (!schema) return null;

        return schema.tables
            .filter(t => selectedSchema[t.table_name] || (dataSourceType === 'file' && t.table_name))
            .map(t => {
                // For files, we might not have a strict selectedSchema entry in the same format
                // but selectedSchema usually contains the file's table name
                const selectedCols = new Set(selectedSchema[t.table_name] || []);
                const columns = dataSourceType === 'file'
                    ? t.columns // Show all columns for files for now, or filter if selection is tracked
                    : t.columns.filter(c => selectedCols.has(c.column_name));

                return { ...t, columns };
            })
            .filter(t => t.columns.length > 0);
    }, [schema, selectedSchema, dataSourceType]);

    return (
        <div className="h-full flex flex-col w-full overflow-hidden">
            <h2 className="text-lg sm:text-xl font-semibold mb-2">Add Data Dictionary / Context</h2>
            <p className="text-gray-500 text-xs sm:text-sm mb-3 sm:mb-4">
                {dataSourceType === 'database'
                    ? "Provide context to help the AI understand your data. Business definitions and rules help generate more accurate SQL."
                    : "Provide any additional context or instructions the AI should know about this document."}
            </p>

            {/* Discovered Schema Context (Read-only) */}
            {schemaDetails && schemaDetails.length > 0 && (
                <div className="mb-4">
                    <div className="bg-blue-50/50 rounded-lg p-3 sm:p-4 border border-blue-100">
                        <div className="flex items-center gap-2 mb-2">
                            <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <h3 className="text-xs sm:text-sm font-semibold text-blue-900 uppercase tracking-tight">
                                {dataSourceType === 'database' ? 'Discovered Schema Context' : 'Detected File Fields'}
                            </h3>
                            <span className="text-[10px] text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded ml-auto">Read-only</span>
                        </div>
                        <div className="max-h-48 overflow-y-auto pr-2 space-y-3">
                            {schemaDetails.map(table => (
                                <div key={table.table_name} className="bg-white/80 rounded border border-blue-50 p-2 sm:p-3 shadow-sm">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-xs font-bold text-gray-800">{table.table_name}</span>
                                        <span className="text-[10px] text-gray-400">({table.columns.length} fields)</span>
                                    </div>
                                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                                        {table.columns.map(col => (
                                            <div key={col.column_name} className="flex items-center gap-1 text-[10px] sm:text-xs">
                                                {col.is_primary_key && <span className="text-yellow-600" title="Primary Key">🔑</span>}
                                                {col.foreign_key && <span className="text-purple-500" title={`FK -> ${col.foreign_key.referenced_table}`}>🔗</span>}
                                                <span className="font-medium text-gray-700">{col.column_name}</span>
                                                <span className="text-gray-400 italic">({col.data_type})</span>
                                                {col.foreign_key && (
                                                    <span className="text-purple-600 text-[9px] sm:text-[10px]">
                                                        → {col.foreign_key.referenced_table}({col.foreign_key.referenced_column})
                                                    </span>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <p className="text-[10px] text-blue-600 mt-2 italic">
                            {dataSourceType === 'database'
                                ? "The metadata above is automatically shared with the AI to ensure correct table joins and primary key awareness."
                                : "The fields above were detected in your file and are shared with the AI as structural context."}
                        </p>
                    </div>
                </div>
            )}

            {dataSourceType === 'file' && fileUploadResult && (
                <div className="mb-3 sm:mb-4">
                    <div className="bg-gray-50 rounded-lg p-2 sm:p-3 border border-gray-200">
                        <div className="max-h-32 sm:max-h-40 overflow-y-auto pr-2">
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

            <div className="flex-1 flex flex-col min-h-[350px] sm:min-h-[450px] border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
                {/* Toolbar */}
                <div className="bg-gray-50 border-b border-gray-200 px-2 sm:px-4 py-2 flex justify-between items-center gap-2">
                    <span className="text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Context Editor
                    </span>
                    <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">
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
                    className="flex-1 min-h-[300px] sm:min-h-[400px] p-2 sm:p-4 font-mono text-xs sm:text-sm leading-relaxed resize-none focus:outline-none disabled:bg-gray-50 disabled:text-gray-500 w-full"
                    placeholder="# Users Table\n- role: 'admin' | 'user'\n- status: 1=active, 0=inactive..."
                    value={dataDictionary}
                    onChange={(e) => setDataDictionary(e.target.value)}
                    spellCheck={false}
                    disabled={!canEdit}
                />
            </div>

            {/* Clear Confirmation Modal */}
            {showClearConfirm && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-4 sm:p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                                <svg className="w-4 h-4 sm:w-5 sm:h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                            </div>
                            <div className="min-w-0">
                                <h3 className="text-base sm:text-lg font-semibold text-gray-900">Clear Data Dictionary</h3>
                                <p className="text-xs sm:text-sm text-gray-500">This action cannot be undone</p>
                            </div>
                        </div>
                        <p className="text-sm text-gray-600 mb-4 sm:mb-6">
                            Are you sure you want to clear all the data dictionary content?
                        </p>
                        <div className="flex justify-end gap-2 sm:gap-3">
                            <button
                                type="button"
                                onClick={() => setShowClearConfirm(false)}
                                className="px-3 sm:px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium text-sm"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setDataDictionary('');
                                    setShowClearConfirm(false);
                                }}
                                className="px-3 sm:px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium text-sm"
                            >
                                Clear
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DictionaryStep;
