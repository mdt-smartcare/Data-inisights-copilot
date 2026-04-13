import React from 'react';
import { Link } from 'react-router-dom';
import DataSourceSelector from '../DataSourceSelector';
import type { IngestionResponse, DataSource } from '../../../services/api';
import { CircleStackIcon, DocumentTextIcon } from '@heroicons/react/24/outline';

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
    isLocked?: boolean;
}

export const DataSourceStep: React.FC<DataSourceStepProps> = ({
    setDataSourceType,
    setConnectionId,
    setConnectionName,
    setFileUploadResult,
    onFileColumnsInit,
    selectedDataSource,
    setSelectedDataSource,
    isLocked = false
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
                    documents: []
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

            {isLocked && (
                <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-3">
                    <div className="flex-shrink-0 mt-0.5">
                        <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-sm font-medium text-blue-800">Agent Source Locked</h3>
                        <p className="text-xs text-blue-700 mt-1">
                            This agent has already been published with a data source. To maintain consistency, the data source cannot be changed.
                            If you need to use a different data source, please create a new agent.
                        </p>
                    </div>
                </div>
            )}

            {isLocked && selectedDataSource && (
                <div className="mb-6 p-4 bg-white border border-blue-100 rounded-lg shadow-sm">
                    <div className="flex items-center gap-3">
                        <div className={`flex-shrink-0 w-10 h-10 rounded flex items-center justify-center ${selectedDataSource.source_type === 'database' ? 'bg-blue-50' : 'bg-green-50'
                            }`}>
                            {selectedDataSource.source_type === 'database'
                                ? <CircleStackIcon className="w-6 h-6 text-blue-600" />
                                : <DocumentTextIcon className="w-6 h-6 text-green-600" />
                            }
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <h4 className="font-semibold text-gray-900 truncate">
                                    {selectedDataSource.title}
                                </h4>
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-900 border border-blue-300">
                                    Agent configured with current data source
                                </span>
                                <span className={`px-1.5 py-0.5 text-xs rounded font-medium ${selectedDataSource.source_type === 'database'
                                    ? 'bg-blue-100 text-blue-700'
                                    : 'bg-green-100 text-green-700'
                                    }`}>
                                    {selectedDataSource.source_type === 'database'
                                        ? (selectedDataSource.db_engine_type || 'Database')
                                        : (selectedDataSource.file_type?.toUpperCase() || 'File')
                                    }
                                </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-0.5 truncate">
                                {selectedDataSource.description || 'No description provided'}
                            </p>
                        </div>
                        {selectedDataSource.row_count !== undefined && selectedDataSource.row_count !== null && (
                            <div className="text-right">
                                <span className="block text-sm font-semibold text-gray-900">
                                    {selectedDataSource.row_count.toLocaleString()}
                                </span>
                                <span className="block text-[10px] text-gray-400 uppercase font-medium">
                                    Rows
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            )}

            <DataSourceSelector
                selectedId={selectedDataSource?.id || null}
                onSelect={handleDataSourceSelect}
                disabled={isLocked}
            />
        </div>
    );
};

export default DataSourceStep;
