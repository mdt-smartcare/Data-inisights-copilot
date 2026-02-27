import React from 'react';

interface ConfigSummaryProps {
    connectionId: number | null;
    connectionName?: string;
    dataSourceType: 'database' | 'file';
    fileInfo?: { name: string; type: string };
    schema: Record<string, string[]>;
    dataDictionary: string;
    activePromptVersion: number | null;
    totalPromptVersions: number;
    lastUpdatedBy?: string | null;
    settings: {
        embedding: {
            model: string;
            vectorDbName?: string;
        };
        llm: {
            model?: string;
            temperature: number;
            maxTokens: number;
        };
    };
}

const ConfigSummary: React.FC<ConfigSummaryProps> = ({
    connectionId,
    connectionName,
    dataSourceType,
    fileInfo,
    schema,
    dataDictionary,
    activePromptVersion,
    totalPromptVersions,
    lastUpdatedBy,
    settings
}) => {
    const tableCount = Object.keys(schema).length;
    const columnCount = Object.values(schema).reduce((acc, cols) => acc + cols.length, 0);
    const dictionarySize = dataDictionary.length;

    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* 1. Source Identity */}
            <div className="bg-white p-3 sm:p-4 rounded-xl border border-gray-200 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                    <div className="p-2 bg-blue-50 rounded-lg flex-shrink-0">
                        {dataSourceType === 'database' ? (
                            <svg className="w-4 h-4 sm:w-5 sm:h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" /></svg>
                        ) : (
                            <svg className="w-4 h-4 sm:w-5 sm:h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                        )}
                    </div>
                    <div className="min-w-0">
                        <h3 className="text-xs font-bold text-gray-900 uppercase tracking-tight">Data Source</h3>
                        <p className="text-[10px] text-gray-400">Identity & Location</p>
                    </div>
                </div>

                <div className="space-y-2">
                    <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                        <p className="text-[9px] font-bold text-gray-400 uppercase mb-0.5">Type</p>
                        <p className="text-xs font-semibold text-gray-700">{dataSourceType === 'database' ? 'SQL Database' : 'Uploaded File'}</p>
                    </div>
                    <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                        <p className="text-[9px] font-bold text-gray-400 uppercase mb-0.5">{dataSourceType === 'database' ? 'Connection' : 'File Name'}</p>
                        <p className="text-xs font-mono font-bold text-gray-700 truncate">
                            {dataSourceType === 'database' ? (connectionName || (connectionId ? `ID: ${connectionId}` : 'Default')) : (fileInfo?.name || 'Unknown')}
                        </p>
                    </div>
                </div>
            </div>

            {/* 2. Knowledge Structure */}
            <div className="bg-white p-3 sm:p-4 rounded-xl border border-gray-200 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                    <div className="p-2 bg-emerald-50 rounded-lg flex-shrink-0">
                        <svg className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                    </div>
                    <div className="min-w-0">
                        <h3 className="text-xs font-bold text-gray-900 uppercase tracking-tight">Intelligence Map</h3>
                        <p className="text-[10px] text-gray-400">Schema & Semantics</p>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-2">
                    <div className="p-2 bg-emerald-50/50 rounded-lg border border-emerald-100">
                        <p className="text-[9px] font-bold text-emerald-600 uppercase mb-0.5">Entities</p>
                        <p className="text-lg sm:text-xl font-black text-gray-900">{tableCount}</p>
                    </div>
                    <div className="p-2 bg-indigo-50/50 rounded-lg border border-indigo-100">
                        <p className="text-[9px] font-bold text-indigo-600 uppercase mb-0.5">Attributes</p>
                        <p className="text-lg sm:text-xl font-black text-gray-900">{columnCount}</p>
                    </div>
                </div>

                <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                    <p className="text-[9px] font-bold text-gray-400 uppercase mb-0.5">Dictionary</p>
                    <div className="flex items-center justify-between">
                        <p className={`text-xs font-bold ${dictionarySize > 0 ? 'text-gray-700' : 'text-amber-500 italic'}`}>
                            {dictionarySize > 0 ? `${dictionarySize} chars` : 'None'}
                        </p>
                        {dictionarySize > 0 && <span className="h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0"></span>}
                    </div>
                </div>
            </div>

            {/* 3. Logic Engine */}
            <div className="bg-white p-3 sm:p-4 rounded-xl border border-gray-200 shadow-sm sm:col-span-2 lg:col-span-1">
                <div className="flex items-center gap-2 mb-3">
                    <div className="p-2 bg-purple-50 rounded-lg flex-shrink-0">
                        <svg className="w-4 h-4 sm:w-5 sm:h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                    </div>
                    <div className="min-w-0">
                        <h3 className="text-xs font-bold text-gray-900 uppercase tracking-tight">Logic Engine</h3>
                        <p className="text-[10px] text-gray-400">LLM & Versions</p>
                    </div>
                </div>

                <div className="space-y-2">
                    <div className="p-2 bg-indigo-50/50 rounded-lg border border-indigo-100">
                        <p className="text-[9px] font-bold text-indigo-600 uppercase mb-0.5">Active Prompt</p>
                        <div className="flex items-center justify-between">
                            <span className="text-sm sm:text-base font-black text-gray-900">v{activePromptVersion || 'Draft'}</span>
                            <span className="text-[8px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full font-bold">LATEST</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                        <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                            <p className="text-[9px] font-bold text-gray-400 uppercase mb-0.5">Temp</p>
                            <p className="text-xs font-bold text-gray-700">{settings.llm.temperature.toFixed(1)}</p>
                        </div>
                        <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                            <p className="text-[9px] font-bold text-gray-400 uppercase mb-0.5">Tokens</p>
                            <p className="text-xs font-bold text-gray-700">{settings.llm.maxTokens}</p>
                        </div>
                    </div>

                    <div className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                        <div className="flex justify-between items-center text-[9px] font-bold text-gray-400 uppercase">
                            <span>Versions</span>
                            <span className="text-gray-700 text-xs">{totalPromptVersions}</span>
                        </div>
                    </div>

                    {lastUpdatedBy && (
                        <p className="text-[9px] text-center text-gray-400 italic truncate">
                            by <span className="text-indigo-500 font-bold">@{lastUpdatedBy}</span>
                        </p>
                    )}
                </div>
            </div>

            {/* 4. Vector Engine (Full Width) */}
            <div className="col-span-1 sm:col-span-2 lg:col-span-3 bg-gradient-to-br from-indigo-900 via-blue-900 to-indigo-800 p-3 sm:p-4 rounded-xl shadow-lg overflow-hidden relative">
                {/* Abstract Background Element */}
                <div className="absolute top-0 right-0 w-24 sm:w-48 h-24 sm:h-48 bg-white/5 rounded-full -mr-8 sm:-mr-16 -mt-8 sm:-mt-16 blur-2xl"></div>

                <div className="relative flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                        <div className="p-2 sm:p-3 bg-white/10 rounded-xl backdrop-blur-md border border-white/20 flex-shrink-0">
                            <svg className="w-5 h-5 sm:w-6 sm:h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                        </div>
                        <div className="min-w-0 flex-1">
                            <h3 className="text-xs sm:text-sm font-black text-white uppercase tracking-wider">Vector Engine</h3>
                            <p className="text-blue-200 text-[10px] sm:text-xs truncate">
                                Index: <span className="font-mono text-white bg-white/10 px-1.5 py-0.5 rounded text-[9px] sm:text-[10px]">{settings.embedding.vectorDbName || 'default'}</span>
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 sm:flex sm:gap-3">
                        <div className="px-2 py-1.5 sm:px-3 sm:py-2 bg-white/10 rounded-lg border border-white/10">
                            <p className="text-[8px] sm:text-[9px] font-bold text-blue-300 uppercase">Model</p>
                            <p className="text-[10px] sm:text-xs font-bold text-white truncate max-w-[100px] sm:max-w-[120px]">{settings.embedding.model}</p>
                        </div>
                        <div className="px-2 py-1.5 sm:px-3 sm:py-2 bg-white/10 rounded-lg border border-white/10">
                            <p className="text-[8px] sm:text-[9px] font-bold text-blue-300 uppercase">Provider</p>
                            <p className="text-[10px] sm:text-xs font-bold text-white uppercase truncate">{settings.embedding.model.includes('/') ? settings.embedding.model.split('/')[0] : 'Local'}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfigSummary;
