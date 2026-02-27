import React from 'react';
import ConfigSummary from '../../ConfigSummary';
import type { ActiveConfig, AdvancedSettings, PromptVersion, VectorDbStatus } from '../../../contexts/AgentContext';

interface OverviewTabProps {
    activeConfig: ActiveConfig;
    connectionName: string;
    advancedSettings: AdvancedSettings;
    history: PromptVersion[];
    vectorDbStatus: VectorDbStatus | null;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
    activeConfig,
    connectionName,
    advancedSettings,
    history,
    vectorDbStatus
}) => {
    return (
        <div className="space-y-8">
            <ConfigSummary
                connectionId={activeConfig.connection_id ?? null}
                connectionName={connectionName}
                dataSourceType={activeConfig.data_source_type as any || 'database'}
                schema={activeConfig.schema_selection ? JSON.parse(activeConfig.schema_selection) : {}}
                dataDictionary={activeConfig.data_dictionary || ''}
                activePromptVersion={activeConfig.version}
                totalPromptVersions={history.length}
                lastUpdatedBy={activeConfig.created_by_username}
                settings={advancedSettings}
            />

            {/* Quick Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Agent Status</h3>
                    <div className="flex items-center gap-2">
                        <span className="flex h-3 w-3 rounded-full bg-green-500"></span>
                        <span className="text-xl font-bold text-gray-900">Active</span>
                    </div>
                </div>
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Total Versions</h3>
                    <div className="flex items-center gap-2">
                        <span className="text-xl font-bold text-gray-900">{history.length}</span>
                        <span className="text-xs text-gray-400 font-medium">Published Prompts</span>
                    </div>
                </div>
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Knowledge Freshness</h3>
                    <div className="flex items-center gap-2">
                        <span className="text-xl font-bold text-gray-900">
                            {vectorDbStatus?.last_updated_at ? 'Synced' : 'Not Run'}
                        </span>
                        <span className="text-xs text-gray-400 font-medium">Vector DB</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default OverviewTab;
