import React, { useState, useEffect } from 'react';
import {
    getObservabilityConfig,
    updateObservabilityConfig,
    getUsageStats,
    getRecentTraces,
    testLogEmission
} from '../services/api';
import { useToast } from './Toast';
import { formatDateTime } from '../utils/datetime';

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
        type?: string;
        calls: number;
        input_tokens: number;
        output_tokens: number;
        total_tokens: number;
        total_cost: number;
        avg_latency_ms: number;
        input_price_per_1m?: number;
        output_price_per_1m?: number;
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

interface ChildObservation {
    id: string;
    name: string;
    type: string;  // "GENERATION", "SPAN", "CHAIN", etc.
    model: string;
    input_preview: string;
    output_preview: string;
    input_tokens: number;
    output_tokens: number;
    cost: number;
    latency_ms: number;
    level: string;
}

interface RecentTrace {
    id: string;
    trace_id: string;
    name: string;
    model: string;
    timestamp: string;
    latency: number;
    user_query: string;
    final_answer: string;
    input_tokens: number;
    output_tokens: number;
    total_cost: number;
    status: string;
    user_id?: string;
    session_id?: string;
    // Hierarchical children for detailed breakdown
    children?: ChildObservation[];
    total_input_tokens?: number;
    total_output_tokens?: number;
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
    const [traces, setTraces] = useState<RecentTrace[]>([]);
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
            const [configRes, statsRes, tracesRes] = await Promise.all([
                getObservabilityConfig(),
                getUsageStats(period),
                getRecentTraces(10)
            ]);
            setConfig(configRes);
            setStats(statsRes);
            setTraces(tracesRes || []);
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
                            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 sm:text-sm rounded-md shadow-sm"
                        >
                            <option value="DEBUG">DEBUG (All details)</option>
                            <option value="INFO">INFO (Standard)</option>
                            <option value="WARNING">WARNING (Issues only)</option>
                            <option value="ERROR">ERROR (Failures only)</option>
                        </select>
                        <p className="mt-1 text-xs text-gray-500">Controls backend log verbosity.</p>
                    </div>

                    {/* Langfuse Tracing Toggle */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Langfuse Tracing</label>
                        <div className="flex items-center gap-3 mt-2">
                            <button
                                onClick={() => handleConfigChange('tracing_provider', config.tracing_provider === 'langfuse' ? 'none' : 'langfuse')}
                                className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 ${
                                    config.tracing_provider === 'langfuse' ? 'bg-purple-600' : 'bg-gray-200'
                                }`}
                            >
                                <span
                                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                        config.tracing_provider === 'langfuse' ? 'translate-x-5' : 'translate-x-0'
                                    }`}
                                />
                            </button>
                            <span className="text-sm text-gray-700">
                                {config.tracing_provider === 'langfuse' ? 'Enabled' : 'Disabled'}
                            </span>
                        </div>
                        <p className="mt-2 text-xs text-gray-500">
                            {stats?.langfuse_enabled ? (
                                <span className="flex items-center gap-1 text-green-600">
                                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                    </svg>
                                    Connected to Langfuse
                                </span>
                            ) : (
                                'Traces queries, feedback, and LLM calls'
                            )}
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
                        value={`${(latencyPercentiles.p95 || 0).toFixed(2)}s`}
                        subtext={`P50: ${(latencyPercentiles.p50 || 0).toFixed(2)}s`}
                    />
                </div>
            </div>

            {/* 3. By Operation - Only show LLM Calls since embeddings/retrieval are local */}
            <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                    </svg>
                    LLM API Usage
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                        <p className="text-sm font-medium text-gray-500">Calls</p>
                        <p className="text-2xl font-semibold mt-1 text-purple-700">{(byOperation.llm?.calls || 0).toLocaleString()}</p>
                    </div>
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                        <p className="text-sm font-medium text-gray-500">Tokens</p>
                        <p className="text-2xl font-semibold mt-1 text-purple-700">{((byOperation.llm?.tokens || 0) / 1000).toFixed(1)}k</p>
                    </div>
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                        <p className="text-sm font-medium text-gray-500">Cost</p>
                        <p className="text-2xl font-semibold mt-1 text-green-600">${(byOperation.llm?.cost || 0).toFixed(4)}</p>
                    </div>
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                        <p className="text-sm font-medium text-gray-500">Avg Latency</p>
                        <p className="text-2xl font-semibold mt-1 text-purple-700">{(byOperation.llm?.avg_latency_ms || 0).toFixed(0)}ms</p>
                    </div>
                </div>
                <p className="mt-3 text-xs text-gray-500">
                    Local operations (embeddings, vector search) run on-device and have no API cost.
                </p>
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
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Calls</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Input Tokens</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Output Tokens</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Cost</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Input $/1M</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Output $/1M</th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Avg Latency</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {stats.by_model.map((model, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50">
                                        <td className="px-4 py-3 text-sm font-medium text-gray-900">{model.model}</td>
                                        <td className="px-4 py-3 text-sm">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                                model.type === 'LLM' 
                                                    ? 'bg-purple-100 text-purple-800' 
                                                    : 'bg-blue-100 text-blue-800'
                                            }`}>
                                                {model.type || 'LLM'}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.calls.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.input_tokens.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.output_tokens.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-sm text-green-600 text-right font-medium">${model.total_cost.toFixed(4)}</td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">
                                            {model.input_price_per_1m ? `$${model.input_price_per_1m.toFixed(2)}` : '-'}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">
                                            {model.output_price_per_1m ? `$${model.output_price_per_1m.toFixed(2)}` : '-'}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-500 text-right">{model.avg_latency_ms.toFixed(0)}ms</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* 5. Recent Traces */}
            {traces.length > 0 && (
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                        <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 012 2h2a2 2 0 012-2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                        </svg>
                        Recent Queries
                    </h2>
                    <div className="space-y-2">
                        {traces.map((trace, idx) => (
                            <TraceCard key={trace.id || idx} trace={trace} />
                        ))}
                    </div>
                    {stats?.langfuse_enabled && (
                        <p className="mt-4 text-xs text-gray-500 text-center">
                            <a 
                                href={stats.langfuse_host} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-purple-600 hover:text-purple-800 underline"
                            >
                                View all traces in Langfuse →
                            </a>
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

// Expandable Trace Card Component with Hierarchical Children
const TraceCard = ({ trace }: { trace: RecentTrace }) => {
    const [expanded, setExpanded] = useState(false);
    
    const hasChildren = trace.children && trace.children.length > 0;
    const totalTokens = (trace.total_input_tokens || trace.input_tokens || 0) + (trace.total_output_tokens || trace.output_tokens || 0);
    
    return (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
            {/* Collapsed Header - Always visible */}
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors text-left"
            >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                    <span className="text-xs font-mono bg-purple-100 text-purple-700 px-2 py-0.5 rounded flex-shrink-0">
                        {trace.model || 'gpt-3.5-turbo'}
                    </span>
                    <span className="text-sm text-gray-700 truncate flex-1" title={trace.user_query}>
                        {trace.user_query || '(no query)'}
                    </span>
                </div>
                <div className="flex items-center gap-4 flex-shrink-0 ml-4">
                    <span className="text-xs text-gray-400">
                        {formatDateTime(trace.timestamp)}
                    </span>
                    <span className="text-xs text-green-600 font-medium">
                        ${(trace.total_cost || 0).toFixed(4)}
                    </span>
                    <span className="text-xs text-gray-500">
                        {(trace.latency || 0).toFixed(2)}s
                    </span>
                    {hasChildren && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                            {trace.children!.length} steps
                        </span>
                    )}
                    <svg 
                        className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`} 
                        fill="none" 
                        stroke="currentColor" 
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                </div>
            </button>
            
            {/* Expanded Details */}
            {expanded && (
                <div className="px-4 py-4 border-t border-gray-200 bg-white space-y-4">
                    {/* User Query */}
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                            </svg>
                            <span className="text-xs font-medium text-gray-500 uppercase">User Query</span>
                        </div>
                        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 max-h-32 overflow-y-auto">
                            <p className="text-sm text-gray-800 whitespace-pre-wrap">{trace.user_query || '(empty)'}</p>
                        </div>
                    </div>
                    
                    {/* AI Response */}
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span className="text-xs font-medium text-gray-500 uppercase">AI Response</span>
                        </div>
                        <div className="bg-green-50 border border-green-100 rounded-lg p-3 max-h-48 overflow-y-auto">
                            <p className="text-sm text-gray-800 whitespace-pre-wrap">{trace.final_answer || '(empty)'}</p>
                        </div>
                    </div>
                    
                    {/* Hierarchical Step Breakdown */}
                    {hasChildren && (
                        <div>
                            <div className="flex items-center gap-2 mb-3">
                                <svg className="w-4 h-4 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                                </svg>
                                <span className="text-xs font-medium text-gray-500 uppercase">Step-by-Step Breakdown</span>
                            </div>
                            <div className="space-y-2">
                                {trace.children!.map((child, idx) => (
                                    <ChildObservationCard key={child.id || idx} child={child} index={idx + 1} />
                                ))}
                            </div>
                            
                            {/* Aggregated Totals */}
                            <div className="mt-4 pt-3 border-t border-gray-200">
                                <div className="flex items-center justify-between bg-purple-50 rounded-lg px-4 py-3">
                                    <span className="text-sm font-medium text-purple-800">Total</span>
                                    <div className="flex items-center gap-6 text-sm">
                                        <div className="text-gray-600">
                                            <span className="font-medium">{totalTokens.toLocaleString()}</span>
                                            <span className="text-gray-400 ml-1">tokens</span>
                                        </div>
                                        <div className="text-green-600 font-semibold">
                                            ${(trace.total_cost || 0).toFixed(4)}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                    
                    {/* Metadata Row */}
                    <div className="flex flex-wrap gap-4 pt-2 border-t border-gray-100 text-xs text-gray-500">
                        {trace.trace_id && (
                            <div className="flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                                </svg>
                                <span className="font-mono">{trace.trace_id.slice(0, 8)}...</span>
                            </div>
                        )}
                        {trace.session_id && (
                            <div className="flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                                </svg>
                                <span>Session: {trace.session_id.slice(0, 8)}...</span>
                            </div>
                        )}
                        {trace.user_id && (
                            <div className="flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                </svg>
                                <span>{trace.user_id}</span>
                            </div>
                        )}
                        <div className="flex items-center gap-1">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span>Latency: {(trace.latency || 0).toFixed(2)}s</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span>Cost: ${(trace.total_cost || 0).toFixed(4)}</span>
                        </div>
                        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                            trace.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                            {trace.status || 'completed'}
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
};

// Child Observation Card for step-by-step breakdown
const ChildObservationCard = ({ child, index }: { child: ChildObservation; index: number }) => {
    const [showDetails, setShowDetails] = useState(false);
    
    const getTypeColor = (type: string) => {
        switch (type) {
            case 'GENERATION': return 'bg-purple-100 text-purple-700 border-purple-200';
            case 'CHAIN': return 'bg-blue-100 text-blue-700 border-blue-200';
            case 'SPAN': return 'bg-gray-100 text-gray-700 border-gray-200';
            case 'TOOL': return 'bg-orange-100 text-orange-700 border-orange-200';
            default: return 'bg-gray-100 text-gray-600 border-gray-200';
        }
    };
    
    const totalTokens = child.input_tokens + child.output_tokens;
    const hasCost = child.cost > 0;
    const hasTokens = totalTokens > 0;
    
    return (
        <div className={`border rounded-lg overflow-hidden ${getTypeColor(child.type)}`}>
            <button
                onClick={() => setShowDetails(!showDetails)}
                className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-opacity-50 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-400 w-5">{index}.</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${getTypeColor(child.type)}`}>
                        {child.type}
                    </span>
                    <span className="text-sm font-medium truncate max-w-xs" title={child.name}>
                        {child.name}
                    </span>
                    {child.model !== 'unknown' && (
                        <span className="text-xs text-gray-500 font-mono">
                            ({child.model})
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-3 text-xs">
                    {hasTokens && (
                        <span className="text-gray-600">
                            {child.input_tokens.toLocaleString()} → {child.output_tokens.toLocaleString()} tokens
                        </span>
                    )}
                    {hasCost && (
                        <span className="text-green-600 font-medium">
                            ${child.cost.toFixed(4)}
                        </span>
                    )}
                    {child.latency_ms > 0 && (
                        <span className="text-gray-400">
                            {child.latency_ms.toFixed(0)}ms
                        </span>
                    )}
                    <svg 
                        className={`w-3 h-3 text-gray-400 transition-transform ${showDetails ? 'rotate-180' : ''}`} 
                        fill="none" 
                        stroke="currentColor" 
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                </div>
            </button>
            
            {showDetails && (
                <div className="px-3 py-2 border-t bg-white space-y-2">
                    {child.input_preview && (
                        <div>
                            <span className="text-xs text-gray-500">Input:</span>
                            <p className="text-xs text-gray-700 mt-1 bg-gray-50 p-2 rounded max-h-20 overflow-y-auto">
                                {child.input_preview}
                            </p>
                        </div>
                    )}
                    {child.output_preview && (
                        <div>
                            <span className="text-xs text-gray-500">Output:</span>
                            <p className="text-xs text-gray-700 mt-1 bg-gray-50 p-2 rounded max-h-20 overflow-y-auto">
                                {child.output_preview}
                            </p>
                        </div>
                    )}
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
export default ObservabilityPanel;
