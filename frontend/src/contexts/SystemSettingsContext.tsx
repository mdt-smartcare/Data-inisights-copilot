import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { getSystemSettings } from '../services/api';
import { useAuth } from './AuthContext';

/**
 * Advanced settings structure that matches the backend system settings.
 * All values come from the Settings page - nothing is hardcoded.
 */
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

/**
 * Embedding job settings from system configuration.
 */
export interface EmbeddingJobSettings {
    batchSize: number;
    maxConcurrent: number;
    maxConsecutiveFailures: number;
    retryAttempts: number;
}

interface SystemSettingsContextType {
    // Settings loaded from backend
    advancedSettings: AdvancedSettings;
    embeddingJobSettings: EmbeddingJobSettings;
    
    // Loading state
    isLoading: boolean;
    isLoaded: boolean;
    error: string | null;
    
    // Actions
    refreshSettings: () => Promise<void>;
    
    // Helper to get settings for embedding modal
    getEmbeddingModalDefaults: () => {
        batch_size: number;
        max_concurrent: number;
        chunking: {
            parent_chunk_size: number;
            parent_chunk_overlap: number;
            child_chunk_size: number;
            child_chunk_overlap: number;
        };
        parallelization: {
            num_workers: number | undefined;
            chunking_batch_size: number | undefined;
            delta_check_batch_size: number;
        };
        max_consecutive_failures: number;
        retry_attempts: number;
    };
}

// Fallback defaults only used if API fails completely
// These should match reasonable defaults but real values come from backend
const FALLBACK_SETTINGS: AdvancedSettings = {
    embedding: { model: 'BAAI/bge-m3' },
    llm: { temperature: 0.0, maxTokens: 4096 },
    chunking: { 
        parentChunkSize: 512, 
        parentChunkOverlap: 100, 
        childChunkSize: 128, 
        childChunkOverlap: 25 
    },
    retriever: { 
        topKInitial: 50, 
        topKFinal: 10, 
        hybridWeights: [0.75, 0.25], 
        rerankEnabled: true, 
        rerankerModel: 'BAAI/bge-reranker-base' 
    }
};

const FALLBACK_EMBEDDING_JOB_SETTINGS: EmbeddingJobSettings = {
    batchSize: 128,
    maxConcurrent: 5,
    maxConsecutiveFailures: 5,
    retryAttempts: 3
};

const SystemSettingsContext = createContext<SystemSettingsContextType | null>(null);

export function SystemSettingsProvider({ children }: { children: ReactNode }) {
    const { isAuthenticated, isLoading: authLoading } = useAuth();
    const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>(FALLBACK_SETTINGS);
    const [embeddingJobSettings, setEmbeddingJobSettings] = useState<EmbeddingJobSettings>(FALLBACK_EMBEDDING_JOB_SETTINGS);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoaded, setIsLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refreshSettings = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        
        try {
            // Fetch all settings categories in parallel
            const [embSettings, ragSettings, llmSettings, chunkingSettings] = await Promise.all([
                getSystemSettings('embedding').catch(() => null),
                getSystemSettings('rag').catch(() => null),
                getSystemSettings('llm').catch(() => null),
                getSystemSettings('chunking').catch(() => null)  // Separate chunking category
            ]);

            setAdvancedSettings(prev => {
                const next = { ...prev };
                
                // Embedding settings
                if (embSettings) {
                    if (embSettings.model_name) {
                        next.embedding = { ...next.embedding, model: embSettings.model_name };
                    }
                    // Embedding job settings
                    if (embSettings.batch_size) {
                        setEmbeddingJobSettings(ejs => ({ ...ejs, batchSize: embSettings.batch_size }));
                    }
                    if (embSettings.max_concurrent) {
                        setEmbeddingJobSettings(ejs => ({ ...ejs, maxConcurrent: embSettings.max_concurrent }));
                    }
                }
                
                // Chunking settings (from dedicated chunking category)
                if (chunkingSettings) {
                    if (chunkingSettings.parent_chunk_size !== undefined) {
                        next.chunking = { ...next.chunking, parentChunkSize: chunkingSettings.parent_chunk_size };
                    }
                    if (chunkingSettings.parent_chunk_overlap !== undefined) {
                        next.chunking = { ...next.chunking, parentChunkOverlap: chunkingSettings.parent_chunk_overlap };
                    }
                    if (chunkingSettings.child_chunk_size !== undefined) {
                        next.chunking = { ...next.chunking, childChunkSize: chunkingSettings.child_chunk_size };
                    }
                    if (chunkingSettings.child_chunk_overlap !== undefined) {
                        next.chunking = { ...next.chunking, childChunkOverlap: chunkingSettings.child_chunk_overlap };
                    }
                }
                
                // RAG settings (retriever only - chunking moved to separate category)
                if (ragSettings) {
                    // Retriever
                    if (ragSettings.top_k_initial !== undefined) {
                        next.retriever = { ...next.retriever, topKInitial: ragSettings.top_k_initial };
                    }
                    if (ragSettings.top_k_final !== undefined) {
                        next.retriever = { ...next.retriever, topKFinal: ragSettings.top_k_final };
                    }
                    if (ragSettings.hybrid_weights) {
                        next.retriever = { ...next.retriever, hybridWeights: ragSettings.hybrid_weights };
                    }
                    if (ragSettings.rerank_enabled !== undefined) {
                        next.retriever = { ...next.retriever, rerankEnabled: ragSettings.rerank_enabled };
                    }
                    if (ragSettings.reranker_model) {
                        next.retriever = { ...next.retriever, rerankerModel: ragSettings.reranker_model };
                    }
                }
                
                // LLM settings
                if (llmSettings) {
                    if (llmSettings.temperature !== undefined) {
                        next.llm = { ...next.llm, temperature: llmSettings.temperature };
                    }
                    if (llmSettings.max_tokens !== undefined) {
                        next.llm = { ...next.llm, maxTokens: llmSettings.max_tokens };
                    }
                    if (llmSettings.model_name) {
                        next.llm = { ...next.llm, model: llmSettings.model_name };
                    }
                }
                
                return next;
            });
            
            setIsLoaded(true);
        } catch (err) {
            console.error('Failed to load system settings:', err);
            setError('Failed to load system settings. Using defaults.');
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Load settings only when authenticated
    useEffect(() => {
        if (!authLoading && isAuthenticated) {
            refreshSettings();
        } else if (!authLoading && !isAuthenticated) {
            // Not authenticated - use fallback settings, stop loading
            setIsLoading(false);
        }
    }, [refreshSettings, isAuthenticated, authLoading]);

    // Helper to get embedding modal defaults in the expected format
    const getEmbeddingModalDefaults = useCallback(() => {
        return {
            batch_size: embeddingJobSettings.batchSize,
            max_concurrent: embeddingJobSettings.maxConcurrent,
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
            max_consecutive_failures: embeddingJobSettings.maxConsecutiveFailures,
            retry_attempts: embeddingJobSettings.retryAttempts,
        };
    }, [advancedSettings, embeddingJobSettings]);

    const value: SystemSettingsContextType = {
        advancedSettings,
        embeddingJobSettings,
        isLoading,
        isLoaded,
        error,
        refreshSettings,
        getEmbeddingModalDefaults,
    };

    return (
        <SystemSettingsContext.Provider value={value}>
            {children}
        </SystemSettingsContext.Provider>
    );
}

/**
 * Hook to access system settings from any component.
 * Settings are loaded once from the backend and cached.
 */
export function useSystemSettings() {
    const context = useContext(SystemSettingsContext);
    if (!context) {
        throw new Error('useSystemSettings must be used within a SystemSettingsProvider');
    }
    return context;
}

export default SystemSettingsContext;
