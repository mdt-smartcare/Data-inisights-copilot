import React, { useState, useMemo } from 'react';

interface ColumnDetail {
    name: string;
    type: string;
}

interface FileColumnSelectorProps {
    /** Column names (simple list) */
    columns?: string[];
    /** Column details with types (preferred if available) */
    columnDetails?: ColumnDetail[];
    /** Currently selected columns (controlled) */
    selectedColumns?: string[];
    /** Callback with selected column names */
    onSelectionChange: (selectedColumns: string[]) => void;
    /** If true, disable all interaction */
    readOnly?: boolean;
}

const TYPE_BADGES: Record<string, string> = {
    VARCHAR: 'bg-emerald-100 text-emerald-700',
    BIGINT: 'bg-blue-100 text-blue-700',
    INTEGER: 'bg-blue-100 text-blue-700',
    DOUBLE: 'bg-purple-100 text-purple-700',
    FLOAT: 'bg-purple-100 text-purple-700',
    BOOLEAN: 'bg-amber-100 text-amber-700',
    DATE: 'bg-pink-100 text-pink-700',
    TIMESTAMP: 'bg-pink-100 text-pink-700',
};

const getBadgeClass = (type: string) => {
    const upper = (type || '').toUpperCase();
    for (const [key, cls] of Object.entries(TYPE_BADGES)) {
        if (upper.includes(key)) return cls;
    }
    return 'bg-gray-100 text-gray-600';
};

/**
 * Column selector for uploaded file data.
 * Allows users to choose which columns to include for embedding / processing.
 */
const FileColumnSelector: React.FC<FileColumnSelectorProps> = ({
    columns,
    columnDetails,
    selectedColumns,
    onSelectionChange,
    readOnly = false,
}) => {
    // Derive items from columnDetails (preferred) or plain columns list
    const items: ColumnDetail[] = useMemo(() => {
        if (columnDetails && columnDetails.length > 0) return columnDetails;
        if (columns && columns.length > 0) return columns.map(c => ({ name: c, type: '' }));
        return [];
    }, [columns, columnDetails]);

    // Selection state - controlled by parent when selectedColumns is provided
    const [selected, setSelected] = useState<Set<string>>(() => {
        if (selectedColumns && selectedColumns.length > 0) {
            return new Set(selectedColumns);
        }
        return new Set(items.map(c => c.name));
    });



    // Initial state is correctly set via useState initializer. 
    // Synchronous state updates in response to prop changes are handled by the 'key' prop in parent.

    const allSelected = selected.size === items.length && items.length > 0;
    const noneSelected = selected.size === 0;

    const toggleColumn = (name: string) => {
        if (readOnly) return;
        const next = new Set(selected);
        if (next.has(name)) {
            next.delete(name);
        } else {
            next.add(name);
        }
        setSelected(next);
        onSelectionChange(Array.from(next));
    };

    const toggleAll = () => {
        if (readOnly) return;
        if (allSelected) {
            setSelected(new Set());
            onSelectionChange([]);
        } else {
            const all = new Set(items.map(c => c.name));
            setSelected(all);
            onSelectionChange(Array.from(all));
        }
    };

    if (items.length === 0) {
        return (
            <div className="text-gray-500 italic text-sm py-4 text-center">
                No columns detected in this file.
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                <div className="flex flex-col">
                    <span className="text-sm font-medium text-gray-700">
                        {selected.size} of {items.length} columns selected
                    </span>
                    <span className="text-xs text-gray-500">
                        Choose which columns to include for embedding
                    </span>
                </div>
                {!readOnly && (
                    <button
                        onClick={toggleAll}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium px-2 py-1 rounded hover:bg-blue-100 flex-shrink-0"
                    >
                        {allSelected ? 'Deselect All' : 'Select All'}
                    </button>
                )}
            </div>

            {/* Column List */}
            <div className="border rounded-md max-h-[350px] overflow-y-auto bg-white">
                {items.map((col) => {
                    const isSelected = selected.has(col.name);
                    return (
                        <div
                            key={col.name}
                            className={`flex items-center px-4 py-2.5 border-b last:border-b-0 border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${isSelected ? 'bg-blue-50/40' : ''}`}
                            onClick={() => toggleColumn(col.name)}
                        >
                            <input
                                type="checkbox"
                                className="rounded text-blue-600 focus:ring-blue-500 h-4 w-4 mr-3 flex-shrink-0"
                                checked={isSelected}
                                onChange={() => { }} // handled by parent onClick
                                disabled={readOnly}
                            />
                            <span className="text-sm font-medium text-gray-900 flex-1 truncate">
                                {col.name}
                            </span>
                            {col.type && (
                                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ml-2 flex-shrink-0 ${getBadgeClass(col.type)}`}>
                                    {col.type}
                                </span>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Warning */}
            {noneSelected && (
                <div className="flex items-center gap-2 p-2 bg-amber-50 border border-amber-200 rounded-lg">
                    <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span className="text-xs text-amber-700">Select at least one column to proceed.</span>
                </div>
            )}
        </div>
    );
};

export default FileColumnSelector;
