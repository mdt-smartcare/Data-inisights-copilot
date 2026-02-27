import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { generateSystemPrompt, publishSystemPrompt, getPromptHistory, getActiveConfigMetadata, handleApiError, startEmbeddingJob, rollbackToVersion, listEmbeddingJobs } from '../services/api';
import type { IngestionResponse } from '../services/api';
import ConnectionManager from '../components/ConnectionManager';
import SchemaSelector from '../components/SchemaSelector';
import DictionaryUploader from '../components/DictionaryUploader';
import FileUploadSource from '../components/FileUploadSource';
import { DocumentPreview } from '../components/config/DocumentPreview';
import PromptEditor from '../components/PromptEditor';
import PromptHistory from '../components/PromptHistory';
import ConfigSummary from '../components/ConfigSummary';
import AdvancedSettings from '../components/AdvancedSettings';
import ObservabilityPanel from '../components/ObservabilityPanel';
import Alert from '../components/Alert';
import EmbeddingProgress from '../components/EmbeddingProgress';

import { ChatHeader } from '../components/chat';
import ScheduleSelector from '../components/ScheduleSelector';
import AgentsTab from '../components/config/AgentsTab'; // Import the new AgentsTab
import AgentUsersTab from '../components/config/AgentUsersTab';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import type { Agent } from '../types/agent';
import { canEditPrompt, canManageConnections, canPublishPrompt } from '../utils/permissions';
import { ArrowLeftIcon, Cog6ToothIcon, CheckCircleIcon, CommandLineIcon, AdjustmentsVerticalIcon, ArrowPathRoundedSquareIcon, UserGroupIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { MessageList, ChatInput } from '../components/chat';
import { chatService } from '../services/chatService';
import type { Message } from '../types';
import EmbeddingSettingsModal from '../components/EmbeddingSettingsModal';
import type { EmbeddingJobCreate } from '../types/rag';

const steps = [
    { id: 0, name: 'Dashboard' },
    { id: 1, name: 'Data Source' },
    { id: 2, name: 'Select Schema' },
    { id: 3, name: 'Data Dictionary' },
    { id: 4, name: 'Advanced Settings' },
    { id: 5, name: 'Review & Publish' },
    { id: 6, name: 'Summary' }
];

const ConfigPage: React.FC = () => {
    const { user, isLoading } = useAuth();
    const { success: showSuccess, error: showError } = useToast();
    const canEdit = canEditPrompt(user);
    const canPublish = canPublishPrompt(user);

    // Agent Selection State
    const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
    const lastProcessedAgentId = useRef<string | null>(null);

    const [searchParams, setSearchParams] = useSearchParams();
    const initialStep = searchParams.get('step') ? parseInt(searchParams.get('step')!) : 1;
    const [currentStep, setCurrentStep] = useState(initialStep);
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [connectionId, setConnectionId] = useState<number | null>(null);
    const [connectionName, setConnectionName] = useState<string>(''); // Added for naming
    const [selectedSchema, setSelectedSchema] = useState<Record<string, string[]>>({});
    const [dataDictionary, setDataDictionary] = useState('');

    // Vector DB Status State
    const [vectorDbStatus, setVectorDbStatus] = useState<{
        name: string;
        exists: boolean;
        total_documents_indexed: number;
        total_vectors: number;
        last_updated_at: string | null;
        embedding_model: string | null;
        llm: string | null;
        last_full_run: string | null;
        last_incremental_run: string | null;
        version: string;
        diagnostics: Array<{ level: string; message: string }>;
    } | null>(null);

    // Data source type: 'database' or 'file'
    const [dataSourceType, setDataSourceType] = useState<'database' | 'file'>('database');
    const [fileUploadResult, setFileUploadResult] = useState<IngestionResponse | null>(null);
    const [reasoning, setReasoning] = useState<Record<string, string>>({});
    const [exampleQuestions, setExampleQuestions] = useState<string[]>([]);
    const [draftPrompt, setDraftPrompt] = useState('');
    const [history, setHistory] = useState<any[]>([]);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [showHistory, _setShowHistory] = useState(false);
    const [showClearConfirm, setShowClearConfirm] = useState(false);
    const [replaceConfirm, setReplaceConfirm] = useState<{ show: boolean; version: any | null }>({ show: false, version: null });

    // Advanced Settings State
    const [advancedSettings, setAdvancedSettings] = useState({
        embedding: {
            model: 'BAAI/bge-m3'
        },
        llm: {
            temperature: 0.0,
            maxTokens: 4096
        },
        chunking: {
            parentChunkSize: 800,
            parentChunkOverlap: 150,
            childChunkSize: 200,
            childChunkOverlap: 50
        },
        retriever: {
            topKInitial: 50,
            topKFinal: 10,
            hybridWeights: [0.75, 0.25] as [number, number],
            rerankEnabled: true,
            rerankerModel: 'BAAI/bge-reranker-base'
        }
    });

    // Config Metadata for Dashboard
    const [activeConfig, setActiveConfig] = useState<any>(null);

    // Status
    const [generating, setGenerating] = useState(false);
    const [publishing, setPublishing] = useState(false);

    // Sandbox State
    const [sandboxMessages, setSandboxMessages] = useState<Message[]>([]);
    const [isSandboxTyping, setIsSandboxTyping] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [compareVersions, setCompareVersions] = useState<{ v1: any; v2: any } | null>(null);
    const [isRollingBack, setIsRollingBack] = useState(false);

    // Dashboard Tab State
    const [dashboardTab, setDashboardTab] = useState('overview');

    // Embedding Settings Modal State
    const [showEmbeddingSettings, setShowEmbeddingSettings] = useState(false);

    // Initial Load - moved into effect
    // Wait for agent selection
    useEffect(() => {
        if (!isLoading && selectedAgent) {
            loadDashboard();
        }
    }, [isLoading, selectedAgent]);

    // Sync state to window for API use (temporary solution for simple passing)
    useEffect(() => {
        (window as any).__config_connectionId = connectionId;
        (window as any).__config_schema = selectedSchema;
        (window as any).__config_dictionary = dataDictionary;
    }, [connectionId, selectedSchema, dataDictionary]);

    // Load history when entering step 4 or dashboard
    useEffect(() => {
        if ((currentStep === 4 || currentStep === 0) && selectedAgent) {
            loadHistory();
        }
    }, [currentStep, selectedAgent]);

    // Handle URL changes and Auto-selection
    useEffect(() => {
        if (isLoading) return;

        // Fetch dynamic system settings for defaults to prevent mismatched configs
        const fetchDefaults = async () => {
            try {
                const { getSystemSettings } = await import('../services/api');
                const [embSettings, ragSettings, llmSettings] = await Promise.all([
                    getSystemSettings('embedding').catch(() => null),
                    getSystemSettings('rag').catch(() => null),
                    getSystemSettings('llm').catch(() => null)
                ]);

                setAdvancedSettings(prev => {
                    const next = { ...prev };
                    if (embSettings && embSettings.model_name) {
                        next.embedding.model = embSettings.model_name;
                    }
                    if (ragSettings) {
                        if (ragSettings.chunk_size) next.chunking.parentChunkSize = ragSettings.chunk_size;
                        if (ragSettings.chunk_overlap) next.chunking.parentChunkOverlap = ragSettings.chunk_overlap;
                        if (ragSettings.top_k_initial) next.retriever.topKInitial = ragSettings.top_k_initial;
                        if (ragSettings.top_k_final) next.retriever.topKFinal = ragSettings.top_k_final;
                        if (ragSettings.hybrid_weights) next.retriever.hybridWeights = ragSettings.hybrid_weights;
                        if (ragSettings.rerank_enabled !== undefined) next.retriever.rerankEnabled = ragSettings.rerank_enabled;
                        if (ragSettings.reranker_model) next.retriever.rerankerModel = ragSettings.reranker_model;
                    }
                    if (llmSettings) {
                        if (llmSettings.temperature !== undefined) next.llm.temperature = llmSettings.temperature;
                        if (llmSettings.max_tokens) next.llm.maxTokens = llmSettings.max_tokens;
                    }
                    return next;
                });
            } catch (err) {
                console.warn("Failed to load backend defaults", err);
            }
        };

        const syncFromUrl = async () => {
            // Sync / Auto-select Agent
            const agentIdParam = searchParams.get('agent_id');
            const currentAgentId = selectedAgent ? selectedAgent.id.toString() : null;

            if (agentIdParam && agentIdParam !== lastProcessedAgentId.current && agentIdParam !== currentAgentId) {
                lastProcessedAgentId.current = agentIdParam;
                try {
                    const { getAgents } = await import('../services/api');
                    const agentList = await getAgents();

                    const agent = agentList.find(a => a.id === parseInt(agentIdParam));
                    if (agent) setSelectedAgent(agent);
                } catch (e) {
                    console.error("Failed to auto-select agent", e);
                }
            }
        };

        fetchDefaults();
        syncFromUrl();
    }, [isLoading, searchParams, selectedAgent]);

    // Sync state TO URL
    useEffect(() => {
        // Only update if changes detected
        const currentStepParam = searchParams.get('step');
        const currentAgentParam = searchParams.get('agent_id');

        const stepChanged = currentStep.toString() !== currentStepParam;
        const agentChanged = (selectedAgent ? selectedAgent.id.toString() : null) !== currentAgentParam;

        if (stepChanged || agentChanged) {
            const newParams: any = { step: currentStep.toString() };
            if (selectedAgent) {
                newParams.agent_id = selectedAgent.id.toString();
            }
            // Keep lastProcessedAgentId in sync with the fact that we've processed it out
            lastProcessedAgentId.current = selectedAgent ? selectedAgent.id.toString() : null;
            setSearchParams(newParams, { replace: true });
        }
    }, [currentStep, selectedAgent, searchParams, setSearchParams]);

    const loadDashboard = async () => {
        if (!selectedAgent) return;
        try {
            const config = await getActiveConfigMetadata(selectedAgent.id);
            if (config) {
                setActiveConfig(config);
                // Pre-fill state
                if (config.connection_id) {
                    setConnectionId(config.connection_id);
                    // Also fetch name for UI consistency
                    import('../services/api').then(api => {
                        api.getConnections().then(conns => {
                            const c = conns.find(x => x.id === config.connection_id);
                            if (c) setConnectionName(c.name);
                        });
                    });
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
                        setReasoning(JSON.parse(config.reasoning));
                    } catch (e) {
                        setReasoning(typeof config.reasoning === 'string' ? JSON.parse(config.reasoning) : config.reasoning);
                    }
                }

                // Pre-fill Advanced Settings
                const parseConf = (c: any) => c ? (typeof c === 'string' ? JSON.parse(c) : c) : null;
                const newSettings = { ...advancedSettings };
                const emb = parseConf(config.embedding_config);
                const llm = parseConf(config.llm_config);
                const chunk = parseConf(config.chunking_config);
                const ret = parseConf(config.retriever_config);

                if (emb) newSettings.embedding = { ...newSettings.embedding, ...emb };
                if (llm) newSettings.llm = { ...newSettings.llm, ...llm };
                if (chunk) newSettings.chunking = { ...newSettings.chunking, ...chunk };
                if (ret) newSettings.retriever = { ...newSettings.retriever, ...ret };
                setAdvancedSettings(newSettings);

                // Fetch Vector DB Status if possible
                try {
                    const embConf = config.embedding_config ? JSON.parse(config.embedding_config) : {};
                    const vDbName = embConf.vectorDbName || (config.data_source_type === 'database' && config.connection_id ? `db_connection_${config.connection_id}_data` : 'default_vector_db');
                    if (vDbName) {
                        import('../services/api').then(api => {
                            api.getVectorDbStatus(vDbName).then(status => {
                                setVectorDbStatus(status);
                            }).catch(err => {
                                console.log("Vector DB not found or error:", err);
                                setVectorDbStatus(null);
                            });
                        });
                    }
                } catch (e) {
                    console.log("Could not load Vector DB status");
                }

                // If we have config, default to Dashboard (Step 0)
                setCurrentStep(0);

                // Fetch any active embedding jobs for this config to restore progress UI if needed
                try {
                    const jobs = await listEmbeddingJobs({
                        config_id: config.id || config.prompt_id,
                        limit: 1
                    });
                    if (jobs.length > 0) {
                        const latestJob = jobs[0];
                        const activeStatuses = ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING'];
                        if (activeStatuses.includes(latestJob.status)) {
                            console.log("Restoring active embedding job:", latestJob.job_id);
                            setEmbeddingJobId(latestJob.job_id);
                        }
                    }
                } catch (jobErr) {
                    console.error("Failed to fetch active jobs", jobErr);
                }
            } else {
                setCurrentStep(1);
            }
            // Load history for total versions count
            loadHistory();
        } catch (e) {
            console.error("Failed to load active config", e);
            setCurrentStep(1);
        }
    };

    const handleSandboxSend = async (content: string) => {
        if (!selectedAgent) return;

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content,
            timestamp: new Date()
        };

        setSandboxMessages(prev => [...prev, userMsg]);
        setIsSandboxTyping(true);

        try {
            const response = await chatService.sendMessage({
                query: content,
                agent_id: selectedAgent.id,
                session_id: 'sandbox-' + selectedAgent.id
            });

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: response.answer,
                timestamp: new Date(response.timestamp),
                sources: response.sources,
                sqlQuery: response.sql_query,
                chartData: response.chart_data,
                traceId: response.trace_id,
                processingTime: response.processing_time
            };
            setSandboxMessages(prev => [...prev, aiMsg]);
        } catch (err: any) {
            console.error("Sandbox chat error", err);
            const errorMsg: Message = {
                id: Date.now().toString(),
                role: 'assistant',
                content: `Error: ${err.message || 'Failed to get response from agent'}`,
                timestamp: new Date()
            };
            setSandboxMessages(prev => [...prev, errorMsg]);
        } finally {
            setIsSandboxTyping(false);
        }
    };

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
        if (currentStep > 0) setCurrentStep(currentStep - 1);
    };

    const handleFileExtractionComplete = (result: IngestionResponse) => {
        setFileUploadResult(result);
    };

    const handleStartNew = async () => {
        // Reset state for fresh config
        setConnectionId(null);
        setSelectedSchema({});
        setDataDictionary('');
        setDraftPrompt('');
        setDataSourceType('database');
        setFileUploadResult(null);
        setCurrentStep(1);

        // Re-fetch backend defaults
        try {
            const { getSystemSettings } = await import('../services/api');
            const [embSettings, ragSettings, llmSettings] = await Promise.all([
                getSystemSettings('embedding').catch(() => null),
                getSystemSettings('rag').catch(() => null),
                getSystemSettings('llm').catch(() => null)
            ]);

            setAdvancedSettings(prev => {
                const next = { ...prev };
                if (embSettings && embSettings.model_name) next.embedding.model = embSettings.model_name;
                if (ragSettings) {
                    if (ragSettings.chunk_size) next.chunking.parentChunkSize = ragSettings.chunk_size;
                    if (ragSettings.chunk_overlap) next.chunking.parentChunkOverlap = ragSettings.chunk_overlap;
                }
                if (llmSettings) {
                    if (llmSettings.temperature !== undefined) next.llm.temperature = llmSettings.temperature;
                    if (llmSettings.max_tokens) next.llm.maxTokens = llmSettings.max_tokens;
                }
                return next;
            });
        } catch (err) {
            console.warn("Failed to reload backend defaults", err);
        }
    };

    const handleEditCurrent = () => {
        // State is already pre-filled from loadDashboard
        setCurrentStep(1);
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
            setCurrentStep(5); // Move to Review & Publish
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setGenerating(false);
        }
    };

    const handlePublish = async () => {
        if (!draftPrompt.trim() || !selectedAgent) return;
        setPublishing(true);
        setError(null);

        // Derive vector db name if missing to ensure multi-tenant isolation
        const finalEmbeddingConfig = { ...advancedSettings.embedding } as any;
        if (!finalEmbeddingConfig.vectorDbName) {
            // Try to use a descriptive name first
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
                // Absolute fallback to agent ID
                finalEmbeddingConfig.vectorDbName = `agent_${selectedAgent.id}_data`;
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
                selectedAgent.id,
                dataSourceType,
                fileUploadResult ? JSON.stringify(fileUploadResult.documents) : undefined,
                fileUploadResult?.file_name,
                fileUploadResult?.file_type
            );
            setSuccessMessage(`Prompt published successfully! Version: ${result.version}`);
            loadHistory(); // Refresh history
            loadDashboard(); // Refresh config metadata
            setCurrentStep(6); // Move to Summary
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setPublishing(false);
        }
    };
    const handleRollback = async (version: any) => {
        if (!selectedAgent) return;
        if (!window.confirm(`Are you sure you want to rollback ${selectedAgent.name} to Version ${version.version}? This will make it the active production configuration.`)) {
            return;
        }

        setIsRollingBack(true);
        try {
            await rollbackToVersion(version.id);
            showSuccess('Rollback Successful', `Agent ${selectedAgent.name} is now running Version ${version.version}`);
            await loadDashboard();
            await loadHistory();
        } catch (err) {
            showError('Rollback Failed', handleApiError(err));
        } finally {
            setIsRollingBack(false);
        }
    };

    const handleCompare = (v1: any, v2: any) => {
        setCompareVersions({ v1, v2 });
    };

    const handleCloseCompare = () => {
        setCompareVersions(null);
    };

    const loadHistory = async () => {
        if (!selectedAgent) return;
        try {
            const data = await getPromptHistory(selectedAgent.id);
            setHistory(data);
        } catch (err) {
            console.error("Failed to load history", err);
        }
    };

    // Handler for basic embedding (quick action buttons)
    const handleStartEmbedding = async (incremental: boolean = true) => {
        const configId = activeConfig?.id || activeConfig?.prompt_id;
        if (!configId) return;

        try {
            const result = await startEmbeddingJob({
                config_id: configId,
                incremental: incremental,
                // Use chunking settings from advancedSettings
                chunking: {
                    parent_chunk_size: advancedSettings.chunking.parentChunkSize,
                    parent_chunk_overlap: advancedSettings.chunking.parentChunkOverlap,
                    child_chunk_size: advancedSettings.chunking.childChunkSize,
                    child_chunk_overlap: advancedSettings.chunking.childChunkOverlap,
                }
            });
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };

    // Handler for advanced embedding settings modal
    const handleStartEmbeddingWithSettings = async (
        settings: {
            batch_size: number;
            max_concurrent: number;
            chunking: {
                parent_chunk_size: number;
                parent_chunk_overlap: number;
                child_chunk_size: number;
                child_chunk_overlap: number;
            };
            parallelization: {
                num_workers?: number;
                chunking_batch_size?: number;
                delta_check_batch_size: number;
            };
            max_consecutive_failures: number;
            retry_attempts: number;
        },
        incremental: boolean
    ) => {
        const configId = activeConfig?.id || activeConfig?.prompt_id;
        if (!configId) return;

        try {
            const jobParams: EmbeddingJobCreate = {
                config_id: configId,
                batch_size: settings.batch_size,
                max_concurrent: settings.max_concurrent,
                incremental: incremental,
                chunking: settings.chunking,
                parallelization: settings.parallelization,
                max_consecutive_failures: settings.max_consecutive_failures,
                retry_attempts: settings.retry_attempts,
            };

            const result = await startEmbeddingJob(jobParams);
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading user profile...</span>
                </div>
            </div>
        );
    }

    // Agent Selection View
    if (!selectedAgent) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 overflow-hidden">
                    <AgentsTab onSelectAgent={setSelectedAgent} />
                </div>
            </div>
        );
    }

    // Configuration View
    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="max-w-7xl mx-auto py-8 px-4 flex flex-col">
                    {/* Header & Steps - Hide steps on Dashboard */}
                    {currentStep > 0 && (
                        <div className="mb-8">
                            <div className="flex items-center gap-4 mb-6">
                                <button
                                    onClick={() => setSelectedAgent(null)}
                                    className="p-2 -ml-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
                                    title="Back to Agents"
                                >
                                    <ArrowLeftIcon className="w-6 h-6" />
                                </button>
                                <div className="flex-1 flex justify-between items-center">
                                    <div>
                                        <h1 className="text-2xl font-bold text-gray-900">
                                            Configure {selectedAgent.name} Agent
                                        </h1>
                                    </div>
                                    <span className="text-sm text-gray-500">Step {currentStep} of 5</span>
                                </div>
                            </div>


                            {/* Progress Bar */}
                            <div className="w-full bg-gray-200 rounded-full h-2 mb-6">
                                <div
                                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                    style={{ width: `${(currentStep / 5) * 100}%` }}
                                ></div>
                            </div>

                            {/* Step Indicators */}
                            <div className="flex justify-between relative">
                                {steps.filter(s => s.id > 0).map((step) => (
                                    <div key={step.id} className="flex flex-col items-center z-10">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors duration-200 
                                    ${currentStep >= step.id ? 'bg-blue-600 text-white' : 'bg-white border-2 border-gray-300 text-gray-400'}`}>
                                            {step.id}
                                        </div>
                                        <span className={`text-xs mt-2 font-medium ${currentStep >= step.id ? 'text-blue-600' : 'text-gray-400'}`}>
                                            {step.name}
                                        </span>
                                    </div>
                                ))}
                                {/* Connecting Line */}
                                <div className="absolute top-4 left-0 w-full h-0.5 bg-gray-200 -z-0"></div>
                            </div>
                        </div>
                    )}

                    {/* Content Area */}
                    <div className={`flex-1 min-h-0 bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden ${currentStep === 0 ? 'bg-gray-50 border-none shadow-none' : ''}`}>
                        {currentStep === 0 ? (
                            // DASHBOARD VIEW
                            <div className="h-full flex flex-col overflow-y-auto">
                                <header className="bg-white px-8 pt-8 pb-4 border-b border-gray-200">
                                    <div className="flex justify-between items-center mb-6">
                                        <div className="flex items-center gap-4">
                                            <button
                                                onClick={() => setSelectedAgent(null)}
                                                className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
                                                title="Back to Agents"
                                            >
                                                <ArrowLeftIcon className="w-6 h-6" />
                                            </button>
                                            <div>
                                                <h1 className="text-2xl font-bold text-gray-900">{selectedAgent.name}</h1>
                                                <p className="text-sm text-gray-500">Agent Configuration & Insights Dashboard</p>
                                            </div>
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={handleEditCurrent}
                                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm transition-all focus:ring-2 focus:ring-blue-200"
                                            >
                                                {canEdit ? 'Edit Active Config' : 'View Configuration'}
                                            </button>
                                        </div>
                                    </div>

                                    {/* Tabs */}
                                    <div className="flex gap-8 border-t border-gray-100 pt-2">
                                        {[
                                            { id: 'overview', name: 'Overview', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg> },
                                            { id: 'knowledge', name: 'Vector DB', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg> },
                                            { id: 'sandbox', name: 'Sandbox', icon: (props: any) => <CommandLineIcon {...props} /> },
                                            { id: 'specs', name: 'Settings & Specs', icon: (props: any) => <AdjustmentsVerticalIcon {...props} /> },
                                            { id: 'users', name: 'Users', icon: (props: any) => <UserGroupIcon {...props} /> },
                                            { id: 'monitoring', name: 'Monitoring', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg> },
                                            { id: 'history', name: 'System Prompt History', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> }
                                        ].map(tab => (
                                            <button
                                                key={tab.id}
                                                onClick={() => setDashboardTab(tab.id)}
                                                className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-all
                                                    ${dashboardTab === tab.id
                                                        ? 'border-blue-600 text-blue-600'
                                                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                                    }`}
                                            >
                                                <tab.icon className={`w-5 h-5 ${dashboardTab === tab.id ? 'text-blue-600' : 'text-gray-400'}`} />
                                                {tab.name}
                                            </button>
                                        ))}
                                    </div>
                                </header>

                                <div className="p-8 pb-16">
                                    {activeConfig ? (
                                        <div className="flex-1 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                            {dashboardTab === 'overview' && (
                                                <div className="space-y-8">
                                                    <ConfigSummary
                                                        connectionId={activeConfig.connection_id}
                                                        connectionName={connectionName}
                                                        dataSourceType={activeConfig.data_source_type as any || 'database'}
                                                        schema={activeConfig.schema_selection ? JSON.parse(activeConfig.schema_selection) : {}}
                                                        dataDictionary={activeConfig.data_dictionary || ''}
                                                        activePromptVersion={activeConfig.version}
                                                        totalPromptVersions={history.length}
                                                        lastUpdatedBy={activeConfig.created_by_username}
                                                        settings={advancedSettings}
                                                    />

                                                    {/* Quick Stats Grid */}
                                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                                                            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Agent Status</h3>
                                                            <div className="flex items-center gap-2">
                                                                <span className="flex h-3 w-3 rounded-full bg-green-500"></span>
                                                                <span className="text-xl font-bold text-gray-900">Active</span>
                                                            </div>
                                                        </div>
                                                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                                                            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Total Versions</h3>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xl font-bold text-gray-900">{history.length}</span>
                                                                <span className="text-xs text-gray-400 font-medium">Published Prompts</span>
                                                            </div>
                                                        </div>
                                                        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                                                            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Knowledge Freshness</h3>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xl font-bold text-gray-900">
                                                                    {vectorDbStatus?.last_updated_at ? 'Synced' : 'Not Run'}
                                                                </span>
                                                                <span className="text-xs text-gray-400 font-medium">Vector DB</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {dashboardTab === 'knowledge' && (
                                                <div className="space-y-8">
                                                    {/* Embedding Section */}
                                                    <div>
                                                        <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                                                            <svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                                                            Knowledge Base Management
                                                        </h2>
                                                        {embeddingJobId ? (
                                                            <EmbeddingProgress
                                                                jobId={embeddingJobId}
                                                                onComplete={() => {
                                                                    showSuccess('Embeddings Generated', 'Knowledge base updated successfully');
                                                                    setEmbeddingJobId(null);
                                                                    if (activeConfig) {
                                                                        const embConf = activeConfig.embedding_config ? (typeof activeConfig.embedding_config === 'string' ? JSON.parse(activeConfig.embedding_config) : activeConfig.embedding_config) : {};
                                                                        const vDbName = embConf.vectorDbName || (activeConfig.data_source_type === 'database' && activeConfig.connection_id ? `db_connection_${activeConfig.connection_id}_data` : 'default_vector_db');
                                                                        if (vDbName) {
                                                                            import('../services/api').then(api => {
                                                                                api.getVectorDbStatus(vDbName).then(status => setVectorDbStatus(status)).catch(err => console.log(err));
                                                                            });
                                                                        }
                                                                    }
                                                                }}
                                                                onError={(err) => showError('Embedding Failed', err)}
                                                                onCancel={() => {
                                                                    showError('Job Cancelled', 'Embedding generation cancelled');
                                                                    setEmbeddingJobId(null);
                                                                }}
                                                            />
                                                        ) : (
                                                            <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm transition-all hover:shadow-md">
                                                                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8">
                                                                    <div className="max-w-xl">
                                                                        <h3 className="text-lg font-semibold text-gray-900">Manage Knowledge Base</h3>
                                                                        <p className="text-gray-500 mt-2">
                                                                            Keep your agent's vector representations up-to-date with your latest data. Update manually or set an automatic sync schedule below.
                                                                        </p>
                                                                    </div>
                                                                    <div className="flex gap-3">
                                                                        <button
                                                                            onClick={() => handleStartEmbedding(true)}
                                                                            className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-semibold shadow-sm transition-all hover:scale-105 active:scale-95"
                                                                        >
                                                                            Update Knowledge
                                                                        </button>
                                                                        <button
                                                                            onClick={() => setShowEmbeddingSettings(true)}
                                                                            className="px-4 py-2.5 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-semibold transition-all flex items-center gap-2"
                                                                            title="Configure batch size, chunking, parallelization, and more"
                                                                        >
                                                                            <Cog6ToothIcon className="w-4 h-4" />
                                                                            Advanced
                                                                        </button>
                                                                        <button
                                                                            onClick={() => {
                                                                                if (window.confirm('Are you sure you want to rebuild the vector database? This will delete all existing knowledge and re-index everything from scratch. This may take a long time and consume LLM tokens.')) {
                                                                                    handleStartEmbedding(false);
                                                                                }
                                                                            }}
                                                                            className="px-6 py-2.5 bg-white border border-red-200 text-red-600 rounded-lg hover:bg-red-50 font-semibold transition-all hover:border-red-300"
                                                                        >
                                                                            Rebuild DB
                                                                        </button>
                                                                    </div>
                                                                </div>

                                                                {/* Vector DB Stats Card */}
                                                                {vectorDbStatus && (
                                                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8 border-t border-gray-100">
                                                                        <div className="p-4 bg-blue-50/50 rounded-xl border border-blue-100">
                                                                            <p className="text-xs text-blue-600 font-bold uppercase tracking-wider mb-2">Stored Documents</p>
                                                                            <div className="flex items-end gap-2">
                                                                                <p className="text-3xl font-bold text-gray-900">{vectorDbStatus.total_documents_indexed.toLocaleString()}</p>
                                                                                <p className="text-sm text-gray-500 font-medium mb-1">Items</p>
                                                                            </div>
                                                                        </div>

                                                                        <div className="p-4 bg-purple-50/50 rounded-xl border border-purple-100">
                                                                            <p className="text-xs text-purple-600 font-bold uppercase tracking-wider mb-2">Vector Embeddings</p>
                                                                            <div className="flex items-end gap-2">
                                                                                <p className="text-3xl font-bold text-gray-900">{vectorDbStatus.total_vectors.toLocaleString()}</p>
                                                                                <p className="text-sm text-gray-500 font-medium mb-1">Vectors</p>
                                                                            </div>
                                                                        </div>

                                                                        <div className="p-4 bg-green-50/50 rounded-xl border border-green-100">
                                                                            <p className="text-xs text-green-600 font-bold uppercase tracking-wider mb-2">Last Synchronized</p>
                                                                            <div className="flex items-center gap-2 mt-2">
                                                                                <CheckCircleIcon className="w-6 h-6 text-green-600" />
                                                                                <p className="text-base font-semibold text-gray-900">
                                                                                    {vectorDbStatus.last_updated_at
                                                                                        ? new Date(vectorDbStatus.last_updated_at + 'Z').toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
                                                                                        : 'Never run'}
                                                                                </p>
                                                                            </div>
                                                                        </div>

                                                                        {/* Enhanced Metadata Fields (T07) */}
                                                                        <div className="col-span-1 md:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-2">
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Embedding Model</p>
                                                                                <p className="text-sm font-medium text-gray-800 truncate" title={vectorDbStatus.embedding_model || 'N/A'}>
                                                                                    {vectorDbStatus.embedding_model || 'N/A'}
                                                                                </p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">LLM Model</p>
                                                                                <p className="text-sm font-medium text-gray-800">
                                                                                    {vectorDbStatus.llm || 'N/A'}
                                                                                </p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Last Full Sync</p>
                                                                                <p className="text-sm font-medium text-gray-800">
                                                                                    {vectorDbStatus.last_full_run ? new Date(vectorDbStatus.last_full_run + 'Z').toLocaleDateString() : 'N/A'}
                                                                                </p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-[10px] text-gray-500 font-bold uppercase mb-1">Version</p>
                                                                                <p className="text-sm font-medium text-gray-800">
                                                                                    {vectorDbStatus.version}
                                                                                </p>
                                                                            </div>
                                                                        </div>

                                                                        {/* Diagnostics Alert (T06) */}
                                                                        {vectorDbStatus.diagnostics && vectorDbStatus.diagnostics.length > 0 && (
                                                                            <div className="col-span-1 md:col-span-3 mt-4">
                                                                                <div className="p-4 bg-amber-50 rounded-xl border border-amber-100">
                                                                                    <div className="flex items-center gap-2 mb-2 text-amber-800">
                                                                                        <ExclamationTriangleIcon className="w-5 h-5" />
                                                                                        <span className="font-bold text-sm">System Diagnostics</span>
                                                                                    </div>
                                                                                    <ul className="space-y-1">
                                                                                        {vectorDbStatus.diagnostics.map((diag, i) => (
                                                                                            <li key={i} className={`text-sm ${diag.level === 'error' ? 'text-red-700' : 'text-amber-700'} flex items-start gap-2`}>
                                                                                                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                                                                                                {diag.message}
                                                                                            </li>
                                                                                        ))}
                                                                                    </ul>
                                                                                </div>
                                                                            </div>
                                                                        )}

                                                                        {(() => {
                                                                            const embConf = activeConfig?.embedding_config ? (typeof activeConfig.embedding_config === 'string' ? JSON.parse(activeConfig.embedding_config) : activeConfig.embedding_config) : {};
                                                                            const vDbName = embConf.vectorDbName || (activeConfig?.data_source_type === 'database' && activeConfig.connection_id ? `db_connection_${activeConfig.connection_id}_data` : 'default_vector_db');
                                                                            return vDbName ? (
                                                                                <div className="col-span-1 md:col-span-3 mt-4 pt-6 border-t border-gray-100">
                                                                                    <ScheduleSelector vectorDbName={vDbName} />
                                                                                </div>
                                                                            ) : null;
                                                                        })()}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>


                                                </div>
                                            )}

                                            {dashboardTab === 'sandbox' && (
                                                <div className="bg-white rounded-2xl border border-gray-200 shadow-xl overflow-hidden flex flex-col h-[700px] animate-in zoom-in-95 duration-300">
                                                    <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                                                        <div>
                                                            <h3 className="font-bold text-gray-900 flex items-center gap-2">
                                                                <CommandLineIcon className="w-5 h-5 text-indigo-600" />
                                                                Agent Sandbox
                                                            </h3>
                                                            <p className="text-xs text-gray-500">Test the current configuration in real-time</p>
                                                        </div>
                                                        <button
                                                            onClick={() => setSandboxMessages([])}
                                                            className="text-xs font-semibold text-gray-500 hover:text-red-600 transition-colors"
                                                        >
                                                            Clear Session
                                                        </button>
                                                    </div>
                                                    <div className="flex-1 overflow-hidden flex flex-col relative bg-gray-50/30">
                                                        <MessageList
                                                            messages={sandboxMessages}
                                                            isLoading={isSandboxTyping}
                                                            username={user?.username}
                                                            emptyStateProps={{
                                                                title: `Testing ${selectedAgent.name}`,
                                                                subtitle: 'Type a message to see how the agent responds with its current settings.',
                                                                suggestions: activeConfig.example_questions ? JSON.parse(activeConfig.example_questions) : [
                                                                    "What can you do?",
                                                                    "Show me the available data",
                                                                    "Summarize the recent records"
                                                                ]
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="p-4 bg-white border-t border-gray-100">
                                                        <ChatInput
                                                            onSendMessage={handleSandboxSend}
                                                            isDisabled={isSandboxTyping}
                                                            placeholder="Test the agent..."
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                            {dashboardTab === 'specs' && (
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
                                                                {(() => {
                                                                    const conf = activeConfig.llm_config ? (typeof activeConfig.llm_config === 'string' ? JSON.parse(activeConfig.llm_config) : activeConfig.llm_config) : {};
                                                                    return (
                                                                        <div className="grid grid-cols-2 gap-4">
                                                                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Model Name</p>
                                                                                <p className="text-sm font-mono font-bold text-gray-700">{conf.model || 'gpt-4o'}</p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Temperature</p>
                                                                                <p className="text-sm font-semibold text-gray-700">{conf.temperature ?? 0.0}</p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Max Tokens</p>
                                                                                <p className="text-sm font-semibold text-gray-700">{conf.maxTokens || 4096}</p>
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                })()}
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
                                                                {(() => {
                                                                    const emb = activeConfig.embedding_config ? (typeof activeConfig.embedding_config === 'string' ? JSON.parse(activeConfig.embedding_config) : activeConfig.embedding_config) : {};
                                                                    const chunk = activeConfig.chunking_config ? (typeof activeConfig.chunking_config === 'string' ? JSON.parse(activeConfig.chunking_config) : activeConfig.chunking_config) : {};
                                                                    return (
                                                                        <div className="grid grid-cols-2 gap-4">
                                                                            <div className="col-span-2 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Embedding Model</p>
                                                                                <p className="text-sm font-mono font-bold text-gray-700">{emb.model || 'BAAI/bge-m3'}</p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Parent Size</p>
                                                                                <p className="text-sm font-semibold text-gray-700">{chunk.parentChunkSize || 800} chars</p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Child Size</p>
                                                                                <p className="text-sm font-semibold text-gray-700">{chunk.childChunkSize || 200} chars</p>
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                })()}
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
                                                                {(() => {
                                                                    const ret = activeConfig.retriever_config ? (typeof activeConfig.retriever_config === 'string' ? JSON.parse(activeConfig.retriever_config) : activeConfig.retriever_config) : {};
                                                                    return (
                                                                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                                                            {ret.hybridWeights && (
                                                                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Semantic Weight</p>
                                                                                    <p className="text-sm font-bold text-purple-700">{(ret.hybridWeights[0] * 100).toFixed(0)}%</p>
                                                                                </div>
                                                                            )}
                                                                            {ret.hybridWeights && (
                                                                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                    <p className="text-xs font-bold text-gray-400 uppercase mb-1">Keyword Weight</p>
                                                                                    <p className="text-sm font-bold text-purple-700">{(ret.hybridWeights[1] * 100).toFixed(0)}%</p>
                                                                                </div>
                                                                            )}
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Top-K Final</p>
                                                                                <p className="text-sm font-bold text-gray-700">{ret.topKFinal || 10}</p>
                                                                            </div>
                                                                            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                                                <p className="text-xs font-bold text-gray-400 uppercase mb-1">Reranking</p>
                                                                                <p className={`text-sm font-bold ${ret.rerankEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                                                                                    {ret.rerankEnabled ? 'Enabled' : 'Disabled'}
                                                                                </p>
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                })()}
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {dashboardTab === 'monitoring' && (
                                                <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                                    <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                                                        <svg className="w-5 h-5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                                                        Agent Performance & Tracing
                                                    </h2>
                                                    <ObservabilityPanel />
                                                </div>
                                            )}

                                            {dashboardTab === 'history' && (
                                                <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                                    <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                                                        <svg className="w-5 h-5 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                        {<span>System Prompt History</span>}
                                                    </h2>
                                                    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                                                        <PromptHistory
                                                            history={history}
                                                            onRollback={handleRollback}
                                                            onCompare={handleCompare}
                                                        />
                                                    </div>

                                                    {/* Comparison Modal */}
                                                    {compareVersions && (
                                                        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
                                                            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                                                                <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                                                                    <div>
                                                                        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                                                            Configuration Comparison
                                                                        </h3>
                                                                        <p className="text-xs text-gray-500">Comparing Version {compareVersions.v1.version} with Version {compareVersions.v2.version}</p>
                                                                    </div>
                                                                    <button onClick={handleCloseCompare} className="p-2 hover:bg-white rounded-full transition-colors">
                                                                        <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                                                    </button>
                                                                </div>
                                                                <div className="flex-1 overflow-y-auto p-6 md:p-8">
                                                                    <div className="grid grid-cols-2 gap-8 h-full">
                                                                        {/* Version 1 */}
                                                                        <div className="space-y-6">
                                                                            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                                                                                <div className="flex items-center gap-3">
                                                                                    <span className="w-10 h-10 rounded-xl bg-gray-100 text-gray-700 flex items-center justify-center font-bold">V{compareVersions.v1.version}</span>
                                                                                    <div>
                                                                                        <p className="text-sm font-bold text-gray-900">Historical Version</p>
                                                                                        <p className="text-xs text-gray-500">{new Date(compareVersions.v1.created_at).toLocaleString()}</p>
                                                                                    </div>
                                                                                </div>
                                                                                <button
                                                                                    onClick={() => { handleRollback(compareVersions.v1); handleCloseCompare(); }}
                                                                                    disabled={isRollingBack}
                                                                                    className={`px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-colors flex items-center gap-2 ${isRollingBack ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                                                >
                                                                                    <ArrowPathRoundedSquareIcon className="w-4 h-4" />
                                                                                    {isRollingBack ? 'Rolling back...' : 'Rollback'}
                                                                                </button>
                                                                            </div>

                                                                            <section>
                                                                                <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">System Prompt</h4>
                                                                                <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 text-[11px] font-mono whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
                                                                                    {compareVersions.v1.prompt_text}
                                                                                </div>
                                                                            </section>

                                                                        </div>

                                                                        {/* Version 2 (Active) */}
                                                                        <div className="space-y-6">
                                                                            <div className="flex items-center justify-between pb-4 border-b border-blue-100">
                                                                                <div className="flex items-center gap-3">
                                                                                    <span className="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-bold">V{compareVersions.v2.version}</span>
                                                                                    <div>
                                                                                        <p className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
                                                                                            Active Version
                                                                                            <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                                                                        </p>
                                                                                        <p className="text-xs text-gray-500">{new Date(compareVersions.v2.created_at).toLocaleString()}</p>
                                                                                    </div>
                                                                                </div>
                                                                                <span className="px-4 py-2 bg-green-50 text-green-700 rounded-lg text-xs font-bold border border-green-100 flex items-center gap-2">
                                                                                    <CheckCircleIcon className="w-4 h-4" />
                                                                                    Active Production
                                                                                </span>
                                                                            </div>

                                                                            <section>
                                                                                <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">System Prompt</h4>
                                                                                <div className="bg-blue-50/30 p-4 rounded-xl border border-blue-100 text-[11px] font-mono whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
                                                                                    {compareVersions.v2.prompt_text}
                                                                                </div>
                                                                            </section>

                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div className="px-8 py-4 bg-gray-50 border-t border-gray-100 flex justify-end">
                                                                    <button onClick={handleCloseCompare} className="px-6 py-2 bg-white border border-gray-200 text-gray-700 rounded-xl text-sm font-bold shadow-sm hover:bg-gray-100 transition-all">
                                                                        Close Comparison
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {dashboardTab === 'users' && selectedAgent && (
                                                <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                                    <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                                                        <UserGroupIcon className="w-5 h-5 text-indigo-600" />
                                                        User Management
                                                    </h2>
                                                    <AgentUsersTab
                                                        agentId={selectedAgent.id}
                                                        agentName={selectedAgent.name}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    ) : dashboardTab === 'users' && selectedAgent ? (
                                        <div className="flex-1 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                                <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                                                    <UserGroupIcon className="w-5 h-5 text-indigo-600" />
                                                    User Management
                                                </h2>
                                                <AgentUsersTab
                                                    agentId={selectedAgent.id}
                                                    agentName={selectedAgent.name}
                                                />
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="min-h-[400px] flex flex-col items-center justify-center text-center p-12 bg-white rounded-2xl border-2 border-dashed border-gray-200 shadow-sm">
                                            <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mb-6">
                                                <Cog6ToothIcon className="w-10 h-10 text-blue-500" />
                                            </div>
                                            <h2 className="text-2xl font-bold text-gray-900 mb-3">No Active Configuration</h2>
                                            <p className="text-gray-500 max-w-sm mx-auto mb-8">
                                                This agent has not been configured yet. Start the setup wizard to connect a data source and define behavior.
                                            </p>
                                            <button
                                                onClick={handleStartNew}
                                                className="px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-bold shadow-lg shadow-blue-200 transition-all hover:-translate-y-1 active:translate-y-0"
                                            >
                                                Start Setup Wizard
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>

                        ) : (
                            <div className="p-6 h-full flex flex-col">
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
                                    <div className="max-w-2xl mx-auto">
                                        <h2 className="text-xl font-semibold mb-4">Connect Data Source</h2>
                                        <p className="text-gray-500 text-sm mb-4">
                                            Choose how you want to provide data to this agent.
                                        </p>

                                        {/* Data Source Toggle */}
                                        <div className="flex rounded-lg border border-gray-200 overflow-hidden mb-6">
                                            <button
                                                type="button"
                                                onClick={() => { setDataSourceType('database'); setFileUploadResult(null); }}
                                                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2
                                                    ${dataSourceType === 'database'
                                                        ? 'bg-blue-600 text-white'
                                                        : 'bg-white text-gray-600 hover:bg-gray-50'
                                                    }`}
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                                                </svg>
                                                Database
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => { setDataSourceType('file'); setConnectionId(null); }}
                                                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2
                                                    ${dataSourceType === 'file'
                                                        ? 'bg-blue-600 text-white'
                                                        : 'bg-white text-gray-600 hover:bg-gray-50'
                                                    }`}
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                                </svg>
                                                File Upload
                                            </button>
                                        </div>

                                        {/* Database Source */}
                                        {dataSourceType === 'database' && (
                                            <>
                                                <p className="text-gray-500 text-sm mb-4">
                                                    Choose the database you want to generate insights from.
                                                </p>
                                                <ConnectionManager
                                                    onSelect={(id, name) => {
                                                        setConnectionId(id);
                                                        setConnectionName(name || '');
                                                    }}
                                                    selectedId={connectionId}
                                                    readOnly={!canManageConnections(user)}
                                                />
                                            </>
                                        )}

                                        {/* File Upload Source */}
                                        {dataSourceType === 'file' && (
                                            <>
                                                <p className="text-gray-500 text-sm mb-4">
                                                    Upload a PDF, CSV, Excel, or JSON file to extract data from.
                                                </p>
                                                <FileUploadSource
                                                    onExtractionComplete={handleFileExtractionComplete}
                                                    disabled={!canEdit}
                                                />
                                            </>
                                        )}
                                    </div>
                                )}

                                {currentStep === 2 && dataSourceType === 'database' && connectionId && (
                                    <div className="max-w-4xl mx-auto">
                                        <h2 className="text-xl font-semibold mb-4">Select Tables</h2>
                                        <p className="text-gray-500 text-sm mb-6">
                                            Select which tables contain relevant data for analysis. The AI will only be aware of the tables you select.
                                        </p>
                                        <SchemaSelector
                                            connectionId={connectionId}
                                            onSelectionChange={setSelectedSchema}
                                            readOnly={!canEdit}
                                            reasoning={reasoning}
                                        />
                                    </div>
                                )}

                                {currentStep === 2 && dataSourceType === 'file' && fileUploadResult && (
                                    <DocumentPreview
                                        documents={fileUploadResult.documents}
                                        fileName={fileUploadResult.file_name}
                                        fileType={fileUploadResult.file_type}
                                        totalDocuments={fileUploadResult.total_documents}
                                    />
                                )}

                                {currentStep === 3 && (
                                    <div className="h-full flex flex-col">
                                        <h2 className="text-xl font-semibold mb-2">Add Data Dictionary / Context</h2>
                                        <p className="text-gray-500 text-sm mb-4">
                                            {dataSourceType === 'database'
                                                ? "Provide context to help the AI understand your data. Upload a file or paste definitions below."
                                                : "Provide any additional context or instructions the AI should know about these documents."}
                                        </p>

                                        {dataSourceType === 'file' && fileUploadResult && (
                                            <div className="mb-4">
                                                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                                                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Reference Documents</h3>
                                                    <div className="max-h-40 overflow-y-auto pr-2">
                                                        <DocumentPreview
                                                            documents={fileUploadResult.documents}
                                                            fileName={fileUploadResult.file_name}
                                                            fileType={fileUploadResult.file_type}
                                                            totalDocuments={fileUploadResult.total_documents}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        <div className="flex-1 flex flex-col min-h-0 border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
                                            {/* Toolbar */}
                                            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex justify-between items-center">
                                                <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                                    Context Editor
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    <DictionaryUploader
                                                        onUpload={(content) => setDataDictionary(prev => prev ? prev + "\n\n" + content : content)}
                                                        disabled={!canEdit}
                                                    />
                                                    {dataDictionary && canEdit && (
                                                        <button
                                                            type="button"
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                e.stopPropagation();
                                                                setShowClearConfirm(true);
                                                            }}
                                                            className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1 rounded hover:bg-red-50"
                                                        >
                                                            Clear
                                                        </button>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Editor Area */}
                                            <textarea
                                                className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none disabled:bg-gray-50 disabled:text-gray-500"
                                                placeholder="# Users Table\n- role: 'admin' | 'user'\n- status: 1=active, 0=inactive..."
                                                value={dataDictionary}
                                                onChange={(e) => setDataDictionary(e.target.value)}
                                                spellCheck={false}
                                                disabled={!canEdit}
                                            />
                                        </div>
                                    </div>
                                )}

                                {currentStep === 4 && (
                                    <div className="h-full flex flex-col">
                                        <AdvancedSettings
                                            settings={advancedSettings}
                                            onChange={setAdvancedSettings}
                                            readOnly={!canEdit}
                                            dataSourceName={dataSourceType === 'file' && fileUploadResult ? fileUploadResult.file_name.split('.')[0] : (connectionName || `db_connection_${connectionId || 'default'}`)}
                                        />
                                    </div>
                                )}

                                {currentStep === 5 && (
                                    <div className="h-full flex flex-col">
                                        <h2 className="text-xl font-semibold mb-4">Review & Configuration</h2>
                                        <div className="flex-1 flex gap-4 min-h-0">
                                            <div className="flex-1 min-h-0">
                                                <PromptEditor
                                                    value={draftPrompt}
                                                    onChange={setDraftPrompt}
                                                    readOnly={!canEdit}
                                                />
                                            </div>

                                            {showHistory && (
                                                <div className="w-64 min-w-[250px] h-full">
                                                    <PromptHistory
                                                        history={history}
                                                        onSelect={(item) => {
                                                            if (!draftPrompt.trim()) {
                                                                setDraftPrompt(item.prompt_text);
                                                            } else {
                                                                setReplaceConfirm({ show: true, version: item });
                                                            }
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </div>

                                        {/* Example Questions Preview */}
                                        {exampleQuestions.length > 0 && (
                                            <div className="mt-4 bg-gradient-to-r from-blue-50 to-indigo-50 p-5 rounded-lg border border-blue-100">
                                                <h3 className="text-sm font-bold text-blue-900 mb-3 flex items-center">
                                                    <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                    Example Questions (Preview)
                                                </h3>
                                                <div className="flex gap-2 flex-wrap">
                                                    {exampleQuestions.map((q, idx) => (
                                                        <span key={idx} className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium bg-white text-blue-700 shadow-sm border border-blue-100">
                                                            {q}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {currentStep === 6 && (
                                    <div className="h-full flex flex-col overflow-y-auto p-6">
                                        <h2 className="text-xl font-semibold mb-4">Configuration Summary</h2>

                                        {/* Success Banner */}
                                        <div className="bg-green-50 p-4 rounded-md mb-4 border border-green-200 flex items-center gap-3">
                                            <div className="flex-shrink-0">
                                                <CheckCircleIcon className="w-6 h-6 text-green-600" />
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-bold text-green-900">Configuration Published!</h3>
                                                <p className="text-sm text-green-700">Your agent configuration has been saved successfully.</p>
                                            </div>
                                            <button
                                                onClick={() => setCurrentStep(0)}
                                                className="px-4 py-2 bg-white text-green-700 border border-green-300 rounded font-medium shadow-sm hover:bg-green-50"
                                            >
                                                Go to Dashboard
                                            </button>
                                        </div>

                                        {/* PROMINENT: Vector DB Required Warning */}
                                        {!embeddingJobId && (
                                            <div className="bg-amber-50 border-2 border-amber-400 rounded-lg p-6 mb-6 shadow-md">
                                                <div className="flex items-start gap-4">
                                                    <div className="flex-shrink-0 mt-0.5">
                                                        <svg className="w-8 h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                                        </svg>
                                                    </div>
                                                    <div className="flex-1">
                                                        <h3 className="text-lg font-bold text-amber-800 mb-2">
                                                            ⚡ Action Required: Build Knowledge Base
                                                        </h3>
                                                        <p className="text-amber-700 mb-4">
                                                            Your configuration is saved, but <strong>the agent cannot answer questions yet</strong>.
                                                            You must create the Vector Database to enable the agent's knowledge base.
                                                        </p>
                                                        <div className="flex flex-wrap gap-3">
                                                            <button
                                                                onClick={() => handleStartEmbedding(false)}
                                                                className="px-6 py-3 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-semibold transition-colors shadow-md flex items-center gap-2"
                                                            >
                                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                                </svg>
                                                                Create Vector DB Now
                                                            </button>
                                                            <button
                                                                onClick={() => setShowEmbeddingSettings(true)}
                                                                className="px-4 py-3 bg-white border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50 font-semibold transition-all flex items-center gap-2"
                                                                title="Configure batch size, chunking, parallelization, and more"
                                                            >
                                                                <Cog6ToothIcon className="w-5 h-5" />
                                                                Advanced Settings
                                                            </button>
                                                            <span className="text-sm text-amber-600 self-center">
                                                                This may take a few minutes depending on your data size.
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Embedding Progress (shown when job is running) */}
                                        {embeddingJobId && (
                                            <div className="mb-6">
                                                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                                                    <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
                                                        <svg className="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                        </svg>
                                                        Building Knowledge Base...
                                                    </h3>
                                                    <p className="text-sm text-blue-700">Your agent will be ready to answer questions once this completes.</p>
                                                </div>
                                                <EmbeddingProgress
                                                    jobId={embeddingJobId}
                                                    onComplete={() => {
                                                        showSuccess('Knowledge Base Ready!', 'Your agent can now answer questions based on your data.');
                                                        setEmbeddingJobId(null);
                                                    }}
                                                    onError={(err) => showError('Embedding Failed', err)}
                                                    onCancel={() => {
                                                        showError('Job Cancelled', 'Knowledge base creation was cancelled.');
                                                        setEmbeddingJobId(null);
                                                    }}
                                                />
                                            </div>
                                        )}

                                        <ConfigSummary
                                            connectionId={connectionId}
                                            connectionName={connectionName}
                                            dataSourceType={dataSourceType}
                                            fileInfo={fileUploadResult ? { name: fileUploadResult.file_name, type: fileUploadResult.file_type } : undefined}
                                            schema={selectedSchema}
                                            dataDictionary={dataDictionary}
                                            activePromptVersion={history.find(p => p.is_active)?.version || null}
                                            totalPromptVersions={history.length}
                                            lastUpdatedBy={history.find(p => p.is_active)?.created_by_username}
                                            settings={advancedSettings}
                                        />

                                        {/* Additional Options (smaller, secondary) */}
                                        {!embeddingJobId && (
                                            <div className="mt-6 pt-6 border-t border-gray-200">
                                                <h3 className="text-sm font-medium text-gray-500 mb-3">Additional Options</h3>
                                                <div className="flex gap-3">
                                                    <button
                                                        onClick={() => handleStartEmbedding(true)}
                                                        className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium transition-colors text-sm"
                                                        title="Only process new or changed data"
                                                    >
                                                        Incremental Update
                                                    </button>
                                                    <button
                                                        onClick={() => setCurrentStep(0)}
                                                        className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium transition-colors text-sm"
                                                    >
                                                        Skip for Now (Go to Dashboard)
                                                    </button>
                                                </div>
                                                <p className="text-xs text-gray-400 mt-2">
                                                    You can always create or update the vector database later from the Dashboard.
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Footer Navigation */}
                    {
                        currentStep > 0 && (
                            <div className="mt-8 flex justify-between">
                                <button
                                    onClick={handleBack}
                                    className={`px-6 py-2 rounded-md font-medium ${currentStep === 1 ? 'text-gray-400 cursor-not-allowed' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                                    disabled={currentStep === 1}
                                >
                                    Back
                                </button>

                                {currentStep === 4 ? (
                                    <button
                                        onClick={handleGenerate}
                                        disabled={generating || !canEdit}
                                        className={`px-6 py-2 rounded-md font-medium text-white transition-all duration-200 flex items-center gap-2
                                ${generating ? 'bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse' : !canEdit ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                        title={!canEdit ? "Read-only mode" : "Generate Prompt"}
                                    >
                                        {generating ? (
                                            <>
                                                <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                </svg>
                                                <span>Generating with AI...</span>
                                            </>
                                        ) : (
                                            <>
                                                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                                            className="px-6 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700 disabled:opacity-50 flex items-center"
                                        >
                                            {publishing ? 'Publishing...' : 'Publish to Production'}
                                        </button>
                                    ) : (
                                        <div className="text-gray-500 italic text-sm border border-gray-200 rounded px-4 py-2 bg-gray-50">
                                            Publish restricted: Requires Super Admin
                                        </div>
                                    )
                                ) : (
                                    <button
                                        onClick={handleNext}
                                        disabled={generating || publishing || (currentStep === 1 && dataSourceType === 'database' && !connectionId) || (currentStep === 1 && dataSourceType === 'file' && !fileUploadResult)}
                                        className={`px-6 py-2 rounded-md font-medium text-white transition-colors duration-200 flex items-center
                                ${generating || publishing || (currentStep === 1 && dataSourceType === 'database' && !connectionId) || (currentStep === 1 && dataSourceType === 'file' && !fileUploadResult) ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                    >
                                        {publishing ? 'Publishing...' : currentStep === 6 ? 'Done' : 'Next'}
                                    </button>
                                )}
                            </div>
                        )
                    }
                </div>
            </div >

            {/* Clear Confirmation Modal */}
            {
                showClearConfirm && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 mx-4">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                                    <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold text-gray-900">Clear Data Dictionary</h3>
                                    <p className="text-sm text-gray-500">This action cannot be undone</p>
                                </div>
                            </div>
                            <p className="text-gray-600 mb-6">
                                Are you sure you want to clear all the data dictionary content? You'll need to re-enter or upload it again.
                            </p>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowClearConfirm(false)}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setDataDictionary('');
                                        setShowClearConfirm(false);
                                    }}
                                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium"
                                >
                                    Clear Content
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Replace Version Confirmation Modal */}
            {
                replaceConfirm.show && replaceConfirm.version && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 mx-4">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold text-gray-900">Replace Current Draft</h3>
                                    <p className="text-sm text-gray-500">Load version {replaceConfirm.version.version}</p>
                                </div>
                            </div>
                            <p className="text-gray-600 mb-6">
                                This will replace your current draft with the content from <strong>v{replaceConfirm.version.version}</strong>.
                                Any unsaved changes will be lost.
                            </p>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setReplaceConfirm({ show: false, version: null })}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setDraftPrompt(replaceConfirm.version.prompt_text);
                                        setReplaceConfirm({ show: false, version: null });
                                    }}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium"
                                >
                                    Replace Draft
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Embedding Settings Modal */}
            <EmbeddingSettingsModal
                isOpen={showEmbeddingSettings}
                onClose={() => setShowEmbeddingSettings(false)}
                onConfirm={handleStartEmbeddingWithSettings}
                defaultSettings={{
                    batch_size: 128,  // Optimized for GPU (MPS/CUDA) with local models
                    max_concurrent: 5,
                    chunking: {
                        parent_chunk_size: advancedSettings.chunking.parentChunkSize,
                        parent_chunk_overlap: advancedSettings.chunking.parentChunkOverlap,
                        child_chunk_size: advancedSettings.chunking.childChunkSize,
                        child_chunk_overlap: advancedSettings.chunking.childChunkOverlap,
                    },
                    parallelization: {
                        num_workers: undefined,
                        chunking_batch_size: undefined,
                        delta_check_batch_size: 50000,
                    },
                    max_consecutive_failures: 5,
                    retry_attempts: 3,
                }}
            />
        </div >
    );
};

export default ConfigPage;
