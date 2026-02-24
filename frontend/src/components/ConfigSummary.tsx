import React from 'react';

interface ConfigSummaryProps {
    connectionId: number | null;
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* 1. Source Identity */}
            <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md h-full flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                    <div className="p-2.5 bg-blue-50 rounded-xl">
                        {dataSourceType === 'database' ? (
                            <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" /></svg>
                        ) : (
                            <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                        )}
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-tight">Data Source</h3>
                        <p className="text-xs text-gray-400">Identity & Location</p>
                    </div>
                </div>

                <div className="space-y-4 flex-1">
                    <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                        <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Type</p>
                        <p className="text-sm font-semibold text-gray-700">{dataSourceType === 'database' ? 'SQL Database' : 'Uploaded File'}</p>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                        <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">{dataSourceType === 'database' ? 'Connection' : 'File Name'}</p>
                        <p className="text-sm font-mono font-bold text-gray-700 truncate">
                            {dataSourceType === 'database' ? (connectionId ? `ID: ${connectionId}` : 'Default') : (fileInfo?.name || 'Unknown')}
                        </p>
                    </div>
                </div>
            </div>

            {/* 2. Knowledge Structure */}
            <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md h-full flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                    <div className="p-2.5 bg-emerald-50 rounded-xl">
                        <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-tight">Intelligence Map</h3>
                        <p className="text-xs text-gray-400">Schema & Semantics</p>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="p-3 bg-emerald-50/30 rounded-xl border border-emerald-100">
                        <p className="text-[10px] font-bold text-emerald-600 uppercase mb-1">Entities</p>
                        <p className="text-2xl font-black text-gray-900">{tableCount}</p>
                    </div>
                    <div className="p-3 bg-indigo-50/30 rounded-xl border border-indigo-100">
                        <p className="text-[10px] font-bold text-indigo-600 uppercase mb-1">Attributes</p>
                        <p className="text-2xl font-black text-gray-900">{columnCount}</p>
                    </div>
                </div>

                <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                    <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Dictionary Content</p>
                    <div className="flex items-center justify-between">
                        <p className={`text-sm font-bold ${dictionarySize > 0 ? 'text-gray-700' : 'text-amber-500 italic'}`}>
                            {dictionarySize > 0 ? `${dictionarySize} Characters` : 'No context provided'}
                        </p>
                        {dictionarySize > 0 && <span className="h-2 w-2 rounded-full bg-green-500"></span>}
                    </div>
                </div>
            </div>

            {/* 3. Logic Engine */}
            <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md h-full flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                    <div className="p-2.5 bg-purple-50 rounded-xl">
                        <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-tight">Logic Engine</h3>
                        <p className="text-xs text-gray-400">LLM & Versions</p>
                    </div>
                </div>

                <div className="space-y-3">
                    <div className="p-3 bg-indigo-50/30 rounded-xl border border-indigo-100">
                        <p className="text-[10px] font-bold text-indigo-600 uppercase mb-1">Active Prompt</p>
                        <div className="flex items-center justify-between">
                            <span className="text-lg font-black text-gray-900">v{activePromptVersion || 'Draft'}</span>
                            <span className="text-[10px] bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-bold">LATEST</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                            <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Temperature</p>
                            <p className="text-sm font-bold text-gray-700">{settings.llm.temperature.toFixed(1)}</p>
                        </div>
                        <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                            <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Max Tokens</p>
                            <p className="text-sm font-bold text-gray-700">{settings.llm.maxTokens}</p>
                        </div>
                    </div>

                    <div className="p-3 bg-gray-50 rounded-xl border border-gray-100 mt-3">
                        <div className="flex justify-between items-center text-[10px] font-bold text-gray-400 uppercase">
                            <span>Total Variations</span>
                            <span className="text-gray-700">{totalPromptVersions}</span>
                        </div>
                    </div>

                    {lastUpdatedBy && (
                        <p className="text-[10px] text-center text-gray-400 italic mt-3">
                            Published by <span className="text-indigo-500 font-bold">@{lastUpdatedBy}</span>
                        </p>
                    )}
                </div>
            </div>

            {/* 4. Embedding Specs (Across) */}
            <div className="md:col-span-2 lg:col-span-3 bg-gradient-to-br from-indigo-900 via-blue-900 to-indigo-800 p-6 rounded-2xl shadow-xl overflow-hidden relative">
                {/* Abstract Background Element */}
                <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -mr-20 -mt-20 blur-3xl"></div>

                <div className="relative flex flex-col md:flex-row items-center gap-6">
                    <div className="p-4 bg-white/10 rounded-2xl backdrop-blur-md border border-white/20">
                        <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </div>

                    <div className="flex-1 text-center md:text-left">
                        <h3 className="text-lg font-black text-white mb-1 uppercase tracking-widest">Vector Engine Readiness</h3>
                        <p className="text-blue-100 text-sm">Target Index: <span className="font-mono text-white bg-white/10 px-2 py-0.5 rounded">{settings.embedding.vectorDbName || 'default'}</span></p>
                    </div>

                    <div className="flex gap-4">
                        <div className="px-4 py-3 bg-white/5 rounded-xl border border-white/10 text-center min-w-[120px]">
                            <p className="text-[9px] font-bold text-blue-300 uppercase mb-1">Model Architecture</p>
                            <p className="text-xs font-bold text-white truncate max-w-[150px]">{settings.embedding.model}</p>
                        </div>
                        <div className="px-4 py-3 bg-white/5 rounded-xl border border-white/10 text-center min-w-[100px]">
                            <p className="text-[9px] font-bold text-blue-300 uppercase mb-1">Provider</p>
                            <p className="text-xs font-bold text-white uppercase">{settings.embedding.model.includes('/') ? settings.embedding.model.split('/')[0] : 'Local'}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfigSummary;
