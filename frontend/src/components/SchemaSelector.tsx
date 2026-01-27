import React, { useState, useEffect } from 'react';
import { getConnectionSchema, handleApiError } from '../services/api';

interface SchemaSelectorProps {
    connectionId: number;
    // Map of TableName -> List of Selected Column Names
    onSelectionChange: (selection: Record<string, string[]>) => void;
}

const SchemaSelector: React.FC<SchemaSelectorProps> = ({ connectionId, onSelectionChange }) => {
    const [tables, setTables] = useState<string[]>([]);
    // details is Record<TableName, {name, type, nullable}[]>
    const [details, setDetails] = useState<Record<string, any[]>>({});

    // Selected state: Record<TableName, Set<ColumnName>>
    // We use Sets internally for O(1) lookups, convert to arrays for prop output.
    const [selected, setSelected] = useState<Record<string, Set<string>>>({});

    const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!connectionId) return;

        const fetchSchema = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await getConnectionSchema(connectionId);
                setTables(data.schema.tables);
                setDetails(data.schema.details);

                // Default: Select ALL columns for ALL tables
                const initialSelection: Record<string, Set<string>> = {};

                data.schema.tables.forEach((table) => {
                    const tableCols = data.schema.details[table] || [];
                    // Create a set of all column names for this table
                    initialSelection[table] = new Set(tableCols.map((c: any) => c.name));
                });

                setSelected(initialSelection);
                emitSelection(initialSelection);

            } catch (err) {
                setError(handleApiError(err));
                setTables([]);
            } finally {
                setLoading(false);
            }
        };

        fetchSchema();
    }, [connectionId]);

    const emitSelection = (currentSelection: Record<string, Set<string>>) => {
        const output: Record<string, string[]> = {};
        Object.entries(currentSelection).forEach(([table, colSet]) => {
            if (colSet.size > 0) {
                output[table] = Array.from(colSet);
            }
        });
        onSelectionChange(output);
    };

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
    const toggleTableSelection = (table: string) => {
        const allCols = details[table]?.map(c => c.name) || [];
        const currentSet = selected[table] || new Set();

        const newSelection = { ...selected };

        if (currentSet.size === allCols.length) {
            // Deselect all
            newSelection[table] = new Set();
        } else {
            // Select all
            newSelection[table] = new Set(allCols);
        }

        setSelected(newSelection);
        emitSelection(newSelection);
    };

    // Toggle single column
    const toggleColumn = (table: string, column: string) => {
        const currentSet = new Set(selected[table] || []);
        if (currentSet.has(column)) {
            currentSet.delete(column);
        } else {
            currentSet.add(column);
        }

        const newSelection = { ...selected, [table]: currentSet };
        setSelected(newSelection);
        emitSelection(newSelection);
    };

    const toggleAllGlobal = () => {
        // Check if completely everything is selected
        let allSelected = true;
        for (const table of tables) {
            const tableCols = details[table] || [];
            const currentSet = selected[table];
            if (!currentSet || currentSet.size !== tableCols.length) {
                allSelected = false;
                break;
            }
        }

        const newSelection: Record<string, Set<string>> = {};
        if (allSelected) {
            // Deselect everything
            tables.forEach(t => newSelection[t] = new Set());
        } else {
            // Select everything
            tables.forEach(t => {
                const cols = details[t]?.map(c => c.name) || [];
                newSelection[t] = new Set(cols);
            });
        }

        setSelected(newSelection);
        emitSelection(newSelection);
    };

    // Helper to count total selected columns
    const totalSelectedCount = Object.values(selected).reduce((acc, set) => acc + (set ? set.size : 0), 0);
    const totalTablesSelected = Object.values(selected).filter(set => set && set.size > 0).length;

    if (loading) {
        return (
            <div className="flex justify-center items-center py-8">
                <svg className="animate-spin h-6 w-6 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span className="ml-2 text-sm text-gray-500">Inspecting database schema...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded text-sm">
                Error fetching schema: {error}
            </div>
        );
    }

    if (tables.length === 0) {
        return <div className="text-gray-500 italic text-sm">No tables found in this database.</div>;
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center bg-gray-50 p-2 rounded">
                <div className="flex flex-col">
                    <span className="text-sm font-medium text-gray-700">
                        {totalTablesSelected} tables ({totalSelectedCount} columns) selected
                    </span>
                    <span className="text-xs text-gray-500">Expand tables to select individual columns</span>
                </div>
                <button
                    onClick={toggleAllGlobal}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium px-2 py-1 rounded hover:bg-blue-100"
                >
                    Select/Deselect All
                </button>
            </div>

            <div className="border rounded-md h-[500px] overflow-y-auto bg-white">
                {tables.map(table => {
                    const tableCols = details[table] || [];
                    const selectedCols = selected[table] || new Set();
                    const isExpanded = expandedTables.has(table);
                    const isAllSelected = selectedCols.size === tableCols.length && tableCols.length > 0;
                    const isIndeterminate = selectedCols.size > 0 && selectedCols.size < tableCols.length;

                    return (
                        <div key={table} className="border-b last:border-b-0 border-gray-100">
                            {/* Table Header Row */}
                            <div
                                className={`flex items-center px-4 py-3 hover:bg-gray-50 cursor-pointer ${selectedCols.size > 0 ? 'bg-blue-50/50' : ''}`}
                                onClick={() => toggleTableExpansion(table)}
                            >
                                <div
                                    className="mr-3"
                                    onClick={(e) => { e.stopPropagation(); toggleTableSelection(table); }}
                                >
                                    <input
                                        type="checkbox"
                                        className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4"
                                        checked={isAllSelected}
                                        ref={input => { if (input) input.indeterminate = isIndeterminate; }}
                                        onChange={() => { }} // Handle click instead
                                    />
                                </div>

                                <div className="flex-1">
                                    <span className="text-sm font-medium text-gray-900">{table}</span>
                                    <span className="ml-2 text-xs text-gray-500">
                                        {selectedCols.size} / {tableCols.length} cols
                                    </span>
                                </div>

                                <div className="text-gray-400">
                                    {isExpanded ? (
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                                    ) : (
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                                    )}
                                </div>
                            </div>

                            {/* Column List (Collapsible) */}
                            {isExpanded && (
                                <div className="bg-gray-50 px-4 py-2 border-t border-gray-100 grid grid-cols-1 md:grid-cols-2 gap-2">
                                    {tableCols.map((col: any) => (
                                        <div key={col.name} className="flex items-center group">
                                            <input
                                                type="checkbox"
                                                id={`${table}-${col.name}`}
                                                className="rounded text-blue-600 focus:ring-blue-500 h-3 w-3 mr-2"
                                                checked={selectedCols.has(col.name)}
                                                onChange={() => toggleColumn(table, col.name)}
                                            />
                                            <label
                                                htmlFor={`${table}-${col.name}`}
                                                className="text-xs text-gray-700 cursor-pointer flex-1 truncate hover:text-blue-700"
                                                title={`${col.name} (${col.type})`}
                                            >
                                                <span className="font-medium">{col.name}</span>
                                                <span className="ml-1 text-gray-400 text-[10px]">{col.type}</span>
                                            </label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default SchemaSelector;
