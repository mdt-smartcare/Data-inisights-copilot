/**
 * Hook for fetching available AI models from the AI Registry.
 * 
 * Used in agent configuration to select LLM, embedding, and reranker models.
 */
import { useState, useEffect, useCallback } from 'react';
import { 
  getAvailableModelsForAgentConfig, 
  getAIModelDefaults,
  type AvailableModel,
  type DefaultsResponse
} from '../services/api';

export interface UseAIRegistryModelsResult {
  // Available models by type
  llmModels: AvailableModel[];
  embeddingModels: AvailableModel[];
  rerankerModels: AvailableModel[];
  
  // Current defaults
  defaults: DefaultsResponse | null;
  
  // Loading state
  isLoading: boolean;
  error: string | null;
  
  // Refresh function
  refresh: () => Promise<void>;
}

export function useAIRegistryModels(): UseAIRegistryModelsResult {
  const [llmModels, setLlmModels] = useState<AvailableModel[]>([]);
  const [embeddingModels, setEmbeddingModels] = useState<AvailableModel[]>([]);
  const [rerankerModels, setRerankerModels] = useState<AvailableModel[]>([]);
  const [defaults, setDefaults] = useState<DefaultsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadModels = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const [availableModels, defaultModels] = await Promise.all([
        getAvailableModelsForAgentConfig(),
        getAIModelDefaults()
      ]);
      
      // Filter to only ready models
      setLlmModels(availableModels.llm?.filter(m => m.is_ready) || []);
      setEmbeddingModels(availableModels.embedding?.filter(m => m.is_ready) || []);
      setRerankerModels(availableModels.reranker?.filter(m => m.is_ready) || []);
      setDefaults(defaultModels);
    } catch (err) {
      console.error('Failed to load AI Registry models:', err);
      setError('Failed to load models from AI Registry');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  return {
    llmModels,
    embeddingModels,
    rerankerModels,
    defaults,
    isLoading,
    error,
    refresh: loadModels
  };
}

export default useAIRegistryModels;
