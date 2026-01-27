import React from 'react';

interface PromptVersion {
    id: number;
    version: number;
    created_at: string;
    prompt_text: string;
    is_active: number;
    created_by_username?: string;
}

interface PromptHistoryProps {
    history: PromptVersion[];
    onSelect: (prompt: PromptVersion) => void;
    currentVersionId?: number | null;
}

const PromptHistory: React.FC<PromptHistoryProps> = ({ history, onSelect, currentVersionId }) => {
    return (
        <div className="flex flex-col h-full bg-white border border-gray-200 rounded-md shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                <h3 className="text-sm font-semibold text-gray-700">Version History</h3>
            </div>

            <div className="flex-1 overflow-y-auto">
                {history.length === 0 ? (
                    <div className="p-4 text-center text-gray-400 text-xs">
                        No history available.
                    </div>
                ) : (
                    <ul className="divide-y divide-gray-100">
                        {history.map((version) => (
                            <li
                                key={version.id}
                                onClick={() => onSelect(version)}
                                className={`px-4 py-3 cursor-pointer hover:bg-blue-50 transition-colors ${currentVersionId === version.id ? 'bg-blue-50 border-l-4 border-blue-500' : 'border-l-4 border-transparent'
                                    }`}
                            >
                                <div className="flex justify-between items-start mb-1">
                                    <div className="flex flex-col">
                                        <span className={`text-xs font-bold ${version.is_active ? 'text-green-600' : 'text-gray-700'}`}>
                                            v{version.version} {version.is_active ? '(Active)' : ''}
                                        </span>
                                        {version.created_by_username && (
                                            <span className="text-[9px] text-gray-500">
                                                by {version.created_by_username}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] text-gray-400">
                                        {new Date(version.created_at).toLocaleDateString()}
                                    </span>
                                </div>
                                <p className="text-xs text-gray-500 line-clamp-2">
                                    {version.prompt_text.slice(0, 100)}...
                                </p>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
};

export default PromptHistory;
