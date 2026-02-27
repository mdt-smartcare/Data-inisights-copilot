import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChatHeader } from '../components/chat';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import { ArrowLeftIcon, CommandLineIcon, AdjustmentsVerticalIcon, UserGroupIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import { getAgents, startEmbeddingJob, rollbackToVersion, getSystemSettings, handleApiError } from '../services/api';
import { canEditPrompt } from '../utils/permissions';
import type { Agent } from '../types/agent';
import type { PromptVersion, VectorDbStatus, AdvancedSettings, ActiveConfig } from '../contexts/AgentContext';

// Import tab components
import { OverviewTab, KnowledgeTab, SandboxTab, SettingsTab, UsersTab, MonitoringTab, HistoryTab } from '../components/config/tabs';

// Import hooks for data fetching
import { getActiveConfigMetadata, getPromptHistory, listEmbeddingJobs, getConnections, getVectorDbStatus } from '../services/api';

const defaultAdvancedSettings: AdvancedSettings = {
    embedding: { model: 'BAAI/bge-m3' },
    llm: { temperature: 0.0, maxTokens: 4096 },
    chunking: { parentChunkSize: 800, parentChunkOverlap: 150, childChunkSize: 200, childChunkOverlap: 50 },
    retriever: { topKInitial: 50, topKFinal: 10, hybridWeights: [0.75, 0.25], rerankEnabled: true, rerankerModel: 'BAAI/bge-reranker-base' }
};

const AgentDashboardPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { user, isLoading: isAuthLoading } = useAuth();
    const { success: showSuccess, error: showError } = useToast();
    const canEdit = canEditPrompt(user);

    // Agent state
    const [agent, setAgent] = useState<Agent | null>(null);
    const [isLoadingAgent, setIsLoadingAgent] = useState(true);

    // Config state
    const [activeConfig, setActiveConfig] = useState<ActiveConfig | null>(null);
    const [history, setHistory] = useState<PromptVersion[]>([]);
    const [vectorDbStatus, setVectorDbStatus] = useState<VectorDbStatus | null>(null);
    const [connectionName, setConnectionName] = useState('');
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(defaultAdvancedSettings);
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [isRollingBack, setIsRollingBack] = useState(false);

    // Dashboard tab state
    const [dashboardTab, setDashboardTab] = useState('overview');

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

    // Load config when agent is loaded
    useEffect(() => {
        const loadConfig = async () => {
            if (!agent) return;
            try {
                const config = await getActiveConfigMetadata(agent.id);
                if (config) {
                    setActiveConfig(config);

                    // Parse and set advanced settings from config
                    const parseConf = (c: any) => c ? (typeof c === 'string' ? JSON.parse(c) : c) : null;
                    const newSettings = { ...defaultAdvancedSettings };
                    const emb = parseConf(config.embedding_config);
                    const llm = parseConf(config.llm_config);
                    const chunk = parseConf(config.chunking_config);
                    const ret = parseConf(config.retriever_config);

                    if (emb) newSettings.embedding = { ...newSettings.embedding, ...emb };
                    if (llm) newSettings.llm = { ...newSettings.llm, ...llm };
                    if (chunk) newSettings.chunking = { ...newSettings.chunking, ...chunk };
                    if (ret) newSettings.retriever = { ...newSettings.retriever, ...ret };
                    setAdvancedSettings(newSettings);

                    // Fetch connection name
                    if (config.connection_id) {
                        try {
                            const conns = await getConnections();
                            const c = conns.find((x: any) => x.id === config.connection_id);
                            if (c) setConnectionName(c.name);
                        } catch (e) {
                            console.error("Failed to fetch connection name", e);
                        }
                    }

                    // Fetch Vector DB Status
                    try {
                        const embConf = config.embedding_config ? JSON.parse(config.embedding_config) : {};
                        const vDbName = embConf.vectorDbName || (config.data_source_type === 'database' && config.connection_id ? `db_connection_${config.connection_id}_data` : 'default_vector_db');
                        if (vDbName) {
                            const status = await getVectorDbStatus(vDbName);
                            setVectorDbStatus(status);
                        }
                    } catch (e) {
                        console.log("Could not load Vector DB status");
                        setVectorDbStatus(null);
                    }

                    // Fetch any active embedding jobs
                    try {
                        const jobs = await listEmbeddingJobs({
                            config_id: config.id || config.prompt_id,
                            limit: 1
                        });
                        if (jobs.length > 0) {
                            const latestJob = jobs[0];
                            const activeStatuses = ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING'];
                            if (activeStatuses.includes(latestJob.status)) {
                                setEmbeddingJobId(latestJob.job_id);
                            }
                        }
                    } catch (jobErr) {
                        console.error("Failed to fetch active jobs", jobErr);
                    }
                }
                // Load history
                const historyData = await getPromptHistory(agent.id);
                setHistory(historyData);
            } catch (e) {
                console.error("Failed to load config", e);
            }
        };
        loadConfig();
    }, [agent]);

    const handleStartEmbedding = async (incremental: boolean = true) => {
        const configId = activeConfig?.id || activeConfig?.prompt_id;
        if (!configId) return;

        try {
            let batchSize = 50;
            let maxConcurrent = 5;

            try {
                const settings = await getSystemSettings('embedding');
                if (settings?.batch_size) batchSize = settings.batch_size;
                if (settings?.max_concurrent) maxConcurrent = settings.max_concurrent;
            } catch (err) {
                console.warn('Failed to fetch embedding settings, using defaults', err);
            }

            const result = await startEmbeddingJob({
                config_id: configId,
                batch_size: batchSize,
                max_concurrent: maxConcurrent,
                incremental: incremental
            });
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };

    const handleEmbeddingComplete = async () => {
        showSuccess('Embeddings Generated', 'Knowledge base updated successfully');
        setEmbeddingJobId(null);
        // Refresh vector DB status
        if (activeConfig) {
            try {
                const embConf = activeConfig.embedding_config
                    ? (typeof activeConfig.embedding_config === 'string'
                        ? JSON.parse(activeConfig.embedding_config)
                        : activeConfig.embedding_config)
                    : {};
                const vDbName = embConf.vectorDbName ||
                    (activeConfig.data_source_type === 'database' && activeConfig.connection_id
                        ? `db_connection_${activeConfig.connection_id}_data`
                        : 'default_vector_db');
                if (vDbName) {
                    const status = await getVectorDbStatus(vDbName);
                    setVectorDbStatus(status);
                }
            } catch (err) {
                console.log("Failed to refresh vector DB status", err);
            }
        }
    };

    const handleRollback = async (version: PromptVersion) => {
        if (!agent) return;
        if (!window.confirm(`Are you sure you want to rollback ${agent.name} to Version ${version.version}? This will make it the active production configuration.`)) {
            return;
        }

        setIsRollingBack(true);
        try {
            await rollbackToVersion(version.id);
            showSuccess('Rollback Successful', `Agent ${agent.name} is now running Version ${version.version}`);
            // Reload config
            const config = await getActiveConfigMetadata(agent.id);
            if (config) setActiveConfig(config);
            const historyData = await getPromptHistory(agent.id);
            setHistory(historyData);
        } catch (err) {
            showError('Rollback Failed', handleApiError(err));
        } finally {
            setIsRollingBack(false);
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

    const tabs = [
        { id: 'overview', name: 'Overview', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg> },
        { id: 'knowledge', name: 'Vector DB', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg> },
        { id: 'sandbox', name: 'Sandbox', icon: (props: any) => <CommandLineIcon {...props} /> },
        { id: 'specs', name: 'Settings & Specs', icon: (props: any) => <AdjustmentsVerticalIcon {...props} /> },
        { id: 'users', name: 'Users', icon: (props: any) => <UserGroupIcon {...props} /> },
        { id: 'monitoring', name: 'Monitoring', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg> },
        { id: 'history', name: 'System Prompt History', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> }
    ];

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="h-full flex flex-col overflow-y-auto">
                    <header className="bg-white px-8 pt-8 pb-4 border-b border-gray-200">
                        <div className="flex justify-between items-center mb-6">
                            <div className="flex items-center gap-4">
                                <button
                                    onClick={() => navigate('/agents')}
                                    className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
                                    title="Back to Agents"
                                >
                                    <ArrowLeftIcon className="w-6 h-6" />
                                </button>
                                <div>
                                    <h1 className="text-2xl font-bold text-gray-900">{agent.name}</h1>
                                    <p className="text-sm text-gray-500">Agent Configuration & Insights Dashboard</p>
                                </div>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => navigate(`/agents/${agent.id}/config`)}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm transition-all focus:ring-2 focus:ring-blue-200"
                                >
                                    {canEdit ? 'Edit Active Config' : 'View Configuration'}
                                </button>
                            </div>
                        </div>

                        {/* Tabs */}
                        <div className="flex gap-8 border-t border-gray-100 pt-2">
                            {tabs.map(tab => (
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
                                    <OverviewTab
                                        activeConfig={activeConfig}
                                        connectionName={connectionName}
                                        advancedSettings={advancedSettings}
                                        history={history}
                                        vectorDbStatus={vectorDbStatus}
                                    />
                                )}

                                {dashboardTab === 'knowledge' && (
                                    <KnowledgeTab
                                        activeConfig={activeConfig}
                                        vectorDbStatus={vectorDbStatus}
                                        embeddingJobId={embeddingJobId}
                                        onStartEmbedding={handleStartEmbedding}
                                        onEmbeddingComplete={handleEmbeddingComplete}
                                        onEmbeddingError={(err) => showError('Embedding Failed', err)}
                                        onEmbeddingCancel={() => {
                                            showError('Job Cancelled', 'Embedding generation cancelled');
                                            setEmbeddingJobId(null);
                                        }}
                                    />
                                )}

                                {dashboardTab === 'sandbox' && (
                                    <SandboxTab agent={agent} activeConfig={activeConfig} />
                                )}

                                {dashboardTab === 'specs' && (
                                    <SettingsTab activeConfig={activeConfig} />
                                )}

                                {dashboardTab === 'users' && (
                                    <UsersTab agentId={agent.id} agentName={agent.name} />
                                )}

                                {dashboardTab === 'monitoring' && (
                                    <MonitoringTab />
                                )}

                                {dashboardTab === 'history' && (
                                    <HistoryTab
                                        history={history}
                                        onRollback={handleRollback}
                                        isRollingBack={isRollingBack}
                                    />
                                )}
                            </div>
                        ) : dashboardTab === 'users' ? (
                            <UsersTab agentId={agent.id} agentName={agent.name} />
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
                                    onClick={() => navigate(`/agents/${agent.id}/config`)}
                                    className="px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-bold shadow-lg shadow-blue-200 transition-all hover:-translate-y-1 active:translate-y-0"
                                >
                                    Start Setup Wizard
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AgentDashboardPage;
