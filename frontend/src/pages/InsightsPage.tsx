import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canViewConfig } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';
import { apiClient } from '../services/api';

const InsightsPage: React.FC = () => {
    const { user } = useAuth();
    const [loading, setLoading] = useState(true);
    const [activeConfig, setActiveConfig] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    const hasAccess = canViewConfig(user);

    useEffect(() => {
        if (hasAccess) {
            loadData();
        }
    }, [hasAccess]);

    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await apiClient.get('/api/v1/config/active-metadata');
            setActiveConfig(res.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to load data');
        } finally {
            setLoading(false);
        }
    };

    // Access check AFTER all hooks
    if (!hasAccess) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
                        <p className="text-gray-500">You don't have permission to access this page.</p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="max-w-7xl mx-auto py-8 px-4">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Insights</h1>
                            <p className="text-gray-500 mt-1">System overview and configuration status</p>
                        </div>
                        <RefreshButton
                            onClick={loadData}
                            isLoading={loading}
                        />
                    </div>

                    {error && (
                        <Alert
                            type="error"
                            message={error}
                            onDismiss={() => setError(null)}
                        />
                    )}

                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600"></div>
                            <span className="mt-4 text-gray-600 font-medium">Loading insights...</span>
                            <span className="mt-1 text-sm text-gray-400">Please wait</span>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Active Configuration Status */}
                            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                                <h2 className="text-lg font-semibold text-gray-900 mb-4">Active Configuration</h2>
                                {activeConfig ? (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                        <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                                            <p className="text-sm text-green-600 font-medium">Status</p>
                                            <p className="text-2xl font-bold text-green-700">Active</p>
                                            <p className="text-xs text-green-500 mt-1">v{activeConfig.version || 1}</p>
                                        </div>
                                        <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                                            <p className="text-sm text-blue-600 font-medium">Connection</p>
                                            <p className="text-lg font-semibold text-blue-700 truncate">
                                                {activeConfig.connection_name || 'Configured'}
                                            </p>
                                            <p className="text-xs text-blue-500 mt-1">
                                                {activeConfig.connection_type || 'Database'}
                                            </p>
                                        </div>
                                        <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                                            <p className="text-sm text-purple-600 font-medium">Schema Tables</p>
                                            <p className="text-2xl font-bold text-purple-700">
                                                {(() => {
                                                    try {
                                                        if (!activeConfig.schema_selection) return 0;
                                                        // It might be an object already or string
                                                        const parsed = typeof activeConfig.schema_selection === 'string'
                                                            ? JSON.parse(activeConfig.schema_selection)
                                                            : activeConfig.schema_selection;

                                                        // It could be an array or object keys
                                                        if (Array.isArray(parsed)) return parsed.length;
                                                        return Object.keys(parsed).length;
                                                    } catch (e) {
                                                        return 0;
                                                    }
                                                })()}
                                            </p>
                                            <p className="text-xs text-purple-500 mt-1">tables selected</p>
                                        </div>
                                        <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                                            <p className="text-sm text-orange-600 font-medium">Last Updated</p>
                                            <p className="text-lg font-semibold text-orange-700">
                                                {(() => {
                                                    try {
                                                        const dateStr = activeConfig.created_at.replace(' ', 'T') + 'Z';
                                                        return new Date(dateStr).toLocaleDateString();
                                                    } catch (e) {
                                                        return activeConfig.created_at;
                                                    }
                                                })()}
                                            </p>
                                            <p className="text-xs text-orange-500 mt-1">
                                                {activeConfig.created_by_username && `by ${activeConfig.created_by_username}`}
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center py-8 text-gray-400">
                                        <p className="text-lg">No active configuration</p>
                                        <p className="text-sm mt-1">Go to Config page to set up a prompt</p>
                                    </div>
                                )}
                            </div>

                            {/* Prompt Preview */}
                            {activeConfig?.prompt_text && (
                                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                                    <h2 className="text-lg font-semibold text-gray-900 mb-4">Active Prompt Preview</h2>
                                    <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded max-h-64 overflow-auto">
                                        {activeConfig.prompt_text.slice(0, 500)}
                                        {activeConfig.prompt_text.length > 500 ? '...' : ''}
                                    </pre>
                                </div>
                            )}

                            {/* Quick Links */}
                            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                                <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <a
                                        href="/chat"
                                        className="flex items-center p-4 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors border border-blue-200"
                                    >
                                        <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 mr-4">
                                            💬
                                        </div>
                                        <div>
                                            <p className="font-semibold text-blue-900">Start Chatting</p>
                                            <p className="text-sm text-blue-600">Ask questions about your data</p>
                                        </div>
                                    </a>
                                    <a
                                        href="/config"
                                        className="flex items-center p-4 bg-green-50 rounded-lg hover:bg-green-100 transition-colors border border-green-200"
                                    >
                                        <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center text-green-600 mr-4">
                                            ⚙️
                                        </div>
                                        <div>
                                            <p className="font-semibold text-green-900">Configure</p>
                                            <p className="text-sm text-green-600">Manage connections & prompts</p>
                                        </div>
                                    </a>
                                    <a
                                        href="/history"
                                        className="flex items-center p-4 bg-purple-50 rounded-lg hover:bg-purple-100 transition-colors border border-purple-200"
                                    >
                                        <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center text-purple-600 mr-4">
                                            📜
                                        </div>
                                        <div>
                                            <p className="font-semibold text-purple-900">Version History</p>
                                            <p className="text-sm text-purple-600">Compare & rollback prompts</p>
                                        </div>
                                    </a>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default InsightsPage;
