import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canEditPrompt } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import { APP_CONFIG } from '../config';

const getAuthToken = (): string | null => localStorage.getItem('auth_token');

interface PromptVersion {
    id: number;
    version: number;
    prompt_text: string;
    is_active: number;
    created_by_username?: string;
    created_at: string;
    connection_id?: number;
    schema_selection?: string;
    data_dictionary?: string;
    reasoning?: string;
    example_questions?: string;
}

const PromptHistoryPage: React.FC = () => {
    const { user } = useAuth();
    const [versions, setVersions] = useState<PromptVersion[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedVersion, setSelectedVersion] = useState<PromptVersion | null>(null);
    const [compareVersion, setCompareVersion] = useState<PromptVersion | null>(null);
    const [showCompare, setShowCompare] = useState(false);
    const [rollbackLoading, setRollbackLoading] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    const canEdit = canEditPrompt(user);

    useEffect(() => {
        loadVersions();
    }, []);

    const loadVersions = async () => {
        setLoading(true);
        setError(null);
        try {
            const token = getAuthToken();
            const res = await fetch('/api/v1/config/history', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load prompt history');
            const data = await res.json();
            setVersions(data);
            if (data.length > 0) {
                const active = data.find((v: PromptVersion) => v.is_active);
                setSelectedVersion(active || data[0]);
            }
        } catch (err: any) {
            setError(err.message || 'Failed to load prompt history');
        } finally {
            setLoading(false);
        }
    };

    const handleCompare = (version: PromptVersion) => {
        if (compareVersion?.id === version.id) {
            setCompareVersion(null);
            setShowCompare(false);
        } else {
            setCompareVersion(version);
            setShowCompare(true);
        }
    };

    const handleRollback = async (version: PromptVersion) => {
        if (!canEdit) {
            setError('You do not have permission to rollback prompts');
            return;
        }
        if (!window.confirm(`Rollback to version ${version.version}? This will make it the active prompt.`)) {
            return;
        }
        setRollbackLoading(true);
        setError(null);
        try {
            const token = getAuthToken();
            const res = await fetch(`/api/v1/config/rollback/${version.id}`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || 'Failed to rollback');
            }
            const data = await res.json();
            setSuccessMessage(`Rolled back to version ${data.version}`);
            loadVersions();
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (err: any) {
            setError(err.message || 'Failed to rollback');
        } finally {
            setRollbackLoading(false);
        }
    };

    const renderDiff = (text1: string, text2: string) => {
        // Simple line-by-line diff visualization
        const lines1 = text1.split('\n');
        const lines2 = text2.split('\n');
        const maxLines = Math.max(lines1.length, lines2.length);

        return (
            <div className="font-mono text-xs overflow-x-auto">
                {Array.from({ length: maxLines }).map((_, i) => {
                    const line1 = lines1[i] || '';
                    const line2 = lines2[i] || '';
                    const isDifferent = line1 !== line2;

                    return (
                        <div key={i} className={`flex ${isDifferent ? 'bg-yellow-50' : ''}`}>
                            <div className="w-8 text-right pr-2 text-gray-400 select-none border-r border-gray-200">
                                {i + 1}
                            </div>
                            <div className="flex-1 grid grid-cols-2 gap-2">
                                <div className={`px-2 py-0.5 ${isDifferent && line1 ? 'bg-red-100 text-red-800' : ''}`}>
                                    {line1}
                                </div>
                                <div className={`px-2 py-0.5 ${isDifferent && line2 ? 'bg-green-100 text-green-800' : ''}`}>
                                    {line2}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-hidden flex">
                {/* Version List Sidebar */}
                <div className="w-72 bg-white border-r border-gray-200 flex flex-col">
                    <div className="p-4 border-b border-gray-200">
                        <h2 className="text-lg font-semibold text-gray-900">Prompt Versions</h2>
                        <p className="text-sm text-gray-500">{versions.length} versions</p>
                    </div>
                    <div className="flex-1 overflow-y-auto">
                        {loading ? (
                            <div className="flex items-center justify-center py-8">
                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                            </div>
                        ) : versions.length === 0 ? (
                            <div className="p-4 text-center text-gray-400">No versions found</div>
                        ) : (
                            <ul className="divide-y divide-gray-100">
                                {versions.map((version) => (
                                    <li
                                        key={version.id}
                                        className={`cursor-pointer transition-colors ${selectedVersion?.id === version.id
                                            ? 'bg-blue-50 border-l-4 border-blue-500'
                                            : 'hover:bg-gray-50 border-l-4 border-transparent'
                                            }`}
                                    >
                                        <div
                                            onClick={() => setSelectedVersion(version)}
                                            className="px-4 py-3"
                                        >
                                            <div className="flex justify-between items-start">
                                                <div>
                                                    <span className={`text-sm font-semibold ${version.is_active ? 'text-green-600' : 'text-gray-700'}`}>
                                                        v{version.version}
                                                    </span>
                                                    {version.is_active ? (
                                                        <span className="ml-2 px-1.5 py-0.5 text-xs bg-green-100 text-green-700 rounded">Active</span>
                                                    ) : null}
                                                </div>
                                                <span className="text-xs text-gray-400">
                                                    {(() => {
                                                        try {
                                                            // Handle SQLite timestamp format "YYYY-MM-DD HH:MM:SS"
                                                            const dateStr = version.created_at.replace(' ', 'T') + 'Z';
                                                            return new Date(dateStr).toLocaleDateString();
                                                        } catch (e) {
                                                            return version.created_at;
                                                        }
                                                    })()}
                                                </span>
                                            </div>
                                            {version.created_by_username && (
                                                <p className="text-xs text-gray-500 mt-1">by {version.created_by_username}</p>
                                            )}
                                        </div>
                                        {selectedVersion && selectedVersion.id !== version.id && (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); handleCompare(version); }}
                                                className={`w-full px-4 py-1.5 text-xs text-left ${compareVersion?.id === version.id
                                                    ? 'bg-purple-100 text-purple-700'
                                                    : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                                                    }`}
                                            >
                                                {compareVersion?.id === version.id ? '✓ Comparing' : 'Compare with selected'}
                                            </button>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 flex flex-col overflow-hidden">
                    {error && (
                        <div className="m-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
                            {error}
                        </div>
                    )}

                    {successMessage && (
                        <div className="m-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded-md text-sm">
                            ✓ {successMessage}
                        </div>
                    )}

                    {selectedVersion && (
                        <div className="flex-1 overflow-auto p-6">
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h3 className="text-xl font-semibold text-gray-900">
                                        Version {selectedVersion.version}
                                        {selectedVersion.is_active && (
                                            <span className="ml-2 text-sm text-green-600">(Active)</span>
                                        )}
                                    </h3>
                                    <p className="text-sm text-gray-500">
                                        Created {(() => {
                                            try {
                                                const dateStr = selectedVersion.created_at.replace(' ', 'T') + 'Z';
                                                return new Date(dateStr).toLocaleString();
                                            } catch (e) {
                                                return selectedVersion.created_at;
                                            }
                                        })()}
                                        {selectedVersion.created_by_username && ` by ${selectedVersion.created_by_username}`}
                                    </p>
                                </div>
                                {canEdit && !selectedVersion.is_active && (
                                    <button
                                        onClick={() => handleRollback(selectedVersion)}
                                        disabled={rollbackLoading}
                                        className="px-4 py-2 bg-orange-600 text-white text-sm font-medium rounded-md hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        {rollbackLoading ? 'Rolling back...' : '↩ Rollback to this version'}
                                    </button>
                                )}
                                {showCompare && compareVersion && (
                                    <div className="text-right">
                                        <p className="text-sm font-medium text-purple-600">
                                            Comparing with v{compareVersion.version}
                                        </p>
                                        <button
                                            onClick={() => { setCompareVersion(null); setShowCompare(false); }}
                                            className="text-xs text-gray-500 hover:text-gray-700"
                                        >
                                            Clear comparison
                                        </button>
                                    </div>
                                )}
                            </div>

                            {showCompare && compareVersion ? (
                                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                                    <div className="grid grid-cols-2 text-center text-sm font-medium text-gray-600 bg-gray-50 border-b border-gray-200">
                                        <div className="py-2 border-r border-gray-200">v{selectedVersion.version} (Selected)</div>
                                        <div className="py-2">v{compareVersion.version} (Compare)</div>
                                    </div>
                                    <div className="max-h-[600px] overflow-auto">
                                        {renderDiff(selectedVersion.prompt_text, compareVersion.prompt_text)}
                                    </div>
                                </div>
                            ) : (
                                <div className="bg-white rounded-lg border border-gray-200 p-4">
                                    <h4 className="text-sm font-medium text-gray-700 mb-2">Prompt Text</h4>
                                    <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded max-h-[600px] overflow-auto">
                                        {selectedVersion.prompt_text}
                                    </pre>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default PromptHistoryPage;
