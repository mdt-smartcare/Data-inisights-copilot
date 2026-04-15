import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';

/**
 * Advanced settings structure that matches the backend system settings.
 * All values come from the Settings page - nothing is hardcoded.
 * 
 * Note: Model IDs (embeddingModelId, llmModelId, rerankerModelId) are sent
 * at the top level of the API request, not inside these config objects.
 */
export interface AdvancedSettings {
    embedding: {
        model: string;  // model_id string like "huggingface/BAAI/bge-m3"
        vectorDbName?: string;
    };
    llm: {
        temperature: number;
        maxTokens: number;
        model?: string;  // model_id string like "openai/gpt-4o"
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
        rerankerModel: string;  // model_id string like "huggingface/BAAI/bge-reranker-v2-m3"
    };
    // AI Registry model IDs (foreign keys to ai_models.id) - sent at request top level
    embeddingModelId?: number;
    llmModelId?: number;
    rerankerModelId?: number;
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
    ensureLoaded: () => Promise<void>;
    
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
    const [isLoading, setIsLoading] = useState(false);  // Start as false, set true when loading
    const [isLoaded, setIsLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Note: Old /api/v1/settings/* endpoints no longer exist in backend
    // Settings now use fallback defaults. In the future, these could come from
    // the AI Models API (/api/v1/ai-models/defaults) or agent configs.
    const refreshSettings = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        
        try {
            // Use fallback settings - old backend endpoints removed
            setAdvancedSettings(FALLBACK_SETTINGS);
            setEmbeddingJobSettings(FALLBACK_EMBEDDING_JOB_SETTINGS);
            setIsLoaded(true);
        } catch (err) {
            console.error('Failed to load system settings:', err);
            setError('Failed to load system settings. Using defaults.');
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Lazy loading - don't auto-load on auth
    // Settings are loaded on-demand when ensureLoaded() is called
    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            // Not authenticated - use fallback settings, stop loading
            setIsLoading(false);
        }
    }, [authLoading, isAuthenticated]);

    // Ensure settings are loaded (call this before accessing settings)
    const ensureLoaded = useCallback(async () => {
        if (!isLoaded && !isLoading && isAuthenticated) {
            await refreshSettings();
        }
    }, [isLoaded, isLoading, isAuthenticated, refreshSettings]);

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
        ensureLoaded,
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
