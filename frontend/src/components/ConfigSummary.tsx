import React from 'react';

interface ConfigSummaryProps {
    connectionId: number | null;
    schema: Record<string, string[]>;
    dataDictionary: string;
    activePromptVersion: number | null;
    totalPromptVersions: number;
    lastUpdatedBy?: string | null;
}

const ConfigSummary: React.FC<ConfigSummaryProps> = ({
    connectionId,
    schema,
    dataDictionary,
    activePromptVersion,
    totalPromptVersions,
    lastUpdatedBy
}) => {
    const tableCount = Object.keys(schema).length;
    const columnCount = Object.values(schema).reduce((acc, cols) => acc + cols.length, 0);
    const dictionarySize = dataDictionary.length;

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full overflow-y-auto p-1">
            {/* Connection Status */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-green-100 rounded-full">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900">Database Connection</h3>
                </div>
                <div className="flex-1">
                    <p className="text-sm text-gray-500 mb-1">Status</p>
                    <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-green-500"></span>
                        <span className="font-medium text-gray-900">Connected</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-4 mb-1">Connection ID</p>
                    <p className="font-mono text-sm bg-gray-50 p-2 rounded">{connectionId}</p>
                </div>
            </div>

            {/* Schema Summary */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-blue-100 rounded-full">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900">Data Schema</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <p className="text-3xl font-bold text-gray-900">{tableCount}</p>
                        <p className="text-sm text-gray-500">Tables Selected</p>
                    </div>
                    <div>
                        <p className="text-3xl font-bold text-gray-900">{columnCount}</p>
                        <p className="text-sm text-gray-500">Columns Included</p>
                    </div>
                </div>
                <div className="mt-4">
                    <p className="text-sm text-gray-500 mb-2">Selected Tables:</p>
                    <div className="flex flex-wrap gap-2">
                        {Object.keys(schema).slice(0, 5).map(table => (
                            <span key={table} className="px-2 py-1 bg-gray-100 border border-gray-200 rounded text-xs text-gray-600">
                                {table}
                            </span>
                        ))}
                        {tableCount > 5 && <span className="text-xs text-gray-400 self-center">+{tableCount - 5} more</span>}
                    </div>
                </div>
            </div>

            {/* Configuration Context */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-purple-100 rounded-full">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900">Context & Dictionary</h3>
                </div>
                <div>
                    <p className="text-sm text-gray-500 mb-1">Content Status</p>
                    <p className={`font-medium ${dictionarySize > 0 ? 'text-green-600' : 'text-orange-500'}`}>
                        {dictionarySize > 0 ? 'Data Dictionary Added' : 'No Dictionary Content'}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">{dictionarySize} characters provided</p>
                </div>
            </div>

            {/* Prompt System Status */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm flex flex-col">
                <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-orange-100 rounded-full">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900">System Prompt</h3>
                </div>
                <div className="flex-1 flex flex-col justify-center">
                    <div className="flex justify-between items-center bg-gray-50 p-3 rounded mb-2">
                        <span className="text-sm text-gray-600">Active Version</span>
                        <div className="text-right">
                            <span className="font-bold text-green-600 block">v{activePromptVersion || '-'}</span>
                            {lastUpdatedBy && <span className="text-[10px] text-gray-500">by {lastUpdatedBy}</span>}
                        </div>
                    </div>
                    <div className="flex justify-between items-center bg-gray-50 p-3 rounded">
                        <span className="text-sm text-gray-600">Total Versions</span>
                        <span className="font-medium text-gray-900">{totalPromptVersions}</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfigSummary;
