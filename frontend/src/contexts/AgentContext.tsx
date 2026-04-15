import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { Agent } from '../types/agent';
import { getActiveConfigMetadata, getPromptHistory, listEmbeddingJobs, getConnections, getVectorDbStatusByConfig } from '../services/api';
import { useSystemSettings } from './SystemSettingsContext';
import type { AdvancedSettings } from './SystemSettingsContext';

// Re-export AdvancedSettings type from SystemSettingsContext
export type { AdvancedSettings } from './SystemSettingsContext';

// Model info interface (from ai_models table)
export interface ModelInfo {
    id: number;
    provider_name: string;
    display_name: string;
    model_id: string;
    model_type: string;
}

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
    ingestion_file_name?: string;
    ingestion_file_type?: string;
    ingestion_documents?: string;
    created_by_username?: string;
    created_at?: string;
    updated_at?: string;
    is_active?: boolean;
    status?: string;
    completed_step?: number;
    db_url?: string;
    db_engine_type?: string;

    // Embedding status
    embedding_status?: string;
    embedding_path?: string;
    vector_collection_name?: string;

    // Model IDs (FK to ai_models)
    llm_model_id?: number;
    embedding_model_id?: number;
    reranker_model_id?: number;

    // Resolved model info (populated by backend)
    llm_model?: ModelInfo;
    embedding_model?: ModelInfo;
    reranker_model?: ModelInfo;

    // Data source info
    data_source?: {
        id: string;
        title: string;
        source_type: string;
        db_url?: string;
        original_filename?: string;
        file_type?: string;
        row_count?: number;
    };
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
    vector_db_type?: 'qdrant' | 'chroma' | string;
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
}

const AgentContext = createContext<AgentContextType | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
    // Get system settings from the centralized context (loaded from backend)
    const { advancedSettings: systemSettings } = useSystemSettings();

    const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
    const [activeConfig, setActiveConfig] = useState<ActiveConfig | null>(null);
    const [history, setHistory] = useState<PromptVersion[]>([]);
    const [vectorDbStatus, setVectorDbStatus] = useState<VectorDbStatus | null>(null);
    const [connectionName, setConnectionName] = useState<string>('');
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [isLoadingConfig, setIsLoadingConfig] = useState(false);

    // Initialize with system settings from backend
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(systemSettings);

    // Update local settings when system settings change (e.g., after initial load)
    useEffect(() => {
        setAdvancedSettings(prev => ({
            ...systemSettings,
            // Preserve any agent-specific overrides like vectorDbName
            embedding: { ...systemSettings.embedding, vectorDbName: prev.embedding.vectorDbName }
        }));
    }, [systemSettings]);

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
            const configId = activeConfig.id || activeConfig.prompt_id;
            if (configId) {
                const status = await getVectorDbStatusByConfig(configId);
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

                // Parse and set advanced settings from config (overrides system defaults)
                const parseConf = (c: any) => c ? (typeof c === 'string' ? JSON.parse(c) : c) : null;
                const newSettings = { ...systemSettings };
                const emb = parseConf(config.embedding_config);
                const llm = parseConf(config.llm_config);
                const chunk = parseConf(config.chunking_config);
                const ret = parseConf(config.retriever_config);

                if (emb) newSettings.embedding = { ...newSettings.embedding, ...emb };
                if (llm) newSettings.llm = { ...newSettings.llm, ...llm };
                if (chunk) newSettings.chunking = { ...newSettings.chunking, ...chunk };
                if (ret) newSettings.retriever = { ...newSettings.retriever, ...ret };
                setAdvancedSettings(newSettings);

                // Set connection name from data_source title (no separate lookup needed)
                if (config.data_source?.title) {
                    setConnectionName(config.data_source.title);
                } else if (config.connection_id) {
                    // Legacy fallback
                    try {
                        const conns = await getConnections();
                        const c = conns.find((x: { id: number }) => x.id === config.connection_id);
                        if (c) setConnectionName(c.name);
                    } catch (e) {
                        console.error("Failed to fetch connection name", e);
                    }
                }

                // Fetch Vector DB Status using config ID
                try {
                    const configId = config.id || config.prompt_id;
                    if (configId) {
                        const status = await getVectorDbStatusByConfig(configId);
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
    }, [selectedAgent, systemSettings, refreshHistory]);

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
