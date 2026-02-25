import React, { useState } from 'react';
import {
    ClockIcon,
    UserIcon,
    CheckCircleIcon,
    ChevronDownIcon,
    ChevronUpIcon
} from '@heroicons/react/24/outline';

export interface PromptVersion {
    id: number;
    version: string | number;
    created_at: string;
    prompt_text: string;
    is_active: number;
    created_by_username?: string;
    connection_id?: number;
    data_source_type?: string;
    schema_selection?: string;
    data_dictionary?: string;
    reasoning?: string;
    example_questions?: string;
    ingestion_documents?: string;
    ingestion_file_name?: string;
    ingestion_file_type?: string;
    embedding_config?: string;
    retriever_config?: string;
    chunking_config?: string;
    llm_config?: string;
}

interface PromptHistoryProps {
    history: PromptVersion[];
    onRollback?: (version: PromptVersion) => void;
    onCompare?: (v1: PromptVersion, v2: PromptVersion) => void;
    onSelect?: (version: PromptVersion) => void;
    currentVersionId?: number | null;
}

const PromptHistory: React.FC<PromptHistoryProps> = ({ history, onRollback, onCompare, onSelect, currentVersionId }) => {
    const [expandedVersion, setExpandedVersion] = useState<number | null>(null);

    // If onSelect is provided but not onRollback, we are in "compact" mode (sidebar)
    const isCompact = !!onSelect && !onRollback;

    const activeVersion = history.find(v => v.is_active === 1);

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleString(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short'
        });
    };

    if (history.length === 0) {
        return (
            <div className={`p-12 text-center ${isCompact ? 'p-6' : ''}`}>
                <ClockIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900">No History Found</h3>
                <p className="text-sm text-gray-500">History will appear here once published.</p>
            </div>
        );
    }

    if (isCompact) {
        return (
            <div className="flex flex-col h-full bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
                    <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Version History</h3>
                    <ClockIcon className="w-4 h-4 text-gray-400" />
                </div>
                <div className="flex-1 overflow-y-auto">
                    <ul className="divide-y divide-gray-100">
                        {history.map((version) => (
                            <li
                                key={version.id}
                                onClick={() => onSelect && onSelect(version)}
                                className={`px-4 py-4 cursor-pointer hover:bg-blue-50/50 transition-colors group ${currentVersionId === version.id ? 'bg-blue-50 border-l-4 border-blue-500' : 'border-l-4 border-transparent'
                                    }`}
                            >
                                <div className="flex justify-between items-start mb-1">
                                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${version.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                                        }`}>
                                        v{version.version}
                                    </span>
                                    <span className="text-[10px] text-gray-400 font-medium">
                                        {new Date(version.created_at).toLocaleDateString()}
                                    </span>
                                </div>
                                <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed group-hover:text-gray-700">
                                    {version.prompt_text.slice(0, 100)}...
                                </p>
                            </li>
                        ))}
                    </ul>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white">
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Version</th>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Data Source</th>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Connection / File</th>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Created By</th>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Date</th>
                            <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Status</th>
                            <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                        {history.map((item) => (
                            <React.Fragment key={item.id}>
                                <tr className={`hover:bg-gray-50 transition-colors ${item.is_active ? 'bg-blue-50/30' : ''}`}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center gap-3">
                                            <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 text-gray-700 font-bold text-sm">
                                                {item.version}
                                            </span>
                                            <div>
                                                <p className="text-sm font-semibold text-gray-900">Version {item.version}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-xs font-semibold text-gray-800 capitalize bg-gray-100 px-2 py-1 rounded-md">
                                            {item.data_source_type || 'database'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                        <div className="max-w-[150px] truncate" title={item.ingestion_file_name || String(item.connection_id)}>
                                            {item.ingestion_file_name || `ID: ${item.connection_id}`}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center gap-2">
                                            <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center">
                                                <UserIcon className="w-3.5 h-3.5 text-indigo-600" />
                                            </div>
                                            <span className="text-sm text-gray-700">{item.created_by_username || 'System'}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {formatDate(item.created_at)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {item.is_active ? (
                                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-green-100 text-green-700">
                                                <CheckCircleIcon className="w-3.5 h-3.5" />
                                                Active
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                                                Historical
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setExpandedVersion(expandedVersion === item.id ? null : item.id)}
                                                className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
                                                title="View Details"
                                            >
                                                {expandedVersion === item.id ? <ChevronUpIcon className="w-5 h-5" /> : <ChevronDownIcon className="w-5 h-5" />}
                                            </button>

                                            {activeVersion && !item.is_active && onCompare && (
                                                <button
                                                    onClick={() => onCompare(item, activeVersion)}
                                                    className="flex items-center px-3 py-1.5 text-emerald-600 hover:text-emerald-700 rounded-lg hover:bg-emerald-50 transition-colors border border-emerald-200"
                                                    title="Compare with Active"
                                                >
                                                    <span>Compare</span>
                                                </button>
                                            )}

                                            {onRollback && !item.is_active && (
                                                <button
                                                    onClick={() => onRollback(item)}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-indigo-600 hover:text-indigo-700 rounded-lg hover:bg-indigo-50 transition-colors border border-indigo-200"
                                                    title="Rollback to this version"
                                                >
                                                    <span>Rollback</span>
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                                {expandedVersion === item.id && (
                                    <tr className="bg-gray-50/50">
                                        <td colSpan={7} className="px-8 py-6">
                                            <div className="animate-in slide-in-from-top-2 duration-200">
                                                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">System Prompt</h4>
                                                <div className="bg-white p-4 rounded-xl border border-gray-200 text-xs font-mono text-gray-700 max-h-80 overflow-y-auto whitespace-pre-wrap leading-relaxed shadow-inner">
                                                    {item.prompt_text}
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default PromptHistory;
