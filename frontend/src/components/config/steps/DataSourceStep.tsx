import React, { useState, useEffect } from 'react';
import ConnectionManager from '../../ConnectionManager';
import FileUploadSource from '../../FileUploadSource';
import type { IngestionResponse } from '../../../services/api';
import { canManageConnections, canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface DataSourceStepProps {
    dataSourceType: 'database' | 'file';
    setDataSourceType: (type: 'database' | 'file') => void;
    connectionId: number | null;
    setConnectionId: (id: number | null) => void;
    setConnectionName: (name: string) => void;
    setFileUploadResult: (result: IngestionResponse | null) => void;
    onFileColumnsInit?: (columns: string[]) => void;
    /** Whether we're editing an existing config */
    isEditMode?: boolean;
    /** Connection name for display in locked state */
    connectionName?: string;
    /** File upload result to show in locked state */
    initialFileResult?: IngestionResponse | null;
}

/** Locked source summary component shown in edit mode */
const LockedSourceSummary: React.FC<{
    dataSourceType: 'database' | 'file';
    connectionName?: string;
    fileResult?: IngestionResponse | null;
    onUnlock: () => void;
}> = ({ dataSourceType, connectionName, fileResult, onUnlock }) => {
    const FILE_TYPE_COLORS: Record<string, string> = {
        csv: 'bg-green-100 text-green-700',
        xlsx: 'bg-blue-100 text-blue-700',
    };
    const typeColor = (type: string) => FILE_TYPE_COLORS[type] || 'bg-gray-100 text-gray-700';

    return (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-4">
                <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                <span className="text-sm font-medium text-gray-600">Currently Selected Data Source</span>
            </div>

            {dataSourceType === 'database' && connectionName && (
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                        <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                        </svg>
                    </div>
                    <div>
                        <p className="text-base font-semibold text-gray-900">{connectionName}</p>
                        <p className="text-sm text-gray-500">Database Connection</p>
                    </div>
                </div>
            )}

            {dataSourceType === 'file' && fileResult && (
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                        <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${typeColor(fileResult.file_type)}`}>
                                {fileResult.file_type.toUpperCase()}
                            </span>
                            <p className="text-base font-semibold text-gray-900">{fileResult.file_name}</p>
                        </div>
                        <p className="text-sm text-gray-500">
                            {fileResult.row_count ? (
                                <>{fileResult.row_count.toLocaleString()} rows</>
                            ) : (
                                <>{fileResult.total_documents?.toLocaleString() || 0} documents</>
                            )}
                            {fileResult.columns && (
                                <span className="text-gray-400 ml-2">• {fileResult.columns.length} columns</span>
                            )}
                        </p>
                    </div>
                </div>
            )}

            <button
                onClick={onUnlock}
                className="w-full sm:w-auto px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors flex items-center justify-center gap-2"
            >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                </svg>
                Change Source
            </button>
        </div>
    );
};

export const DataSourceStep: React.FC<DataSourceStepProps> = ({
    dataSourceType,
    setDataSourceType,
    connectionId,
    setConnectionId,
    setConnectionName,
    setFileUploadResult,
    onFileColumnsInit,
    isEditMode = false,
    connectionName,
    initialFileResult
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    // Track if step is locked (only in edit mode with existing source)
    const hasExistingSource = (dataSourceType === 'database' && connectionId !== null) ||
                              (dataSourceType === 'file' && initialFileResult !== null);
    const [isLocked, setIsLocked] = useState(isEditMode && hasExistingSource);

    // Re-lock when entering edit mode with existing source
    useEffect(() => {
        if (isEditMode && hasExistingSource) {
            setIsLocked(true);
        }
    }, [isEditMode, hasExistingSource]);

    const handleFileExtractionComplete = (result: IngestionResponse) => {
        setFileUploadResult(result);
        // Default: select all columns
        if (result.columns && onFileColumnsInit) {
            onFileColumnsInit(result.columns);
        }
    };

    const handleUnlock = () => {
        setIsLocked(false);
    };

    // Show locked state in edit mode
    if (isLocked && hasExistingSource) {
        return (
            <div className="w-full max-w-2xl mx-auto overflow-x-hidden">
                <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Connect Data Source</h2>
                <p className="text-gray-500 text-xs sm:text-sm mb-3 sm:mb-4">
                    Your previously selected data source is shown below. Click "Change Source" to select a different one.
                </p>
                <LockedSourceSummary
                    dataSourceType={dataSourceType}
                    connectionName={connectionName}
                    fileResult={initialFileResult}
                    onUnlock={handleUnlock}
                />
            </div>
        );
    }

    return (
        <div className="w-full max-w-2xl mx-auto overflow-x-hidden">
            <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Connect Data Source</h2>
            <p className="text-gray-500 text-xs sm:text-sm mb-3 sm:mb-4">
                Choose how you want to provide data to this agent.
            </p>

            {/* Data Source Toggle */}
            <div className="flex rounded-lg border border-gray-200 overflow-hidden mb-4 sm:mb-6">
                <button
                    type="button"
                    onClick={() => { setDataSourceType('database'); setFileUploadResult(null); }}
                    className={`flex-1 px-3 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors flex items-center justify-center gap-1.5 sm:gap-2
                        ${dataSourceType === 'database'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white text-gray-600 hover:bg-gray-50'
                        }`}
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                    </svg>
                    Database
                </button>
                <button
                    type="button"
                    onClick={() => { setDataSourceType('file'); setConnectionId(null); }}
                    className={`flex-1 px-3 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors flex items-center justify-center gap-1.5 sm:gap-2
                        ${dataSourceType === 'file'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white text-gray-600 hover:bg-gray-50'
                        }`}
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <span className="hidden sm:inline">File Upload</span>
                    <span className="sm:hidden">Upload</span>
                </button>
            </div>

            {/* Database Source */}
            {dataSourceType === 'database' && (
                <>
                    <p className="text-gray-500 text-xs sm:text-sm mb-3 sm:mb-4">
                        Choose the database you want to generate insights from.
                    </p>
                    <ConnectionManager
                        onSelect={(id, name) => {
                            setConnectionId(id);
                            setConnectionName(name || '');
                        }}
                        selectedId={connectionId}
                        readOnly={!canManageConnections(user)}
                    />
                </>
            )}

            {/* File Upload Source */}
            {dataSourceType === 'file' && (
                <>
                    <p className="text-gray-500 text-xs sm:text-sm mb-3 sm:mb-4">
                        Upload a CSV or Excel file to extract and select columns from.
                    </p>
                    <FileUploadSource
                        onExtractionComplete={handleFileExtractionComplete}
                        disabled={!canEdit}
                        initialResult={initialFileResult}
                    />
                </>
            )}
        </div>
    );
};

export default DataSourceStep;
