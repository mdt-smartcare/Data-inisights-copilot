import React from 'react';
import { CommandLineIcon } from '@heroicons/react/24/outline';
import type { ActiveConfig } from '../../../contexts/AgentContext';

interface SettingsTabProps {
    activeConfig: ActiveConfig;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
    activeConfig
}) => {
    const parseConfig = (config: string | undefined | null) => {
        if (!config) return {};
        try {
            return typeof config === 'string' ? JSON.parse(config) : config;
        } catch {
            return {};
        }
    };

    const llmConf = parseConfig(activeConfig.llm_config);
    const embConf = parseConfig(activeConfig.embedding_config);
    const chunkConf = parseConfig(activeConfig.chunking_config);
    const retConf = parseConfig(activeConfig.retriever_config);

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* LLM Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-indigo-50 rounded-xl flex items-center justify-center">
                            <CommandLineIcon className="w-6 h-6 text-indigo-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Logic Engine (LLM)</h3>
                            <p className="text-sm text-gray-500">Core reasoning configuration</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Model Name</p>
                                <p className="text-sm font-mono font-bold text-gray-700">{llmConf.model || 'gpt-4o'}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Temperature</p>
                                <p className="text-sm font-semibold text-gray-700">{llmConf.temperature ?? 0.0}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Max Tokens</p>
                                <p className="text-sm font-semibold text-gray-700">{llmConf.maxTokens || 4096}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Embedding Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-emerald-50 rounded-xl flex items-center justify-center">
                            <svg className="w-6 h-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Knowledge Engine</h3>
                            <p className="text-sm text-gray-500">Vectorization & Chunking</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Embedding Model</p>
                                <p className="text-sm font-mono font-bold text-gray-700">{embConf.model || 'BAAI/bge-m3'}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Parent Size</p>
                                <p className="text-sm font-semibold text-gray-700">{chunkConf.parentChunkSize || 800} chars</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Child Size</p>
                                <p className="text-sm font-semibold text-gray-700">{chunkConf.childChunkSize || 200} chars</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Retriever Specs */}
                <div className="bg-white p-8 rounded-2xl border border-gray-200 shadow-sm transition-all hover:shadow-md col-span-1 md:col-span-2">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="w-12 h-12 bg-purple-50 rounded-xl flex items-center justify-center">
                            <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Retrieval Strategy</h3>
                            <p className="text-sm text-gray-500">Search weights and reranking</p>
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            {retConf.hybridWeights && (
                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Semantic Weight</p>
                                    <p className="text-sm font-bold text-purple-700">{(retConf.hybridWeights[0] * 100).toFixed(0)}%</p>
                                </div>
                            )}
                            {retConf.hybridWeights && (
                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Keyword Weight</p>
                                    <p className="text-sm font-bold text-purple-700">{(retConf.hybridWeights[1] * 100).toFixed(0)}%</p>
                                </div>
                            )}
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Top-K Final</p>
                                <p className="text-sm font-bold text-gray-700">{retConf.topKFinal || 10}</p>
                            </div>
                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Reranking</p>
                                <p className={`text-sm font-bold ${retConf.rerankEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                                    {retConf.rerankEnabled ? 'Enabled' : 'Disabled'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SettingsTab;
