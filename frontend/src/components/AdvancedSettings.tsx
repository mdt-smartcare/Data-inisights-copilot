import React, { useState, useEffect, useCallback } from 'react';
import { getEmbeddingModels, getLLMModels, getCompatibleLLMs } from '../services/api';
import type { ModelInfo } from '../services/api';

interface AdvancedSettingsProps {
    settings: {
        embedding: {
            model: string;
            chunkSize: number;
            chunkOverlap: number;
        };
        retriever: {
            topKInitial: number;
            topKFinal: number;
            hybridWeights: [number, number];
        };
    };
    onChange: (settings: any) => void;
    readOnly?: boolean;
}

const AdvancedSettings: React.FC<AdvancedSettingsProps> = ({ settings, onChange, readOnly = false }) => {
    const [localSettings, setLocalSettings] = useState(settings);

    // Model registry state
    const [embeddingModels, setEmbeddingModels] = useState<ModelInfo[]>([]);
    const [llmModels, setLLMModels] = useState<ModelInfo[]>([]);
    const [compatibleLLMs, setCompatibleLLMs] = useState<ModelInfo[]>([]);
    const [loadingModels, setLoadingModels] = useState(true);
    const [modelError, setModelError] = useState<string | null>(null);

    // Active selections (from DB)
    const [activeEmbedding, setActiveEmbedding] = useState<ModelInfo | null>(null);
    const [activeLLM, setActiveLLM] = useState<ModelInfo | null>(null);

    useEffect(() => {
        setLocalSettings(settings);
    }, [settings]);

    // Load models from backend
    const loadModels = useCallback(async () => {
        setLoadingModels(true);
        setModelError(null);
        try {
            const [embModels, llModels, compat] = await Promise.all([
                getEmbeddingModels(),
                getLLMModels(),
                getCompatibleLLMs()
            ]);
            setEmbeddingModels(embModels);
            setLLMModels(llModels);
            setCompatibleLLMs(compat);

            // Find active models
            const activeEmb = embModels.find(m => m.is_active === 1) || null;
            const activeLl = llModels.find(m => m.is_active === 1) || null;
            setActiveEmbedding(activeEmb);
            setActiveLLM(activeLl);

            // Sync active embedding model to parent settings
            if (activeEmb && activeEmb.model_name !== localSettings.embedding.model) {
                handleChange('embedding', 'model', activeEmb.model_name);
            }
        } catch (err: any) {
            console.error('Failed to load models:', err);
            setModelError('Could not load model registry. Using manual input.');
        } finally {
            setLoadingModels(false);
        }
    }, []);

    useEffect(() => {
        loadModels();
    }, [loadModels]);

    const handleChange = (section: 'embedding' | 'retriever', field: string, value: any) => {
        if (readOnly) return;
        const newSettings = {
            ...localSettings,
            [section]: {
                ...localSettings[section],
                [field]: value
            }
        };
        setLocalSettings(newSettings);
        onChange(newSettings);
    };

    return (
        <div className="h-full overflow-y-auto p-1">
            <h2 className="text-xl font-semibold mb-4 text-gray-900">Advanced Configuration</h2>
            <p className="text-sm text-gray-500 mb-6">
                Fine-tune the RAG pipeline parameters. These settings control how data is processed, indexed, and retrieved.
            </p>

            <div className="space-y-6">
                {/* ============================================================ */}
                {/* Embedding Configuration */}
                {/* ============================================================ */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-indigo-100 rounded-full">
                            <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Embedding Strategy</h3>
                        {activeEmbedding && (
                            <span className="ml-auto inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                Active: {activeEmbedding.display_name}
                            </span>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Model Selector */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Embedding Model</label>
                            {loadingModels ? (
                                <div className="w-full rounded-md border-gray-300 shadow-sm p-2 border bg-gray-50 text-gray-400 text-sm flex items-center gap-2">
                                    <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Loading models...
                                </div>
                            ) : modelError || embeddingModels.length === 0 ? (
                                <>
                                    <input
                                        type="text"
                                        value={localSettings.embedding.model}
                                        onChange={(e) => handleChange('embedding', 'model', e.target.value)}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                    />
                                    <p className="mt-1 text-xs text-gray-500">HuggingFace model ID (e.g., BAAI/bge-m3)</p>
                                    {modelError && <p className="mt-1 text-xs text-amber-600">{modelError}</p>}
                                </>
                            ) : (
                                <>
                                    <select
                                        value={localSettings.embedding.model}
                                        onChange={(e) => handleChange('embedding', 'model', e.target.value)}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border bg-white"
                                    >
                                        {embeddingModels.map(m => (
                                            <option key={m.id} value={m.model_name}>
                                                {m.display_name} ({m.model_name}) {m.is_active ? '✓' : ''}
                                            </option>
                                        ))}
                                    </select>
                                    {activeEmbedding && (
                                        <p className="mt-1 text-xs text-gray-500">
                                            {activeEmbedding.dimensions}d vectors • Max {activeEmbedding.max_tokens} tokens
                                            {activeEmbedding.is_custom ? ' • Custom' : ' • Built-in'}
                                        </p>
                                    )}
                                </>
                            )}
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Chunk Size</label>
                                <input
                                    type="number"
                                    value={localSettings.embedding.chunkSize}
                                    onChange={(e) => handleChange('embedding', 'chunkSize', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Overlap</label>
                                <input
                                    type="number"
                                    value={localSettings.embedding.chunkOverlap}
                                    onChange={(e) => handleChange('embedding', 'chunkOverlap', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                {/* ============================================================ */}
                {/* LLM Configuration - NEW */}
                {/* ============================================================ */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-purple-100 rounded-full">
                            <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">LLM Configuration</h3>
                        {activeLLM && (
                            <span className="ml-auto inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                                Active: {activeLLM.display_name}
                            </span>
                        )}
                    </div>

                    {loadingModels ? (
                        <div className="text-sm text-gray-400 flex items-center gap-2 p-3">
                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Loading LLM models...
                        </div>
                    ) : modelError || llmModels.length === 0 ? (
                        <p className="text-sm text-gray-500">LLM model registry unavailable. Configure via backend settings.</p>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* All LLM Models */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Active LLM Model</label>
                                <div className="space-y-2">
                                    {llmModels.map(m => (
                                        <div
                                            key={m.id}
                                            className={`flex items-center p-3 rounded-lg border cursor-default transition-colors ${m.is_active
                                                    ? 'border-purple-300 bg-purple-50 ring-1 ring-purple-200'
                                                    : 'border-gray-200 bg-gray-50'
                                                }`}
                                        >
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2">
                                                    <span className={`text-sm font-medium ${m.is_active ? 'text-purple-900' : 'text-gray-700'}`}>
                                                        {m.display_name}
                                                    </span>
                                                    {m.is_active === 1 && (
                                                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">Active</span>
                                                    )}
                                                    {m.is_custom === 1 && (
                                                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">Custom</span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-500 mt-0.5">
                                                    {m.provider} • {m.model_name}
                                                    {m.context_length ? ` • ${(m.context_length / 1000).toFixed(0)}K ctx` : ''}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Compatible LLMs */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Compatible with Active Embedding</label>
                                {compatibleLLMs.length === 0 ? (
                                    <div className="p-3 text-sm text-gray-500 border border-dashed border-gray-300 rounded-lg text-center">
                                        No compatibility data available
                                    </div>
                                ) : (
                                    <div className="space-y-1">
                                        {compatibleLLMs.map(m => (
                                            <div key={m.id} className="flex items-center gap-2 px-3 py-2 rounded-md bg-emerald-50 border border-emerald-200">
                                                <svg className="w-4 h-4 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                </svg>
                                                <span className="text-sm text-emerald-800 font-medium">{m.display_name}</span>
                                                <span className="text-xs text-emerald-600 ml-auto">{m.provider}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {activeEmbedding && (
                                    <p className="mt-2 text-xs text-gray-400">
                                        Showing LLMs compatible with {activeEmbedding.display_name}
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* ============================================================ */}
                {/* Retrieval Configuration */}
                {/* ============================================================ */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-emerald-100 rounded-full">
                            <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Retrieval Parameters</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Initial)</label>
                                <input
                                    type="number"
                                    value={localSettings.retriever.topKInitial}
                                    onChange={(e) => handleChange('retriever', 'topKInitial', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                                <p className="mt-1 text-xs text-gray-500">Candidates before reranking</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Final)</label>
                                <input
                                    type="number"
                                    value={localSettings.retriever.topKFinal}
                                    onChange={(e) => handleChange('retriever', 'topKFinal', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                                <p className="mt-1 text-xs text-gray-500">Results sent to LLM</p>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Hybrid Search Weights (Dense / Sparse)</label>
                            <div className="flex items-center gap-4">
                                <div className="flex-1">
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.05"
                                        value={localSettings.retriever.hybridWeights[0]}
                                        onChange={(e) => {
                                            const val = parseFloat(e.target.value);
                                            handleChange('retriever', 'hybridWeights', [val, parseFloat((1 - val).toFixed(2))]);
                                        }}
                                        disabled={readOnly}
                                        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                                    />
                                </div>
                            </div>
                            <div className="flex justify-between text-xs text-gray-500 mt-2">
                                <span>Vector: {localSettings.retriever.hybridWeights[0]}</span>
                                <span>Keyword: {localSettings.retriever.hybridWeights[1]}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AdvancedSettings;
