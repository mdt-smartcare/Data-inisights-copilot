/**
 * VectorRegistryPage - Central registry for all Vector Databases
 * 
 * Features:
 * - View all registered Vector DBs in a table
 * - See disk sizes, document counts, vector counts
 * - Monitor sync status and schedule information
 * - Health status indicators
 * - Delete vector databases
 * - Identify orphaned ChromaDB folders
 */
import { useState, useEffect } from 'react';
import {
  getVectorDbRegistry,
  deleteVectorDb,
  triggerVectorDbSync,
  type VectorDbRegistryResponse,
} from '../services/api';
import ChatHeader from '../components/chat/ChatHeader';
import { APP_CONFIG } from '../config';
import { formatDateTime } from '../utils/datetime';

type HealthStatus = 'healthy' | 'warning' | 'error' | 'missing' | 'orphaned';

const healthStatusConfig: Record<HealthStatus, { color: string; bgColor: string; label: string; icon: string }> = {
  healthy: { color: 'text-green-700', bgColor: 'bg-green-100', label: 'Healthy', icon: '✓' },
  warning: { color: 'text-yellow-700', bgColor: 'bg-yellow-100', label: 'Warning', icon: '⚠' },
  error: { color: 'text-red-700', bgColor: 'bg-red-100', label: 'Error', icon: '✕' },
  missing: { color: 'text-gray-700', bgColor: 'bg-gray-100', label: 'Missing Files', icon: '?' },
  orphaned: { color: 'text-orange-700', bgColor: 'bg-orange-100', label: 'Orphaned', icon: '⊘' },
};

export default function VectorRegistryPage() {
  const [registry, setRegistry] = useState<VectorDbRegistryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [triggeringSync, setTriggeringSync] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState<'name' | 'disk_size_bytes' | 'document_count' | 'created_at'>('name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  useEffect(() => {
    loadRegistry();
  }, []);

  const loadRegistry = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getVectorDbRegistry();
      setRegistry(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load vector database registry');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteVectorDb(name, true);
      setDeleteConfirm(null);
      loadRegistry();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete vector database');
    }
  };

  const handleTriggerSync = async (name: string) => {
    try {
      setTriggeringSync(name);
      await triggerVectorDbSync(name);
      loadRegistry();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to trigger sync');
    } finally {
      setTriggeringSync(null);
    }
  };


  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedVectorDbs = registry?.vector_dbs
    ?.filter(db => db.name.toLowerCase().includes(searchTerm.toLowerCase()))
    ?.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
      }
      return 0;
    }) || [];

  const SortIcon = ({ field }: { field: typeof sortField }) => (
    <span className="ml-1 inline-block">
      {sortField === field ? (
        sortDirection === 'asc' ? '↑' : '↓'
      ) : (
        <span className="text-gray-300">↕</span>
      )}
    </span>
  );

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

      {/* Page Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex-shrink-0">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Vector Registry</h1>
            <p className="text-sm text-gray-500 mt-1">
              Central management for all ChromaDB vector databases
            </p>
          </div>
          <button
            onClick={loadRegistry}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      {registry && (
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border-b border-indigo-100 px-6 py-4 flex-shrink-0">
          <div className="max-w-7xl mx-auto grid grid-cols-4 gap-6">
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-2xl font-bold text-indigo-600">{registry.total_vector_dbs}</div>
              <div className="text-sm text-gray-500">Total Vector DBs</div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-2xl font-bold text-purple-600">{registry.total_disk_size_formatted}</div>
              <div className="text-sm text-gray-500">Total Disk Usage</div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-2xl font-bold text-green-600">
                {registry.vector_dbs.filter(db => db.health_status === 'healthy').length}
              </div>
              <div className="text-sm text-gray-500">Healthy</div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow-sm">
              <div className="text-2xl font-bold text-orange-600">{registry.orphaned_dbs.length}</div>
              <div className="text-sm text-gray-500">Orphaned</div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
              <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <p className="text-sm font-medium text-red-800">Error</p>
                <p className="text-sm text-red-600">{error}</p>
              </div>
              <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600" title="Dismiss error">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          )}

          {loading ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 flex items-center justify-center">
              <div className="text-center">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto mb-4" />
                <p className="text-sm text-gray-500">Loading vector database registry...</p>
              </div>
            </div>
          ) : (
            <>
              {/* Search Bar */}
              <div className="mb-4">
                <input
                  type="text"
                  placeholder="Search vector databases..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full max-w-md px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              {/* Vector DBs Table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6">
                <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
                  <h2 className="font-semibold text-gray-900">Registered Vector Databases</h2>
                </div>
                
                {sortedVectorDbs.length === 0 ? (
                  <div className="p-12 text-center">
                    <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                    </svg>
                    <p className="text-sm text-gray-500">No vector databases found</p>
                    <p className="text-xs text-gray-400 mt-1">Create an agent with RAG to see vector databases here</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <th 
                            className="px-4 py-3 text-left font-medium text-gray-600 cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort('name')}
                          >
                            Name <SortIcon field="name" />
                          </th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                          <th 
                            className="px-4 py-3 text-right font-medium text-gray-600 cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort('disk_size_bytes')}
                          >
                            Disk Size <SortIcon field="disk_size_bytes" />
                          </th>
                          <th 
                            className="px-4 py-3 text-right font-medium text-gray-600 cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort('document_count')}
                          >
                            Documents <SortIcon field="document_count" />
                          </th>
                          <th className="px-4 py-3 text-right font-medium text-gray-600">Vectors</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Embedding Model</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Last Sync</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Schedule</th>
                          <th className="px-4 py-3 text-center font-medium text-gray-600">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {sortedVectorDbs.map((db) => {
                          const status = healthStatusConfig[db.health_status as HealthStatus] || healthStatusConfig.healthy;
                          return (
                            <tr key={db.name} className="hover:bg-gray-50">
                              <td className="px-4 py-3">
                                <div className="font-medium text-gray-900">{db.name}</div>
                                {db.data_source_id && (
                                  <div className="text-xs text-gray-500 truncate max-w-xs">{db.data_source_id}</div>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bgColor} ${status.color}`}>
                                  <span>{status.icon}</span>
                                  {status.label}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">
                                {db.disk_size_formatted}
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">
                                {db.document_count.toLocaleString()}
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">
                                {db.vector_count.toLocaleString()}
                              </td>
                              <td className="px-4 py-3">
                                {db.embedding_model ? (
                                  <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">
                                    {db.embedding_model}
                                  </span>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-600">
                                {db.schedule?.last_run_at ? (
                                  <div>
                                    <div>{formatDateTime(db.schedule.last_run_at)}</div>
                                    {db.schedule.last_run_status && (
                                      <span className={`text-xs ${
                                        db.schedule.last_run_status === 'success' ? 'text-green-600' :
                                        db.schedule.last_run_status === 'failed' ? 'text-red-600' :
                                        'text-yellow-600'
                                      }`}>
                                        {db.schedule.last_run_status}
                                      </span>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-gray-400">Never</span>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                {db.schedule ? (
                                  <div className="text-sm">
                                    <span className={`inline-flex items-center gap-1 ${db.schedule.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                                      <span className={`w-2 h-2 rounded-full ${db.schedule.enabled ? 'bg-green-500' : 'bg-gray-300'}`} />
                                      {db.schedule.schedule_type}
                                    </span>
                                    {db.schedule.next_run_at && (
                                      <div className="text-xs text-gray-500 mt-0.5">
                                        Next: {formatDateTime(db.schedule.next_run_at)}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-gray-400 text-sm">Not scheduled</span>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center justify-center gap-2">
                                  {db.schedule?.enabled && (
                                    <button
                                      onClick={() => handleTriggerSync(db.name)}
                                      disabled={triggeringSync === db.name}
                                      className="p-1.5 text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors disabled:opacity-50"
                                      title="Trigger sync now"
                                    >
                                      {triggeringSync === db.name ? (
                                        <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                                      ) : (
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                        </svg>
                                      )}
                                    </button>
                                  )}
                                  {deleteConfirm === db.name ? (
                                    <div className="flex items-center gap-1">
                                      <button
                                        onClick={() => handleDelete(db.name)}
                                        className="px-2 py-1 text-xs font-medium text-white bg-red-600 rounded hover:bg-red-700"
                                      >
                                        Confirm
                                      </button>
                                      <button
                                        onClick={() => setDeleteConfirm(null)}
                                        className="px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      onClick={() => setDeleteConfirm(db.name)}
                                      className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                      title="Delete vector database"
                                    >
                                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                      </svg>
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Orphaned DBs Section */}
              {registry && registry.orphaned_dbs.length > 0 && (
                <div className="bg-white rounded-xl border border-orange-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-4 border-b border-orange-200 bg-orange-50">
                    <h2 className="font-semibold text-orange-800 flex items-center gap-2">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      Orphaned Vector Databases
                    </h2>
                    <p className="text-sm text-orange-600 mt-1">
                      These ChromaDB folders exist on disk but are not registered. They may be left over from deleted agents.
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-orange-50 border-b border-orange-200">
                          <th className="px-4 py-3 text-left font-medium text-orange-700">Name</th>
                          <th className="px-4 py-3 text-left font-medium text-orange-700">Path</th>
                          <th className="px-4 py-3 text-right font-medium text-orange-700">Disk Size</th>
                          <th className="px-4 py-3 text-right font-medium text-orange-700">Vectors</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-orange-100">
                        {registry.orphaned_dbs.map((db) => (
                          <tr key={db.name} className="hover:bg-orange-50">
                            <td className="px-4 py-3 font-medium text-gray-900">{db.name}</td>
                            <td className="px-4 py-3 text-xs text-gray-500 font-mono truncate max-w-md">{db.path}</td>
                            <td className="px-4 py-3 text-right font-mono text-gray-700">{db.disk_size_formatted}</td>
                            <td className="px-4 py-3 text-right font-mono text-gray-700">{db.vector_count.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
