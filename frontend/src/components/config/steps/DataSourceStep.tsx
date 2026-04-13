import React from 'react';
import { Link } from 'react-router-dom';
import DataSourceSelector from '../DataSourceSelector';
import type { IngestionResponse, DataSource } from '../../../services/api';

interface DataSourceStepProps {
    dataSourceType: 'database' | 'file';
    setDataSourceType: (type: 'database' | 'file') => void;
    connectionId: number | null;
    setConnectionId: (id: number | null) => void;
    setConnectionName: (name: string) => void;
    setFileUploadResult: (result: IngestionResponse | null) => void;
    onFileColumnsInit?: (columns: string[]) => void;
    selectedDataSource?: DataSource | null;
    setSelectedDataSource?: (ds: DataSource | null) => void;
}

export const DataSourceStep: React.FC<DataSourceStepProps> = ({
    setDataSourceType,
    setConnectionId,
    setConnectionName,
    setFileUploadResult,
    onFileColumnsInit,
    selectedDataSource,
    setSelectedDataSource
}) => {
    const handleDataSourceSelect = (ds: DataSource) => {
        // Update data source type based on selection
        setDataSourceType(ds.source_type);
        setConnectionName(ds.title);
        
        // Notify parent of selection
        if (setSelectedDataSource) {
            setSelectedDataSource(ds);
        }
        
        // For file sources, build the fileUploadResult from data source columns
        if (ds.source_type === 'file' && ds.columns_json) {
            try {
                const columns = JSON.parse(ds.columns_json);
                const columnNames = columns.map((c: any) => c.name || c);
                setFileUploadResult({
                    status: 'success',
                    file_name: ds.original_file_path || ds.title,
                    file_type: ds.file_type || 'csv',
                    total_documents: ds.row_count || 0,
                    table_name: ds.duckdb_table_name,
                    columns: columnNames,
                    column_details: columns,
                    row_count: ds.row_count,
                });
                // Auto-select all columns
                if (onFileColumnsInit) {
                    onFileColumnsInit(columnNames);
                }
            } catch {
                setFileUploadResult(null);
            }
        } else {
            setFileUploadResult(null);
            // For database sources, clear connection ID (legacy)
            setConnectionId(null);
        }
    };

    return (
        <div className="w-full max-w-4xl mx-auto overflow-x-hidden">
            <h2 className="text-lg sm:text-xl font-semibold mb-2">Select Data Source</h2>
            <p className="text-gray-500 text-xs sm:text-sm mb-4 sm:mb-6">
                Choose an existing data source for this agent. You can create new data sources in the{' '}
                <Link to="/data-sources" className="text-blue-600 hover:underline">Data Sources</Link> page.
            </p>

            <DataSourceSelector
                selectedId={selectedDataSource?.id || null}
                onSelect={handleDataSourceSelect}
            />
        </div>
    );
};

export default DataSourceStep;
