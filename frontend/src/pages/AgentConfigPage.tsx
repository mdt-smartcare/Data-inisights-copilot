import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ChatHeader } from '../components/chat';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import { useConfigDraft } from '../hooks';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import {
    getAgent,
    generatePrompt,
    handleApiError,
    startEmbeddingJob,
    getDataSource,
    getConfigHistory,
    type DataSource,
    type DataSourceSchemaResponse
} from '../services/api';
import type { IngestionResponse } from '../services/api';
import { canPublishPrompt } from '../utils/permissions';
import type { Agent } from '../types/agent';
import type { AdvancedSettings } from '../contexts/AgentContext';

// Utility to convert snake_case keys to camelCase
const snakeToCamel = (str: string): string =>
    str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());

const toCamelCaseKeys = <T extends Record<string, unknown>>(obj: T | null | undefined): Record<string, unknown> | null => {
    if (!obj || typeof obj !== 'object') return null;
    return Object.fromEntries(
        Object.entries(obj).map(([key, value]) => [snakeToCamel(key), value])
    );
};

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
    { id: 5, name: 'System Prompt' },
    { id: 6, name: 'Knowledge Base' }
];

const defaultAdvancedSettings: AdvancedSettings = {
    embedding: { model: 'huggingface/BAAI/bge-m3' },
    llm: { model: 'openai/gpt-4o-mini', temperature: 0.0, maxTokens: 4096 },
    chunking: { parentChunkSize: 512, parentChunkOverlap: 100, childChunkSize: 128, childChunkOverlap: 25 },
    retriever: { topKInitial: 50, topKFinal: 10, hybridWeights: [0.75, 0.25], rerankEnabled: true, rerankerModel: 'huggingface/BAAI/bge-reranker-v2-m3' }
};

const AgentConfigPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const { user, isLoading: isAuthLoading } = useAuth();
    const { success: showSuccess, error: showError } = useToast();
    const canPublish = canPublishPrompt(user);

    // Draft config hook
    const {
        draft,
        versionId: hookVersionId,
        isLoading: isDraftLoading,
        isSaving,
        isPublishing,
        error: draftError,
        loadDraft,
        loadVersion,
        createNewDraft,
        saveStep,
        publish,
    } = useConfigDraft();

    // Agent state
    const [agent, setAgent] = useState<Agent | null>(null);
    const [isLoadingAgent, setIsLoadingAgent] = useState(true);

    // Wizard state  
    const initialStep = searchParams.get('step') ? parseInt(searchParams.get('step')!) : 1;
    const urlVersionId = searchParams.get('versionId') ? parseInt(searchParams.get('versionId')!) : null;
    const [currentStep, setCurrentStep] = useState(initialStep);
    const [hasDraft, setHasDraft] = useState(false);

    // Config state
    const [selectedDataSource, setSelectedDataSource] = useState<DataSource | null>(null);
    const [connectionId, setConnectionId] = useState<number | null>(null);
    const [connectionName, setConnectionName] = useState('');
    const [selectedSchema, setSelectedSchema] = useState<Record<string, string[]>>({});
    const [dataDictionary, setDataDictionary] = useState('');
    const [dataSourceType, setDataSourceType] = useState<'database' | 'file'>('database');
    const [fileUploadResult, setFileUploadResult] = useState<IngestionResponse | null>(null);
    const [selectedFileColumns, setSelectedFileColumns] = useState<string[]>([]);
    const [fullSchema, setFullSchema] = useState<DataSourceSchemaResponse | null>(null);
    const [reasoning, setReasoning] = useState<Record<string, string>>({});
    const [exampleQuestions, setExampleQuestions] = useState<string[]>([]);
    const [draftPrompt, setDraftPrompt] = useState('');
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(defaultAdvancedSettings);
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [isDataSourceLocked, setIsDataSourceLocked] = useState(false);

    // Refs for auto-scrolling steps
    const stepsContainerRef = useRef<HTMLDivElement>(null);
    const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

    // Status
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Track if initial load has been done
    const initialLoadDoneRef = useRef(false);

    // Load agent and draft/version - only runs once on mount
    useEffect(() => {
        // Skip if already loaded
        if (initialLoadDoneRef.current) return;

        const loadAgentAndConfig = async () => {
            if (!id) return;
            initialLoadDoneRef.current = true;
            setIsLoadingAgent(true);
            try {
                // Fetch agent
                const [foundAgent] = await Promise.all([
                    getAgent(id),
                ]);
                setAgent(foundAgent);

                // Check if agent has published configs to lock data source
                try {
                    const history = await getConfigHistory(id);
                    const hasPublished = history.configs.some(c => c.status === 'published');
                    setIsDataSourceLocked(hasPublished);
                } catch (err) {
                    console.error('Failed to fetch config history:', err);
                }

                // If versionId is in URL, load that specific version
                // Otherwise, check for existing draft
                let config = null;
                if (urlVersionId) {
                    config = await loadVersion(id, urlVersionId);
                } else {
                    config = await loadDraft(id);
                }

                if (config) {
                    setHasDraft(true);
                    // Use URL step if present, otherwise go to next step after last completed
                    const urlStep = searchParams.get('step');
                    if (!urlStep) {
                        setCurrentStep(Math.min((config.completed_step || 0) + 1, 6));
                    }
                    // Pre-fill state from config - fetch full data source to get type
                    let sourceType: 'database' | 'file' = 'database';
                    if (config.data_source_id) {
                        try {
                            const ds = await getDataSource(config.data_source_id);
                            setSelectedDataSource(ds);
                            sourceType = ds.source_type;
                            setDataSourceType(ds.source_type);
                        } catch {
                            // Fallback to minimal object if fetch fails
                            setSelectedDataSource({ id: config.data_source_id } as DataSource);
                        }
                    }
                    if (config.system_prompt) setDraftPrompt(config.system_prompt);
                    if (config.example_questions) setExampleQuestions(config.example_questions);
                    // Handle selected_columns - now always object format { table_name: columns[] }
                    if (config.selected_columns) {
                        if (typeof config.selected_columns === 'object' && !Array.isArray(config.selected_columns)) {
                            const schemaObj = config.selected_columns as Record<string, string[]>;
                            if (sourceType === 'file') {
                                // For files: extract columns from the single table entry
                                const firstTable = Object.keys(schemaObj)[0];
                                if (firstTable) {
                                    setSelectedFileColumns(schemaObj[firstTable]);
                                }
                            } else {
                                // Database: keep the full schema mapping
                                setSelectedSchema(schemaObj);
                            }
                        } else if (Array.isArray(config.selected_columns)) {
                            // Legacy format: flat array (file source)
                            setSelectedFileColumns(config.selected_columns);
                            setDataSourceType('file');
                        }
                    }
                    if (config.data_dictionary?.content) setDataDictionary(config.data_dictionary.content as string);
                    // Pre-fill advanced settings from config (normalize snake_case to camelCase)
                    if (config.llm_config || config.embedding_config || config.chunking_config || config.rag_config ||
                        config.embedding_model_id || config.llm_model_id || config.reranker_model_id) {
                        const llmNorm = toCamelCaseKeys(config.llm_config);
                        const embNorm = toCamelCaseKeys(config.embedding_config);
                        const chunkNorm = toCamelCaseKeys(config.chunking_config);
                        const ragNorm = toCamelCaseKeys(config.rag_config);
                        setAdvancedSettings(prev => ({
                            ...prev,
                            ...(llmNorm && { llm: { ...prev.llm, ...llmNorm } }),
                            ...(embNorm && { embedding: { ...prev.embedding, ...embNorm } }),
                            ...(chunkNorm && { chunking: { ...prev.chunking, ...chunkNorm } }),
                            ...(ragNorm && { retriever: { ...prev.retriever, ...ragNorm } }),
                            // Restore model IDs from config
                            ...(config.embedding_model_id && { embeddingModelId: config.embedding_model_id }),
                            ...(config.llm_model_id && { llmModelId: config.llm_model_id }),
                            ...(config.reranker_model_id && { rerankerModelId: config.reranker_model_id }),
                        }));
                    }
                }
            } catch (err) {
                console.error('Failed to load agent', err);
                showError('Agent Not Found', 'The requested agent could not be found.');
                navigate('/agents');
            } finally {
                setIsLoadingAgent(false);
            }
        };
        loadAgentAndConfig();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    // Fetch schema if it's missing but we have a data source (e.g. on reload)
    useEffect(() => {
        if (selectedDataSource?.id && !fullSchema && dataSourceType === 'database') {
            const fetchSchema = async () => {
                try {
                    const { getDataSourceSchema } = await import('../services/api');
                    const schema = await getDataSourceSchema(selectedDataSource.id);
                    setFullSchema(schema);
                } catch (err) {
                    console.error('Failed to auto-fetch schema:', err);
                }
            };
            fetchSchema();
        }
    }, [selectedDataSource, fullSchema, dataSourceType]);

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

    // Sync step and versionId to URL
    useEffect(() => {
        const currentStepParam = searchParams.get('step');
        const currentVersionParam = searchParams.get('versionId');
        const newParams: Record<string, string> = { step: currentStep.toString() };

        // Add versionId to URL if we have one
        if (hookVersionId) {
            newParams.versionId = hookVersionId.toString();
        }

        // Only update if something changed
        const stepChanged = currentStep.toString() !== currentStepParam;
        const versionChanged = hookVersionId?.toString() !== currentVersionParam;

        if (stepChanged || versionChanged) {
            setSearchParams(newParams, { replace: true });
        }
    }, [currentStep, hookVersionId, searchParams, setSearchParams]);

    // Get step data for saving
    const getStepData = useCallback((step: number): Record<string, any> => {
        switch (step) {
            case 1:
                return selectedDataSource ? { data_source_id: selectedDataSource.id } : {};
            case 2: {
                // Use consistent selected_schema format for both file and database
                // Format: { table_name: string[] }
                let schemaSelection: Record<string, string[]>;
                if (dataSourceType === 'file') {
                    // For files, wrap columns in object with table name
                    const tableName = fileUploadResult?.table_name || selectedDataSource?.duckdb_table_name || 'data';
                    schemaSelection = { [tableName]: selectedFileColumns };
                } else {
                    schemaSelection = selectedSchema;
                }
                return {
                    selected_columns: schemaSelection,
                };
            }
            case 3:
                return {
                    data_dictionary: dataDictionary ? { content: dataDictionary } : { content: '' },
                };
            case 4:
                return {
                    llm_config: advancedSettings.llm,
                    embedding_config: advancedSettings.embedding,
                    chunking_config: advancedSettings.chunking,
                    rag_config: advancedSettings.retriever,
                    // Model IDs from AI Registry
                    embeddingModelId: advancedSettings.embeddingModelId,
                    llmModelId: advancedSettings.llmModelId,
                    rerankerModelId: advancedSettings.rerankerModelId,
                };
            case 5:
                return {
                    system_prompt: draftPrompt,
                    example_questions: exampleQuestions,
                };
            case 6:
                return {
                    embedding_path: advancedSettings.embedding?.vectorDbName,
                };
            default:
                return {};
        }
    }, [selectedDataSource, dataSourceType, selectedFileColumns, selectedSchema, dataDictionary, advancedSettings, draftPrompt, exampleQuestions, fileUploadResult]);

    const handleNext = async () => {
        if (currentStep === 1) {
            if (!selectedDataSource) {
                setError("Please select a data source.");
                return;
            }

            // Create new draft when starting (if no draft was loaded on page init)
            if (!draft && agent) {
                const newDraft = await createNewDraft(agent.id, selectedDataSource.id);
                if (!newDraft) {
                    setError(draftError || "Failed to create draft config");
                    return;
                }
                setHasDraft(true);
            } else if (draft) {
                // Save step 1 data if we have a draft
                const stepData = getStepData(1);
                await saveStep(1, stepData);
            }
        } else if (draft) {
            // Save current step data before moving to next
            const stepData = getStepData(currentStep);
            await saveStep(currentStep, stepData);
        }

        if (currentStep === 2 && dataSourceType === 'database') {
            // For databases, schema selection is temporarily skipped
            // Just proceed to next step
        }
        if (currentStep === 2 && dataSourceType === 'file' && selectedFileColumns.length === 0) {
            setError("Please select at least one column.");
            return;
        }
        setError(null);
        if (currentStep < 6) setCurrentStep(currentStep + 1);
    };

    const handleBack = () => {
        if (currentStep > 1) setCurrentStep(currentStep - 1);
    };

    const handleGenerate = async () => {
        if (!agent || !hookVersionId) {
            setError('No agent or version ID available. Please complete earlier steps first.');
            return;
        }

        setGenerating(true);
        setError(null);
        try {
            // Save all relevant steps before generating to ensure DB has latest data
            // This handles the case where user made changes in previous steps but didn't click "Next"
            if (draft) {
                await saveStep(2, getStepData(2)); // Schema selection
                await saveStep(3, getStepData(3)); // Data dictionary
                await saveStep(4, getStepData(4)); // Advanced settings
            }

            // Generate prompt using endpoint that reads from saved DB data
            const result = await generatePrompt(agent.id, hookVersionId);
            setDraftPrompt(result.draft_prompt);
            if (result.reasoning) setReasoning(result.reasoning);
            if (result.example_questions) setExampleQuestions(result.example_questions);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setGenerating(false);
        }
    };

    const handlePublish = async () => {
        if (!draftPrompt.trim() || !agent) return;
        setError(null);

        try {
            // Use the new step-based publish API
            const published = await publish(draftPrompt, exampleQuestions);

            if (published) {
                setSuccessMessage(`Configuration published successfully!`);
                setCurrentStep(6); // Move to Summary
            } else {
                setError(draftError || 'Failed to publish configuration');
            }
        } catch (err) {
            setError(handleApiError(err));
        }
    };

    const handleStartEmbedding = async (incremental: boolean = false) => {
        if (!agent) return;
        try {
            // Use draft config id directly
            const configId = draft?.id;
            if (!configId) {
                showError('Error', 'No configuration found to embed.');
                return;
            }

            // Only send config_id and incremental - backend gets all settings from agent_config table
            const result = await startEmbeddingJob({
                config_id: configId,
                incremental: incremental,
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

    if (isAuthLoading || isLoadingAgent || isDraftLoading) {
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
                                    {hasDraft && (
                                        <span className="ml-2 text-xs font-normal text-blue-600 bg-blue-100 px-2 py-0.5 rounded">
                                            Draft
                                        </span>
                                    )}
                                </h1>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                    {isSaving && (
                                        <span className="text-xs text-gray-500 flex items-center gap-1">
                                            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                            </svg>
                                            Saving...
                                        </span>
                                    )}
                                    <span className="text-xs sm:text-sm text-gray-500">Step {currentStep} of 6</span>
                                </div>
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
                                    onFileColumnsInit={setSelectedFileColumns}
                                    selectedDataSource={selectedDataSource}
                                    setSelectedDataSource={setSelectedDataSource}
                                    isLocked={isDataSourceLocked}
                                />
                            )}

                            {currentStep === 2 && (
                                <SchemaSelectionStep
                                    dataSourceType={dataSourceType}
                                    connectionId={connectionId}
                                    setSelectedSchema={setSelectedSchema}
                                    initialSchema={selectedSchema}
                                    fileUploadResult={fileUploadResult}
                                    reasoning={reasoning}
                                    onFileColumnsChange={setSelectedFileColumns}
                                    selectedFileColumns={selectedFileColumns}
                                    selectedDataSource={selectedDataSource}
                                    onSchemaFetch={setFullSchema}
                                />
                            )}

                            {currentStep === 3 && (
                                <DictionaryStep
                                    dataSourceType={dataSourceType}
                                    dataDictionary={dataDictionary}
                                    setDataDictionary={setDataDictionary}
                                    fileUploadResult={fileUploadResult}
                                    schema={fullSchema}
                                    selectedSchema={selectedSchema}
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
                                    onGeneratePrompt={handleGenerate}
                                    isGenerating={generating}
                                    agent={agent}
                                    dataDictionary={dataDictionary}
                                    schema={fullSchema}
                                    selectedSchema={selectedSchema}
                                    advancedSettings={advancedSettings}
                                    dataSourceType={dataSourceType}
                                />
                            )}

                            {currentStep === 6 && (
                                <SummaryStep
                                    configId={draft?.id}
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
                            {currentStep === 5 ? (
                                // Step 5: Show Publish button only when prompt exists
                                draftPrompt ? (
                                    canPublish ? (
                                        <button
                                            onClick={handlePublish}
                                            disabled={isPublishing}
                                            className="w-full sm:w-auto px-4 sm:px-6 py-2 bg-green-600 text-white rounded-md font-medium text-sm sm:text-base hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                                        >
                                            {isPublishing ? (
                                                <>
                                                    <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                    </svg>
                                                    Publishing...
                                                </>
                                            ) : (
                                                <>
                                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                    </svg>
                                                    Publish
                                                </>
                                            )}
                                        </button>
                                    ) : (
                                        <div className="text-gray-500 italic text-xs sm:text-sm border border-gray-200 rounded px-3 sm:px-4 py-2 bg-gray-50 text-center">
                                            Publish restricted
                                        </div>
                                    )
                                ) : (
                                    // No prompt yet - show disabled placeholder (actual button is in the step component)
                                    <div className="text-black-400">
                                        Generate a prompt to continue
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
                                    disabled={generating || isPublishing || (currentStep === 1 && !selectedDataSource)}
                                    className={`w-full sm:w-auto px-4 sm:px-6 py-2 rounded-md font-medium text-white text-sm sm:text-base transition-colors duration-200 flex items-center justify-center
                                            ${generating || isPublishing || (currentStep === 1 && !selectedDataSource) ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
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
