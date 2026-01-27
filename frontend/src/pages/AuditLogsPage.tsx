import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canViewAllAuditLogs, getRoleDisplayName } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';

const getAuthToken = (): string | null => localStorage.getItem('auth_token');

interface AuditLog {
    id: number;
    timestamp: string;
    actor_id?: number;
    actor_username?: string;
    actor_role?: string;
    action: string;
    resource_type?: string;
    resource_id?: string;
    resource_name?: string;
    details?: Record<string, any>;
}

const AuditLogsPage: React.FC = () => {
    const { user } = useAuth();
    const [logs, setLogs] = useState<AuditLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filters, setFilters] = useState({
        actor: '',
        action: '',
        resource_type: ''
    });
    const [actionTypes, setActionTypes] = useState<string[]>([]);

    const hasAccess = canViewAllAuditLogs(user);

    useEffect(() => {
        if (hasAccess) {
            loadLogs();
            loadActionTypes();
        }
    }, [hasAccess]);

    const loadLogs = async () => {
        setLoading(true);
        setError(null);
        try {
            const token = getAuthToken();
            const params = new URLSearchParams();
            if (filters.actor) params.set('actor', filters.actor);
            if (filters.action) params.set('action', filters.action);
            if (filters.resource_type) params.set('resource_type', filters.resource_type);

            const res = await fetch(`/api/v1/audit/logs?${params.toString()}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to load audit logs');
            const data = await res.json();
            setLogs(data);
        } catch (err: any) {
            setError(err.message || 'Failed to load audit logs');
        } finally {
            setLoading(false);
        }
    };

    const loadActionTypes = async () => {
        try {
            const token = getAuthToken();
            const res = await fetch('/api/v1/audit/actions', {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) return;
            const data = await res.json();
            setActionTypes(data);
        } catch (err) {
            console.error('Failed to load action types', err);
        }
    };

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        loadLogs();
    };

    const formatAction = (action: string) => {
        if (!action) return '-';
        return action
            .split('.')
            .map(part => part.replace(/_/g, ' '))
            .join(' → ')
            .replace(/\b\w/g, l => l.toUpperCase());
    };

    const getActionColor = (action: string) => {
        if (action.includes('delete')) return 'text-red-600 bg-red-50';
        if (action.includes('create')) return 'text-green-600 bg-green-50';
        if (action.includes('update') || action.includes('edit')) return 'text-blue-600 bg-blue-50';
        if (action.includes('publish')) return 'text-purple-600 bg-purple-50';
        return 'text-gray-600 bg-gray-50';
    };

    const renderDetails = (details: Record<string, any> | undefined) => {
        if (!details || Object.keys(details).length === 0) return '-';

        return (
            <div className="flex flex-wrap gap-2 py-1">
                {Object.entries(details).map(([key, value]) => (
                    <div key={key} className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-gray-50 border border-gray-200 rounded text-[10px] leading-none whitespace-nowrap">
                        <span className="text-gray-400 font-bold uppercase tracking-wider text-[9px]">{key.replace(/_/g, ' ')}:</span>
                        <span className={`font-semibold ${typeof value === 'boolean' ? (value ? 'text-green-600' : 'text-red-600') : 'text-gray-700'}`}>
                            {typeof value === 'boolean' ? (value ? 'Active' : 'Inactive') :
                                key === 'role' ? getRoleDisplayName(value) :
                                    String(value).length > 30 ? String(value).slice(0, 30) + '...' : String(value)}
                        </span>
                    </div>
                ))}
            </div>
        );
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
                        <p className="text-sm text-gray-400 mt-2">Only Super Admin can view audit logs.</p>
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
                            <h1 className="text-3xl font-bold text-gray-900">Audit Logs</h1>
                            <p className="text-gray-500 mt-1">View all system activity and changes</p>
                        </div>
                        <RefreshButton
                            onClick={loadLogs}
                            isLoading={loading}
                        />
                    </div>

                    {/* Filters */}
                    <form onSubmit={handleSearch} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Actor</label>
                                <input
                                    type="text"
                                    value={filters.actor}
                                    onChange={(e) => setFilters(f => ({ ...f, actor: e.target.value }))}
                                    placeholder="Username"
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                />
                            </div>
                            <div>
                                <label htmlFor="action-filter-select" className="block text-sm font-medium text-gray-700 mb-1">Action Type</label>
                                <select
                                    id="action-filter-select"
                                    value={filters.action}
                                    onChange={(e) => setFilters(f => ({ ...f, action: e.target.value }))}
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                >
                                    <option value="">All Categories</option>
                                    {Array.from(new Set(actionTypes.map(a => a.split('.')[0]))).map(cat => (
                                        <option key={cat} value={cat}>
                                            {cat.charAt(0).toUpperCase() + cat.slice(1)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Resource Type</label>
                                <input
                                    type="text"
                                    value={filters.resource_type}
                                    onChange={(e) => setFilters(f => ({ ...f, resource_type: e.target.value }))}
                                    placeholder="prompt, user, connection..."
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                />
                            </div>
                            <div className="flex items-end gap-2">
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium shadow-sm hover:shadow-md transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                                >
                                    Search
                                </button>
                                <RefreshButton
                                    onClick={loadLogs}
                                    isLoading={loading}
                                    size="md"
                                    className="!px-4"
                                />
                            </div>
                        </div>
                    </form>

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
                            <span className="mt-4 text-gray-600 font-medium">Loading audit logs...</span>
                            <span className="mt-1 text-sm text-gray-400">Please wait</span>
                        </div>
                    ) : logs.length === 0 ? (
                        <div className="text-center py-16 bg-white rounded-lg shadow-sm border border-gray-200">
                            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <p className="text-lg font-medium text-gray-900">No audit logs found</p>
                            <p className="text-sm text-gray-500 mt-1">Logs will appear as actions are performed in the system</p>
                        </div>
                    ) : (
                        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50">
                                        <tr>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actor</th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Resource</th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Details</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {logs.map((log) => (
                                            <tr key={log.id} className="hover:bg-gray-50">
                                                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                                                    {new Date(log.timestamp).toLocaleString()}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <div className="text-sm font-medium text-gray-900">{log.actor_username || 'System'}</div>
                                                    <div className="text-xs text-gray-500">{getRoleDisplayName(log.actor_role)}</div>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${getActionColor(log.action)}`}>
                                                        {formatAction(log.action)}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <div className="text-sm text-gray-900">{log.resource_name || log.resource_id || '-'}</div>
                                                    <div className="text-xs text-gray-500">{log.resource_type}</div>
                                                </td>
                                                <td className="px-4 py-3 max-w-sm">
                                                    {renderDetails(log.details)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AuditLogsPage;
