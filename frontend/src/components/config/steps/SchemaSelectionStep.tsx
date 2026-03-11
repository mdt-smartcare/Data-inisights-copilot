import React from 'react';
import SchemaSelector from '../../SchemaSelector';
import FileColumnSelector from '../../FileColumnSelector';
import { DocumentPreview } from '../DocumentPreview';
import type { IngestionResponse } from '../../../services/api';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface SchemaSelectionStepProps {
    dataSourceType: 'database' | 'file';
    connectionId: number | null;
    setSelectedSchema: (schema: Record<string, string[]>) => void;
    fileUploadResult: IngestionResponse | null;
    reasoning: Record<string, string>;
    onFileColumnsChange?: (columns: string[]) => void;
    selectedFileColumns?: string[];
}

export const SchemaSelectionStep: React.FC<SchemaSelectionStepProps> = ({
    dataSourceType,
    connectionId,
    setSelectedSchema,
    fileUploadResult,
    reasoning,
    onFileColumnsChange,
    selectedFileColumns = []
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    if (dataSourceType === 'database' && connectionId) {
        return (
            <div className="w-full max-w-4xl mx-auto overflow-x-hidden">
                <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables</h2>
                <p className="text-gray-500 text-xs sm:text-sm mb-4 sm:mb-6">
                    Select which tables contain relevant data for analysis. The AI will only be aware of the tables you select.
                </p>
                <SchemaSelector
                    connectionId={connectionId}
                    onSelectionChange={setSelectedSchema}
                    readOnly={!canEdit}
                    reasoning={reasoning}
                />
            </div>
        );
    }

    if (dataSourceType === 'file' && fileUploadResult) {
        const hasSelection = selectedFileColumns.length > 0;

        return (
            <div className="w-full max-w-4xl mx-auto space-y-6">
                <h2 className="text-lg sm:text-xl font-semibold mb-1">Select Columns</h2>
                <p className="text-gray-500 text-xs sm:text-sm mb-4">
                    Choose which columns from <strong>{fileUploadResult.file_name}</strong> to include for embedding and analysis.
                </p>

                <FileColumnSelector
                    columns={fileUploadResult.columns}
                    columnDetails={fileUploadResult.column_details}
                    onSelectionChange={onFileColumnsChange || (() => { })}
                    readOnly={!canEdit}
                />

                {/* Data preview — only shown after columns are selected */}
                {hasSelection && fileUploadResult.documents && fileUploadResult.documents.length > 0 && (
                    <div className="mt-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                        <DocumentPreview
                            documents={fileUploadResult.documents}
                            fileName={fileUploadResult.file_name}
                            fileType={fileUploadResult.file_type}
                            totalDocuments={fileUploadResult.total_documents}
                        />
                    </div>
                )}
            </div>
        );
    }

    return (
        <div className="w-full max-w-2xl mx-auto text-center py-8 sm:py-12 px-4">
            <p className="text-gray-500 text-sm">
                Please go back and {dataSourceType === 'database' ? 'select a database connection' : 'upload a file'} first.
            </p>
        </div>
    );
};

export default SchemaSelectionStep;

