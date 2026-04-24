import React from 'react';
import type { ActiveConfig, ModelInfo } from '../../../contexts/AgentContext';
import type { Agent } from '../../../types/agent';
import AgentDetailsCard from '../../AgentDetailsCard';
import AgentDangerZone from '../../AgentDangerZone';
import { CircleStackIcon, SparklesIcon, AdjustmentsHorizontalIcon } from '@heroicons/react/24/outline';

interface OverviewTabProps {
    activeConfig: ActiveConfig;
    connectionName: string;
    agent?: Agent;
    canEdit?: boolean;
    onAgentUpdate?: () => void;
}

// Helper to format model display
const ModelDisplay: React.FC<{ label: string; model?: ModelInfo; fallback?: string }> = ({ label, model, fallback }) => (
    <div className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0">
        <span className="text-sm text-gray-500">{label}</span>
        <span className="text-sm font-medium text-gray-900">
            {model ? (
                <span className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded">{model.provider_name}</span>
                    {model.display_name}
                </span>
            ) : fallback || 'Not configured'}
        </span>
    </div>
);

export const OverviewTab: React.FC<OverviewTabProps> = ({
    activeConfig,
    connectionName,
    agent,
    canEdit = false,
    onAgentUpdate
}) => {
    const parseConfig = (config: string | undefined | null) => {
        if (!config) return {};
        try {
            return typeof config === 'string' ? JSON.parse(config) : config;
        } catch {
            return {};
        }
    };

    const llmConf = parseConfig(activeConfig.llm_config);
    const embConf = parseConfig(activeConfig.embedding_config);
    const retConf = parseConfig(activeConfig.retriever_config);

    // Build fileInfo from activeConfig for file-based data sources
    const fileInfo = activeConfig.data_source_type === 'file' && activeConfig.ingestion_file_name
        ? { name: activeConfig.ingestion_file_name, type: activeConfig.ingestion_file_type || 'unknown' }
        : undefined;

    // Parse schema from schema_selection (works for both file and database sources)
    // schema_selection contains the selected_columns from agent config
    let schema: Record<string, string[]> = {};
    if (activeConfig.schema_selection) {
        try {
            const parsed = typeof activeConfig.schema_selection === 'string'
                ? JSON.parse(activeConfig.schema_selection)
                : activeConfig.schema_selection;
            if (typeof parsed === 'object' && parsed !== null && Object.keys(parsed).length > 0) {
                schema = parsed;
            }
        } catch {
            schema = {};
        }
    }

    // Helper to mask sensitive info in DB URL
    const maskDbUrl = (url?: string) => {
        if (!url) return '';
        try {
            // Simple regex to mask password in common DB URIs
            // e.g., postgresql://user:password@host:port/db -> postgresql://user:****@host:port/db
            return url.replace(/:\/\/([^:]+):([^@]+)@/, '://$1:****@');
        } catch {
            return url;
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">


            {/* Main Content Grid */}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* Agent Details Section - At top */}
                {agent && (
                    <AgentDetailsCard
                        agent={agent}
                        canEdit={canEdit}
                        onAgentUpdate={onAgentUpdate}
                    />
                )}
                {/* Data Source Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
                            <CircleStackIcon className="w-5 h-5 text-indigo-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">Data Source</h3>
                            <p className="text-xs text-gray-500">Connected knowledge source</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Type</span>
                            <span className="text-sm font-medium text-gray-900 capitalize">{activeConfig.data_source_type || 'Database'}</span>
                        </div>
                        {activeConfig.data_source_type === 'database' ? (
                            <>
                                <div className="flex justify-between py-2 border-b border-gray-100">
                                    <span className="text-sm text-gray-500">Connection</span>
                                    <span className="text-sm font-medium text-gray-900">{connectionName || 'Not set'}</span>
                                </div>
                                {activeConfig.db_url && (
                                    <div className="flex flex-col py-2 border-b border-gray-100">
                                        <span className="text-sm text-gray-500 mb-1">Endpoint</span>
                                        <span className="text-xs font-mono text-gray-600 break-all bg-gray-50 p-2 rounded-md border border-gray-100">
                                            {maskDbUrl(activeConfig.db_url)}
                                        </span>
                                    </div>
                                )}
                            </>
                        ) : (
                            <div className="flex justify-between py-2 border-b border-gray-100">
                                <span className="text-sm text-gray-500">File</span>
                                <span className="text-sm font-medium text-gray-900">{fileInfo?.name || 'Not set'}</span>
                            </div>
                        )}
                        <div className="flex justify-between py-2">
                            <span className="text-sm text-gray-500">Tables/Columns</span>
                            <span className="text-sm font-medium text-gray-900">
                                {Object.keys(schema).length} tables, {Object.values(schema).flat().length} columns
                            </span>
                        </div>
                    </div>
                </div>

                {/* AI Models Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center">
                            <SparklesIcon className="w-5 h-5 text-purple-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">AI Models</h3>
                            <p className="text-xs text-gray-500">Intelligence configuration</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <ModelDisplay
                            label="LLM"
                            model={activeConfig.llm_model}
                            fallback={llmConf.model}
                        />
                        <ModelDisplay
                            label="Embedding"
                            model={activeConfig.embedding_model}
                            fallback={embConf.model}
                        />
                        <ModelDisplay
                            label="Reranker"
                            model={activeConfig.reranker_model}
                            fallback={retConf.rerankerModel || retConf.reranker_model}
                        />
                    </div>
                </div>

                {/* RAG Settings Card */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center">
                            <AdjustmentsHorizontalIcon className="w-5 h-5 text-green-600" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-gray-900">RAG Settings</h3>
                            <p className="text-xs text-gray-500">Retrieval configuration</p>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Top K (Initial)</span>
                            <span className="text-sm font-medium text-gray-900">{retConf.topKInitial || retConf.top_k_initial || 50}</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Top K (Final)</span>
                            <span className="text-sm font-medium text-gray-900">{retConf.topKFinal || retConf.top_k_final || 10}</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-100">
                            <span className="text-sm text-gray-500">Reranking</span>
                            {(() => {
                                const isEnabled = activeConfig.reranker_model || activeConfig.reranker_model_id || retConf.rerankEnabled || retConf.rerank_enabled;
                                return (
                                    <span className={`text-sm font-medium ${isEnabled ? 'text-green-600' : 'text-gray-400'}`}>
                                        {isEnabled ? 'Enabled' : 'Disabled'}
                                    </span>
                                );
                            })()}
                        </div>
                        <div className="flex justify-between py-2">
                            <span className="text-sm text-gray-500">Hybrid Weights</span>
                            <span className="text-sm font-medium text-gray-900">
                                {(retConf.hybridWeights || retConf.hybrid_weights || [0.75, 0.25]).join(' / ')}
                            </span>
                        </div>
                    </div>
                </div>

            </div>

            {/* Danger Zone - Delete Agent */}
            {agent && canEdit && (
                <AgentDangerZone agent={agent} />
            )}
        </div>
    );
};

export default OverviewTab;
