/**
 * ConfigVersionHistory - Displays version history with rollback capability.
 * 
 * Shows all configuration versions for an agent with:
 * - Version number and status (draft/published/active)
 * - Created date and data source info
 * - Rollback/activate buttons
 * - Diff preview (optional)
 */
import React, { useState, useEffect } from 'react';
import {
  ClockIcon,
  CheckCircleIcon,
  DocumentDuplicateIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  PencilSquareIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { getConfigHistory, activateConfig, type AgentConfig } from '../../services/api';
import { formatDateTime } from '../../utils/datetime';

interface ConfigVersionHistoryProps {
  agentId: string;
  onRollback?: (config: AgentConfig) => void;
  onCloneAsDraft?: (configId: number) => void;
  className?: string;
}

const ConfigVersionHistory: React.FC<ConfigVersionHistoryProps> = ({
  agentId,
  onRollback,
  onCloneAsDraft,
  className = '',
}) => {
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [confirmRollback, setConfirmRollback] = useState<AgentConfig | null>(null);

  const loadHistory = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await getConfigHistory(agentId);
      setConfigs(result.configs || []);
    } catch (err) {
      setError('Failed to load version history');
      console.error('Failed to load config history:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const handleActivate = async (config: AgentConfig) => {
    if (config.status === 'draft') {
      setError('Cannot activate a draft. Publish it first.');
      return;
    }

    setActivatingId(config.id);
    try {
      await activateConfig(config.id);
      await loadHistory(); // Refresh list
      onRollback?.(config);
    } catch (err) {
      setError('Failed to activate configuration');
      console.error('Failed to activate config:', err);
    } finally {
      setActivatingId(null);
      setConfirmRollback(null);
    }
  };

  const getStatusBadge = (config: AgentConfig) => {
    if (config.status === 'draft') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
          <PencilSquareIcon className="w-3 h-3" />
          Draft
        </span>
      );
    }
    if (config.is_active) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
          <CheckCircleIcon className="w-3 h-3" />
          Active
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
        <ClockIcon className="w-3 h-3" />
        v{config.version}
      </span>
    );
  };

  const getStepProgress = (completedStep: number) => {
    const stepNames = ['Not Started', 'Data Source', 'Schema', 'Dictionary', 'Settings', 'Prompt', 'Complete'];
    if (completedStep >= 5) return 'All steps completed - Ready to publish';
    return `${completedStep}/5 steps completed - ${stepNames[completedStep + 1] || 'Next'} next`;
  };

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center py-8 ${className}`}>
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
        <span className="ml-2 text-gray-500">Loading history...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`p-4 bg-red-50 rounded-lg ${className}`}>
        <div className="flex items-center gap-2 text-red-600">
          <ExclamationTriangleIcon className="w-5 h-5" />
          <span>{error}</span>
        </div>
        <button
          onClick={loadHistory}
          className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (configs.length === 0) {
    return (
      <div className={`p-6 text-center text-gray-500 bg-gray-50 rounded-lg ${className}`}>
        <ClockIcon className="w-10 h-10 mx-auto mb-2 text-gray-400" />
        <p>No configuration versions yet.</p>
        <p className="text-sm">Complete the setup wizard to create your first configuration.</p>
      </div>
    );
  }

  // Separate draft and published configs
  const draftConfig = configs.find(c => c.status === 'draft');
  const publishedConfigs = configs.filter(c => c.status === 'published');

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Rollback Confirmation Modal */}
      {confirmRollback && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-yellow-100 rounded-full">
                <ArrowPathIcon className="w-6 h-6 text-yellow-600" />
              </div>
              <h3 className="text-lg font-semibold">Confirm Rollback</h3>
            </div>
            <p className="text-gray-600 mb-4">
              Are you sure you want to activate <strong>Version {confirmRollback.version}</strong>?
              This will make it the active configuration for this agent.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmRollback(null)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={() => handleActivate(confirmRollback)}
                disabled={activatingId === confirmRollback.id}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
              >
                {activatingId === confirmRollback.id ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Activating...
                  </>
                ) : (
                  <>
                    <ArrowPathIcon className="w-4 h-4" />
                    Activate
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Draft Section */}
      {draftConfig && (
        <div className="border-2 border-yellow-200 bg-yellow-50 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {getStatusBadge(draftConfig)}
              <span className="text-sm text-yellow-700">
                {getStepProgress(draftConfig.completed_step)}
              </span>
            </div>
            <span className="text-xs text-gray-500">
              {formatDateTime(draftConfig.updated_at)}
            </span>
          </div>
          <p className="text-sm text-yellow-800">
            You have an incomplete draft configuration. Continue editing to publish it.
          </p>
        </div>
      )}

      {/* Published Versions */}
      <div className="border rounded-lg divide-y">
        <div className="px-4 py-3 bg-gray-50 border-b">
          <h3 className="font-medium text-gray-900 flex items-center gap-2">
            <ClockIcon className="w-5 h-5 text-gray-500" />
            Version History
            <span className="text-sm font-normal text-gray-500">
              ({publishedConfigs.length} version{publishedConfigs.length !== 1 ? 's' : ''})
            </span>
          </h3>
        </div>

        {publishedConfigs.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            No published versions yet.
          </div>
        ) : (
          publishedConfigs.map((config) => (
            <div key={config.id} className="bg-white">
              {/* Version Header */}
              <div
                className={`px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 ${
                  expandedId === config.id ? 'bg-gray-50' : ''
                }`}
                onClick={() => setExpandedId(expandedId === config.id ? null : config.id)}
              >
                <div className="flex items-center gap-3">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                    <span className="font-medium text-gray-900">Version {config.version}</span>
                    {getStatusBadge(config)}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500 hidden sm:inline">
                    {formatDateTime(config.created_at)}
                  </span>
                  {expandedId === config.id ? (
                    <ChevronUpIcon className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDownIcon className="w-5 h-5 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === config.id && (
                <div className="px-4 py-3 bg-gray-50 border-t space-y-3">
                  {/* Config Details */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500">Created:</span>{' '}
                      <span className="text-gray-900">{formatDateTime(config.created_at)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Data Source:</span>{' '}
                      <span className="text-gray-900">
                        {config.data_source?.title || config.data_source_id.slice(0, 8) + '...'}
                      </span>
                    </div>
                    {config.embedding_status && (
                      <div>
                        <span className="text-gray-500">Embedding:</span>{' '}
                        <span className={`${
                          config.embedding_status === 'completed' ? 'text-green-600' :
                          config.embedding_status === 'in_progress' ? 'text-yellow-600' :
                          'text-gray-600'
                        }`}>
                          {config.embedding_status}
                        </span>
                      </div>
                    )}
                    {config.system_prompt && (
                      <div className="sm:col-span-2">
                        <span className="text-gray-500">Prompt Preview:</span>
                        <p className="mt-1 text-gray-700 text-xs line-clamp-2 bg-white p-2 rounded border">
                          {config.system_prompt.slice(0, 200)}...
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-wrap gap-2 pt-2 border-t">
                    {!config.is_active && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmRollback(config);
                        }}
                        className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-1"
                      >
                        <ArrowPathIcon className="w-4 h-4" />
                        Rollback to This Version
                      </button>
                    )}
                    {onCloneAsDraft && !draftConfig && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCloneAsDraft(config.id);
                        }}
                        className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-100 flex items-center gap-1"
                      >
                        <DocumentDuplicateIcon className="w-4 h-4" />
                        Clone as Draft
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Refresh Button */}
      <div className="flex justify-center">
        <button
          onClick={loadHistory}
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          <ArrowPathIcon className="w-4 h-4" />
          Refresh History
        </button>
      </div>
    </div>
  );
};

export default ConfigVersionHistory;
