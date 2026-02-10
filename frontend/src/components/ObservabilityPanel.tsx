import React, { useState, useEffect } from 'react';
import {
    getObservabilityConfig,
    updateObservabilityConfig,
    getUsageStats,
    testLogEmission
} from '../services/api';
import { useToast } from './Toast';

interface UsageStats {
    period: string;
    llm: { calls: number; tokens: number; cost: number; latency: number };
    embedding: { calls: number; tokens: number; cost: number; latency: number };
    vector_search: { calls: number; tokens: number; cost: number; latency: number };
    total_cost: number;
}

const ObservabilityPanel: React.FC = () => {
    const { success, error } = useToast();
    const [loading, setLoading] = useState(true);
    const [config, setConfig] = useState<any>({
        log_level: 'INFO',
        tracing_provider: 'none',
        trace_sample_rate: 0.1,
        log_destinations: ['console', 'file']
    });
    const [stats, setStats] = useState<UsageStats | null>(null);
    const [period, setPeriod] = useState('24h');
    const [refreshing, setRefreshing] = useState(false);

    useEffect(() => {
        loadData();
        // Auto-refresh stats every 30s
        const interval = setInterval(() => loadStats(period, true), 30000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        loadStats(period);
    }, [period]);

    const loadData = async () => {
        setLoading(true);
        try {
            const [configRes, statsRes] = await Promise.all([
                getObservabilityConfig(),
                getUsageStats(period)
            ]);
            setConfig(configRes);
            setStats(statsRes);
        } catch (err: any) {
            error('Failed to load observability data', err.message);
        } finally {
            setLoading(false);
        }
    };

    const loadStats = async (p: string, silent = false) => {
        if (!silent) setRefreshing(true);
        try {
            const res = await getUsageStats(p);
            setStats(res);
        } catch (err) {
            // quiet fail on auto-refresh
            console.error(err);
        } finally {
            if (!silent) setRefreshing(false);
        }
    };

    const handleConfigChange = async (key: string, value: any) => {
        // Optimistic update
        const oldConfig = { ...config };
        setConfig({ ...config, [key]: value });

        try {
            await updateObservabilityConfig({ [key]: value });
            success('Configuration Updated', `${key} set to ${value}`);
        } catch (err: any) {
            setConfig(oldConfig);
            error('Update Failed', err.message);
        }
    };

    const handleTestLog = async () => {
        try {
            await testLogEmission('INFO', 'Test log from admin dashboard');
            success('Log Emitted', 'Check the backend logs to verify');
        } catch (err: any) {
            error('Log Emission Failed', err.message);
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading observability settings...</div>;

    return (
        <div className="space-y-6">

            {/* 1. Configuration Section */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                        <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        Observability Settings
                    </h2>
                    <button onClick={handleTestLog} className="text-xs text-gray-500 hover:text-purple-600 underline">
                        Emit Test Log
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">

                    {/* Log Level */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Log Level</label>
                        <select
                            value={config.log_level}
                            onChange={(e) => handleConfigChange('log_level', e.target.value)}
                            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-purple-500 focus:border-purple-500 sm:text-sm rounded-md"
                        >
                            <option value="DEBUG">DEBUG (All details)</option>
                            <option value="INFO">INFO (Standard)</option>
                            <option value="WARNING">WARNING (Issues only)</option>
                            <option value="ERROR">ERROR (Failures only)</option>
                        </select>
                        <p className="mt-1 text-xs text-gray-500">Controls backend log verbosity.</p>
                    </div>

                    {/* Tracing Provider */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Tracing Provider</label>
                        <div className="flex gap-4 mt-2">
                            <label className="inline-flex items-center">
                                <input
                                    type="radio"
                                    className="form-radio text-purple-600 focus:ring-purple-500"
                                    name="tracing"
                                    value="none"
                                    checked={config.tracing_provider === 'none'}
                                    onChange={() => handleConfigChange('tracing_provider', 'none')}
                                />
                                <span className="ml-2 text-sm text-gray-700">None</span>
                            </label>
                            <label className="inline-flex items-center">
                                <input
                                    type="radio"
                                    className="form-radio text-purple-600 focus:ring-purple-500"
                                    name="tracing"
                                    value="langfuse"
                                    checked={config.tracing_provider === 'langfuse'}
                                    onChange={() => handleConfigChange('tracing_provider', 'langfuse')}
                                />
                                <span className="ml-2 text-sm text-gray-700">Langfuse</span>
                            </label>
                            <label className="inline-flex items-center">
                                <input
                                    type="radio"
                                    className="form-radio text-purple-600 focus:ring-purple-500"
                                    name="tracing"
                                    value="opentelemetry"
                                    checked={config.tracing_provider === 'opentelemetry'}
                                    onChange={() => handleConfigChange('tracing_provider', 'opentelemetry')}
                                />
                                <span className="ml-2 text-sm text-gray-700">OpenTelemetry</span>
                            </label>
                            <label className="inline-flex items-center">
                                <input
                                    type="radio"
                                    className="form-radio text-purple-600 focus:ring-purple-500"
                                    name="tracing"
                                    value="both"
                                    checked={config.tracing_provider === 'both'}
                                    onChange={() => handleConfigChange('tracing_provider', 'both')}
                                />
                                <span className="ml-2 text-sm text-gray-700">Both</span>
                            </label>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">Destination for RAG pipeline traces.</p>
                    </div>
                </div>
            </div>

            {/* 2. Usage Statistics */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                        <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        System Usage & Costs
                    </h2>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">{refreshing ? 'Refreshing...' : 'Auto-refresh on'}</span>
                        <select
                            value={period}
                            onChange={(e) => setPeriod(e.target.value)}
                            className="text-sm border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500"
                        >
                            <option value="1h">Last Hour</option>
                            <option value="24h">Last 24 Hours</option>
                            <option value="7d">Last 7 Days</option>
                            <option value="30d">Last 30 Days</option>
                        </select>
                    </div>
                </div>

                {stats && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <StatCard
                            label="Total Cost (Est.)"
                            value={`$${stats.total_cost.toFixed(4)}`}
                            subtext="Combined LLM & Embedding"
                            color="text-green-600"
                        />
                        <StatCard
                            label="LLM Calls"
                            value={stats.llm.calls.toLocaleString()}
                            subtext={`${(stats.llm.tokens / 1000).toFixed(1)}k tokens`}
                        />
                        <StatCard
                            label="Embeddings"
                            value={stats.embedding.calls.toLocaleString()}
                            subtext={`${(stats.embedding.tokens / 1000).toFixed(1)}k tokens`}
                        />
                        <StatCard
                            label="Vector Searches"
                            value={stats.vector_search.calls.toLocaleString()}
                            subtext={`Avg Latency: ${stats.vector_search.latency}ms`}
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

const StatCard = ({ label, value, subtext, color = "text-gray-900" }: any) => (
    <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        <p className={`text-2xl font-semibold mt-1 ${color}`}>{value}</p>
        <p className="text-xs text-gray-400 mt-1">{subtext}</p>
    </div>
);

export default ObservabilityPanel;
