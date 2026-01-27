import React, { useState, useEffect } from 'react';
import { getConnections, saveConnection, deleteConnection, handleApiError } from '../services/api';
import Alert from './Alert';
import ConfirmationModal from './ConfirmationModal';
import { CONFIRMATION_MESSAGES } from '../config';
import type { DbConnection } from '../services/api';

interface ConnectionManagerProps {
    onSelect: (connectionId: number | null) => void;
    selectedId: number | null;
    readOnly?: boolean;
}

const ConnectionManager: React.FC<ConnectionManagerProps> = ({ onSelect, selectedId, readOnly = false }) => {
    const [connections, setConnections] = useState<DbConnection[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Form State
    const [isAdding, setIsAdding] = useState(false);
    const [newName, setNewName] = useState('');
    const [newUri, setNewUri] = useState('');

    // Deletion Modal
    const [deleteConfirm, setDeleteConfirm] = useState<{ show: boolean; id: number | null }>({ show: false, id: null });

    const fetchConnections = async () => {
        setLoading(true);
        try {
            const data = await getConnections();
            setConnections(data);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConnections();
    }, []);

    const handleSave = async () => {
        if (!newName || !newUri) {
            setError("Name and Connection String are required");
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const result = await saveConnection(newName, newUri);
            await fetchConnections();
            setIsAdding(false);
            setNewName('');
            setNewUri('');
            onSelect(result.id); // Auto-select new connection
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteClick = (id: number, e: React.MouseEvent) => {
        e.stopPropagation();
        setDeleteConfirm({ show: true, id });
    };

    const confirmDelete = async () => {
        if (deleteConfirm.id === null) return;

        const id = deleteConfirm.id;
        setDeleteConfirm({ show: false, id: null });

        setLoading(true);
        try {
            await deleteConnection(id);
            await fetchConnections();
            if (selectedId === id) onSelect(null); // Deselect if deleted
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-medium text-gray-900">Database Connections</h3>
                {!readOnly && (
                    <button
                        onClick={() => setIsAdding(!isAdding)}
                        className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                    >
                        {isAdding ? 'Cancel' : '+ New Connection'}
                    </button>
                )}
            </div>

            {error && (
                <Alert
                    type="error"
                    message={error}
                    onDismiss={() => setError(null)}
                />
            )}

            {isAdding && (
                <div className="bg-gray-50 p-4 rounded border border-gray-200 space-y-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-700">Name</label>
                        <input
                            type="text"
                            className="w-full mt-1 p-2 border rounded text-sm"
                            placeholder="e.g. Production DB"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-700">Connection URI</label>
                        <input
                            type="text"
                            className="w-full mt-1 p-2 border rounded text-sm font-mono"
                            placeholder="postgresql://user:pass@host:5432/dbname"
                            value={newUri}
                            onChange={(e) => setNewUri(e.target.value)}
                        />
                    </div>
                    <button
                        onClick={handleSave}
                        disabled={loading}
                        className="w-full py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                    >
                        {loading ? 'Saving...' : 'Save Connection'}
                    </button>
                </div>
            )}

            <div className="space-y-2">
                {connections.length === 0 && !loading && (
                    <p className="text-sm text-gray-500 italic">No connections saved.</p>
                )}

                {connections.map((conn) => (
                    <div
                        key={conn.id}
                        onClick={() => onSelect(conn.id)}
                        className={`p-3 rounded border cursor-pointer flex justify-between items-center transition-colors ${selectedId === conn.id
                            ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                            : 'border-gray-200 hover:bg-gray-50'
                            }`}
                    >
                        <div>
                            <p className="font-medium text-sm text-gray-900">{conn.name}</p>
                            <p className="text-xs text-gray-500 font-mono truncate max-w-xs">{conn.uri}</p>
                        </div>
                        {selectedId === conn.id && (
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-blue-600 font-semibold">Selected</span>
                                {!readOnly && (
                                    <button
                                        onClick={(e) => handleDeleteClick(conn.id, e)}
                                        className="text-gray-400 hover:text-red-600 p-1"
                                        title="Delete"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                        </svg>
                                    </button>
                                )}
                            </div>
                        )}
                        {selectedId !== conn.id && !readOnly && (
                            <button
                                onClick={(e) => handleDeleteClick(conn.id, e)}
                                className="text-gray-300 hover:text-red-500 p-1 opacity-0 group-hover:opacity-100 font-bold text-[10px]"
                            >
                                DELETE
                            </button>
                        )}
                    </div>
                ))}
            </div>

            {/* Confirmation Modal */}
            <ConfirmationModal
                show={deleteConfirm.show}
                title="Delete Connection"
                message={CONFIRMATION_MESSAGES.DELETE_CONNECTION}
                confirmText="Delete"
                onConfirm={confirmDelete}
                onCancel={() => setDeleteConfirm({ show: false, id: null })}
                isLoading={loading}
                type="danger"
            />
        </div>
    );
};

export default ConnectionManager;
