import React, { useEffect, useState, useMemo } from 'react';
import FileColumnSelector from '../../FileColumnSelector';
import { DocumentPreview } from '../DocumentPreview';
import type { IngestionResponse, DataSource, DataSourceSchemaResponse, TableInfoResponse, ColumnInfo, TableRelationship, DataSourcePreviewResponse } from '../../../services/api';
import { getDataSourceSchema, getDataSourcePreview } from '../../../services/api';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface SchemaSelectionStepProps {
    dataSourceType: 'database' | 'file';
    connectionId: number | null;
    setSelectedSchema: (schema: Record<string, string[]>) => void;
    initialSchema?: Record<string, string[]>;  // Saved selection from config
    fileUploadResult: IngestionResponse | null;
    reasoning: Record<string, string>;
    onFileColumnsChange?: (columns: string[]) => void;
    selectedFileColumns?: string[];
    selectedDataSource?: DataSource | null;
    onSchemaFetch?: (schema: DataSourceSchemaResponse) => void;
}

export const SchemaSelectionStep: React.FC<SchemaSelectionStepProps> = ({
    dataSourceType,
    setSelectedSchema,
    initialSchema,
    fileUploadResult,
    reasoning = {},
    onFileColumnsChange,
    selectedFileColumns = [],
    selectedDataSource,
    onSchemaFetch
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    // State for schema fetching
    const [schema, setSchema] = useState<DataSourceSchemaResponse | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // State for file preview data
    const [preview, setPreview] = useState<DataSourcePreviewResponse | null>(null);

    // Selected state: Record<TableName, Set<ColumnName>> - internal use
    const [selected, setSelected] = useState<Record<string, Set<string>>>({});
    const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

    // Build a map of table -> primary key columns
    const primaryKeyMap = useMemo(() => {
        if (!schema) return new Map<string, Set<string>>();
        const map = new Map<string, Set<string>>();
        schema.tables.forEach(table => {
            const pkCols = new Set(table.primary_key_columns || []);
            // Also check individual columns for is_primary_key flag
            table.columns.forEach(col => {
                if (col.is_primary_key) {
                    pkCols.add(col.column_name);
                }
            });
            map.set(table.table_name, pkCols);
        });
        return map;
    }, [schema]);

    // Build dependency map: table -> tables it depends on (FK references)
    const dependencyMap = useMemo(() => {
        if (!schema?.relationships) return new Map<string, Set<string>>();
        const map = new Map<string, Set<string>>();
        schema.relationships.forEach((rel: TableRelationship) => {
            if (!map.has(rel.from_table)) {
                map.set(rel.from_table, new Set());
            }
            map.get(rel.from_table)!.add(rel.to_table);
        });
        return map;
    }, [schema]);

    // Check which selected tables have missing dependencies
    const missingDependencies = useMemo(() => {
        const missing: Record<string, string[]> = {};
        const selectedTables = new Set(
            Object.entries(selected)
                .filter(([_, cols]) => cols.size > 0)
                .map(([table]) => table)
        );

        selectedTables.forEach(table => {
            const deps = dependencyMap.get(table);
            if (deps) {
                const missingDeps = Array.from(deps).filter(dep => !selectedTables.has(dep));
                if (missingDeps.length > 0) {
                    missing[table] = missingDeps;
                }
            }
        });

        return missing;
    }, [selected, dependencyMap]);

    // Emit selection to parent
    const emitSelection = (currentSelection: Record<string, Set<string>>) => {
        const output: Record<string, string[]> = {};
        Object.entries(currentSelection).forEach(([table, colSet]) => {
            if (colSet.size > 0) {
                output[table] = Array.from(colSet);
            }
        });
        setSelectedSchema(output);
    };

    // Ensure primary keys are included when table has selections
    const ensurePrimaryKeys = (tableName: string, columnSet: Set<string>): Set<string> => {
        // Only add PKs if there are other columns selected (table is "active")
        if (columnSet.size === 0) return columnSet;

        const pkCols = primaryKeyMap.get(tableName) || new Set();
        const newSet = new Set(columnSet);
        pkCols.forEach(pk => newSet.add(pk));
        return newSet;
    };

    // Check if a table has any columns selected (is "active")
    const isTableSelected = (tableName: string): boolean => {
        const cols = selected[tableName];
        return cols ? cols.size > 0 : false;
    };

    // Fetch schema function
    const fetchSchema = async () => {
        if (!selectedDataSource?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            const result = await getDataSourceSchema(selectedDataSource.id);
            setSchema(result);
            if (onSchemaFetch) onSchemaFetch(result);

            // For file sources, also fetch preview data
            if (result.source_type === 'file') {
                try {
                    const previewResult = await getDataSourcePreview(selectedDataSource.id, 10);
                    setPreview(previewResult);
                } catch (previewErr) {
                    console.warn('Failed to fetch preview:', previewErr);
                    // Preview is optional, continue without it
                }
            }

            // Check if we have saved selection from config
            const hasSavedSelection = initialSchema && Object.keys(initialSchema).length > 0;

            let initialSelection: Record<string, Set<string>> = {};

            if (hasSavedSelection) {
                // Use saved selection from config
                Object.entries(initialSchema!).forEach(([table, columns]) => {
                    initialSelection[table] = new Set(columns);
                });
                // Ensure all tables exist in selection (mark empty ones)
                result.tables.forEach((table: TableInfoResponse) => {
                    if (!initialSelection[table.table_name]) {
                        initialSelection[table.table_name] = new Set();
                    }
                });
                // Don't emit - we're just restoring saved state
                setSelected(initialSelection);
            } else {
                // Default: Select ALL columns for ALL tables
                result.tables.forEach((table: TableInfoResponse) => {
                    initialSelection[table.table_name] = new Set(table.columns.map(c => c.column_name));
                });
                setSelected(initialSelection);
                // Only emit when creating new selection (not restoring saved)
                emitSelection(initialSelection);

                // For file sources, also initialize file columns if not already set
                if (result.source_type === 'file' && onFileColumnsChange) {
                    const allColumns = result.tables[0]?.columns?.map(c => c.column_name) || [];
                    if (allColumns.length > 0 && (!selectedFileColumns || selectedFileColumns.length === 0)) {
                        onFileColumnsChange(allColumns);
                    }
                }
            }
        } catch (err) {
            console.error('Failed to fetch schema:', err);
            setError('Failed to load schema. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    // Fetch schema when data source changes
    useEffect(() => {
        fetchSchema();
    }, [selectedDataSource?.id]);

    const toggleTableExpansion = (table: string) => {
        const newExpanded = new Set(expandedTables);
        if (newExpanded.has(table)) {
            newExpanded.delete(table);
        } else {
            newExpanded.add(table);
        }
        setExpandedTables(newExpanded);
    };

    // Toggle all columns for a specific table
    // When selecting: all columns selected (PKs auto-included)
    // When deselecting: all columns deselected (including PKs)
    const toggleTableSelection = (table: string, columns: string[]) => {
        const currentSet = selected[table] || new Set();
        const newSelection = { ...selected };

        if (currentSet.size === columns.length) {
            // Deselect all (including PKs) - table becomes inactive
            newSelection[table] = new Set();
        } else {
            // Select all
            newSelection[table] = new Set(columns);
        }

        setSelected(newSelection);
        emitSelection(newSelection);
    };

    // Toggle single column
    // PKs cannot be toggled off individually when table is selected
    const toggleColumn = (table: string, column: string, isPrimaryKey: boolean) => {
        const tableIsSelected = isTableSelected(table);

        // If it's a PK and table is selected, don't allow toggle
        if (isPrimaryKey && tableIsSelected) return;

        const currentSet = new Set(selected[table] || []);
        if (currentSet.has(column)) {
            currentSet.delete(column);
        } else {
            currentSet.add(column);
        }

        // Ensure PKs remain selected if table still has other selections
        const newSet = ensurePrimaryKeys(table, currentSet);
        const newSelection = { ...selected, [table]: newSet };
        setSelected(newSelection);
        emitSelection(newSelection);
    };

    const toggleAllGlobal = () => {
        if (!schema) return;

        // Check if completely everything is selected
        let allSelected = true;
        for (const table of schema.tables) {
            const currentSet = selected[table.table_name];
            if (!currentSet || currentSet.size !== table.columns.length) {
                allSelected = false;
                break;
            }
        }

        const newSelection: Record<string, Set<string>> = {};
        if (allSelected) {
            // Deselect everything (including PKs)
            schema.tables.forEach(t => {
                newSelection[t.table_name] = new Set();
            });
        } else {
            // Select everything
            schema.tables.forEach(t => {
                newSelection[t.table_name] = new Set(t.columns.map(c => c.column_name));
            });
        }

        setSelected(newSelection);
        emitSelection(newSelection);
    };

    // Helper to count total selected columns
    const totalSelectedCount = Object.values(selected).reduce((acc, set) => acc + (set ? set.size : 0), 0);
    const totalTablesSelected = Object.values(selected).filter(set => set && set.size > 0).length;

    if (isLoading) {
        return (
            <div className="w-full max-w-4xl mx-auto">
                <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables & Columns</h2>
                <div className="flex justify-center items-center py-8">
                    <svg className="animate-spin h-6 w-6 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span className="ml-2 text-xs sm:text-sm text-gray-500">Inspecting database schema...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="w-full max-w-4xl mx-auto">
                <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables & Columns</h2>
                <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
                    <p className="text-red-800 font-medium">{error}</p>
                    <button
                        onClick={fetchSchema}
                        className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                    >
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    if (dataSourceType === 'database' && schema) {
        // Check if there's a connection error from the backend
        if ((schema as any).error) {
            const errorMessage = (schema as any).error;
            return (
                <div className="w-full max-w-4xl mx-auto">
                    <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables & Columns</h2>
                    <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                        <div className="flex items-start gap-3">
                            <svg className="w-6 h-6 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <div className="flex-1 min-w-0">
                                <p className="text-red-800 font-medium">Database Connection Error</p>
                                <p className="text-red-700 text-sm mt-1 break-words">{errorMessage}</p>
                                <div className="mt-4 text-sm text-gray-600">
                                    <p className="font-medium">Common causes:</p>
                                    <ul className="list-disc list-inside mt-1 space-y-1 text-xs">
                                        <li>Database host is unreachable (check firewall/VPN)</li>
                                        <li>Invalid connection URL format (missing port or database name)</li>
                                        <li>Incorrect credentials</li>
                                        <li>Database server is down</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={fetchSchema}
                            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                        >
                            Retry Connection
                        </button>
                    </div>
                </div>
            );
        }

        if (schema.tables.length === 0) {
            return (
                <div className="w-full max-w-4xl mx-auto">
                    <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables & Columns</h2>
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
                        <div className="flex items-start gap-3">
                            <svg className="w-6 h-6 text-yellow-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <div>
                                <p className="text-yellow-800 font-medium">No tables found</p>
                                <p className="text-yellow-700 text-sm mt-1">
                                    Connected successfully, but no accessible tables were found.
                                    The database may be empty or the user may not have permission to view tables.
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={fetchSchema}
                            className="mt-4 px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700"
                        >
                            Refresh
                        </button>
                    </div>
                </div>
            );
        }

        return (
            <div className="w-full max-w-4xl mx-auto overflow-x-hidden">
                <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4">Select Tables & Columns</h2>
                <p className="text-gray-500 text-xs sm:text-sm mb-4 sm:mb-6">
                    Select which tables and columns to include for analysis. The AI will only be aware of the data you select.
                </p>

                <div className="space-y-3 sm:space-y-4 w-full overflow-hidden">
                    {/* Missing dependencies warning banner */}
                    {Object.keys(missingDependencies).length > 0 && (
                        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-start gap-2">
                                <span className="text-red-500 flex-shrink-0">⚠️</span>
                                <div className="text-sm">
                                    <p className="font-medium text-red-800">Missing table dependencies</p>
                                    <p className="text-red-700 text-xs mt-1">
                                        Some selected tables have foreign key references to tables that are not selected.
                                        This may cause issues with data analysis.
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 bg-gray-50 p-2 sm:p-3 rounded">
                        <div className="flex flex-col min-w-0">
                            <span className="text-xs sm:text-sm font-medium text-gray-700">
                                {totalTablesSelected} tables ({totalSelectedCount} columns) selected
                            </span>
                            <span className="text-[10px] sm:text-xs text-gray-500">
                                🔑 = Primary Key (locked when table selected) • 🔗 = Foreign Key
                            </span>
                        </div>
                        {canEdit && (
                            <button
                                onClick={toggleAllGlobal}
                                className="text-xs text-blue-600 hover:text-blue-800 font-medium px-2 py-1 rounded hover:bg-blue-100 self-start sm:self-auto flex-shrink-0"
                            >
                                Select/Deselect All
                            </button>
                        )}
                    </div>

                    <div className="border rounded-md h-[350px] sm:h-[500px] overflow-y-auto overflow-x-hidden bg-white w-full">
                        {schema.tables.map((table: TableInfoResponse) => {
                            const tableCols = table.columns;
                            const selectedCols = selected[table.table_name] || new Set();
                            const isExpanded = expandedTables.has(table.table_name);
                            const isAllSelected = selectedCols.size === tableCols.length && tableCols.length > 0;
                            const isIndeterminate = selectedCols.size > 0 && selectedCols.size < tableCols.length;

                            return (
                                <div key={table.table_name} className="border-b last:border-b-0 border-gray-100">
                                    {/* Table Header Row */}
                                    <div
                                        className={`flex items-center px-2 sm:px-4 py-2 sm:py-3 hover:bg-gray-50 cursor-pointer ${selectedCols.size > 0 ? 'bg-blue-50/50' : ''}`}
                                        onClick={() => toggleTableExpansion(table.table_name)}
                                    >
                                        <div
                                            className="mr-2 sm:mr-3 flex-shrink-0"
                                            onClick={(e) => { e.stopPropagation(); toggleTableSelection(table.table_name, tableCols.map(c => c.column_name)); }}
                                        >
                                            <input
                                                type="checkbox"
                                                className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4"
                                                checked={isAllSelected}
                                                ref={input => { if (input) input.indeterminate = isIndeterminate; }}
                                                onChange={() => { }}
                                                disabled={!canEdit}
                                            />
                                        </div>

                                        <div className="flex-1 min-w-0 overflow-hidden">
                                            <div className="flex flex-wrap items-center gap-1">
                                                <span className="text-xs sm:text-sm font-medium text-gray-900 truncate">{table.table_name}</span>
                                                <span className="text-[10px] sm:text-xs text-gray-500 flex-shrink-0">
                                                    {selectedCols.size} / {tableCols.length} cols
                                                </span>
                                            </div>
                                            {reasoning && reasoning[table.table_name] && (
                                                <span className="text-[10px] text-amber-600 bg-amber-50 px-1 sm:px-2 py-0.5 rounded border border-amber-200 truncate block mt-1 max-w-full" title={reasoning[table.table_name]}>
                                                    💡 {reasoning[table.table_name]}
                                                </span>
                                            )}
                                            {/* Show missing dependency warning */}
                                            {missingDependencies[table.table_name] && (
                                                <span className="text-[10px] text-red-600 bg-red-50 px-1 sm:px-2 py-0.5 rounded border border-red-200 block mt-1 max-w-full">
                                                    ⚠️ Requires: {missingDependencies[table.table_name].join(', ')}
                                                </span>
                                            )}
                                        </div>

                                        <div className="text-gray-400 flex-shrink-0 ml-2">
                                            {isExpanded ? (
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                                            ) : (
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                                            )}
                                        </div>
                                    </div>

                                    {/* Column List (Collapsible) */}
                                    {isExpanded && (
                                        <div className="bg-gray-50 px-2 sm:px-4 py-2 border-t border-gray-100 grid grid-cols-1 sm:grid-cols-2 gap-1 sm:gap-2">
                                            {tableCols.map((col: ColumnInfo) => {
                                                const isPK = col.is_primary_key || (primaryKeyMap.get(table.table_name)?.has(col.column_name) ?? false);
                                                const hasFK = !!col.foreign_key;
                                                const tableHasSelections = selectedCols.size > 0;
                                                // PKs are disabled only when table has selections
                                                const isPKDisabled = isPK && tableHasSelections;
                                                const isDisabled = !canEdit || isPKDisabled;

                                                return (
                                                    <div key={col.column_name} className={`flex items-center group min-w-0 ${isPK && tableHasSelections ? 'bg-yellow-50 rounded px-1' : ''}`}>
                                                        <input
                                                            type="checkbox"
                                                            id={`${table.table_name}-${col.column_name}`}
                                                            className={`rounded h-3 w-3 mr-2 flex-shrink-0 ${isPKDisabled ? 'text-yellow-600 cursor-not-allowed' : 'text-blue-600'} focus:ring-blue-500`}
                                                            checked={selectedCols.has(col.column_name)}
                                                            onChange={() => !isDisabled && toggleColumn(table.table_name, col.column_name, isPK)}
                                                            disabled={isDisabled}
                                                        />
                                                        <label
                                                            htmlFor={`${table.table_name}-${col.column_name}`}
                                                            className={`text-[10px] sm:text-xs flex-1 truncate flex items-center min-w-0 ${isPKDisabled ? 'text-yellow-800 cursor-not-allowed' : 'text-gray-700 cursor-pointer hover:text-blue-700'}`}
                                                            title={`${col.column_name} (${col.data_type})${isPK ? ' - Primary Key' : ''}${hasFK ? ` - FK → ${col.foreign_key?.referenced_table}` : ''}`}
                                                        >
                                                            {isPK && <span className="text-yellow-600 mr-1 flex-shrink-0" title="Primary Key">🔑</span>}
                                                            {hasFK && <span className="text-purple-500 mr-1 flex-shrink-0" title={`Foreign Key → ${col.foreign_key?.referenced_table}`}>🔗</span>}
                                                            <span className="font-medium mr-1 truncate">{col.column_name}</span>
                                                            <span className="text-gray-400 text-[9px] sm:text-[10px] flex-shrink-0">{col.data_type}</span>
                                                            {reasoning && reasoning[`${table.table_name}.${col.column_name}`] && (
                                                                <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 rounded border border-amber-100 truncate max-w-[150px] ml-1" title={reasoning[`${table.table_name}.${col.column_name}`]}>
                                                                    💡 {reasoning[`${table.table_name}.${col.column_name}`]}
                                                                </span>
                                                            )}
                                                        </label>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        );
    }

    if (dataSourceType === 'file') {
        // For files, use schema from API or fallback to fileUploadResult
        const columns = schema?.tables?.[0]?.columns?.map(c => c.column_name) || preview?.columns || fileUploadResult?.columns || [];
        const columnDetails = preview?.column_details || fileUploadResult?.column_details;

        // Get documents from either fileUploadResult (fresh upload) or preview API (existing source)
        const documents = fileUploadResult?.documents?.length
            ? fileUploadResult.documents
            : preview?.documents || [];
        const totalDocuments = fileUploadResult?.total_documents || preview?.total_documents || 0;
        const fileName = schema?.file_name || preview?.file_name || fileUploadResult?.file_name || 'your file';
        const fileType = fileUploadResult?.file_type || 'csv';

        return (
            <div className="w-full max-w-4xl mx-auto space-y-6">
                <h2 className="text-lg sm:text-xl font-semibold mb-1">Select Columns</h2>
                <p className="text-gray-500 text-xs sm:text-sm mb-4">
                    Choose which columns from <strong>{fileName}</strong> to include for embedding and analysis.
                    {(schema?.row_count || preview?.row_count) && (
                        <span className="ml-1">({(schema?.row_count || preview?.row_count)?.toLocaleString()} rows)</span>
                    )}
                </p>

                <FileColumnSelector
                    key={columns.join(',')}
                    columns={columns}
                    columnDetails={columnDetails}
                    selectedColumns={selectedFileColumns}
                    onSelectionChange={onFileColumnsChange || (() => { })}
                    readOnly={!canEdit}
                />

                {/* Data preview — shown when documents are available */}
                {documents.length > 0 && (
                    <div className="mt-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                        <DocumentPreview
                            documents={documents}
                            fileName={fileName}
                            fileType={fileType}
                            totalDocuments={totalDocuments}
                        />
                    </div>
                )}
            </div>
        );
    }

    return (
        <div className="w-full max-w-2xl mx-auto text-center py-8 sm:py-12 px-4">
            <p className="text-gray-500 text-sm">
                Please go back and select a data source first.
            </p>
        </div>
    );
};

export default SchemaSelectionStep;

