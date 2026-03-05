import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ChatHeader } from '../components/chat';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import {
    getAgents,
    generateSystemPrompt,
    publishSystemPrompt,
    getPromptHistory,
    getActiveConfigMetadata,
    handleApiError,
    startEmbeddingJob,
    getSystemSettings,
    getConnections
} from '../services/api';
import type { IngestionResponse } from '../services/api';
import { canEditPrompt, canPublishPrompt } from '../utils/permissions';
import type { Agent } from '../types/agent';
import type { AdvancedSettings, PromptVersion } from '../contexts/AgentContext';

// Import step components
import {
    DataSourceStep,
    SchemaSelectionStep,
    DictionaryStep,
    AdvancedSettingsStep,
    ReviewPublishStep,
    SummaryStep
} from '../components/config/steps';

const steps = [
    { id: 1, name: 'Data Source' },
    { id: 2, name: 'Select Schema' },
    { id: 3, name: 'Data Dictionary' },
    { id: 4, name: 'Advanced Settings' },
    { id: 5, name: 'Review & Publish' },
    { id: 6, name: 'Summary' }
];

const defaultAdvancedSettings: AdvancedSettings = {
    embedding: { model: 'BAAI/bge-m3' },
    llm: { temperature: 0.0, maxTokens: 4096 },
    chunking: { parentChunkSize: 800, parentChunkOverlap: 150, childChunkSize: 200, childChunkOverlap: 50 },
    retriever: { topKInitial: 50, topKFinal: 10, hybridWeights: [0.75, 0.25], rerankEnabled: true, rerankerModel: 'BAAI/bge-reranker-base' }
};

const AgentConfigPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const { user, isLoading: isAuthLoading } = useAuth();
    const { success: showSuccess, error: showError } = useToast();
    const canEdit = canEditPrompt(user);
    const canPublish = canPublishPrompt(user);

    // Agent state
    const [agent, setAgent] = useState<Agent | null>(null);
    const [isLoadingAgent, setIsLoadingAgent] = useState(true);

    // Wizard state
    const initialStep = searchParams.get('step') ? parseInt(searchParams.get('step')!) : 1;
    const [currentStep, setCurrentStep] = useState(initialStep);

    // Config state
    const [connectionId, setConnectionId] = useState<number | null>(null);
    const [connectionName, setConnectionName] = useState('');
    const [selectedSchema, setSelectedSchema] = useState<Record<string, string[]>>({});
    const [dataDictionary, setDataDictionary] = useState('');
    const [dataSourceType, setDataSourceType] = useState<'database' | 'file'>('database');
    const [fileUploadResult, setFileUploadResult] = useState<IngestionResponse | null>(null);
    const [reasoning, setReasoning] = useState<Record<string, string>>({});
    const [exampleQuestions, setExampleQuestions] = useState<string[]>([]);
    const [draftPrompt, setDraftPrompt] = useState('');
    const [history, setHistory] = useState<PromptVersion[]>([]);
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(defaultAdvancedSettings);
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);

    // Refs for auto-scrolling steps
    const stepsContainerRef = useRef<HTMLDivElement>(null);
    const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

    // Status
    const [generating, setGenerating] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Load agent
    useEffect(() => {
        const loadAgent = async () => {
            if (!id) return;
            setIsLoadingAgent(true);
            try {
                const agents = await getAgents();
                const foundAgent = agents.find((a: Agent) => a.id === parseInt(id));
                if (foundAgent) {
                    setAgent(foundAgent);
                } else {
                    showError('Agent Not Found', 'The requested agent could not be found.');
                    navigate('/agents');
                }
            } catch (err) {
                console.error('Failed to load agent', err);
                showError('Error', 'Failed to load agent.');
                navigate('/agents');
            } finally {
                setIsLoadingAgent(false);
            }
        };
        loadAgent();
    }, [id, navigate, showError]);

    // Load existing config and defaults
    useEffect(() => {
        const loadConfig = async () => {
            if (!agent) return;

            // Fetch system defaults
            try {
                const [embSettings, ragSettings, llmSettings] = await Promise.all([
                    getSystemSettings('embedding').catch(() => null),
                    getSystemSettings('rag').catch(() => null),
                    getSystemSettings('llm').catch(() => null)
                ]);

                setAdvancedSettings(prev => {
                    const next = { ...prev };
                    if (embSettings && embSettings.model_name) next.embedding = { ...next.embedding, model: embSettings.model_name };
                    if (ragSettings) {
                        if (ragSettings.chunk_size) next.chunking = { ...next.chunking, parentChunkSize: ragSettings.chunk_size };
                        if (ragSettings.chunk_overlap) next.chunking = { ...next.chunking, parentChunkOverlap: ragSettings.chunk_overlap };
                        if (ragSettings.top_k_initial) next.retriever = { ...next.retriever, topKInitial: ragSettings.top_k_initial };
                        if (ragSettings.top_k_final) next.retriever = { ...next.retriever, topKFinal: ragSettings.top_k_final };
                        if (ragSettings.hybrid_weights) next.retriever = { ...next.retriever, hybridWeights: ragSettings.hybrid_weights };
                        if (ragSettings.rerank_enabled !== undefined) next.retriever = { ...next.retriever, rerankEnabled: ragSettings.rerank_enabled };
                        if (ragSettings.reranker_model) next.retriever = { ...next.retriever, rerankerModel: ragSettings.reranker_model };
                    }
                    if (llmSettings) {
                        if (llmSettings.temperature !== undefined) next.llm = { ...next.llm, temperature: llmSettings.temperature };
                        if (llmSettings.max_tokens) next.llm = { ...next.llm, maxTokens: llmSettings.max_tokens };
                    }
                    return next;
                });
            } catch (err) {
                console.warn("Failed to load backend defaults", err);
            }

            // Load existing config
            try {
                const config = await getActiveConfigMetadata(agent.id);
                if (config) {
                    // Pre-fill state from existing config
                    if (config.connection_id) {
                        setConnectionId(config.connection_id);
                        // Fetch connection name
                        try {
                            const conns = await getConnections();
                            const c = conns.find((x: any) => x.id === config.connection_id);
                            if (c) setConnectionName(c.name);
                        } catch (e) {
                            console.error("Failed to fetch connection name", e);
                        }
                    }
                    if (config.schema_selection) {
                        try {
                            setSelectedSchema(JSON.parse(config.schema_selection));
                        } catch (e) {
                            console.error("Failed to parse schema", e);
                        }
                    }
                    if (config.data_dictionary) setDataDictionary(config.data_dictionary);
                    if (config.prompt_text) setDraftPrompt(config.prompt_text);
                    if (config.reasoning) {
                        try {
                            setReasoning(typeof config.reasoning === 'string' ? JSON.parse(config.reasoning) : config.reasoning);
                        } catch (e) {
                            console.error("Failed to parse reasoning", e);
                        }
                    }
                    if (config.data_source_type) setDataSourceType(config.data_source_type as 'database' | 'file');

                    // Pre-fill Advanced Settings from config
                    const parseConf = (c: any) => c ? (typeof c === 'string' ? JSON.parse(c) : c) : null;
                    const emb = parseConf(config.embedding_config);
                    const llm = parseConf(config.llm_config);
                    const chunk = parseConf(config.chunking_config);
                    const ret = parseConf(config.retriever_config);

                    setAdvancedSettings(prev => {
                        const next = { ...prev };
                        if (emb) next.embedding = { ...next.embedding, ...emb };
                        if (llm) next.llm = { ...next.llm, ...llm };
                        if (chunk) next.chunking = { ...next.chunking, ...chunk };
                        if (ret) next.retriever = { ...next.retriever, ...ret };
                        return next;
                    });
                }
            } catch (e) {
                console.error("Failed to load existing config", e);
            }

            // Load history
            try {
                const historyData = await getPromptHistory(agent.id);
                setHistory(historyData);
            } catch (err) {
                console.error("Failed to load history", err);
            }
        };
        loadConfig();
    }, [agent]);

    // Sync state to window for API use (temporary solution)
    useEffect(() => {
        (window as any).__config_connectionId = connectionId;
        (window as any).__config_schema = selectedSchema;
        (window as any).__config_dictionary = dataDictionary;
    }, [connectionId, selectedSchema, dataDictionary]);

    // Auto-scroll to current step when it changes
    useEffect(() => {
        const stepElement = stepRefs.current[currentStep - 1];
        const container = stepsContainerRef.current;
        if (stepElement && container) {
            const containerRect = container.getBoundingClientRect();
            const stepRect = stepElement.getBoundingClientRect();
            const scrollLeft = stepRect.left - containerRect.left + container.scrollLeft - (containerRect.width / 2) + (stepRect.width / 2);
            container.scrollTo({ left: scrollLeft, behavior: 'smooth' });
        }
    }, [currentStep]);

    // Sync step to URL
    useEffect(() => {
        const currentStepParam = searchParams.get('step');
        if (currentStep.toString() !== currentStepParam) {
            setSearchParams({ step: currentStep.toString() }, { replace: true });
        }
    }, [currentStep, searchParams, setSearchParams]);

    const handleNext = () => {
        if (currentStep === 1) {
            if (dataSourceType === 'database' && !connectionId) {
                setError("Please select a database connection.");
                return;
            }
            if (dataSourceType === 'file' && !fileUploadResult) {
                setError("Please upload a file first.");
                return;
            }
        }
        if (currentStep === 2 && dataSourceType === 'database' && Object.keys(selectedSchema).length === 0) {
            setError("Please select at least one table/column.");
            return;
        }
        setError(null);
        if (currentStep < 6) setCurrentStep(currentStep + 1);
    };

    const handleBack = () => {
        if (currentStep > 1) setCurrentStep(currentStep - 1);
    };

    const handleGenerate = async () => {
        setGenerating(true);
        setError(null);
        try {
            let fullContext = dataDictionary;

            if (dataSourceType === 'database') {
                let schemaContext = "Selected Tables and Columns:\n";
                Object.entries(selectedSchema).forEach(([table, cols]) => {
                    schemaContext += `- ${table}: [${cols.join(', ')}]\n`;
                });
                schemaContext += "\n";
                fullContext = schemaContext + dataDictionary;
            } else if (dataSourceType === 'file' && fileUploadResult) {
                let documentContext = "Extracted Document Content:\n";
                documentContext += fileUploadResult.documents.map((doc, i) =>
                    `--- Document ${i + 1} ---\n${doc.page_content}`
                ).join('\n\n');
                fullContext = documentContext + "\n\nUser Notes / Context:\n" + dataDictionary;
            }

            const result = await generateSystemPrompt(fullContext, dataSourceType);
            setDraftPrompt(result.draft_prompt);
            if (result.reasoning) setReasoning(result.reasoning);
            if (result.example_questions) setExampleQuestions(result.example_questions);
            setCurrentStep(5); // Move to Review & Publish (was incorrectly set to 4)
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setGenerating(false);
        }
    };

    const handlePublish = async () => {
        if (!draftPrompt.trim() || !agent) return;
        setPublishing(true);
        setError(null);

        // Derive vector db name if missing
        const finalEmbeddingConfig = { ...advancedSettings.embedding } as any;
        if (!finalEmbeddingConfig.vectorDbName) {
            let baseName = '';
            if (dataSourceType === 'database' && connectionName) {
                baseName = connectionName;
            } else if (dataSourceType === 'file' && fileUploadResult) {
                baseName = fileUploadResult.file_name.split('.')[0];
            }

            if (baseName) {
                const formatted = baseName.replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase();
                finalEmbeddingConfig.vectorDbName = `${formatted}_data`;
            } else {
                finalEmbeddingConfig.vectorDbName = `agent_${agent.id}_data`;
            }
        }

        try {
            const result = await publishSystemPrompt(
                draftPrompt,
                reasoning,
                exampleQuestions,
                finalEmbeddingConfig,
                advancedSettings.retriever,
                advancedSettings.chunking,
                advancedSettings.llm,
                agent.id,
                dataSourceType,
                fileUploadResult ? JSON.stringify(fileUploadResult.documents) : undefined,
                fileUploadResult?.file_name,
                fileUploadResult?.file_type
            );
            setSuccessMessage(`Prompt published successfully! Version: ${result.version}`);
            // Refresh history
            const historyData = await getPromptHistory(agent.id);
            setHistory(historyData);
            setCurrentStep(6); // Move to Summary
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setPublishing(false);
        }
    };

    const handleStartEmbedding = async (incremental: boolean = false, settings?: any) => {
        if (!agent) return;
        try {
            // Get config id
            const config = await getActiveConfigMetadata(agent.id);
            const configId = config?.id || config?.prompt_id;
            if (!configId) {
                showError('Error', 'No configuration found to embed.');
                return;
            }

            // Use settings from modal if provided, otherwise use defaults
            let batchSize = settings?.batch_size || 128;
            let maxConcurrent = settings?.max_concurrent || 5;

            if (!settings) {
                try {
                    const systemSettings = await getSystemSettings('embedding');
                    if (systemSettings?.batch_size) batchSize = systemSettings.batch_size;
                    if (systemSettings?.max_concurrent) maxConcurrent = systemSettings.max_concurrent;
                } catch (err) {
                    console.warn('Failed to fetch embedding settings, using defaults', err);
                }
            }

            const result = await startEmbeddingJob({
                config_id: configId,
                batch_size: batchSize,
                max_concurrent: maxConcurrent,
                incremental: incremental,
                // Pass chunking from settings or from advancedSettings
                chunking: settings?.chunking || {
                    parent_chunk_size: advancedSettings.chunking.parentChunkSize,
                    parent_chunk_overlap: advancedSettings.chunking.parentChunkOverlap,
                    child_chunk_size: advancedSettings.chunking.childChunkSize,
                    child_chunk_overlap: advancedSettings.chunking.childChunkOverlap,
                },
                // Pass additional settings from modal
                parallelization: settings?.parallelization,
                medical_context_config: settings?.medical_context_config,
                max_consecutive_failures: settings?.max_consecutive_failures,
                retry_attempts: settings?.retry_attempts,
            });
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };

    const handleGoToDashboard = () => {
        if (agent) {
            navigate(`/agents/${agent.id}`);
        }
    };

    if (isAuthLoading || isLoadingAgent) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading...</span>
                </div>
            </div>
        );
    }

    if (!agent) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <p className="text-gray-500">Agent not found</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50 overflow-x-hidden">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="max-w-7xl mx-auto py-4 sm:py-8 px-3 sm:px-4 flex flex-col">
                    {/* Header & Steps */}
                    <div className="mb-4 sm:mb-8">
                        <div className="flex items-center gap-2 sm:gap-4 mb-4 sm:mb-6">
                            <button
                                onClick={() => navigate(`/agents/${agent.id}`)}
                                className="p-2 -ml-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-full transition-colors flex-shrink-0"
                                title="Back to Dashboard"
                            >
                                <ArrowLeftIcon className="w-5 h-5 sm:w-6 sm:h-6" />
                            </button>
                            <div className="flex-1 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1 min-w-0">
                                <h1 className="text-lg sm:text-2xl font-bold text-gray-900 truncate">
                                    Configure {agent.name}
                                </h1>
                                <span className="text-xs sm:text-sm text-gray-500 flex-shrink-0">Step {currentStep} of 6</span>
                            </div>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-gray-200 rounded-full h-1.5 sm:h-2 mb-4 sm:mb-6">
                            <div
                                className="bg-blue-600 h-1.5 sm:h-2 rounded-full transition-all duration-300"
                                style={{ width: `${(currentStep / 6) * 100}%` }}
                            ></div>
                        </div>

                        {/* Step Indicators - Scrollable on mobile with auto-scroll */}
                        <div 
                            ref={stepsContainerRef}
                            className="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0 scrollbar-hide"
                        >
                            <div className="flex justify-between relative min-w-[500px] sm:min-w-0">
                                {steps.map((step, index) => (
                                    <div 
                                        key={step.id} 
                                        ref={(el) => { stepRefs.current[index] = el; }}
                                        className="flex flex-col items-center z-10"
                                    >
                                        <div className={`w-6 h-6 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-xs sm:text-sm font-medium transition-colors duration-200 
                                            ${currentStep >= step.id ? 'bg-blue-600 text-white' : 'bg-white border-2 border-gray-300 text-gray-400'}`}>
                                            {step.id}
                                        </div>
                                        <span className={`text-[10px] sm:text-xs mt-1 sm:mt-2 font-medium text-center whitespace-nowrap ${currentStep >= step.id ? 'text-blue-600' : 'text-gray-400'}`}>
                                            {step.name}
                                        </span>
                                    </div>
                                ))}
                                {/* Connecting Line */}
                                <div className="absolute top-3 sm:top-4 left-0 w-full h-0.5 bg-gray-200 -z-0"></div>
                            </div>
                        </div>
                    </div>

                    {/* Content Area */}
                    <div className="flex-1 min-h-0 bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                        <div className="p-3 sm:p-6 h-full flex flex-col overflow-x-hidden">
                            {successMessage && (
                                <Alert
                                    type="success"
                                    message={successMessage}
                                    onDismiss={() => setSuccessMessage(null)}
                                />
                            )}

                            {error && (
                                <Alert
                                    type="error"
                                    message={error}
                                    onDismiss={() => setError(null)}
                                />
                            )}

                            {currentStep === 1 && (
                                <DataSourceStep
                                    dataSourceType={dataSourceType}
                                    setDataSourceType={setDataSourceType}
                                    connectionId={connectionId}
                                    setConnectionId={setConnectionId}
                                    setConnectionName={setConnectionName}
                                    setFileUploadResult={setFileUploadResult}
                                />
                            )}

                            {currentStep === 2 && (
                                <SchemaSelectionStep
                                    dataSourceType={dataSourceType}
                                    connectionId={connectionId}
                                    setSelectedSchema={setSelectedSchema}
                                    fileUploadResult={fileUploadResult}
                                    reasoning={reasoning}
                                />
                            )}

                            {currentStep === 3 && (
                                <DictionaryStep
                                    dataSourceType={dataSourceType}
                                    dataDictionary={dataDictionary}
                                    setDataDictionary={setDataDictionary}
                                    fileUploadResult={fileUploadResult}
                                />
                            )}

                            {currentStep === 4 && (
                                <AdvancedSettingsStep
                                    advancedSettings={advancedSettings}
                                    setAdvancedSettings={setAdvancedSettings}
                                    dataSourceType={dataSourceType}
                                    connectionName={connectionName}
                                    connectionId={connectionId}
                                    fileName={fileUploadResult?.file_name}
                                />
                            )}

                            {currentStep === 5 && (
                                <ReviewPublishStep
                                    draftPrompt={draftPrompt}
                                    setDraftPrompt={setDraftPrompt}
                                    exampleQuestions={exampleQuestions}
                                    history={history}
                                />
                            )}

                            {currentStep === 6 && (
                                <SummaryStep
                                    connectionId={connectionId}
                                    connectionName={connectionName}
                                    dataSourceType={dataSourceType}
                                    fileUploadResult={fileUploadResult}
                                    selectedSchema={selectedSchema}
                                    dataDictionary={dataDictionary}
                                    history={history}
                                    advancedSettings={advancedSettings}
                                    embeddingJobId={embeddingJobId}
                                    onStartEmbedding={handleStartEmbedding}
                                    onEmbeddingComplete={() => {
                                        showSuccess('Knowledge Base Ready!', 'Your agent can now answer questions based on your data.');
                                        setEmbeddingJobId(null);
                                    }}
                                    onEmbeddingError={(err) => showError('Embedding Failed', err)}
                                    onEmbeddingCancel={() => {
                                        showError('Job Cancelled', 'Knowledge base creation was cancelled.');
                                        setEmbeddingJobId(null);
                                    }}
                                    onGoToDashboard={handleGoToDashboard}
                                />
                            )}
                        </div>
                    </div>

                    {/* Footer Navigation */}
                    <div className="mt-4 sm:mt-8 flex flex-col sm:flex-row justify-between gap-3 sm:gap-0">
                        <button
                            onClick={handleBack}
                            className={`px-4 sm:px-6 py-2 rounded-md font-medium text-sm sm:text-base order-2 sm:order-1 ${currentStep === 1 ? 'text-gray-400 cursor-not-allowed' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                            disabled={currentStep === 1}
                        >
                            Back
                        </button>

                        <div className="order-1 sm:order-2">
                            {currentStep === 4 ? (
                                <button
                                    onClick={handleGenerate}
                                    disabled={generating || !canEdit}
                                    className={`w-full sm:w-auto px-4 sm:px-6 py-2 rounded-md font-medium text-white text-sm sm:text-base transition-all duration-200 flex items-center justify-center gap-2
                                        ${generating ? 'bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse' : !canEdit ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                    title={!canEdit ? "Read-only mode" : "Generate Prompt"}
                                >
                                    {generating ? (
                                        <>
                                            <svg className="animate-spin h-4 w-4 sm:h-5 sm:w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            <span className="hidden sm:inline">Generating with AI...</span>
                                            <span className="sm:hidden">Generating...</span>
                                        </>
                                    ) : (
                                        <>
                                            <svg className="h-4 w-4 sm:h-5 sm:w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                            </svg>
                                            <span>Generate Prompt</span>
                                        </>
                                    )}
                                </button>
                            ) : currentStep === 5 ? (
                                canPublish ? (
                                    <button
                                        onClick={handlePublish}
                                        disabled={publishing}
                                        className="w-full sm:w-auto px-4 sm:px-6 py-2 bg-green-600 text-white rounded-md font-medium text-sm sm:text-base hover:bg-green-700 disabled:opacity-50 flex items-center justify-center"
                                    >
                                        {publishing ? 'Publishing...' : 'Publish'}
                                    </button>
                                ) : (
                                    <div className="text-gray-500 italic text-xs sm:text-sm border border-gray-200 rounded px-3 sm:px-4 py-2 bg-gray-50 text-center">
                                        Publish restricted
                                    </div>
                                )
                            ) : currentStep === 6 ? (
                                <button
                                    onClick={handleGoToDashboard}
                                    className="w-full sm:w-auto px-4 sm:px-6 py-2 bg-blue-600 text-white rounded-md font-medium text-sm sm:text-base hover:bg-blue-700 shadow-md"
                                >
                                    Go to Dashboard
                                </button>
                            ) : (
                                <button
                                    onClick={handleNext}
                                    disabled={generating || publishing || (currentStep === 1 && dataSourceType === 'database' && !connectionId) || (currentStep === 1 && dataSourceType === 'file' && !fileUploadResult)}
                                    className={`w-full sm:w-auto px-4 sm:px-6 py-2 rounded-md font-medium text-white text-sm sm:text-base transition-colors duration-200 flex items-center justify-center
                                        ${generating || publishing || (currentStep === 1 && dataSourceType === 'database' && !connectionId) || (currentStep === 1 && dataSourceType === 'file' && !fileUploadResult) ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                >
                                    Next
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AgentConfigPage;
