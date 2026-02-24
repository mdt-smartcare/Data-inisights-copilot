import React, { useState, useEffect, useCallback } from 'react';
import {
    getEmbeddingModels, getLLMModels, getCompatibleLLMs,
    activateEmbeddingModel, activateLLMModel, handleApiError,
    registerEmbeddingModel, registerLLMModel
} from '../services/api';
import type { ModelInfo } from '../services/api';

interface AdvancedSettingsProps {
    settings: {
        embedding: {
            model: string;
        };
        llm: {
            temperature: number;
            maxTokens: number;
        };
        chunking: {
            parentChunkSize: number;
            parentChunkOverlap: number;
            childChunkSize: number;
            childChunkOverlap: number;
        };
        retriever: {
            topKInitial: number;
            topKFinal: number;
            hybridWeights: [number, number];
            rerankEnabled: boolean;
            rerankerModel: string;
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

    // Activation state
    const [activatingId, setActivatingId] = useState<number | null>(null);
    const [activationMsg, setActivationMsg] = useState<string | null>(null);

    // Active selections
    const [activeEmbedding, setActiveEmbedding] = useState<ModelInfo | null>(null);
    const [activeLLM, setActiveLLM] = useState<ModelInfo | null>(null);

    // Registration UI state
    const [showRegisterEmbedding, setShowRegisterEmbedding] = useState(false);
    const [showRegisterLLM, setShowRegisterLLM] = useState(false);

    const [newModelForm, setNewModelForm] = useState({
        provider: 'huggingface',
        model_name: '',
        display_name: '',
        dimensions: 768,
        max_tokens: 512,
        context_length: 4096,
        max_output_tokens: 1024
    });

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

            const activeEmb = embModels.find(m => m.is_active === 1) || null;
            const activeLl = llModels.find(m => m.is_active === 1) || null;
            setActiveEmbedding(activeEmb);
            setActiveLLM(activeLl);

            // Sync with parent settings if out of bounds
            if (activeEmb && activeEmb.model_name !== localSettings.embedding.model) {
                handleChange('embedding', 'model', activeEmb.model_name);
            }
        } catch (err: any) {
            console.error('Failed to load models:', err);
            setModelError('Could not load model registry. Using manual input.');
        } finally {
            setLoadingModels(false);
        }
    }, [localSettings.embedding.model]);

    useEffect(() => {
        loadModels();
    }, [loadModels]);

    const handleChange = (section: keyof AdvancedSettingsProps['settings'], field: string, value: any) => {
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

    // Handle embedding model activation via API
    const handleEmbeddingSelect = async (modelId: number) => {
        if (readOnly || activatingId) return;
        const model = embeddingModels.find(m => m.id === modelId);
        if (!model || model.is_active === 1) return;

        setActivatingId(modelId);
        setActivationMsg(null);
        try {
            await activateEmbeddingModel(modelId);
            setActivationMsg(`✓ Switched to ${model.display_name}`);
            await loadModels();
        } catch (err) {
            setActivationMsg(`✗ ${handleApiError(err)}`);
        } finally {
            setActivatingId(null);
            setTimeout(() => setActivationMsg(null), 4000);
        }
    };

    // Handle LLM model activation via API
    const handleLLMSelect = async (modelId: number) => {
        if (readOnly || activatingId) return;
        const model = llmModels.find(m => m.id === modelId);
        if (!model || model.is_active === 1) return;

        setActivatingId(modelId);
        setActivationMsg(null);
        try {
            await activateLLMModel(modelId);
            setActivationMsg(`✓ Switched to ${model.display_name}`);
            await loadModels();
        } catch (err) {
            setActivationMsg(`✗ ${handleApiError(err)}`);
        } finally {
            setActivatingId(null);
            setTimeout(() => setActivationMsg(null), 4000);
        }
    };

    // Handle Custom Model Registration
    const handleRegisterModel = async (type: 'embedding' | 'llm') => {
        setActivationMsg(null);
        try {
            if (type === 'embedding') {
                await registerEmbeddingModel({
                    provider: newModelForm.provider,
                    model_name: newModelForm.model_name,
                    display_name: newModelForm.display_name,
                    dimensions: newModelForm.dimensions,
                    max_tokens: newModelForm.max_tokens
                });
                setShowRegisterEmbedding(false);
            } else {
                await registerLLMModel({
                    provider: newModelForm.provider,
                    model_name: newModelForm.model_name,
                    display_name: newModelForm.display_name,
                    context_length: newModelForm.context_length,
                    max_output_tokens: newModelForm.max_output_tokens,
                    parameters: { temperature: 0.0 }
                });
                setShowRegisterLLM(false);
            }
            setActivationMsg(`✓ Successfully registered model ${newModelForm.display_name}`);
            // Reset form
            setNewModelForm({
                provider: 'huggingface',
                model_name: '',
                display_name: '',
                dimensions: 768,
                max_tokens: 512,
                context_length: 4096,
                max_output_tokens: 1024
            });
            await loadModels();
        } catch (err) {
            setActivationMsg(`✗ Registration failed: ${handleApiError(err)}`);
        }
    };

    return (
        <div className="h-full overflow-y-auto p-1">
            <h2 className="text-xl font-semibold mb-4 text-gray-900">Advanced Configuration</h2>
            <p className="text-sm text-gray-500 mb-6">
                Fine-tune the RAG pipeline parameters. These settings control how data is processed, indexed, and retrieved.
            </p>

            {/* Feedback toast */}
            {activationMsg && (
                <div className={`mb-4 px-4 py-3 rounded-lg text-sm font-medium flex items-center gap-2 transition-all duration-300 ${activationMsg.startsWith('✓')
                    ? 'bg-green-50 text-green-800 border border-green-200'
                    : 'bg-red-50 text-red-800 border border-red-200'
                    }`}>
                    {activationMsg}
                </div>
            )}

            <div className="space-y-6">
                {/* ============================================================ */}
                {/* 1. Embedding Configuration                             */}
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

                    {loadingModels ? (
                        <div className="flex items-center gap-2 text-sm text-gray-400 p-3">
                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            Loading models...
                        </div>
                    ) : modelError || embeddingModels.length === 0 ? (
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-1">Model Name</label>
                            <input type="text" value={localSettings.embedding.model} onChange={(e) => handleChange('embedding', 'model', e.target.value)} disabled={readOnly} className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border" />
                            {modelError && <p className="mt-1 text-xs text-amber-600">{modelError}</p>}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                            {embeddingModels.map(m => {
                                const isActive = m.is_active === 1;
                                const isLoading = activatingId === m.id;
                                return (
                                    <button
                                        key={m.id}
                                        type="button"
                                        onClick={() => handleEmbeddingSelect(m.id)}
                                        disabled={readOnly || isActive || !!activatingId}
                                        className={`text-left p-4 rounded-lg border-2 transition-all duration-200 ${isActive ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-200 shadow-sm'
                                            : readOnly || activatingId ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed'
                                                : 'border-gray-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/50 cursor-pointer hover:shadow-sm'
                                            }`}
                                    >
                                        <div className="flex items-start justify-between">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className={`text-sm font-semibold ${isActive ? 'text-indigo-900' : 'text-gray-800'}`}>{m.display_name}</span>
                                                    {isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">Active</span>}
                                                    {m.is_custom === 1 && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">Custom</span>}
                                                </div>
                                                <p className="text-xs text-gray-500 truncate">{m.provider} • {m.model_name}</p>
                                                <p className="text-xs text-gray-400 mt-1">{m.dimensions}d • Max {m.max_tokens}</p>
                                            </div>
                                            {!isLoading && !isActive && !readOnly && <span className="text-xs text-indigo-500 font-medium ml-2 flex-shrink-0 mt-0.5">Select →</span>}
                                        </div>
                                    </button>
                                );
                            })}

                            {/* Add Custom Embedded Model Button */}
                            {!readOnly && (
                                <button
                                    type="button"
                                    onClick={() => setShowRegisterEmbedding(!showRegisterEmbedding)}
                                    className="border-2 border-dashed border-gray-300 rounded-lg p-4 flex flex-col items-center justify-center text-gray-500 hover:bg-gray-50 hover:border-gray-400 hover:text-gray-700 transition-colors"
                                >
                                    <svg className="w-6 h-6 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                                    <span className="text-sm font-medium">Register Custom Model</span>
                                </button>
                            )}
                        </div>
                    )}

                    {/* Registration Form */}
                    {showRegisterEmbedding && !readOnly && (
                        <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                            <h4 className="text-sm font-medium text-gray-900 mb-3">Register New Embedding Model</h4>
                            <div className="grid grid-cols-2 gap-4 mb-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Provider</label>
                                    <select value={newModelForm.provider} onChange={e => setNewModelForm({ ...newModelForm, provider: e.target.value })} className="w-full text-sm border-gray-300 rounded-md p-1.5 border">
                                        <option value="huggingface">HuggingFace</option>
                                        <option value="openai">OpenAI</option>
                                        <option value="sentence-transformers">Sentence Transformers</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Display Name</label>
                                    <input type="text" placeholder="e.g. My Custom BGE" value={newModelForm.display_name} onChange={e => setNewModelForm({ ...newModelForm, display_name: e.target.value })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Model ID / Name</label>
                                    <input type="text" placeholder="e.g. BAAI/bge-large-en-v1.5" value={newModelForm.model_name} onChange={e => setNewModelForm({ ...newModelForm, model_name: e.target.value })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Dimensions</label>
                                    <input type="number" value={newModelForm.dimensions} onChange={e => setNewModelForm({ ...newModelForm, dimensions: parseInt(e.target.value) })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Max Tokens</label>
                                    <input type="number" value={newModelForm.max_tokens} onChange={e => setNewModelForm({ ...newModelForm, max_tokens: parseInt(e.target.value) })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                </div>
                            </div>
                            <div className="flex justify-end gap-2">
                                <button type="button" onClick={() => setShowRegisterEmbedding(false)} className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-900 font-medium">Cancel</button>
                                <button type="button" onClick={() => handleRegisterModel('embedding')} disabled={!newModelForm.model_name || !newModelForm.display_name} className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 font-medium disabled:opacity-50">Register Model</button>
                            </div>
                        </div>
                    )}
                </div>

                {/* ============================================================ */}
                {/* 2. LLM Configuration                                   */}
                {/* ============================================================ */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-purple-100 rounded-full">
                            <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">LLM Generation Parameters</h3>
                        {activeLLM && (
                            <span className="ml-auto inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                                Active: {activeLLM.display_name}
                            </span>
                        )}
                    </div>

                    {loadingModels ? (
                        <div className="text-sm text-gray-400 flex items-center gap-2 p-3">
                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            Loading LLM models...
                        </div>
                    ) : modelError || llmModels.length === 0 ? (
                        <p className="text-sm text-gray-500">LLM model registry unavailable. Configure via backend settings.</p>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* Block 1: Model Selection & Registration */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Select LLM Model</label>
                                <div className="space-y-2 mb-4">
                                    {llmModels.map(m => {
                                        const isActive = m.is_active === 1;
                                        const isCompatible = compatibleLLMs.some(c => c.id === m.id);
                                        const isLoading = activatingId === m.id;
                                        return (
                                            <button
                                                key={m.id}
                                                type="button"
                                                onClick={() => handleLLMSelect(m.id)}
                                                disabled={readOnly || isActive || !!activatingId}
                                                className={`w-full text-left p-3 rounded-lg border-2 transition-all duration-200 ${isActive ? 'border-purple-400 bg-purple-50 ring-1 ring-purple-200 shadow-sm'
                                                    : readOnly || activatingId ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed'
                                                        : 'border-gray-200 bg-white hover:border-purple-300 hover:bg-purple-50/50 cursor-pointer hover:shadow-sm'
                                                    }`}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className={`text-sm font-semibold ${isActive ? 'text-purple-900' : 'text-gray-800'}`}>{m.display_name}</span>
                                                            {isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">Active</span>}
                                                            {isCompatible && !isActive && <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                                                            {!isCompatible && !isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-red-50 text-red-600">Incompatible</span>}
                                                        </div>
                                                        <p className="text-xs text-gray-500 mt-0.5">{m.provider} • {m.model_name}</p>
                                                    </div>
                                                    {!isLoading && !isActive && !readOnly && <span className="text-xs text-purple-500 font-medium ml-2 flex-shrink-0">Select →</span>}
                                                </div>
                                            </button>
                                        );
                                    })}

                                    {!readOnly && (
                                        <button
                                            type="button"
                                            onClick={() => setShowRegisterLLM(!showRegisterLLM)}
                                            className="w-full border-2 border-dashed border-gray-300 rounded-lg p-3 flex items-center justify-center text-gray-500 hover:bg-gray-50 hover:border-gray-400 hover:text-gray-700 transition-colors"
                                        >
                                            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                                            <span className="text-sm font-medium">Register Custom LLM</span>
                                        </button>
                                    )}
                                </div>

                                {/* Registration Form */}
                                {showRegisterLLM && !readOnly && (
                                    <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                                        <h4 className="text-sm font-medium text-gray-900 mb-3">Register Custom LLM Model</h4>
                                        <div className="grid grid-cols-2 gap-4 mb-4">
                                            <div>
                                                <label className="block text-xs font-medium text-gray-700 mb-1">Provider</label>
                                                <select value={newModelForm.provider} onChange={e => setNewModelForm({ ...newModelForm, provider: e.target.value })} className="w-full text-sm border-gray-300 rounded-md p-1.5 border">
                                                    <option value="openai">OpenAI</option>
                                                    <option value="anthropic">Anthropic</option>
                                                    <option value="ollama">Ollama</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-xs font-medium text-gray-700 mb-1">Display Name</label>
                                                <input type="text" placeholder="e.g. My Llama 3" value={newModelForm.display_name} onChange={e => setNewModelForm({ ...newModelForm, display_name: e.target.value })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                            </div>
                                            <div className="col-span-2">
                                                <label className="block text-xs font-medium text-gray-700 mb-1">Model Name</label>
                                                <input type="text" placeholder="e.g. llama3.1:latest" value={newModelForm.model_name} onChange={e => setNewModelForm({ ...newModelForm, model_name: e.target.value })} className="w-full text-sm rounded-md p-1.5 border border-gray-300" />
                                            </div>
                                        </div>
                                        <div className="flex justify-end gap-2">
                                            <button type="button" onClick={() => setShowRegisterLLM(false)} className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-900 font-medium">Cancel</button>
                                            <button type="button" onClick={() => handleRegisterModel('llm')} disabled={!newModelForm.model_name || !newModelForm.display_name} className="px-3 py-1.5 text-xs bg-purple-600 text-white rounded hover:bg-purple-700 font-medium disabled:opacity-50">Register Model</button>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Block 2: Hyperparameters & Compatibility */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Hyperparameters (Active LLM)</label>
                                <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 space-y-4 mb-6">
                                    <div>
                                        <div className="flex justify-between items-center mb-1">
                                            <label className="block text-xs font-medium text-gray-700">Temperature</label>
                                            <span className="text-xs text-gray-500 font-mono">{localSettings.llm.temperature.toFixed(1)}</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="0"
                                            max="2"
                                            step="0.1"
                                            value={localSettings.llm.temperature}
                                            onChange={(e) => handleChange('llm', 'temperature', parseFloat(e.target.value))}
                                            disabled={readOnly}
                                            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-600"
                                        />
                                        <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                                            <span>Precise</span>
                                            <span>Creative</span>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-gray-700 mb-1">Max Output Tokens</label>
                                        <input
                                            type="number"
                                            min="1"
                                            value={localSettings.llm.maxTokens}
                                            onChange={(e) => handleChange('llm', 'maxTokens', parseInt(e.target.value))}
                                            disabled={readOnly}
                                            className="w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-xs p-1.5 border"
                                        />
                                    </div>
                                </div>

                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Compatible with {activeEmbedding?.display_name || 'Active Embedding'}
                                </label>
                                {compatibleLLMs.length === 0 ? (
                                    <div className="p-3 text-sm text-gray-500 border border-dashed border-gray-300 rounded-lg text-center">
                                        No compatibility data available
                                    </div>
                                ) : (
                                    <div className="space-y-1">
                                        {compatibleLLMs.map(m => (
                                            <div key={m.id} className="flex items-center gap-2 px-3 py-2 rounded-md bg-emerald-50 border border-emerald-200">
                                                <svg className="w-4 h-4 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                                <span className="text-sm text-emerald-800 font-medium">{m.display_name}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* ============================================================ */}
                {/* 3. Chunking Configuration                              */}
                {/* ============================================================ */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-blue-100 rounded-full">
                            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Chunking Strategy</h3>
                    </div>

                    <p className="text-xs text-gray-500 mb-5 leading-relaxed">
                        Data is split using a small-to-big retrieval strategy. Large <b>Parent Chunks</b> are returned to the LLM for full context, while small <b>Child Chunks</b> are used for precise semantic vector search.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Parent Splitter */}
                        <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                            <h4 className="text-sm font-semibold text-gray-800 mb-3 flex items-center">
                                Parent Document Splitter
                                <span className="ml-2 text-[10px] font-normal px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full">Sent to LLM</span>
                            </h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Chunk Size</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.parentChunkSize}
                                        onChange={(e) => handleChange('chunking', 'parentChunkSize', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Overlap</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.parentChunkOverlap}
                                        onChange={(e) => handleChange('chunking', 'parentChunkOverlap', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Child Splitter */}
                        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                            <h4 className="text-sm font-semibold text-blue-900 mb-3 flex items-center">
                                Child Chunk Splitter
                                <span className="ml-2 text-[10px] font-normal px-2 py-0.5 bg-blue-200 text-blue-800 rounded-full">Embedded</span>
                            </h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Chunk Size</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.childChunkSize}
                                        onChange={(e) => handleChange('chunking', 'childChunkSize', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-blue-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border bg-white"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Overlap</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.childChunkOverlap}
                                        onChange={(e) => handleChange('chunking', 'childChunkOverlap', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-blue-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border bg-white"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ============================================================ */}
                {/* 4. Retrieval Configuration                             */}
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

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Block 1: Multi-stage retrieval stats */}
                        <div className="space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Initial)</label>
                                    <input
                                        type="number"
                                        value={localSettings.retriever.topKInitial}
                                        onChange={(e) => handleChange('retriever', 'topKInitial', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 sm:text-sm p-2 border"
                                    />
                                    <p className="mt-1 text-xs text-gray-500 leading-tight">Candidates fetched from vector base before reranking</p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Final)</label>
                                    <input
                                        type="number"
                                        value={localSettings.retriever.topKFinal}
                                        onChange={(e) => handleChange('retriever', 'topKFinal', parseInt(e.target.value))}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 sm:text-sm p-2 border"
                                    />
                                    <p className="mt-1 text-xs text-gray-500 leading-tight">Final results sent to LLM context window</p>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-3">Hybrid Search Weights</label>
                                <div className="flex items-center gap-4 px-2">
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
                                        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                                    />
                                </div>
                                <div className="flex justify-between text-xs text-gray-600 mt-2 px-2 font-medium">
                                    <span>Dense (Vector): {Math.round(localSettings.retriever.hybridWeights[0] * 100)}%</span>
                                    <span>Sparse (BM25): {Math.round(localSettings.retriever.hybridWeights[1] * 100)}%</span>
                                </div>
                            </div>
                        </div>

                        {/* Block 2: Cross-Encoder Reranker */}
                        <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                            <div className="flex items-center justify-between mb-4">
                                <h4 className="text-sm font-semibold text-gray-800">Cross-Encoder Reranking</h4>
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="sr-only peer"
                                        checked={localSettings.retriever.rerankEnabled}
                                        onChange={(e) => handleChange('retriever', 'rerankEnabled', e.target.checked)}
                                        disabled={readOnly}
                                    />
                                    <div className="w-9 h-5 bg-gray-300 hover:bg-gray-400 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                                </label>
                            </div>

                            <p className="text-xs text-gray-500 mb-4 leading-relaxed">
                                Reranking dramatically improves accuracy by using a lightweight cross-encoder to re-score the initial retrieval candidates before passing them to the generative LLM.
                            </p>

                            <div className={`transition-opacity duration-200 ${localSettings.retriever.rerankEnabled ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
                                <label className="block text-xs font-medium text-gray-700 mb-1">Reranker Model</label>
                                <input
                                    type="text"
                                    value={localSettings.retriever.rerankerModel}
                                    onChange={(e) => handleChange('retriever', 'rerankerModel', e.target.value)}
                                    disabled={readOnly || !localSettings.retriever.rerankEnabled}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 sm:text-sm p-2 border"
                                />
                                <p className="mt-1 text-[10px] text-gray-400">HuggingFace Model ID (e.g. BAAI/bge-reranker-base)</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AdvancedSettings;
