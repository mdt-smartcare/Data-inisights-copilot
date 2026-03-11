import React from 'react';
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
}

export const DataSourceStep: React.FC<DataSourceStepProps> = ({
    dataSourceType,
    setDataSourceType,
    connectionId,
    setConnectionId,
    setConnectionName,
    setFileUploadResult
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    const handleFileExtractionComplete = (result: IngestionResponse) => {
        setFileUploadResult(result);
    };

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
                        Upload a PDF, CSV, Excel, or JSON file to extract data from.
                    </p>
                    <FileUploadSource
                        onExtractionComplete={handleFileExtractionComplete}
                        disabled={!canEdit}
                    />
                </>
            )}
        </div>
    );
};

export default DataSourceStep;
