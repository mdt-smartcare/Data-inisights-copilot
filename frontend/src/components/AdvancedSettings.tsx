import React, { useState, useEffect, useCallback } from 'react';
import {
    listAIModels, setAIModelDefault, handleApiError
} from '../services/api';
import type { AIModel, ModelType } from '../services/api';
import AIModelSelector from './AIModelSelector';
import { useAIRegistryModels } from '../hooks/useAIRegistryModels';

export type AccordionSection = 'embedding' | 'llm' | 'chunking' | 'retrieval';

interface AdvancedSettingsProps {
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
        // AI Registry model IDs at top level
        embeddingModelId?: number;
        llmModelId?: number;
        rerankerModelId?: number;
    };
    onChange: (settings: AdvancedSettingsProps['settings']) => void;
    readOnly?: boolean;
    dataSourceName?: string;
    /** If true, only one accordion section can be open at a time. Default: false (multiple can be open) */
    singleAccordionMode?: boolean;
    /** Sections to open by default. Default: ['embedding'] */
    defaultOpenSections?: AccordionSection[];
}

const AdvancedSettings: React.FC<AdvancedSettingsProps> = ({ 
    settings, 
    onChange, 
    readOnly = false, 
    dataSourceName = '',
    singleAccordionMode = true,
    defaultOpenSections = []
}) => {
    const [localSettings, setLocalSettings] = useState(settings);

    // Accordion state - tracks which sections are open
    const [openSections, setOpenSections] = useState<Set<AccordionSection>>(
        new Set(defaultOpenSections)
    );

    // Toggle accordion section
    const toggleSection = useCallback((section: AccordionSection) => {
        setOpenSections(prev => {
            const isCurrentlyOpen = prev.has(section);
            
            if (singleAccordionMode) {
                // In single mode: if clicking the open section, close it; otherwise open clicked and close others
                if (isCurrentlyOpen) {
                    return new Set<AccordionSection>();
                }
                return new Set<AccordionSection>([section]);
            } else {
                // In multi mode: toggle the clicked section
                const newSet = new Set(prev);
                if (isCurrentlyOpen) {
                    newSet.delete(section);
                } else {
                    newSet.add(section);
                }
                return newSet;
            }
        });
    }, [singleAccordionMode]);

    const isSectionOpen = (section: AccordionSection) => openSections.has(section);

    // Vector DB Name Validation State
    const [vectorDbValidation, setVectorDbValidation] = useState<{ valid: boolean; message: string; checking: boolean }>({
        valid: true,
        message: '',
        checking: false
    });

    // Model registry state (from AI Registry)
    const [embeddingModels, setEmbeddingModels] = useState<AIModel[]>([]);
    const [llmModels, setLLMModels] = useState<AIModel[]>([]);
    const [compatibleLLMs, setCompatibleLLMs] = useState<AIModel[]>([]);
    const [loadingModels, setLoadingModels] = useState(true);
    const [modelError, setModelError] = useState<string | null>(null);

    // AI Registry models (new system)
    const aiRegistry = useAIRegistryModels();

    // Activation state
    const [activatingId, setActivatingId] = useState<number | null>(null);
    const [activationMsg, setActivationMsg] = useState<string | null>(null);

    // Active selections
    const [activeEmbedding, setActiveEmbedding] = useState<AIModel | null>(null);
    const [activeLLM, setActiveLLM] = useState<AIModel | null>(null);

    // Track if we've already set the default reranker
    const hasSetDefaultReranker = React.useRef(false);
    // Track if we've synced embedding/LLM defaults
    const hasSetDefaultEmbedding = React.useRef(false);
    const hasSetDefaultLLM = React.useRef(false);

    useEffect(() => {
        setLocalSettings(settings);
    }, [settings]);

    // Pre-select default reranker model from AI Registry
    // Only if the current value doesn't match any available model
    useEffect(() => {
        if (readOnly) return;
        if (hasSetDefaultReranker.current) return;
        if (aiRegistry.isLoading || aiRegistry.rerankerModels.length === 0) return;
        if (!aiRegistry.defaults?.reranker) return;
        
        const currentRerankerModelId = localSettings.rerankerModelId;
        const isValidSelection = currentRerankerModelId && aiRegistry.rerankerModels.some(m => m.id === currentRerankerModelId);
        
        // If current selection is not valid, use the default
        if (!isValidSelection) {
            hasSetDefaultReranker.current = true;
            const defaultReranker = aiRegistry.defaults.reranker;
            const newSettings = {
                ...localSettings,
                retriever: {
                    ...localSettings.retriever,
                    rerankerModel: defaultReranker.model_id,
                },
                rerankerModelId: defaultReranker.id,  // Store at top level
            };
            setLocalSettings(newSettings);
            onChange(newSettings);
        }
    }, [aiRegistry.isLoading, aiRegistry.rerankerModels, aiRegistry.defaults?.reranker, readOnly, localSettings, onChange]);

    // Handle Vector DB Default formatting
    useEffect(() => {
        if (!localSettings.embedding.vectorDbName && dataSourceName) {
            // format: alphanumeric + underscores, no spaces, strip extras
            const formatted = dataSourceName.replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase().replace(/_+/g, '_').replace(/^_+|_+$/g, '');
            const defaultName = formatted ? `${formatted}_data` : 'default_vector_db';
            handleChange('embedding', 'vectorDbName', defaultName);
        }
    }, [dataSourceName, localSettings.embedding.vectorDbName]);

    // Validate Vector DB Name
    useEffect(() => {
        const checkName = async () => {
            const name = localSettings.embedding.vectorDbName;
            if (!name) {
                setVectorDbValidation({ valid: false, message: 'Vector DB name is required', checking: false });
                return;
            }
            if (!/^[a-zA-Z0-9_]+$/.test(name)) {
                setVectorDbValidation({ valid: false, message: 'Only alphanumeric characters and underscores allowed', checking: false });
                return;
            }

            setVectorDbValidation(prev => ({ ...prev, checking: true }));
            try {
                // We assume there's an api client configured for this
                const { apiClient } = await import('../services/api');
                const response = await apiClient.get(`/api/v1/vector-db/check-name?name=${encodeURIComponent(name)}`);
                setVectorDbValidation({ valid: response.data.valid, message: response.data.message, checking: false });
            } catch (err) {
                setVectorDbValidation({ valid: true, message: 'Could not validate with server (assuming valid)', checking: false });
            }
        };

        const timer = setTimeout(checkName, 500);
        return () => clearTimeout(timer);
    }, [localSettings.embedding.vectorDbName]);

    // Load models from AI Registry
    const loadModels = useCallback(async () => {
        setLoadingModels(true);
        setModelError(null);
        try {
            const [embResult, llmResult] = await Promise.all([
                listAIModels({ model_type: 'embedding' as ModelType }),
                listAIModels({ model_type: 'llm' as ModelType })
            ]);
            
            // Filter to only ready models
            const embModels = (embResult.models || []).filter(m => m.is_ready);
            const llModels = (llmResult.models || []).filter(m => m.is_ready);
            
            setEmbeddingModels(embModels);
            setLLMModels(llModels);
            // For compatibility, set all LLMs as compatible for now
            setCompatibleLLMs(llModels);

            const activeEmb = embModels.find(m => m.is_default) || null;
            const activeLl = llModels.find(m => m.is_default) || null;
            setActiveEmbedding(activeEmb);
            setActiveLLM(activeLl);
        } catch (err: unknown) {
            console.error('Failed to load models:', err);
            setModelError('Could not load AI Registry. Using manual input.');
        } finally {
            setLoadingModels(false);
        }
    }, []);

    useEffect(() => {
        loadModels();
    }, [loadModels]);

    // Sync default models to local settings on initial load (only if not already set)
    useEffect(() => {
        if (readOnly || loadingModels) return;
        
        // Use functional update to access current state and avoid stale closures
        setLocalSettings(currentSettings => {
            let needsUpdate = false;
            const newSettings = { ...currentSettings };
            
            // Sync embedding model (model string + top-level embeddingModelId)
            if (activeEmbedding && !hasSetDefaultEmbedding.current && !currentSettings.embeddingModelId) {
                newSettings.embedding = {
                    ...currentSettings.embedding,
                    model: activeEmbedding.model_id,
                };
                newSettings.embeddingModelId = activeEmbedding.id;
                hasSetDefaultEmbedding.current = true;
                needsUpdate = true;
            }
            
            // Sync LLM model (model string + top-level llmModelId)
            if (activeLLM && !hasSetDefaultLLM.current && !currentSettings.llmModelId) {
                newSettings.llm = {
                    ...currentSettings.llm,
                    model: activeLLM.model_id,
                };
                newSettings.llmModelId = activeLLM.id;
                hasSetDefaultLLM.current = true;
                needsUpdate = true;
            }
            
            if (needsUpdate) {
                // Use setTimeout to call onChange after state update to avoid batching issues
                setTimeout(() => onChange(newSettings), 0);
                return newSettings;
            }
            return currentSettings;
        });
    }, [activeEmbedding, activeLLM, loadingModels, readOnly, onChange]);

    const handleChange = (section: keyof AdvancedSettingsProps['settings'], field: string, value: unknown) => {
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
        if (!model || model.is_default) return;

        setActivatingId(modelId);
        setActivationMsg(null);
        try {
            await setAIModelDefault('embedding', modelId);
            // Update local settings with model_id string and top-level embeddingModelId
            const newSettings = {
                ...localSettings,
                embedding: {
                    ...localSettings.embedding,
                    model: model.model_id,
                },
                embeddingModelId: model.id,  // Store at top level
            };
            setLocalSettings(newSettings);
            onChange(newSettings);
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
        if (!model || model.is_default) return;

        setActivatingId(modelId);
        setActivationMsg(null);
        try {
            await setAIModelDefault('llm', modelId);
            // Update local settings with model_id string and top-level llmModelId
            const newSettings = {
                ...localSettings,
                llm: {
                    ...localSettings.llm,
                    model: model.model_id,
                },
                llmModelId: model.id,  // Store at top level
            };
            setLocalSettings(newSettings);
            onChange(newSettings);
            setActivationMsg(`✓ Switched to ${model.display_name}`);
            await loadModels();
        } catch (err) {
            setActivationMsg(`✗ ${handleApiError(err)}`);
        } finally {
            setActivatingId(null);
            setTimeout(() => setActivationMsg(null), 4000);
        }
    };

    return (
        <div className="h-full overflow-y-auto overflow-x-hidden p-1 w-full">
            <h2 className="text-lg sm:text-xl font-semibold mb-2 sm:mb-4 text-gray-900">Advanced Configuration</h2>
            <p className="text-xs sm:text-sm text-gray-500 mb-4 sm:mb-6">
                Fine-tune the RAG pipeline parameters. These settings control how data is processed, indexed, and retrieved.
            </p>

            {/* Feedback toast */}
            {activationMsg && (
                <div className={`mb-4 px-3 sm:px-4 py-2 sm:py-3 rounded-lg text-xs sm:text-sm font-medium flex items-center gap-2 transition-all duration-300 ${activationMsg.startsWith('✓')
                    ? 'bg-green-50 text-green-800 border border-green-200'
                    : 'bg-red-50 text-red-800 border border-red-200'
                    }`}>
                    {activationMsg}
                </div>
            )}

            <div className="space-y-4 sm:space-y-6">

                {/* Vector DB Naming Section - Outside accordion */}
                <div className="p-3 sm:p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <label className="block text-xs sm:text-sm font-semibold text-gray-800 mb-1">
                        Vector Database Namespace
                    </label>
                    <p className="text-[10px] sm:text-xs text-gray-500 mb-2 sm:mb-3">
                        A unique identifier for where your embeddings will be stored.
                    </p>
                    <div className="relative">
                        <input
                            type="text"
                            value={localSettings.embedding.vectorDbName || ''}
                            onChange={(e) => handleChange('embedding', 'vectorDbName', e.target.value)}
                            disabled={readOnly}
                            placeholder="e.g. my_dataset_data"
                            className={`w-full rounded-md shadow-sm text-xs sm:text-sm p-2 border focus:ring-1 
                                ${vectorDbValidation.checking ? 'border-gray-300' :
                                    vectorDbValidation.valid ? 'border-green-300 focus:border-green-500 focus:ring-green-500' :
                                        'border-red-300 focus:border-red-500 focus:ring-red-500'}`}
                        />
                        {vectorDbValidation.checking && (
                            <div className="absolute right-3 top-2">
                                <svg className="animate-spin h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            </div>
                        )}
                    </div>
                    {!vectorDbValidation.checking && vectorDbValidation.message && (
                        <p className={`mt-1 text-[10px] sm:text-xs ${vectorDbValidation.valid ? 'text-green-600' : 'text-red-600'}`}>
                            {vectorDbValidation.valid ? '✓ ' : '✗ '}{vectorDbValidation.message}
                        </p>
                    )}
                </div>

                {/* ============================================================ */}
                {/* 1. Embedding Configuration                             */}
                {/* ============================================================ */}
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                    {/* Accordion Header */}
                    <div className="flex items-center justify-between p-3 sm:p-6">
                        <button
                            type="button"
                            onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSection('embedding'); }}
                            className="flex-1 flex items-center justify-between hover:bg-gray-50 transition-colors -m-3 sm:-m-6 p-3 sm:p-6"
                        >
                            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                                <div className="p-1.5 sm:p-2 bg-indigo-100 rounded-full flex-shrink-0">
                                    <svg className="w-4 h-4 sm:w-5 sm:h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                                    </svg>
                                </div>
                                <h3 className="text-base sm:text-lg font-medium text-gray-900">Embedding Strategy</h3>
                                {activeEmbedding && (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-green-100 text-green-800">
                                        Active: {activeEmbedding.display_name}
                                    </span>
                                )}
                            </div>
                            <svg 
                                className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isSectionOpen('embedding') ? 'rotate-180' : ''}`} 
                                fill="none" 
                                stroke="currentColor" 
                                viewBox="0 0 24 24"
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                        </button>
                    </div>

                    {/* Accordion Content */}
                    {isSectionOpen('embedding') && (
                        <div className="p-3 sm:p-6 border-t border-gray-100">

                    {loadingModels ? (
                        <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-400 p-3">
                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            Loading models...
                        </div>
                    ) : modelError || embeddingModels.length === 0 ? (
                        <div className="mb-4">
                            <label className="block text-xs sm:text-sm font-medium text-gray-700 mb-1">Model Name</label>
                            <input type="text" value={localSettings.embedding.model} onChange={(e) => handleChange('embedding', 'model', e.target.value)} disabled={readOnly} className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs sm:text-sm p-2 border" />
                            {modelError && <p className="mt-1 text-[10px] sm:text-xs text-amber-600">{modelError}</p>}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-2 sm:gap-3 mb-4">
                            {embeddingModels.map(m => {
                                const isActive = m.is_default;
                                const isLoading = activatingId === m.id;
                                const isLocal = m.deployment_type === 'local';
                                return (
                                    <button
                                        key={m.id}
                                        type="button"
                                        onClick={() => handleEmbeddingSelect(m.id)}
                                        disabled={readOnly || isActive || !!activatingId}
                                        className={`text-left p-3 sm:p-4 rounded-lg border-2 transition-all duration-200 ${isActive ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-200 shadow-sm'
                                            : readOnly || activatingId ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed'
                                                : 'border-gray-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/50 cursor-pointer hover:shadow-sm'
                                            }`}
                                    >
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex flex-wrap items-center gap-1 sm:gap-2 mb-1">
                                                    <span className={`text-xs sm:text-sm font-semibold ${isActive ? 'text-indigo-900' : 'text-gray-800'}`}>{m.display_name}</span>
                                                    {isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">Default</span>}
                                                    {/* Deployment Type Badge */}
                                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${isLocal ? 'bg-orange-100 text-orange-700' : 'bg-sky-100 text-sky-700'}`}>
                                                        {isLocal ? 'Local' : 'Cloud'}
                                                    </span>
                                                </div>
                                                <p className="text-[10px] sm:text-xs text-gray-500 truncate">{m.provider_name} • {m.model_id}</p>
                                                <p className="text-[10px] text-gray-400 mt-1">{m.dimensions}d{m.max_input_tokens ? ` • Max ${m.max_input_tokens}` : ''}</p>
                                            </div>
                                            {!isLoading && !isActive && !readOnly && <span className="text-[10px] sm:text-xs text-indigo-500 font-medium flex-shrink-0">Select →</span>}
                                        </div>
                                    </button>
                                );
                            })}

                            {/* Link to AI Registry */}
                            {!readOnly && (
                                <button
                                    type="button"
                                    onClick={() => window.open('/ai-registry', '_blank')}
                                    className="mt-2 inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                                >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                                    Add new model in AI Registry
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                </button>
                            )}
                        </div>
                    )}
                        </div>
                    )}
                </div>

                {/* ============================================================ */}
                {/* 2. LLM Configuration                                   */}
                {/* ============================================================ */}
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                    {/* Accordion Header */}
                    <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSection('llm'); }}
                        className="w-full p-4 sm:p-6 flex items-center justify-between hover:bg-gray-50 transition-colors"
                    >
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-purple-100 rounded-full">
                                <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-medium text-gray-900">LLM Generation Parameters</h3>
                            {activeLLM && (
                                <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                                    Active: {activeLLM.display_name}
                                </span>
                            )}
                        </div>
                        <svg 
                            className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isSectionOpen('llm') ? 'rotate-180' : ''}`} 
                            fill="none" 
                            stroke="currentColor" 
                            viewBox="0 0 24 24"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>

                    {/* Accordion Content */}
                    {isSectionOpen('llm') && (
                        <div className="p-6 border-t border-gray-100">
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
                                        const isActive = m.is_default;
                                        const isCompatible = compatibleLLMs.some(c => c.id === m.id);
                                        const isLoading = activatingId === m.id;
                                        const isLocal = m.deployment_type === 'local';
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
                                                        <div className="flex flex-wrap items-center gap-1 sm:gap-2">
                                                            <span className={`text-sm font-semibold ${isActive ? 'text-purple-900' : 'text-gray-800'}`}>{m.display_name}</span>
                                                            {isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">Default</span>}
                                                            {isCompatible && !isActive && <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                                                            {!isCompatible && !isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-600">Incompatible</span>}
                                                            {/* Deployment Type Badge */}
                                                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${isLocal ? 'bg-orange-100 text-orange-700' : 'bg-sky-100 text-sky-700'}`}>
                                                                {isLocal ? 'Local' : 'Cloud'}
                                                            </span>
                                                        </div>
                                                        <p className="text-xs text-gray-500 mt-0.5">{m.provider_name} • {m.model_id}</p>
                                                    </div>
                                                    {!isLoading && !isActive && !readOnly && <span className="text-xs text-purple-500 font-medium ml-2 flex-shrink-0">Select →</span>}
                                                </div>
                                            </button>
                                        );
                                    })}

                                    {/* Link to AI Registry */}
                                    {!readOnly && (
                                        <button
                                            type="button"
                                            onClick={() => window.open('/ai-registry', '_blank')}
                                            className="mt-2 w-full inline-flex items-center justify-center gap-1 text-xs text-purple-600 hover:text-purple-800 font-medium py-2"
                                        >
                                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                                            Add new model in AI Registry
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                        </button>
                                    )}
                                </div>
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
                    )}
                </div>

                {/* ============================================================ */}
                {/* 3. Chunking Configuration                              */}
                {/* ============================================================ */}
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                    {/* Accordion Header */}
                    <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSection('chunking'); }}
                        className="w-full p-4 sm:p-6 flex items-center justify-between hover:bg-gray-50 transition-colors"
                    >
                        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                            <div className="p-2 bg-blue-100 rounded-full">
                                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-medium text-gray-900">Indexing Strategy</h3>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-blue-100 text-blue-800">
                                Schema-Aware (DDL per table)
                            </span>
                        </div>
                        <svg 
                            className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isSectionOpen('chunking') ? 'rotate-180' : ''}`} 
                            fill="none" 
                            stroke="currentColor" 
                            viewBox="0 0 24 24"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>

                    {/* Accordion Content */}
                    {isSectionOpen('chunking') && (
                        <div className="p-6 border-t border-gray-100">
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
                                        onChange={(e) => {
                                            const val = e.target.value === '' ? 0 : parseInt(e.target.value, 10);
                                            if (!isNaN(val)) handleChange('chunking', 'parentChunkSize', val);
                                        }}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Overlap</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.parentChunkOverlap}
                                        onChange={(e) => {
                                            const val = e.target.value === '' ? 0 : parseInt(e.target.value, 10);
                                            if (!isNaN(val)) handleChange('chunking', 'parentChunkOverlap', val);
                                        }}
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
                                        onChange={(e) => {
                                            const val = e.target.value === '' ? 0 : parseInt(e.target.value, 10);
                                            if (!isNaN(val)) handleChange('chunking', 'childChunkSize', val);
                                        }}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-blue-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border bg-white"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-700 mb-1">Overlap</label>
                                    <input
                                        type="number"
                                        value={localSettings.chunking.childChunkOverlap}
                                        onChange={(e) => {
                                            const val = e.target.value === '' ? 0 : parseInt(e.target.value, 10);
                                            if (!isNaN(val)) handleChange('chunking', 'childChunkOverlap', val);
                                        }}
                                        disabled={readOnly}
                                        className="w-full rounded-md border-blue-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border bg-white"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                        </div>
                    )}
                </div>

                {/* ============================================================ */}
                {/* 4. Retrieval Configuration                             */}
                {/* ============================================================ */}
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                    {/* Accordion Header */}
                    <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSection('retrieval'); }}
                        className="w-full p-4 sm:p-6 flex items-center justify-between hover:bg-gray-50 transition-colors"
                    >
                        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                            <div className="p-2 bg-emerald-100 rounded-full">
                                <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-medium text-gray-900">Retrieval Parameters</h3>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-emerald-100 text-emerald-800">
                                Top-K: {localSettings.retriever.topKInitial} → {localSettings.retriever.topKFinal}
                            </span>
                            {localSettings.retriever.rerankEnabled && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-amber-100 text-amber-800">
                                    Rerank: On
                                </span>
                            )}
                        </div>
                        <svg 
                            className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isSectionOpen('retrieval') ? 'rotate-180' : ''}`} 
                            fill="none" 
                            stroke="currentColor" 
                            viewBox="0 0 24 24"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>

                    {/* Accordion Content */}
                    {isSectionOpen('retrieval') && (
                        <div className="p-6 border-t border-gray-100">
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
                                {/* AI Registry Reranker Selector */}
                                {aiRegistry.rerankerModels.length > 0 ? (
                                    <AIModelSelector
                                        modelType="reranker"
                                        models={aiRegistry.rerankerModels}
                                        selectedModelId={localSettings.retriever.rerankerModel || null}
                                        onSelect={(modelId) => {
                                            // Look up the model to get the database ID
                                            const model = aiRegistry.rerankerModels.find(m => m.model_id === modelId);
                                            const newSettings = {
                                                ...localSettings,
                                                retriever: {
                                                    ...localSettings.retriever,
                                                    rerankerModel: modelId,
                                                },
                                                rerankerModelId: model?.id,  // Store at top level
                                            };
                                            setLocalSettings(newSettings);
                                            onChange(newSettings);
                                        }}
                                        disabled={readOnly || !localSettings.retriever.rerankEnabled}
                                        isLoading={aiRegistry.isLoading}
                                        label="Reranker Model"
                                        compact={true}
                                    />
                                ) : (
                                    <>
                                        <label className="block text-xs font-medium text-gray-700 mb-1">Reranker Model</label>
                                        <input
                                            type="text"
                                            value={localSettings.retriever.rerankerModel}
                                            onChange={(e) => handleChange('retriever', 'rerankerModel', e.target.value)}
                                            disabled={readOnly || !localSettings.retriever.rerankEnabled}
                                            className="w-full rounded-md border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 sm:text-sm p-2 border"
                                        />
                                        <p className="mt-1 text-[10px] text-gray-400">HuggingFace Model ID (e.g. BAAI/bge-reranker-base)</p>
                                    </>
                                )}

                                {/* Link to AI Registry */}
                                {!readOnly && (
                                    <button
                                        type="button"
                                        onClick={() => window.open('/ai-registry', '_blank')}
                                        className="mt-3 inline-flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium"
                                    >
                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                                        Add new model in AI Registry
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AdvancedSettings;
