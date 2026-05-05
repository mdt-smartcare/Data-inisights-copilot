import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { canViewAllAuditLogs, getRoleDisplayName } from '../utils/permissions';
import { ChatHeader } from '../components/chat';
import RefreshButton from '../components/RefreshButton';
import Alert from '../components/Alert';
import { APP_CONFIG } from '../config';
import { apiClient } from '../services/api';
import { formatDateTime } from '../utils/datetime';

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

// Resource types available for filtering
const RESOURCE_TYPES = [
    { value: '', label: 'All Resources' },
    { value: 'user', label: 'User' },
    { value: 'agent', label: 'Agent' },
    { value: 'agent_config', label: 'Agent Config' },
    { value: 'datasource', label: 'Data Source' },
    { value: 'aimodel', label: 'AI Model' },
    { value: 'embedding_job', label: 'Embedding Job' },
];

const PAGE_SIZE = 50;

const AuditLogsPage: React.FC = () => {
    const { user } = useAuth();
    const [logs, setLogs] = useState<AuditLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filters, setFilters] = useState({
        actor: '',
        resource_type: '',
        start_date: '',
        end_date: ''
    });
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);

    const totalPages = Math.ceil(totalCount / PAGE_SIZE);
    const hasAccess = canViewAllAuditLogs(user);

    useEffect(() => {
        if (hasAccess) {
            loadLogs();
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentPage]); // Reload when page changes

    const loadLogs = async () => {
        setLoading(true);
        setError(null);
        try {
            const offset = (currentPage - 1) * PAGE_SIZE;
            const params = new URLSearchParams();
            if (filters.actor) params.set('actor', filters.actor);
            if (filters.resource_type) params.set('resource_type', filters.resource_type);
            
            // Convert local dates to UTC ISO strings for proper timezone handling
            if (filters.start_date) {
                // Start of the selected day in local timezone, converted to UTC
                const startLocal = new Date(filters.start_date + 'T00:00:00');
                params.set('start_date', startLocal.toISOString());
            }
            if (filters.end_date) {
                // End of the selected day in local timezone (23:59:59.999), converted to UTC
                const endLocal = new Date(filters.end_date + 'T23:59:59.999');
                params.set('end_date', endLocal.toISOString());
            }
            
            params.set('limit', String(PAGE_SIZE));
            params.set('offset', String(offset));

            const res = await apiClient.get(`/api/v1/audit/logs?${params.toString()}`);
            setLogs(res.data?.logs || []);
            setTotalCount(res.data?.total || 0);
        } catch {
            // Silently fail - audit logs are non-critical
            setLogs([]);
            setTotalCount(0);
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setCurrentPage(1);
        loadLogs();
    };

    const handlePageChange = (page: number) => {
        if (page >= 1 && page <= totalPages) {
            setCurrentPage(page);
        }
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
        if (action.includes('deleted') || action.includes('revoked') || action.includes('demoted') || action.includes('deactivated')) 
            return 'text-red-600 bg-red-50';
        if (action.includes('created') || action.includes('registered') || action.includes('granted') || action.includes('promoted') || action.includes('activated')) 
            return 'text-green-600 bg-green-50';
        if (action.includes('updated') || action.includes('settings')) 
            return 'text-blue-600 bg-blue-50';
        if (action.includes('completed') || action.includes('partially_completed')) 
            return 'text-purple-600 bg-purple-50';
        if (action.includes('started')) 
            return 'text-indigo-600 bg-indigo-50';
        if (action.includes('failed') || action.includes('cancelled')) 
            return 'text-orange-600 bg-orange-50';
        return 'text-gray-600 bg-gray-50';
    };

    const formatValue = (value: any): string => {
        if (value === null || value === undefined) return '-';
        if (typeof value === 'boolean') return value ? 'Yes' : 'No';
        if (typeof value === 'string') return value;
        if (typeof value === 'number') return String(value);
        if (Array.isArray(value)) {
            if (value.length === 0) return '[]';
            // For arrays of objects, show count
            if (typeof value[0] === 'object') {
                return `[${value.length} item${value.length > 1 ? 's' : ''}]`;
            }
            return value.join(', ');
        }
        if (typeof value === 'object') {
            // For nested objects, show a brief summary
            const keys = Object.keys(value);
            if (keys.length === 0) return '{}';
            return `{${keys.slice(0, 2).join(', ')}${keys.length > 2 ? '...' : ''}}`;
        }
        return String(value);
    };

    const renderNestedValue = (value: any, depth: number = 0): React.ReactNode => {
        if (value === null || value === undefined) return <span className="text-gray-400">-</span>;
        if (typeof value === 'boolean') {
            return <span className={value ? 'text-green-600' : 'text-red-600'}>{value ? 'Yes' : 'No'}</span>;
        }
        if (typeof value === 'string' || typeof value === 'number') {
            return <span className="text-gray-700">{String(value)}</span>;
        }
        if (Array.isArray(value)) {
            if (value.length === 0) return <span className="text-gray-400">[]</span>;
            return (
                <div className={`${depth > 0 ? 'ml-3 mt-1' : ''}`}>
                    {value.map((item, index) => (
                        <div key={index} className="border-l-2 border-gray-200 pl-2 py-1 my-1">
                            {typeof item === 'object' ? renderNestedValue(item, depth + 1) : (
                                <span className="text-gray-700">{String(item)}</span>
                            )}
                        </div>
                    ))}
                </div>
            );
        }
        if (typeof value === 'object') {
            return (
                <div className={`${depth > 0 ? 'ml-3 mt-1' : ''} space-y-1`}>
                    {Object.entries(value).map(([key, val]) => (
                        <div key={key} className="flex flex-wrap items-start gap-1">
                            <span className="text-gray-500 text-xs font-medium">{key.replace(/_/g, ' ')}:</span>
                            {typeof val === 'object' ? renderNestedValue(val, depth + 1) : (
                                <span className="text-gray-700 text-xs">{formatValue(val)}</span>
                            )}
                        </div>
                    ))}
                </div>
            );
        }
        return <span className="text-gray-700">{String(value)}</span>;
    };

    const renderDetails = (details: Record<string, any> | undefined) => {
        if (!details || Object.keys(details).length === 0) return '-';
        
        const entries = Object.entries(details);
        const hasComplexValues = entries.some(([, value]) => 
            Array.isArray(value) || (typeof value === 'object' && value !== null)
        );

        if (!hasComplexValues && entries.length <= 2) {
            // Simple case: just show badges, no expandable needed
            return (
                <div className="flex items-center gap-2 py-1">
                    {entries.map(([key, value]) => (
                        <div key={key} className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded text-[10px] leading-none whitespace-nowrap">
                            <span className="text-gray-400 font-bold uppercase tracking-wider text-[9px]">{key.replace(/_/g, ' ')}:</span>
                            <span className={`font-semibold truncate max-w-[80px] ${typeof value === 'boolean' ? (value ? 'text-green-600' : 'text-red-600') : 'text-gray-700'}`}>
                                {typeof value === 'boolean' ? (value ? 'Active' : 'Inactive') :
                                    key === 'role' ? getRoleDisplayName(value) : formatValue(value)}
                            </span>
                        </div>
                    ))}
                </div>
            );
        }

        return (
            <details className="group">
                <summary className="flex items-center gap-2 py-1 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                    <div className="flex items-center gap-1.5 overflow-hidden">
                        {entries.slice(0, 2).map(([key, value]) => (
                            <div key={key} className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded text-[10px] leading-none whitespace-nowrap">
                                <span className="text-gray-400 font-bold uppercase tracking-wider text-[9px]">{key.replace(/_/g, ' ')}:</span>
                                <span className={`font-semibold truncate max-w-[80px] ${typeof value === 'boolean' ? (value ? 'text-green-600' : 'text-red-600') : 'text-gray-700'}`}>
                                    {typeof value === 'boolean' ? (value ? 'Active' : 'Inactive') :
                                        key === 'role' ? getRoleDisplayName(value) : formatValue(value)}
                                </span>
                            </div>
                        ))}
                        {entries.length > 2 && (
                            <span className="text-[10px] text-gray-400 whitespace-nowrap">+{entries.length - 2}</span>
                        )}
                    </div>
                    <span className="text-[10px] text-blue-600 hover:text-blue-800 font-medium inline-flex items-center gap-0.5 whitespace-nowrap flex-shrink-0">
                        <svg className="w-2.5 h-2.5 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                        <span className="group-open:hidden">View</span>
                        <span className="hidden group-open:inline">Hide</span>
                    </span>
                </summary>
                <div className="mt-1 bg-gray-50 border border-gray-200 rounded-lg p-3 max-w-lg">
                    <div className="space-y-2">
                        {entries.map(([key, value]) => (
                            <div key={key} className="text-xs">
                                <span className="text-gray-500 font-medium uppercase tracking-wider text-[10px]">
                                    {key.replace(/_/g, ' ')}:
                                </span>
                                <div className="mt-0.5">
                                    {renderNestedValue(value)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </details>
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
                            onClick={() => loadLogs()}
                            isLoading={loading}
                        />
                    </div>

                    {/* Filters */}
                    <form onSubmit={handleSearch} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
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
                                <label htmlFor="resource-type-select" className="block text-sm font-medium text-gray-700 mb-1">Resource Type</label>
                                <select
                                    id="resource-type-select"
                                    value={filters.resource_type}
                                    onChange={(e) => setFilters(f => ({ ...f, resource_type: e.target.value }))}
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                >
                                    {RESOURCE_TYPES.map(rt => (
                                        <option key={rt.value} value={rt.value}>{rt.label}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
                                <input
                                    type="date"
                                    value={filters.start_date}
                                    onChange={(e) => setFilters(f => ({ ...f, start_date: e.target.value }))}
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm [color-scheme:light]"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
                                <input
                                    type="date"
                                    value={filters.end_date}
                                    onChange={(e) => setFilters(f => ({ ...f, end_date: e.target.value }))}
                                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm [color-scheme:light]"
                                />
                            </div>
                            <div className="flex items-end">
                                <button
                                    type="submit"
                                    className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium shadow-sm hover:shadow-md transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                                >
                                    Search
                                </button>
                            </div>
                        </div>
                        {totalCount > 0 && (
                            <div className="mt-3 text-sm text-gray-500">
                                Showing {((currentPage - 1) * PAGE_SIZE) + 1} - {Math.min(currentPage * PAGE_SIZE, totalCount)} of {totalCount} logs
                            </div>
                        )}
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
                                            <tr key={log.id} className="hover:bg-gray-50 align-top">
                                                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                                                    {formatDateTime(log.timestamp)}
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
                                                <td className="px-4 py-3 max-w-md">
                                                    {renderDetails(log.details)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            
                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="px-4 py-4 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
                                    <div className="text-sm text-gray-500">
                                        Page {currentPage} of {totalPages}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handlePageChange(1)}
                                            disabled={currentPage === 1 || loading}
                                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            First
                                        </button>
                                        <button
                                            onClick={() => handlePageChange(currentPage - 1)}
                                            disabled={currentPage === 1 || loading}
                                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Previous
                                        </button>
                                        
                                        {/* Page numbers */}
                                        <div className="flex items-center gap-1">
                                            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                                                let pageNum: number;
                                                if (totalPages <= 5) {
                                                    pageNum = i + 1;
                                                } else if (currentPage <= 3) {
                                                    pageNum = i + 1;
                                                } else if (currentPage >= totalPages - 2) {
                                                    pageNum = totalPages - 4 + i;
                                                } else {
                                                    pageNum = currentPage - 2 + i;
                                                }
                                                return (
                                                    <button
                                                        key={pageNum}
                                                        onClick={() => handlePageChange(pageNum)}
                                                        disabled={loading}
                                                        className={`px-3 py-1.5 text-sm border rounded-md ${
                                                            currentPage === pageNum
                                                                ? 'bg-blue-600 text-white border-blue-600'
                                                                : 'border-gray-300 bg-white hover:bg-gray-50'
                                                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                                                    >
                                                        {pageNum}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                        
                                        <button
                                            onClick={() => handlePageChange(currentPage + 1)}
                                            disabled={currentPage === totalPages || loading}
                                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Next
                                        </button>
                                        <button
                                            onClick={() => handlePageChange(totalPages)}
                                            disabled={currentPage === totalPages || loading}
                                            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Last
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AuditLogsPage;
