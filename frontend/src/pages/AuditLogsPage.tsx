import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canViewAllAuditLogs, getRoleDisplayName } from '../utils/permissions';

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
        return action.replace('.', ' → ').replace(/_/g, ' ');
    };

    const getActionColor = (action: string) => {
        if (action.includes('delete')) return 'text-red-600 bg-red-50';
        if (action.includes('create')) return 'text-green-600 bg-green-50';
        if (action.includes('update') || action.includes('edit')) return 'text-blue-600 bg-blue-50';
        if (action.includes('publish')) return 'text-purple-600 bg-purple-50';
        return 'text-gray-600 bg-gray-50';
    };

    // Access check AFTER all hooks
    if (!hasAccess) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
                    <p className="text-gray-500">You don't have permission to access this page.</p>
                    <p className="text-sm text-gray-400 mt-2">Only Super Admin can view audit logs.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto py-8 px-4">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Audit Logs</h1>
                    <p className="text-gray-500 mt-1">View all system activity and changes</p>
                </div>
            </div>

            {/* Filters */}
            <form onSubmit={handleSearch} className="bg-white rounded-lg shadow border border-gray-200 p-4 mb-6">
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
                        <label className="block text-sm font-medium text-gray-700 mb-1">Action Type</label>
                        <select
                            value={filters.action}
                            onChange={(e) => setFilters(f => ({ ...f, action: e.target.value }))}
                            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                        >
                            <option value="">All Actions</option>
                            {actionTypes.map(a => (
                                <option key={a} value={a.split('.')[0]}>{a.split('.')[0]}</option>
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
                    <div className="flex items-end">
                        <button type="submit" className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
                            Search
                        </button>
                    </div>
                </div>
            </form>

            {error && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
                    <span>{error}</span>
                    <button onClick={() => setError(null)} className="text-red-500">&times;</button>
                </div>
            )}

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading audit logs...</span>
                </div>
            ) : logs.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                    <p className="text-lg">No audit logs found</p>
                    <p className="text-sm mt-1">Logs will appear as actions are performed in the system</p>
                </div>
            ) : (
                <div className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
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
                                        <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate">
                                            {log.details ? JSON.stringify(log.details).slice(0, 100) : '-'}
                                        </td>
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

export default AuditLogsPage;
