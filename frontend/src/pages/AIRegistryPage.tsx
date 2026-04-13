/**
 * AI Models Page - Simplified Single-Table Design
 * 
 * Features:
 * - Add cloud models with API keys
 * - Add local models and download from HuggingFace
 * - Set default models per type
 * 
 * No providers needed - everything is on the model.
 */
import { useState, useEffect, useCallback } from 'react';
import ConfirmationModal from '../components/ConfirmationModal';
import ChatHeader from '../components/chat/ChatHeader';
import { APP_CONFIG } from '../config';

import {
  listAIModels,
  createAIModel,
  updateAIModel,
  deleteAIModel,
  searchHuggingFace,
  quickAddFromHuggingFace,
  startModelDownload,
  getDownloadProgress,
  cancelDownload,
  getAIModelDefaults,
  setAIModelDefault,
  type AIModel,
  type AIModelCreate,
  type AIModelUpdate,
  type ModelType,
  type DeploymentType,
  type DownloadStatus,
  type HFModelInfo,
  type DefaultsResponse,
} from '../services/api';

// ============================================
// Types
// ============================================

type TabType = 'models' | 'huggingface' | 'defaults';

const MODEL_TYPE_OPTIONS: { value: ModelType; label: string }[] = [
  { value: 'llm', label: 'LLM' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'reranker', label: 'Reranker' },
];

const DEPLOYMENT_TYPE_OPTIONS: { value: DeploymentType; label: string }[] = [
  { value: 'cloud', label: 'Cloud (API)' },
  { value: 'local', label: 'Local (Download)' },
];

const COMMON_PROVIDERS = ['openai', 'anthropic', 'cohere', 'huggingface', 'ollama', 'azure', 'google'];

const DOWNLOAD_STATUS_COLORS: Record<DownloadStatus, string> = {
  not_downloaded: 'bg-gray-100 text-gray-800',
  pending: 'bg-yellow-100 text-yellow-800',
  downloading: 'bg-blue-100 text-blue-800',
  ready: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
};

// ============================================
// Main Component
// ============================================

export default function AIRegistryPage() {
  const [activeTab, setActiveTab] = useState<TabType>('models');
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto">
          {/* Error Banner */}
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {error}
              <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700">×</button>
            </div>
          )}

          {/* Tabs */}
          <div className="border-b border-gray-200 mb-6">
            <nav className="flex space-x-8">
              {(['models', 'huggingface', 'defaults'] as TabType[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`py-3 px-1 border-b-2 font-medium text-sm ${activeTab === tab
                    ? 'border-indigo-500 text-indigo-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                >
                  {tab === 'models' && ' Models'}
                  {tab === 'huggingface' && ' HuggingFace'}
                  {tab === 'defaults' && ' Defaults'}
                </button>
              ))}
            </nav>
          </div>

          {/* Tab Content */}
          {activeTab === 'models' && <ModelsTab onError={setError} />}
          {activeTab === 'huggingface' && <HuggingFaceTab onError={setError} />}
          {activeTab === 'defaults' && <DefaultsTab onError={setError} />}
        </div>
      </main>
    </div>
  );
}

// ============================================
// Models Tab - CRUD for all models
// ============================================

interface TabProps {
  onError: (error: string | null) => void;
}

function ModelsTab({ onError }: TabProps) {
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingModel, setEditingModel] = useState<AIModel | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ show: boolean; model: AIModel | null }>({ show: false, model: null });

  // Filters
  const [filterType, setFilterType] = useState<string>('');
  const [filterDeployment, setFilterDeployment] = useState<string>('');

  const loadModels = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, string | boolean | undefined> = {};
      if (filterType) params.model_type = filterType;
      if (filterDeployment) params.deployment_type = filterDeployment;

      const response = await listAIModels(params);
      setModels(response.models);
    } catch (err) {
      onError('Failed to load models');
    } finally {
      setLoading(false);
    }
  }, [filterType, filterDeployment, onError]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // Download polling - track downloading IDs to avoid re-creating intervals
  const [downloadingIds, setDownloadingIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    // Update tracking set when models change
    const currentDownloading = new Set(
      models
        .filter(m => m.download_status === 'downloading' || m.download_status === 'pending')
        .map(m => m.id)
    );
    setDownloadingIds(currentDownloading);
  }, [models]);

  useEffect(() => {
    if (downloadingIds.size === 0) return;

    const interval = setInterval(async () => {
      for (const modelId of downloadingIds) {
        try {
          const progress = await getDownloadProgress(modelId);
          setModels(prev => prev.map(m =>
            m.id === modelId
              ? {
                ...m,
                download_status: progress.status,
                download_progress: progress.progress,
                download_error: progress.error,
                download_queue_position: progress.queue_position
              }
              : m
          ));
          // Stop tracking if completed or failed
          if (progress.status === 'ready' || progress.status === 'error' || progress.status === 'not_downloaded') {
            setDownloadingIds(prev => {
              const next = new Set(prev);
              next.delete(modelId);
              return next;
            });
          }
        } catch {
          // Ignore polling errors
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [downloadingIds]);

  const handleDelete = async () => {
    if (!deleteConfirm.model) return;
    try {
      await deleteAIModel(deleteConfirm.model.id);
      setDeleteConfirm({ show: false, model: null });
      loadModels();
    } catch (err) {
      onError('Failed to delete model');
    }
  };

  const handleDownload = async (model: AIModel) => {
    try {
      await startModelDownload(model.id);
      loadModels();
    } catch (err) {
      onError('Failed to start download');
    }
  };

  const handleCancelDownload = async (model: AIModel) => {
    try {
      await cancelDownload(model.id);
      loadModels();
    } catch (err) {
      onError('Failed to cancel download');
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex gap-4">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="">All Types</option>
            {MODEL_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={filterDeployment}
            onChange={(e) => setFilterDeployment(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="">All Deployments</option>
            {DEPLOYMENT_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <button
          onClick={() => { setEditingModel(null); setShowForm(true); }}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
          + Add Model
        </button>
      </div>

      {/* Models List */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Loading...</div>
      ) : models.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border">
          <p className="text-gray-500 mb-4">No models configured yet</p>
          <button
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            Add Your First Model
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {models.map(model => (
            <ModelCard
              key={model.id}
              model={model}
              onEdit={() => { setEditingModel(model); setShowForm(true); }}
              onDelete={() => setDeleteConfirm({ show: true, model })}
              onDownload={() => handleDownload(model)}
              onCancelDownload={() => handleCancelDownload(model)}
            />
          ))}
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <ModelForm
          model={editingModel}
          onClose={() => { setShowForm(false); setEditingModel(null); }}
          onSaved={() => { setShowForm(false); setEditingModel(null); loadModels(); }}
          onError={onError}
        />
      )}

      {/* Delete Confirmation */}
      <ConfirmationModal
        show={deleteConfirm.show}
        title="Delete Model"
        message={`Are you sure you want to delete "${deleteConfirm.model?.display_name}"?`}
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ show: false, model: null })}
        type="danger"
      />
    </div>
  );
}

// ============================================
// Model Card Component
// ============================================

interface ModelCardProps {
  model: AIModel;
  onEdit: () => void;
  onDelete: () => void;
  onDownload: () => void;
  onCancelDownload: () => void;
}

function ModelCard({ model, onEdit, onDelete, onDownload, onCancelDownload }: ModelCardProps) {
  return (
    <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h3 className="font-semibold text-gray-900">{model.display_name}</h3>
            {model.is_default && (
              <span className="px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs rounded-full">Default</span>
            )}
            <span className={`px-2 py-0.5 text-xs rounded-full ${model.model_type === 'llm' ? 'bg-purple-100 text-purple-800' :
              model.model_type === 'embedding' ? 'bg-blue-100 text-blue-800' :
                'bg-green-100 text-green-800'
              }`}>
              {(model.model_type || 'unknown').toUpperCase()}
            </span>
            <span className={`px-2 py-0.5 text-xs rounded-full ${model.deployment_type === 'cloud' ? 'bg-sky-100 text-sky-800' : 'bg-orange-100 text-orange-800'
              }`}>
              {model.deployment_type}
            </span>
          </div>

          <p className="text-sm text-gray-500 mb-2">
            <span className="font-mono">{model.model_id}</span>
            {model.provider_name && <span className="ml-2">({model.provider_name})</span>}
          </p>

          {/* Cloud Info */}
          {model.deployment_type === 'cloud' && (
            <div className="text-sm text-gray-600">
              {model.has_api_key ? (
                <span className="text-green-600">✓ API Key configured</span>
              ) : model.api_key_env_var ? (
                <span className="text-blue-600">🔑 Using {model.api_key_env_var}</span>
              ) : (
                <span className="text-yellow-600">⚠ No API key</span>
              )}
            </div>
          )}

          {/* Local Info */}
          {model.deployment_type === 'local' && (
            <div className="flex items-center gap-2 mt-2">
              <span className={`px-2 py-0.5 text-xs rounded-full ${DOWNLOAD_STATUS_COLORS[model.download_status]}`}>
                {model.download_status.replace('_', ' ')}
                {model.download_status === 'pending' && model.download_queue_position && (
                  <span className="ml-1">(#{model.download_queue_position} in queue)</span>
                )}
              </span>
              {model.download_status === 'downloading' && (
                <div className="flex items-center gap-2">
                  <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${model.download_progress}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500">{model.download_progress}%</span>
                </div>
              )}
              {model.download_error && (
                <span className="text-xs text-red-600">{model.download_error}</span>
              )}
            </div>
          )}

          {/* Specs */}
          <div className="flex gap-4 mt-2 text-xs text-gray-500">
            {model.context_length && <span>Context: {model.context_length.toLocaleString()}</span>}
            {model.dimensions && <span>Dims: {model.dimensions}</span>}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {model.deployment_type === 'local' && model.download_status === 'not_downloaded' && (
            <button
              onClick={onDownload}
              className="px-3 py-1 text-sm bg-blue-50 text-blue-600 rounded hover:bg-blue-100"
            >
              Download
            </button>
          )}
          {model.deployment_type === 'local' && (model.download_status === 'downloading' || model.download_status === 'pending') && (
            <button
              onClick={onCancelDownload}
              className="px-3 py-1 text-sm bg-red-50 text-red-600 rounded hover:bg-red-100"
            >
              Cancel
            </button>
          )}
          <button
            onClick={onEdit}
            className="px-3 py-1 text-sm bg-gray-50 text-gray-600 rounded hover:bg-gray-100"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1 text-sm bg-red-50 text-red-600 rounded hover:bg-red-100"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Model Form Modal
// ============================================

interface ModelFormProps {
  model: AIModel | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: string | null) => void;
}

function ModelForm({ model, onClose, onSaved, onError }: ModelFormProps) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState<AIModelCreate>({
    model_id: model?.model_id || '',
    display_name: model?.display_name || '',
    model_type: model?.model_type || 'llm',
    provider_name: model?.provider_name || 'openai',
    deployment_type: model?.deployment_type || 'cloud',
    api_base_url: model?.api_base_url || '',
    api_key: '',
    api_key_env_var: model?.api_key_env_var || '',
    hf_model_id: model?.hf_model_id || '',
    context_length: model?.context_length || undefined,
    dimensions: model?.dimensions || undefined,
    description: model?.description || '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (model) {
        const updateData: AIModelUpdate = {
          display_name: form.display_name,
          api_base_url: form.api_base_url || undefined,
          api_key: form.api_key || undefined,
          api_key_env_var: form.api_key_env_var || undefined,
          context_length: form.context_length,
          dimensions: form.dimensions,
          description: form.description || undefined,
        };
        await updateAIModel(model.id, updateData);
      } else {
        await createAIModel(form);
      }
      onSaved();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save model';
      onError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b">
          <h2 className="text-xl font-semibold">{model ? 'Edit Model' : 'Add Model'}</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Model ID *</label>
              <input
                type="text"
                value={form.model_id}
                onChange={(e) => setForm(f => ({ ...f, model_id: e.target.value }))}
                placeholder="openai/gpt-4o"
                className="w-full px-3 py-2 border rounded-lg"
                required
                disabled={!!model}
              />
              <p className="text-xs text-gray-500 mt-1">Format: provider/model-name</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name *</label>
              <input
                type="text"
                value={form.display_name}
                onChange={(e) => setForm(f => ({ ...f, display_name: e.target.value }))}
                placeholder="GPT-4o"
                className="w-full px-3 py-2 border rounded-lg"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type *</label>
              <select
                value={form.model_type}
                onChange={(e) => setForm(f => ({ ...f, model_type: e.target.value as ModelType }))}
                className="w-full px-3 py-2 border rounded-lg"
                disabled={!!model}
              >
                {MODEL_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Provider *</label>
              <input
                type="text"
                list="providers"
                value={form.provider_name}
                onChange={(e) => setForm(f => ({ ...f, provider_name: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg"
                required
                disabled={!!model}
              />
              <datalist id="providers">
                {COMMON_PROVIDERS.map(p => <option key={p} value={p} />)}
              </datalist>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Deployment *</label>
              <select
                value={form.deployment_type}
                onChange={(e) => setForm(f => ({ ...f, deployment_type: e.target.value as DeploymentType }))}
                className="w-full px-3 py-2 border rounded-lg"
                disabled={!!model}
              >
                {DEPLOYMENT_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Cloud Config */}
          {form.deployment_type === 'cloud' && (
            <div className="border-t pt-4">
              <h3 className="font-medium text-gray-900 mb-3">Cloud Configuration</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API Base URL</label>
                  <input
                    type="text"
                    value={form.api_base_url}
                    onChange={(e) => setForm(f => ({ ...f, api_base_url: e.target.value }))}
                    placeholder="https://api.openai.com/v1"
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={(e) => setForm(f => ({ ...f, api_key: e.target.value }))}
                    placeholder={model?.has_api_key ? '••••••••' : 'sk-...'}
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                  <p className="text-xs text-gray-500 mt-1">Leave blank to keep existing</p>
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Or use Environment Variable</label>
                  <input
                    type="text"
                    value={form.api_key_env_var}
                    onChange={(e) => setForm(f => ({ ...f, api_key_env_var: e.target.value }))}
                    placeholder="OPENAI_API_KEY"
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Local Config */}
          {form.deployment_type === 'local' && (
            <div className="border-t pt-4">
              <h3 className="font-medium text-gray-900 mb-3">Local Configuration</h3>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">HuggingFace Model ID</label>
                <input
                  type="text"
                  value={form.hf_model_id}
                  onChange={(e) => setForm(f => ({ ...f, hf_model_id: e.target.value }))}
                  placeholder="BAAI/bge-m3"
                  className="w-full px-3 py-2 border rounded-lg"
                />
                <p className="text-xs text-gray-500 mt-1">Required for downloading</p>
              </div>
            </div>
          )}

          {/* Model Specs */}
          <div className="border-t pt-4">
            <h3 className="font-medium text-gray-900 mb-3">Model Specifications</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Context Length</label>
                <input
                  type="number"
                  value={form.context_length || ''}
                  onChange={(e) => setForm(f => ({ ...f, context_length: e.target.value ? parseInt(e.target.value) : undefined }))}
                  placeholder="128000"
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dimensions</label>
                <input
                  type="number"
                  value={form.dimensions || ''}
                  onChange={(e) => setForm(f => ({ ...f, dimensions: e.target.value ? parseInt(e.target.value) : undefined }))}
                  placeholder="1024"
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full px-3 py-2 border rounded-lg"
              rows={2}
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? 'Saving...' : (model ? 'Update' : 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================
// HuggingFace Tab
// ============================================

function HuggingFaceTab({ onError }: TabProps) {
  const [query, setQuery] = useState('');
  const [modelType, setModelType] = useState<ModelType>('embedding');
  const [results, setResults] = useState<HFModelInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    try {
      const response = await searchHuggingFace({ query, model_type: modelType, limit: 20 });
      setResults(response.models);
    } catch (err) {
      onError('Failed to search HuggingFace');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAdd = async (hfModel: HFModelInfo, autoDownload: boolean) => {
    setAdding(hfModel.model_id);
    try {
      await quickAddFromHuggingFace({
        hf_model_id: hfModel.model_id,
        model_type: modelType,
        display_name: hfModel.model_name,
        auto_download: autoDownload,
      });
      // Mark as registered
      setResults(prev => prev.map(m =>
        m.model_id === hfModel.model_id ? { ...m, is_registered: true } : m
      ));
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to add model';
      onError(errorMessage);
    } finally {
      setAdding(null);
    }
  };

  return (
    <div>
      {/* Search Form */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h3 className="font-semibold mb-4">Search HuggingFace Hub</h3>
        <div className="flex gap-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search models (e.g., bge-m3, all-MiniLM)..."
            className="flex-1 px-4 py-2 border rounded-lg"
          />
          <select
            value={modelType}
            onChange={(e) => setModelType(e.target.value as ModelType)}
            className="px-4 py-2 border rounded-lg"
          >
            {MODEL_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="grid gap-3">
          {results.map(hfModel => (
            <div key={hfModel.model_id} className="bg-white border rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="font-medium text-gray-900">{hfModel.model_name}</h4>
                  <p className="text-sm text-gray-500">{hfModel.author}/{hfModel.model_name}</p>
                  <div className="flex gap-4 mt-2 text-xs text-gray-500">
                    <span>⬇️ {hfModel.downloads.toLocaleString()}</span>
                    <span>❤️ {hfModel.likes}</span>
                    {hfModel.pipeline_tag && <span>📦 {hfModel.pipeline_tag}</span>}
                  </div>
                </div>
                <div className="flex gap-2">
                  {hfModel.is_registered ? (
                    <span className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm">Added</span>
                  ) : (
                    <>
                      <button
                        onClick={() => handleQuickAdd(hfModel, false)}
                        disabled={adding === hfModel.model_id}
                        className="px-3 py-1 text-sm bg-gray-50 text-gray-700 rounded hover:bg-gray-100 disabled:opacity-50"
                      >
                        Add
                      </button>
                      <button
                        onClick={() => handleQuickAdd(hfModel, true)}
                        disabled={adding === hfModel.model_id}
                        className="px-3 py-1 text-sm bg-indigo-50 text-indigo-700 rounded hover:bg-indigo-100 disabled:opacity-50"
                      >
                        {adding === hfModel.model_id ? 'Adding...' : 'Add & Download'}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================
// Defaults Tab
// ============================================

function DefaultsTab({ onError }: TabProps) {
  const [defaults, setDefaults] = useState<DefaultsResponse>({ llm: undefined, embedding: undefined, reranker: undefined });
  const [models, setModels] = useState<AIModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [defaultsRes, modelsRes] = await Promise.all([
          getAIModelDefaults(),
          listAIModels({ is_active: true })
        ]);
        setDefaults(defaultsRes);
        setModels(modelsRes.models);
      } catch (err) {
        onError('Failed to load defaults');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [onError]);

  const handleSetDefault = async (modelType: ModelType, modelId: number) => {
    try {
      const response = await setAIModelDefault(modelType, modelId);
      setDefaults(response);
    } catch (err) {
      onError('Failed to set default');
    }
  };

  if (loading) {
    return <div className="text-center py-8 text-gray-500">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      {MODEL_TYPE_OPTIONS.map(({ value: type, label }) => {
        const typeModels = models.filter(m => m.model_type === type && m.is_ready);
        const currentDefault = defaults[type];

        return (
          <div key={type} className="bg-white border rounded-lg p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Default {label}</h3>

            {typeModels.length === 0 ? (
              <p className="text-gray-500">No ready {label.toLowerCase()} models available</p>
            ) : (
              <div className="space-y-2">
                {typeModels.map(model => (
                  <label key={model.id} className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name={`default-${type}`}
                      checked={currentDefault?.id === model.id}
                      onChange={() => handleSetDefault(type, model.id)}
                      className="w-4 h-4 text-indigo-600"
                    />
                    <div className="flex-1">
                      <span className="font-medium">{model.display_name}</span>
                      <span className="ml-2 text-sm text-gray-500 font-mono">{model.model_id}</span>
                    </div>
                    <span className={`px-2 py-0.5 text-xs rounded-full ${model.deployment_type === 'cloud' ? 'bg-sky-100 text-sky-800' : 'bg-orange-100 text-orange-800'
                      }`}>
                      {model.deployment_type}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
