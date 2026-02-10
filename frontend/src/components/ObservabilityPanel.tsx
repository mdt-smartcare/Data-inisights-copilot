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
    from_timestamp: string;
    to_timestamp: string;
    langfuse_enabled: boolean;
    langfuse_host: string;
    summary: {
        total_traces: number;
        total_observations: number;
        total_generations: number;
        total_cost: number;
        total_tokens: number;
    };
    by_model: Array<{
        model: string;
        calls: number;
        input_tokens: number;
        output_tokens: number;
        total_tokens: number;
        total_cost: number;
        avg_latency_ms: number;
    }>;
    by_operation: {
        llm: { calls: number; tokens: number; cost: number; avg_latency_ms: number };
        embedding: { calls: number; tokens: number; cost: number; avg_latency_ms: number };
        retrieval: { calls: number; tokens: number; cost: number; avg_latency_ms: number };
    };
    latency_percentiles: {
        p50: number;
        p75: number;
        p90: number;
        p95: number;
        p99: number;
    };
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

    // Safe accessor helpers
    const getSummary = () => stats?.summary || { total_traces: 0, total_observations: 0, total_generations: 0, total_cost: 0, total_tokens: 0 };
    const getByOperation = () => stats?.by_operation || { 
        llm: { calls: 0, tokens: 0, cost: 0, avg_latency_ms: 0 },
        embedding: { calls: 0, tokens: 0, cost: 0, avg_latency_ms: 0 },
        retrieval: { calls: 0, tokens: 0, cost: 0, avg_latency_ms: 0 }
    };
    const getLatencyPercentiles = () => stats?.latency_percentiles || { p50: 0, p75: 0, p90: 0, p95: 0, p99: 0 };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading observability settings...</div>;

    const summary = getSummary();
    const byOperation = getByOperation();
    const latencyPercentiles = getLatencyPercentiles();

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
                    <div className="flex items-center gap-4">
                        {stats?.langfuse_enabled && (
                            <a 
                                href={stats.langfuse_host} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-xs text-purple-600 hover:text-purple-800 underline"
                            >
                                Open Langfuse Dashboard →
                            </a>
                        )}
                        <button onClick={handleTestLog} className="text-xs text-gray-500 hover:text-purple-600 underline">
                            Emit Test Log
                        </button>
                    </div>
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
                        <p className="mt-1 text-xs text-gray-500">
                            {stats?.langfuse_enabled ? '✓ Langfuse connected' : 'Destination for RAG pipeline traces.'}
                        </p>
                    </div>
                </div>
            </div>

            {/* 2. Usage Statistics Summary */}
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

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <StatCard
                        label="Total Cost"
                        value={`$${(summary.total_cost || 0).toFixed(4)}`}
                        subtext="From Langfuse"
                        color="text-green-600"
                    />
                    <StatCard
                        label="Total Traces"
                        value={(summary.total_traces || 0).toLocaleString()}
                        subtext={`${(summary.total_generations || 0).toLocaleString()} generations`}
                    />
                    <StatCard
                        label="Total Tokens"
                        value={`${((summary.total_tokens || 0) / 1000).toFixed(1)}k`}
                        subtext="Input + Output"
                    />
                    <StatCard
                        label="P95 Latency"
                        value={`${((latencyPercentiles.p95 || 0) * 1000).toFixed(0)}ms`}
                        subtext={`P50: ${((latencyPercentiles.p50 || 0) * 1000).toFixed(0)}ms`}
                    />
                </div>
            </div>

            {/* 3. By Operation */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                    </svg>
                    Usage by Operation Type
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <OperationCard
                        title="LLM Calls"
                        calls={byOperation.llm?.calls || 0}
                        tokens={byOperation.llm?.tokens || 0}
                        cost={byOperation.llm?.cost || 0}
                        latency={byOperation.llm?.avg_latency_ms || 0}
                        color="purple"
                    />
                    <OperationCard
                        title="Embeddings"
                        calls={byOperation.embedding?.calls || 0}
                        tokens={byOperation.embedding?.tokens || 0}
                        cost={byOperation.embedding?.cost || 0}
                        latency={byOperation.embedding?.avg_latency_ms || 0}
                        color="blue"
                    />
                    <OperationCard
                        title="Retrieval"
                        calls={byOperation.retrieval?.calls || 0}
                        tokens={byOperation.retrieval?.tokens || 0}
                        cost={byOperation.retrieval?.cost || 0}
                        latency={byOperation.retrieval?.avg_latency_ms || 0}
                        color="green"
                    />
                </div>
            </div>

            {/* 4. By Model */}
            {stats?.by_model && stats.by_model.length > 0 && (
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                        <svg className="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Usage by Model
                    </h2>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Model</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Calls</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Input Tokens</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Output Tokens</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Cost</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Avg Latency</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {stats.by_model.map((model, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50">
                                        <td className="px-4 py-3 text-sm font-medium text-gray-900">{model.model}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.calls.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.input_tokens.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.output_tokens.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-green-600 text-right font-medium">${model.total_cost.toFixed(4)}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.avg_latency_ms.toFixed(0)}ms</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};

const StatCard = ({ label, value, subtext, color = "text-gray-900" }: { label: string; value: string; subtext: string; color?: string }) => (
    <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        <p className={`text-2xl font-semibold mt-1 ${color}`}>{value}</p>
        <p className="text-xs text-gray-400 mt-1">{subtext}</p>
    </div>
);

const OperationCard = ({ title, calls, tokens, cost, latency, color }: { title: string; calls: number; tokens: number; cost: number; latency: number; color: string }) => {
    const colorClasses: Record<string, string> = {
        purple: 'border-purple-200 bg-purple-50',
        blue: 'border-blue-200 bg-blue-50',
        green: 'border-green-200 bg-green-50',
    };
    
    return (
        <div className={`p-4 rounded-lg border ${colorClasses[color] || 'border-gray-200 bg-gray-50'}`}>
            <h3 className="font-medium text-gray-900 mb-3">{title}</h3>
            <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                    <span className="text-gray-500">Calls</span>
                    <span className="font-medium">{calls.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-500">Tokens</span>
                    <span className="font-medium">{(tokens / 1000).toFixed(1)}k</span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-500">Cost</span>
                    <span className="font-medium text-green-600">${cost.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-500">Avg Latency</span>
                    <span className="font-medium">{latency.toFixed(0)}ms</span>
                </div>
            </div>
        </div>
    );
};

export default ObservabilityPanel;
