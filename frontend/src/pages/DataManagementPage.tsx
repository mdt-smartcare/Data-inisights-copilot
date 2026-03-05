/**
 * DataManagementPage - Unified page for File Data and Vector Registry
 * 
 * Features:
 * - Tab-based navigation between File Data and Vector Registry
 * - File Data: List uploaded tables, view schema, preview data, configure RAG
 * - Vector Registry: View all vector DBs, disk sizes, sync status, health monitoring
 */
import { useState, useEffect } from 'react';
import {
  getFileSqlTables,
  deleteFileSqlTable,
  getFileSqlTableSchema,
  executeFileSqlQuery,
  classifyTableColumns,
  getRAGStatus,
  getWorkflowCapabilities,
  getVectorDbRegistry,
  deleteVectorDb,
  triggerVectorDbSync,
  type FileTable,
  type TableSchema,
  type ColumnClassificationResult,
  type RAGStatus,
  type WorkflowCapabilities,
  type VectorDbRegistryResponse,
} from '../services/api';
import ChatHeader from '../components/chat/ChatHeader';
import RAGConfigPanel from '../components/RAGConfigPanel';
import { APP_CONFIG } from '../config';

// ============================================
// Types
// ============================================

interface TableDetails {
  schema: TableSchema | null;
  preview: Record<string, any>[] | null;
  classification: ColumnClassificationResult | null;
  ragStatus: RAGStatus | null;
}

type MainTab = 'files' | 'vectors';
type FileDetailTab = 'schema' | 'preview' | 'rag';
type HealthStatus = 'healthy' | 'warning' | 'error' | 'missing' | 'orphaned';

const healthStatusConfig: Record<HealthStatus, { color: string; bgColor: string; label: string; icon: string }> = {
  healthy: { color: 'text-green-700', bgColor: 'bg-green-100', label: 'Healthy', icon: '✓' },
  warning: { color: 'text-yellow-700', bgColor: 'bg-yellow-100', label: 'Warning', icon: '⚠' },
  error: { color: 'text-red-700', bgColor: 'bg-red-100', label: 'Error', icon: '✕' },
  missing: { color: 'text-gray-700', bgColor: 'bg-gray-100', label: 'Missing Files', icon: '?' },
  orphaned: { color: 'text-orange-700', bgColor: 'bg-orange-100', label: 'Orphaned', icon: '⊘' },
};

// ============================================
// Main Component
// ============================================

export default function DataManagementPage() {
  // Main tab state
  const [mainTab, setMainTab] = useState<MainTab>('files');
  const [error, setError] = useState<string | null>(null);

  // File Data state
  const [tables, setTables] = useState<FileTable[]>([]);
  const [tablesLoading, setTablesLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetails, setTableDetails] = useState<TableDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [capabilities, setCapabilities] = useState<WorkflowCapabilities | null>(null);
  const [fileDetailTab, setFileDetailTab] = useState<FileDetailTab>('schema');
  const [deleteTableConfirm, setDeleteTableConfirm] = useState<string | null>(null);

  // Vector Registry state
  const [registry, setRegistry] = useState<VectorDbRegistryResponse | null>(null);
  const [registryLoading, setRegistryLoading] = useState(true);
  const [deleteVectorConfirm, setDeleteVectorConfirm] = useState<string | null>(null);
  const [triggeringSync, setTriggeringSync] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState<'name' | 'disk_size_bytes' | 'document_count' | 'created_at'>('name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // Load data on mount
  useEffect(() => {
    loadTables();
    loadCapabilities();
    loadRegistry();
  }, []);

  // ============================================
  // File Data Functions
  // ============================================

  const loadTables = async () => {
    try {
      setTablesLoading(true);
      const response = await getFileSqlTables();
      setTables(response.tables || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tables');
    } finally {
      setTablesLoading(false);
    }
  };

  const loadCapabilities = async () => {
    try {
      const caps = await getWorkflowCapabilities();
      setCapabilities(caps);
    } catch (err) {
      console.error('Failed to load capabilities:', err);
    }
  };

  const loadTableDetails = async (tableName: string) => {
    setDetailsLoading(true);
    setTableDetails(null);

    try {
      const [schemaRes, classificationRes, ragStatusRes] = await Promise.allSettled([
        getFileSqlTableSchema(tableName),
        classifyTableColumns(tableName),
        getRAGStatus(tableName),
      ]);

      let previewData: Record<string, any>[] | null = null;
      try {
        const previewRes = await executeFileSqlQuery(`SELECT * FROM ${tableName} LIMIT 10`);
        previewData = previewRes.rows || null;
      } catch {
        previewData = null;
      }

      setTableDetails({
        schema: schemaRes.status === 'fulfilled' ? schemaRes.value : null,
        preview: previewData,
        classification: classificationRes.status === 'fulfilled' ? classificationRes.value : null,
        ragStatus: ragStatusRes.status === 'fulfilled' ? ragStatusRes.value : null,
      });
    } catch (err) {
      console.error('Failed to load table details:', err);
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleSelectTable = (tableName: string) => {
    setSelectedTable(tableName);
    setFileDetailTab('schema');
    loadTableDetails(tableName);
  };

  const handleDeleteTable = async (tableName: string) => {
    try {
      await deleteFileSqlTable(tableName);
      setTables(tables.filter(t => t.name !== tableName));
      if (selectedTable === tableName) {
        setSelectedTable(null);
        setTableDetails(null);
      }
      setDeleteTableConfirm(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete table');
    }
  };

  const handleRAGStatusChange = (status: RAGStatus | null) => {
    setTableDetails(prev => prev ? { ...prev, ragStatus: status } : null);
    loadCapabilities();
  };

  // ============================================
  // Vector Registry Functions
  // ============================================

  const loadRegistry = async () => {
    try {
      setRegistryLoading(true);
      const data = await getVectorDbRegistry();
      setRegistry(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load vector database registry');
    } finally {
      setRegistryLoading(false);
    }
  };

  const handleDeleteVector = async (name: string) => {
    try {
      await deleteVectorDb(name, true);
      setDeleteVectorConfirm(null);
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

  // ============================================
  // Utility Functions
  // ============================================

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  const handleRefresh = () => {
    setError(null);
    if (mainTab === 'files') {
      loadTables();
      loadCapabilities();
    } else {
      loadRegistry();
    }
  };

  const SortIcon = ({ field }: { field: typeof sortField }) => (
    <span className="ml-1 inline-block">
      {sortField === field ? (sortDirection === 'asc' ? '↑' : '↓') : <span className="text-gray-300">↕</span>}
    </span>
  );

  // ============================================
  // Render
  // ============================================

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

      {/* Page Header with Main Tabs */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex-shrink-0">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Data Management</h1>
              <p className="text-sm text-gray-500 mt-1">
                Manage uploaded files and vector databases
              </p>
            </div>
            <button
              onClick={handleRefresh}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>

          {/* Main Tab Navigation */}
          <div className="flex gap-1 border-b border-gray-200 -mb-4">
            <button
              onClick={() => setMainTab('files')}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                mainTab === 'files'
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              File Data
              <span className="ml-1 px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">
                {tables.length}
              </span>
            </button>
            <button
              onClick={() => setMainTab('vectors')}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                mainTab === 'vectors'
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              Vector Registry
              <span className="ml-1 px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">
                {registry?.total_vector_dbs || 0}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Workflow Capabilities Banner (for Files tab) */}
      {mainTab === 'files' && capabilities && (
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border-b border-indigo-100 px-6 py-3 flex-shrink-0">
          <div className="max-w-7xl mx-auto flex items-center gap-6 text-sm">
            <span className="font-medium text-gray-700">Available Workflows:</span>
            <div className="flex items-center gap-4">
              <span className={`flex items-center gap-1.5 ${capabilities.workflows.sql.available ? 'text-green-700' : 'text-gray-400'}`}>
                <span className={`w-2 h-2 rounded-full ${capabilities.workflows.sql.available ? 'bg-green-500' : 'bg-gray-300'}`} />
                SQL ({capabilities.workflows.sql.tables.length} tables)
              </span>
              <span className={`flex items-center gap-1.5 ${capabilities.workflows.rag.available ? 'text-green-700' : 'text-gray-400'}`}>
                <span className={`w-2 h-2 rounded-full ${capabilities.workflows.rag.available ? 'bg-green-500' : 'bg-gray-300'}`} />
                RAG ({capabilities.workflows.rag.tables.length} tables)
              </span>
              <span className={`flex items-center gap-1.5 ${capabilities.workflows.agentic_hybrid.available ? 'text-green-700' : 'text-gray-400'}`}>
                <span className={`w-2 h-2 rounded-full ${capabilities.workflows.agentic_hybrid.available ? 'bg-green-500' : 'bg-gray-300'}`} />
                Agentic Hybrid
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Summary Stats Banner (for Vectors tab) */}
      {mainTab === 'vectors' && registry && (
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
          {/* Error Display */}
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

          {/* FILE DATA TAB CONTENT */}
          {mainTab === 'files' && (
            <div className="grid grid-cols-12 gap-6">
              {/* Table List - Left Panel */}
              <div className="col-span-4">
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <h2 className="font-semibold text-gray-900">Uploaded Tables</h2>
                    <p className="text-xs text-gray-500 mt-0.5">{tables.length} table{tables.length !== 1 ? 's' : ''} available</p>
                  </div>

                  {tablesLoading ? (
                    <div className="p-8 flex items-center justify-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
                    </div>
                  ) : tables.length === 0 ? (
                    <div className="p-8 text-center">
                      <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                      </svg>
                      <p className="text-sm text-gray-500">No tables uploaded yet</p>
                      <p className="text-xs text-gray-400 mt-1">Upload a CSV or Excel file to get started</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
                      {tables.map((table) => (
                        <div
                          key={table.name}
                          className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${selectedTable === table.name ? 'bg-indigo-50 border-l-4 border-indigo-500' : ''}`}
                          onClick={() => handleSelectTable(table.name)}
                        >
                          <div className="flex items-start justify-between">
                            <div className="min-w-0 flex-1">
                              <h3 className="font-medium text-gray-900 truncate">{table.name}</h3>
                              <p className="text-xs text-gray-500 truncate mt-0.5">{table.original_filename}</p>
                              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                                <span className="flex items-center gap-1">
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                                  </svg>
                                  {table.row_count.toLocaleString()} rows
                                </span>
                                <span className="flex items-center gap-1">
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7" />
                                  </svg>
                                  {table.columns.length} cols
                                </span>
                              </div>
                            </div>
                            <span className={`px-2 py-0.5 text-xs font-medium rounded ${table.file_type === 'csv' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                              {table.file_type.toUpperCase()}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Table Details - Right Panel */}
              <div className="col-span-8">
                {!selectedTable ? (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
                    <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                    </svg>
                    <h3 className="text-lg font-medium text-gray-900">Select a table</h3>
                    <p className="text-sm text-gray-500 mt-1">Choose a table from the list to view its details</p>
                  </div>
                ) : detailsLoading ? (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 flex items-center justify-center">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto mb-4" />
                      <p className="text-sm text-gray-500">Loading table details...</p>
                    </div>
                  </div>
                ) : (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                    {/* Table Header */}
                    <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
                      <div>
                        <h2 className="text-lg font-semibold text-gray-900">{selectedTable}</h2>
                        <p className="text-sm text-gray-500">
                          {tables.find(t => t.name === selectedTable)?.original_filename}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {deleteTableConfirm === selectedTable ? (
                          <>
                            <span className="text-sm text-red-600 mr-2">Delete this table?</span>
                            <button onClick={() => handleDeleteTable(selectedTable)} className="px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700">Confirm</button>
                            <button onClick={() => setDeleteTableConfirm(null)} className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
                          </>
                        ) : (
                          <button onClick={() => setDeleteTableConfirm(selectedTable)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 transition-colors">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Delete
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Detail Tabs */}
                    <div className="border-b border-gray-200">
                      <nav className="flex -mb-px">
                        {[
                          { id: 'schema', label: 'Schema', icon: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7' },
                          { id: 'preview', label: 'Preview', icon: 'M4 6h16M4 10h16M4 14h16M4 18h16' },
                          { id: 'rag', label: 'RAG Config', icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z' },
                        ].map((tab) => (
                          <button
                            key={tab.id}
                            onClick={() => setFileDetailTab(tab.id as FileDetailTab)}
                            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                              fileDetailTab === tab.id
                                ? 'border-indigo-500 text-indigo-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
                            </svg>
                            {tab.label}
                          </button>
                        ))}
                      </nav>
                    </div>

                    {/* Tab Content */}
                    <div className="p-6">
                      {fileDetailTab === 'schema' && tableDetails?.schema && (
                        <div>
                          <h3 className="text-sm font-semibold text-gray-700 mb-3">Column Definitions</h3>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="bg-gray-50">
                                  <th className="px-4 py-2 text-left font-medium text-gray-600">Column Name</th>
                                  <th className="px-4 py-2 text-left font-medium text-gray-600">Data Type</th>
                                  <th className="px-4 py-2 text-left font-medium text-gray-600">Classification</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {tableDetails.schema.schema.map((col, idx) => (
                                  <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-4 py-2 font-mono text-gray-900">{col.column_name}</td>
                                    <td className="px-4 py-2 text-gray-600">{col.data_type}</td>
                                    <td className="px-4 py-2">
                                      {tableDetails.classification?.classifications[col.column_name] && (
                                        <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                                          tableDetails.classification.classifications[col.column_name].type === 'text'
                                            ? 'bg-purple-100 text-purple-700'
                                            : 'bg-gray-100 text-gray-600'
                                        }`}>
                                          {tableDetails.classification.classifications[col.column_name].type}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {fileDetailTab === 'preview' && (
                        <div>
                          <h3 className="text-sm font-semibold text-gray-700 mb-3">Data Preview (First 10 Rows)</h3>
                          {tableDetails?.preview && tableDetails.preview.length > 0 ? (
                            <div className="overflow-x-auto border border-gray-200 rounded-lg">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="bg-gray-50">
                                    {Object.keys(tableDetails.preview[0]).map((col) => (
                                      <th key={col} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">{col}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                  {tableDetails.preview.map((row, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50">
                                      {Object.values(row).map((val: any, colIdx) => (
                                        <td key={colIdx} className="px-3 py-2 text-gray-900 max-w-xs truncate">
                                          {val === null ? <span className="text-gray-400 italic">null</span> : String(val)}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <p className="text-sm text-gray-500">No preview data available</p>
                          )}
                        </div>
                      )}

                      {fileDetailTab === 'rag' && selectedTable && (
                        <RAGConfigPanel
                          tableName={selectedTable}
                          onStatusChange={handleRAGStatusChange}
                          onError={(msg) => setError(msg)}
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* VECTOR REGISTRY TAB CONTENT */}
          {mainTab === 'vectors' && (
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
                
                {registryLoading ? (
                  <div className="p-12 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
                  </div>
                ) : sortedVectorDbs.length === 0 ? (
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
                          <th className="px-4 py-3 text-left font-medium text-gray-600 cursor-pointer hover:bg-gray-100" onClick={() => handleSort('name')}>
                            Name <SortIcon field="name" />
                          </th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                          <th className="px-4 py-3 text-right font-medium text-gray-600 cursor-pointer hover:bg-gray-100" onClick={() => handleSort('disk_size_bytes')}>
                            Disk Size <SortIcon field="disk_size_bytes" />
                          </th>
                          <th className="px-4 py-3 text-right font-medium text-gray-600 cursor-pointer hover:bg-gray-100" onClick={() => handleSort('document_count')}>
                            Documents <SortIcon field="document_count" />
                          </th>
                          <th className="px-4 py-3 text-right font-medium text-gray-600">Vectors</th>
                          <th className="px-4 py-3 text-left font-medium text-gray-600">Model</th>
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
                                {db.data_source_id && <div className="text-xs text-gray-500 truncate max-w-xs">{db.data_source_id}</div>}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${status.bgColor} ${status.color}`}>
                                  <span>{status.icon}</span> {status.label}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">{db.disk_size_formatted}</td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">{db.document_count.toLocaleString()}</td>
                              <td className="px-4 py-3 text-right font-mono text-gray-700">{db.vector_count.toLocaleString()}</td>
                              <td className="px-4 py-3">
                                {db.embedding_model ? (
                                  <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">{db.embedding_model}</span>
                                ) : <span className="text-gray-400">-</span>}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-600">
                                {db.schedule?.last_run_at ? (
                                  <div>
                                    <div>{formatDate(db.schedule.last_run_at)}</div>
                                    {db.schedule.last_run_status && (
                                      <span className={`text-xs ${db.schedule.last_run_status === 'success' ? 'text-green-600' : db.schedule.last_run_status === 'failed' ? 'text-red-600' : 'text-yellow-600'}`}>
                                        {db.schedule.last_run_status}
                                      </span>
                                    )}
                                  </div>
                                ) : <span className="text-gray-400">Never</span>}
                              </td>
                              <td className="px-4 py-3">
                                {db.schedule ? (
                                  <div className="text-sm">
                                    <span className={`inline-flex items-center gap-1 ${db.schedule.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                                      <span className={`w-2 h-2 rounded-full ${db.schedule.enabled ? 'bg-green-500' : 'bg-gray-300'}`} />
                                      {db.schedule.schedule_type}
                                    </span>
                                    {db.schedule.next_run_at && <div className="text-xs text-gray-500 mt-0.5">Next: {formatDate(db.schedule.next_run_at)}</div>}
                                  </div>
                                ) : <span className="text-gray-400 text-sm">Not scheduled</span>}
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
                                  {deleteVectorConfirm === db.name ? (
                                    <div className="flex items-center gap-1">
                                      <button onClick={() => handleDeleteVector(db.name)} className="px-2 py-1 text-xs font-medium text-white bg-red-600 rounded hover:bg-red-700">Confirm</button>
                                      <button onClick={() => setDeleteVectorConfirm(null)} className="px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200">Cancel</button>
                                    </div>
                                  ) : (
                                    <button onClick={() => setDeleteVectorConfirm(db.name)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Delete vector database">
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
