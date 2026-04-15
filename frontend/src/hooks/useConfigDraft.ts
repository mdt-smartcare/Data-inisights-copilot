/**
 * Hook for managing agent configuration versions with step-by-step saving.
 * 
 * Features:
 * - Fetches or creates config version
 * - Tracks step progress with version_id
 * - Comparison logic to avoid unnecessary saves
 * - Publishes version when complete
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import {
  getDraftConfig,
  deleteVersion,
  publishVersion,
  cloneConfigAsDraft,
  getConfigHistory,
  getVersion,
  // Per-step APIs (named steps with version_id)
  saveDataSourceStep,
  saveSchemaSelectionStep,
  saveDataDictionaryStep,
  saveSettingsStep,
  savePromptStep,
  type AgentConfig,
} from '../services/api';

// Simple deep equality check without lodash dependency
function isEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (typeof a !== 'object' || typeof b !== 'object') return false;
  const keysA = Object.keys(a as object);
  const keysB = Object.keys(b as object);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => 
    isEqual((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key])
  );
}

interface UseConfigDraftReturn {
  // State
  draft: AgentConfig | null;
  agentId: string | null;
  versionId: number | null;  // The config ID (version)
  isLoading: boolean;
  isSaving: boolean;
  isPublishing: boolean;
  error: string | null;
  currentStep: number;
  
  // Config history
  configHistory: AgentConfig[];
  
  // Actions
  fetchOrCreateDraft: (agentId: string, dataSourceId: string, versionId?: number) => Promise<AgentConfig | null>;
  createNewDraft: (agentId: string, dataSourceId: string) => Promise<AgentConfig | null>;
  loadDraft: (agentId: string) => Promise<AgentConfig | null>;
  loadVersion: (agentId: string, versionId: number) => Promise<AgentConfig | null>;
  saveStep: (step: number, data: Record<string, unknown>) => Promise<AgentConfig | null>;
  publish: (systemPrompt: string, exampleQuestions?: string[]) => Promise<AgentConfig | null>;
  createDraftFromConfig: (configId: number) => Promise<AgentConfig | null>;
  discardDraft: () => Promise<boolean>;
  loadHistory: (agentId: string) => Promise<void>;
  setCurrentStep: (step: number) => void;
  
  // Helpers
  hasUnsavedChanges: (step: number, data: Record<string, unknown>) => boolean;
  getStepData: (step: number) => Record<string, unknown>;
}

/**
 * Map step number to the fields it manages
 */
const STEP_FIELDS: Record<number, string[]> = {
  1: ['data_source_id'],
  2: ['selected_columns'],
  3: ['data_dictionary'],
  4: ['llm_config', 'embedding_config', 'chunking_config', 'rag_config', 'llm_model_id', 'embedding_model_id', 'reranker_model_id'],
  5: ['system_prompt', 'example_questions'],
  6: ['embedding_path', 'vector_collection_name'],
};

/**
 * Extract step-specific data from config
 */
function extractStepData(config: AgentConfig | null, step: number): Record<string, unknown> {
  if (!config) return {};
  
  const fields = STEP_FIELDS[step] || [];
  const data: Record<string, unknown> = {};
  
  fields.forEach((field) => {
    const value = (config as unknown as Record<string, unknown>)[field];
    if (value !== undefined) {
      data[field] = value;
    }
  });
  
  return data;
}

export function useConfigDraft(): UseConfigDraftReturn {
  const [draft, setDraft] = useState<AgentConfig | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [configHistory, setConfigHistory] = useState<AgentConfig[]>([]);
  
  // Track last saved state for comparison
  const lastSavedRef = useRef<Record<number, Record<string, unknown>>>({});
  
  // Update last saved ref when draft changes
  useEffect(() => {
    if (draft) {
      // Populate lastSavedRef with current draft state for all steps
      for (let step = 1; step <= 6; step++) {
        lastSavedRef.current[step] = extractStepData(draft, step);
      }
    }
  }, [draft]);
  
  /**
   * Load existing draft for an agent (doesn't create if not exists)
   */
  const loadDraft = useCallback(async (targetAgentId: string): Promise<AgentConfig | null> => {
    setIsLoading(true);
    setError(null);
    setAgentId(targetAgentId);
    
    try {
      const existingDraft = await getDraftConfig(targetAgentId);
      if (existingDraft) {
        setDraft(existingDraft);
        setVersionId(existingDraft.id);
        // Navigate to next step after the last completed one
        setCurrentStep(Math.min((existingDraft.completed_step || 0) + 1, 6));
      } else {
        setVersionId(null);
      }
      return existingDraft;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to load draft';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  /**
   * Load a specific version by ID
   */
  const loadVersion = useCallback(async (targetAgentId: string, targetVersionId: number): Promise<AgentConfig | null> => {
    setIsLoading(true);
    setError(null);
    setAgentId(targetAgentId);
    
    try {
      const config = await getVersion(targetAgentId, targetVersionId);
      if (config) {
        setDraft(config);
        setVersionId(config.id);
        // Navigate to next step after the last completed one
        setCurrentStep(Math.min((config.completed_step || 0) + 1, 6));
      }
      return config;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to load version';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  /**
   * Fetch existing draft or create new version via data-source step
   */
  const fetchOrCreateDraft = useCallback(async (
    targetAgentId: string,
    dataSourceId: string,
    existingVersionId?: number
  ): Promise<AgentConfig | null> => {
    setIsLoading(true);
    setError(null);
    setAgentId(targetAgentId);
    
    try {
      // If editing existing version, use that version_id
      if (existingVersionId) {
        const config = await saveDataSourceStep(targetAgentId, { 
          data_source_id: dataSourceId, 
          version_id: existingVersionId 
        });
        setDraft(config);
        setVersionId(config.id);
        setCurrentStep(Math.min((config.completed_step || 0) + 1, 6));
        return config;
      }
      
      // Try to get existing draft first
      const existingDraft = await getDraftConfig(targetAgentId);
      
      if (existingDraft) {
        setDraft(existingDraft);
        setVersionId(existingDraft.id);
        setCurrentStep(Math.min((existingDraft.completed_step || 0) + 1, 6));
        return existingDraft;
      }
      
      // Create new version via data-source step (no version_id = create new)
      const newDraft = await saveDataSourceStep(targetAgentId, { data_source_id: dataSourceId });
      setDraft(newDraft);
      setVersionId(newDraft.id);
      setCurrentStep(1);
      return newDraft;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to create draft';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Create a new draft directly (no existing draft check)
   * Use this when you already know there's no draft (e.g., after page load check)
   */
  const createNewDraft = useCallback(async (
    targetAgentId: string,
    dataSourceId: string
  ): Promise<AgentConfig | null> => {
    setIsLoading(true);
    setError(null);
    setAgentId(targetAgentId);
    
    try {
      // Create new version via data-source step (no version_id = create new)
      const newDraft = await saveDataSourceStep(targetAgentId, { data_source_id: dataSourceId });
      setDraft(newDraft);
      setVersionId(newDraft.id);
      setCurrentStep(2); // Move to step 2 after creating
      return newDraft;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to create draft';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  /**
   * Check if step data has changed from last saved state
   */
  const hasUnsavedChanges = useCallback((step: number, data: Record<string, unknown>): boolean => {
    const lastSaved = lastSavedRef.current[step] || {};
    return !isEqual(data, lastSaved);
  }, []);
  
  /**
   * Get data for a specific step from current draft
   */
  const getStepData = useCallback((step: number): Record<string, unknown> => {
    return extractStepData(draft, step);
  }, [draft]);
  
  /**
   * Save step-specific data with change detection using per-step APIs
   */
  const saveStep = useCallback(async (
    step: number,
    data: Record<string, unknown>
  ): Promise<AgentConfig | null> => {
    if (!agentId) {
      setError('No agent ID set');
      return null;
    }
    
    // Steps 2-5 require versionId
    if (step >= 2 && !versionId) {
      setError('No version ID set. Complete step 1 first.');
      return null;
    }
    
    // Check if data has actually changed
    if (!hasUnsavedChanges(step, data)) {
      console.log(`Step ${step}: No changes detected, skipping save`);
      // Just update current step if progressing forward
      if (step > currentStep) {
        setCurrentStep(step);
      }
      return draft;
    }
    
    setIsSaving(true);
    setError(null);
    
    try {
      let updated: AgentConfig;
      
      // Call appropriate per-step API
      switch (step) {
        case 1:
          // Step 1 can create or update (version_id optional)
          updated = await saveDataSourceStep(agentId, { 
            data_source_id: data.data_source_id as string,
            version_id: versionId ?? undefined,
          });
          // Update versionId if this created a new version
          setVersionId(updated.id);
          break;
        case 2: {
          // Always use selected_schema format: { table_name: columns[] }
          const selectedSchema = data.selected_columns as Record<string, string[]>;
          updated = await saveSchemaSelectionStep(agentId, versionId!, { 
            selected_schema: selectedSchema,
          });
          break;
        }
        case 3:
          updated = await saveDataDictionaryStep(agentId, versionId!, { 
            data_dictionary: data.data_dictionary as Record<string, unknown> 
          });
          break;
        case 4: {
          // Map to API format - strip model fields when model IDs are provided
          const embeddingModelId = data.embeddingModelId as number | undefined;
          const llmModelId = data.llmModelId as number | undefined;
          const rerankerModelId = data.rerankerModelId as number | undefined;
          
          // Build config objects, excluding model field when ID is provided
          const embeddingConfig = data.embedding_config as Record<string, unknown> | undefined;
          const llmConfig = data.llm_config as Record<string, unknown> | undefined;
          const ragConfig = data.rag_config as Record<string, unknown> | undefined;
          
          // Strip model from embedding config when embeddingModelId is set
          const cleanEmbeddingConfig = embeddingConfig ? { ...embeddingConfig } : undefined;
          if (cleanEmbeddingConfig && embeddingModelId) {
            delete cleanEmbeddingConfig.model;
          }
          
          // Strip model from llm config when llmModelId is set
          const cleanLlmConfig = llmConfig ? { ...llmConfig } : undefined;
          if (cleanLlmConfig && llmModelId) {
            delete cleanLlmConfig.model;
          }
          
          // Strip rerankerModel from rag config when rerankerModelId is set
          // Also normalize rerankEnabled (not rerankingEnabled)
          const cleanRagConfig = ragConfig ? { ...ragConfig } : undefined;
          if (cleanRagConfig) {
            if (rerankerModelId) {
              delete cleanRagConfig.rerankerModel;
            }
            // Remove any duplicate rerankingEnabled field
            delete cleanRagConfig.rerankingEnabled;
          }
          
          updated = await saveSettingsStep(agentId, versionId!, {
            embeddingConfig: cleanEmbeddingConfig,
            chunkingConfig: data.chunking_config as Record<string, unknown> | undefined,
            ragConfig: cleanRagConfig,
            llmConfig: cleanLlmConfig,
            // Pass model IDs from top level
            embeddingModelId,
            llmModelId,
            rerankerModelId,
          });
          break;
        }
        case 5:
          updated = await savePromptStep(agentId, versionId!, {
            system_prompt: data.system_prompt as string,
            example_questions: data.example_questions as string[] | undefined,
          });
          break;
        default:
          throw new Error(`Invalid step: ${step}`);
      }
      
      // Update local state
      setDraft(updated);
      lastSavedRef.current[step] = data;
      
      // Update current step if progressing forward
      if (step > currentStep) {
        setCurrentStep(step);
      }
      
      console.log(`Step ${step}: Saved successfully`);
      return updated;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to save step';
      setError(message);
      return null;
    } finally {
      setIsSaving(false);
    }
  }, [agentId, versionId, draft, currentStep, hasUnsavedChanges]);
  
  /**
   * Publish the version (make it active)
   */
  const publish = useCallback(async (
    systemPrompt: string,
    exampleQuestions?: string[]
  ): Promise<AgentConfig | null> => {
    if (!agentId || !versionId) {
      setError('No agent ID or version ID set');
      return null;
    }
    
    if (!systemPrompt?.trim()) {
      setError('System prompt is required');
      return null;
    }
    
    setIsPublishing(true);
    setError(null);
    
    try {
      const published = await publishVersion(agentId, versionId, {
        systemPrompt,
        exampleQuestions: exampleQuestions || [],
      });
      // Keep the published config in draft state so we can use its ID for embedding
      setDraft(published);
      return published;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to publish';
      setError(message);
      return null;
    } finally {
      setIsPublishing(false);
    }
  }, [agentId, versionId]);
  
  /**
   * Create a new draft by cloning an existing config
   */
  const createDraftFromConfig = useCallback(async (
    configId: number
  ): Promise<AgentConfig | null> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const newDraft = await cloneConfigAsDraft(configId);
      setDraft(newDraft);
      setVersionId(newDraft.id);
      setCurrentStep(6); // Cloned config has all steps completed
      return newDraft;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to create draft';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  /**
   * Discard the current version
   */
  const discardDraft = useCallback(async (): Promise<boolean> => {
    if (!agentId || !versionId) {
      return true;
    }
    
    setIsLoading(true);
    setError(null);
    
    try {
      await deleteVersion(agentId, versionId);
      setDraft(null);
      setVersionId(null);
      setCurrentStep(1);
      lastSavedRef.current = {};
      return true;
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const message = errorObj?.response?.data?.detail || errorObj?.message || 'Failed to delete version';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [agentId, versionId]);
  
  /**
   * Load configuration history for an agent
   */
  const loadHistory = useCallback(async (targetAgentId: string): Promise<void> => {
    try {
      const result = await getConfigHistory(targetAgentId);
      setConfigHistory(result.configs || []);
    } catch (err: unknown) {
      console.error('Failed to load config history:', err);
    }
  }, []);
  
  return {
    // State
    draft,
    agentId,
    versionId,
    isLoading,
    isSaving,
    isPublishing,
    error,
    currentStep,
    configHistory,
    
    // Actions
    fetchOrCreateDraft,
    createNewDraft,
    loadDraft,
    loadVersion,
    saveStep,
    publish,
    createDraftFromConfig,
    discardDraft,
    loadHistory,
    setCurrentStep,
    
    // Helpers
    hasUnsavedChanges,
    getStepData,
  };
}

export default useConfigDraft;
