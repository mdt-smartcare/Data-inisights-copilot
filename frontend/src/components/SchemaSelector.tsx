import React, { useState, useEffect } from 'react';
import { getConnectionSchema, handleApiError } from '../services/api';

interface SchemaSelectorProps {
    connectionId: number;
    onSelectionChange: (selectedTables: string[]) => void;
}

const SchemaSelector: React.FC<SchemaSelectorProps> = ({ connectionId, onSelectionChange }) => {
    const [tables, setTables] = useState<string[]>([]);
    const [details, setDetails] = useState<Record<string, any[]>>({});
    const [selected, setSelected] = useState<Set<string>>(new Set());
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
                // Default: Select all tables initially? Or none?
                // Let's select all by default for convenience
                const all = new Set(data.schema.tables);
                setSelected(all);
                onSelectionChange(Array.from(all));
            } catch (err) {
                setError(handleApiError(err));
                setTables([]);
            } finally {
                setLoading(false);
            }
        };

        fetchSchema();
    }, [connectionId]);

    const toggleTable = (table: string) => {
        const newSelected = new Set(selected);
        if (newSelected.has(table)) {
            newSelected.delete(table);
        } else {
            newSelected.add(table);
        }
        setSelected(newSelected);
        onSelectionChange(Array.from(newSelected));
    };

    const toggleAll = () => {
        if (selected.size === tables.length) {
            setSelected(new Set());
            onSelectionChange([]);
        } else {
            const all = new Set(tables);
            setSelected(all);
            onSelectionChange(tables);
        }
    };

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
                <span className="text-sm font-medium text-gray-700">{selected.size} tables selected</span>
                <button
                    onClick={toggleAll}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium px-2 py-1 rounded hover:bg-blue-100"
                >
                    {selected.size === tables.length ? 'Deselect All' : 'Select All'}
                </button>
            </div>

            <div className="border rounded-md max-h-[400px] overflow-y-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50 sticky top-0">
                        <tr>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-10">
                                <input
                                    type="checkbox"
                                    checked={selected.size === tables.length && tables.length > 0}
                                    onChange={toggleAll}
                                    className="rounded text-blue-600 focus:ring-blue-500"
                                />
                            </th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Table Name</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Columns</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {tables.map((table) => (
                            <tr key={table} className={selected.has(table) ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                                <td className="px-4 py-2 whitespace-nowrap">
                                    <input
                                        type="checkbox"
                                        checked={selected.has(table)}
                                        onChange={() => toggleTable(table)}
                                        className="rounded text-blue-600 focus:ring-blue-500"
                                    />
                                </td>
                                <td className="px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
                                    {table}
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-500 max-w-xs truncate" title={details[table]?.map(c => c.name).join(', ')}>
                                    {details[table]?.length || 0} columns ({details[table]?.slice(0, 3).map(c => c.name).join(', ')}...)
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default SchemaSelector;
