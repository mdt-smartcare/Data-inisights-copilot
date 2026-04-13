/**
 * AIModelSelector - Dropdown component for selecting AI models from the registry.
 * 
 * Used in agent configuration for selecting:
 * - LLM models for chat/generation
 * - Embedding models for vectorization
 * - Reranker models for retrieval refinement
 */
import React from 'react';
import type { AvailableModel } from '../services/api';

interface AIModelSelectorProps {
  /** Type of model being selected */
  modelType: 'llm' | 'embedding' | 'reranker';
  /** Available models to choose from */
  models: AvailableModel[];
  /** Currently selected model_id (e.g., "openai/gpt-4o") */
  selectedModelId: string | null;
  /** Callback when selection changes */
  onSelect: (modelId: string) => void;
  /** Whether selector is disabled */
  disabled?: boolean;
  /** Loading state */
  isLoading?: boolean;
  /** Error message */
  error?: string | null;
  /** Label override */
  label?: string;
  /** Show provider badges */
  showProvider?: boolean;
  /** Compact mode */
  compact?: boolean;
}

const MODEL_TYPE_CONFIG = {
  llm: {
    label: 'LLM Model',
    description: 'Language model for generating responses',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
      </svg>
    ),
    emptyMessage: 'No LLM models available. Add models in AI Registry.'
  },
  embedding: {
    label: 'Embedding Model',
    description: 'Model for text vectorization',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
    ),
    emptyMessage: 'No embedding models available. Add models in AI Registry.'
  },
  reranker: {
    label: 'Reranker Model',
    description: 'Model for re-ranking search results',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
      </svg>
    ),
    emptyMessage: 'No reranker models available. Add models in AI Registry.'
  }
};

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-green-100 text-green-800',
  anthropic: 'bg-orange-100 text-orange-800',
  huggingface: 'bg-yellow-100 text-yellow-800',
  google: 'bg-blue-100 text-blue-800',
  azure: 'bg-cyan-100 text-cyan-800',
  ollama: 'bg-purple-100 text-purple-800',
  local: 'bg-gray-100 text-gray-800',
};

export const AIModelSelector: React.FC<AIModelSelectorProps> = ({
  modelType,
  models,
  selectedModelId,
  onSelect,
  disabled = false,
  isLoading = false,
  error = null,
  label,
  showProvider = true,
  compact = false
}) => {
  const config = MODEL_TYPE_CONFIG[modelType];
  const selectedModel = models.find(m => m.model_id === selectedModelId);

  if (isLoading) {
    return (
      <div className={`${compact ? 'py-2' : 'p-4'} bg-gray-50 rounded-lg border border-gray-200`}>
        <div className="flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />
          <span className="text-sm text-gray-500">Loading models...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`${compact ? 'py-2' : 'p-4'} bg-red-50 rounded-lg border border-red-200`}>
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className={compact ? '' : 'space-y-2'}>
      {/* Label */}
      {!compact && (
        <div className="flex items-center gap-2">
          <span className="text-indigo-600">{config.icon}</span>
          <label className="block text-sm font-medium text-gray-700">
            {label || config.label}
          </label>
        </div>
      )}

      {/* Select */}
      <div className="relative">
        <select
          value={selectedModelId || ''}
          onChange={(e) => onSelect(e.target.value)}
          disabled={disabled || models.length === 0}
          className={`
            w-full rounded-lg border-gray-300 shadow-sm 
            focus:border-blue-500 focus:ring-blue-500
            ${compact ? 'text-sm py-1.5 pl-3 pr-8' : 'text-sm py-2 pl-3 pr-10'}
            ${disabled ? 'bg-gray-100 cursor-not-allowed' : 'bg-white cursor-pointer'}
            appearance-none
          `}
        >
          {models.length === 0 ? (
            <option value="">No models available</option>
          ) : (
            <>
              <option value="">Select a model...</option>
              {models.map(model => (
                <option key={model.id} value={model.model_id}>
                  {model.display_name}
                  {model.is_default ? ' (Default) ' : ''}
                  {model.dimensions ? ` (${model.dimensions}d)` : ''}
                  {model.context_length ? ` (${Math.round(model.context_length / 1000)}k ctx)` : ''}
                </option>
              ))}
            </>
          )}
        </select>

        {/* Dropdown Arrow */}
        <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
          <svg className="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Selected Model Info */}
      {selectedModel && showProvider && !compact && (
        <div className="flex items-center gap-2 mt-2">
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${PROVIDER_COLORS[selectedModel.provider_name] || PROVIDER_COLORS.local}`}>
            {selectedModel.provider_name}
          </span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${selectedModel.deployment_type === 'local' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'
            }`}>
            {selectedModel.deployment_type}
          </span>
          {selectedModel.is_default && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
              Default
            </span>
          )}
        </div>
      )}

      {/* Empty State */}
      {models.length === 0 && !compact && (
        <p className="text-xs text-gray-500 mt-1">{config.emptyMessage}</p>
      )}
    </div>
  );
};

export default AIModelSelector;
