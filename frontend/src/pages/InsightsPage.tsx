import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canViewConfig } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import { APP_CONFIG } from '../config';

const getAuthToken = (): string | null => localStorage.getItem('auth_token');

interface InsightsSummary {
    totalQueries: number;
    avgProcessingTime: number;
    successRate: number;
    positiveFeedback: number;
    negativeFeedback: number;
    recentQueries: QueryExecution[];
}

interface QueryExecution {
    id: string;
    timestamp: string;
    query: string;
    sqlGenerated: boolean;
    processingTime?: number;
    status: 'success' | 'error';
}

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
            const token = getAuthToken();
            const res = await fetch('/api/v1/config/active-metadata', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load config');
            const data = await res.json();
            setActiveConfig(data);
        } catch (err: any) {
            setError(err.message || 'Failed to load data');
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
                    <div className="flex justify-between items-center mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Insights</h1>
                            <p className="text-gray-500 mt-1">System overview and configuration status</p>
                        </div>
                        <button
                            onClick={loadData}
                            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                        >
                            Refresh
                        </button>
                    </div>

                    {error && (
                        <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-md">
                            {error}
                        </div>
                    )}

                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                            <span className="ml-3 text-gray-500">Loading insights...</span>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Active Configuration Status */}
                            <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
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
                                                {activeConfig.schema_selection ?
                                                    JSON.parse(activeConfig.schema_selection).length :
                                                    0
                                                }
                                            </p>
                                            <p className="text-xs text-purple-500 mt-1">tables selected</p>
                                        </div>
                                        <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                                            <p className="text-sm text-orange-600 font-medium">Last Updated</p>
                                            <p className="text-lg font-semibold text-orange-700">
                                                {new Date(activeConfig.created_at).toLocaleDateString()}
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
                                <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
                                    <h2 className="text-lg font-semibold text-gray-900 mb-4">Active Prompt Preview</h2>
                                    <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded max-h-64 overflow-auto">
                                        {activeConfig.prompt_text.slice(0, 500)}
                                        {activeConfig.prompt_text.length > 500 ? '...' : ''}
                                    </pre>
                                </div>
                            )}

                            {/* Quick Links */}
                            <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
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
