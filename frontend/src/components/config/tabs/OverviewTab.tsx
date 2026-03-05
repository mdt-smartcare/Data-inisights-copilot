import React, { useEffect, useState } from 'react';
import ConfigSummary from '../../ConfigSummary';
import type { ActiveConfig, AdvancedSettings, PromptVersion, VectorDbStatus } from '../../../contexts/AgentContext';
import { getFileSqlTables } from '../../../services/api';

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
    const [fileSchema, setFileSchema] = useState<Record<string, string[]>>({});

    // Build fileInfo from activeConfig for file-based data sources
    const fileInfo = activeConfig.data_source_type === 'file' && activeConfig.ingestion_file_name
        ? { name: activeConfig.ingestion_file_name, type: activeConfig.ingestion_file_type || 'unknown' }
        : undefined;

    // Fetch file schema from DuckDB for file-based sources
    useEffect(() => {
        if (activeConfig.data_source_type === 'file') {
            getFileSqlTables()
                .then((response) => {
                    if (response && response.tables && response.tables.length > 0) {
                        // Build schema from file tables
                        const schema: Record<string, string[]> = {};
                        response.tables.forEach((table: any) => {
                            schema[table.name || table.original_filename] = table.columns || [];
                        });
                        setFileSchema(schema);
                    }
                })
                .catch((err) => {
                    console.log('Could not fetch file tables:', err);
                });
        }
    }, [activeConfig.data_source_type]);

    // Parse schema - for file sources, use fetched fileSchema
    let schema: Record<string, string[]> = {};
    if (activeConfig.data_source_type === 'file') {
        schema = fileSchema;
    } else if (activeConfig.schema_selection) {
        try {
            const parsed = JSON.parse(activeConfig.schema_selection);
            // Handle both formats: {table: [cols]} or just {table: cols}
            if (typeof parsed === 'object' && Object.keys(parsed).length > 0) {
                schema = parsed;
            }
        } catch {
            schema = {};
        }
    }
    
    // Fallback: try to extract from data_dictionary if still empty
    if (Object.keys(schema).length === 0 && activeConfig.data_dictionary) {
        const columnMatches = activeConfig.data_dictionary.match(/^\s*-\s*\w+/gm);
        if (columnMatches) {
            const tableName = activeConfig.ingestion_file_name || 'uploaded_file';
            schema = { [tableName]: columnMatches.map(m => m.replace(/^\s*-\s*/, '').trim()) };
        }
    }

    return (
        <div className="space-y-8">
            <ConfigSummary
                connectionId={activeConfig.connection_id ?? null}
                connectionName={connectionName}
                dataSourceType={activeConfig.data_source_type as 'database' | 'file' || 'database'}
                fileInfo={fileInfo}
                schema={schema}
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
