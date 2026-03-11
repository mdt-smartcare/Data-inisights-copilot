import React from 'react';
import SchemaSelector from '../../SchemaSelector';
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
}

export const SchemaSelectionStep: React.FC<SchemaSelectionStepProps> = ({
    dataSourceType,
    connectionId,
    setSelectedSchema,
    fileUploadResult,
    reasoning
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
        return (
            <DocumentPreview
                documents={fileUploadResult.documents}
                fileName={fileUploadResult.file_name}
                fileType={fileUploadResult.file_type}
                totalDocuments={fileUploadResult.total_documents}
            />
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
