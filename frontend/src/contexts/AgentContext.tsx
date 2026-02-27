import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { Agent } from '../types/agent';
import { getActiveConfigMetadata, getPromptHistory, listEmbeddingJobs, getConnections, getVectorDbStatus, getSystemSettings } from '../services/api';

// Types for active config
export interface ActiveConfig {
    id?: number;
    prompt_id?: number;
    version: number;
    prompt_text: string;
    connection_id?: number;
    schema_selection?: string;
    data_dictionary?: string;
    reasoning?: string;
    example_questions?: string;
    embedding_config?: string;
    llm_config?: string;
    chunking_config?: string;
    retriever_config?: string;
    data_source_type?: 'database' | 'file';
    created_by_username?: string;
    created_at?: string;
    is_active?: boolean;
}

export interface PromptVersion {
    id: number;
    version: string | number;
    prompt_text: string;
    created_at: string;
    created_by_username?: string;
    is_active: number;
}

export interface VectorDbStatus {
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
}

export interface AdvancedSettings {
    embedding: {
        model: string;
        vectorDbName?: string;
    };
    llm: {
        temperature: number;
        maxTokens: number;
        model?: string;
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
}

interface AgentContextType {
    // Selected agent
    selectedAgent: Agent | null;
    setSelectedAgent: (agent: Agent | null) => void;

    // Config data
    activeConfig: ActiveConfig | null;
    history: PromptVersion[];
    vectorDbStatus: VectorDbStatus | null;
    connectionName: string;
    advancedSettings: AdvancedSettings;
    setAdvancedSettings: React.Dispatch<React.SetStateAction<AdvancedSettings>>;

    // Embedding job
    embeddingJobId: string | null;
    setEmbeddingJobId: (jobId: string | null) => void;

    // Loading states
    isLoadingConfig: boolean;

    // Actions
    refreshConfig: () => Promise<void>;
    refreshHistory: () => Promise<void>;
    refreshVectorDbStatus: () => Promise<void>;

    // Defaults
    loadSystemDefaults: () => Promise<void>;
}

const defaultAdvancedSettings: AdvancedSettings = {
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
        hybridWeights: [0.75, 0.25],
        rerankEnabled: true,
        rerankerModel: 'BAAI/bge-reranker-base'
    }
};

const AgentContext = createContext<AgentContextType | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
    const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
    const [activeConfig, setActiveConfig] = useState<ActiveConfig | null>(null);
    const [history, setHistory] = useState<PromptVersion[]>([]);
    const [vectorDbStatus, setVectorDbStatus] = useState<VectorDbStatus | null>(null);
    const [connectionName, setConnectionName] = useState<string>('');
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [isLoadingConfig, setIsLoadingConfig] = useState(false);
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(defaultAdvancedSettings);

    const loadSystemDefaults = useCallback(async () => {
        try {
            const [embSettings, ragSettings, llmSettings] = await Promise.all([
                getSystemSettings('embedding').catch(() => null),
                getSystemSettings('rag').catch(() => null),
                getSystemSettings('llm').catch(() => null)
            ]);

            setAdvancedSettings(prev => {
                const next = { ...prev };
                if (embSettings && embSettings.model_name) {
                    next.embedding = { ...next.embedding, model: embSettings.model_name };
                }
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
    }, []);

    const refreshHistory = useCallback(async () => {
        if (!selectedAgent) return;
        try {
            const data = await getPromptHistory(selectedAgent.id);
            setHistory(data);
        } catch (err) {
            console.error("Failed to load history", err);
        }
    }, [selectedAgent]);

    const refreshVectorDbStatus = useCallback(async () => {
        if (!activeConfig) return;
        try {
            const embConf = activeConfig.embedding_config ? JSON.parse(activeConfig.embedding_config) : {};
            const vDbName = embConf.vectorDbName || (activeConfig.data_source_type === 'database' && activeConfig.connection_id ? `db_connection_${activeConfig.connection_id}_data` : 'default_vector_db');
            if (vDbName) {
                const status = await getVectorDbStatus(vDbName);
                setVectorDbStatus(status);
            }
        } catch (err) {
            console.log("Vector DB not found or error:", err);
            setVectorDbStatus(null);
        }
    }, [activeConfig]);

    const refreshConfig = useCallback(async () => {
        if (!selectedAgent) return;
        setIsLoadingConfig(true);
        try {
            const config = await getActiveConfigMetadata(selectedAgent.id);
            if (config) {
                setActiveConfig(config);

                // Parse and set advanced settings from config
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
                            console.log("Restoring active embedding job:", latestJob.job_id);
                            setEmbeddingJobId(latestJob.job_id);
                        }
                    }
                } catch (jobErr) {
                    console.error("Failed to fetch active jobs", jobErr);
                }
            } else {
                setActiveConfig(null);
            }
            // Load history
            await refreshHistory();
        } catch (e) {
            console.error("Failed to load active config", e);
            setActiveConfig(null);
        } finally {
            setIsLoadingConfig(false);
        }
    }, [selectedAgent, advancedSettings, refreshHistory]);

    // Load config when agent changes
    useEffect(() => {
        if (selectedAgent) {
            refreshConfig();
        } else {
            setActiveConfig(null);
            setHistory([]);
            setVectorDbStatus(null);
            setConnectionName('');
            setEmbeddingJobId(null);
        }
    }, [selectedAgent]);

    const value: AgentContextType = {
        selectedAgent,
        setSelectedAgent,
        activeConfig,
        history,
        vectorDbStatus,
        connectionName,
        advancedSettings,
        setAdvancedSettings,
        embeddingJobId,
        setEmbeddingJobId,
        isLoadingConfig,
        refreshConfig,
        refreshHistory,
        refreshVectorDbStatus,
        loadSystemDefaults
    };

    return (
        <AgentContext.Provider value={value}>
            {children}
        </AgentContext.Provider>
    );
}

export function useAgent() {
    const context = useContext(AgentContext);
    if (!context) {
        throw new Error('useAgent must be used within an AgentProvider');
    }
    return context;
}

export default AgentContext;
