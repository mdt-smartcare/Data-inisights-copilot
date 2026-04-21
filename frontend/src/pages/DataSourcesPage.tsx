/**
 * DataSourcesPage - Manage database connections and file uploads
 * 
 * Provides a unified interface for:
 * - Adding database connections (PostgreSQL, MySQL, SQLite, etc.)
 * - Uploading files (CSV, Excel) for SQL queries via DuckDB
 * - Listing and managing all data sources
 * - Testing database connections
 */
import { useState, useEffect, useRef } from 'react';
import { ChatHeader } from '../components/chat';
import { useToast } from '../components/Toast';
import { APP_CONFIG } from '../config';
import ConfirmationModal from '../components/ConfirmationModal';
import {
  getDataSources,
  createDatabaseSource,
  deleteDataSource,
  uploadDataSourceFile,
  updateDataSource,
  type DataSource,
} from '../services/api';
import { formatDateTime } from '../utils/datetime';

// ============================================
// Types
// ============================================

type TabType = 'all' | 'database' | 'file';
type ModalType = 'database' | 'file' | null;

interface FormState {
  title: string;
  description: string;
  db_url: string;
  db_engine_type: string;
}

// ============================================
// Main Component
// ============================================

export default function DataSourcesPage() {
  // Data state
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Toast notifications
  const { error: errorToast } = useToast();

  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>('all');

  // Modal state
  const [modalType, setModalType] = useState<ModalType>(null);
  const [formState, setFormState] = useState<FormState>({
    title: '',
    description: '',
    db_url: '',
    db_engine_type: 'postgresql',
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<{ show: boolean; id: string | null; title: string }>({
    show: false,
    id: null,
    title: '',
  });

  // Edit state
  const [editingSource, setEditingSource] = useState<DataSource | null>(null);

  // ============================================
  // Data Loading
  // ============================================

  const loadDataSources = async () => {
    try {
      setLoading(true);
      const sourceType = activeTab === 'all' ? undefined : activeTab;
      const response = await getDataSources({ source_type: sourceType });
      setDataSources(response.data_sources || []);
    } catch {
      // Silently fail - show empty state
      setDataSources([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDataSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // ============================================
  // Database Connection Handlers
  // ============================================

  const handleCreateDatabase = async () => {
    if (!formState.title || !formState.db_url || !formState.db_engine_type) {
      setFormError('Please fill in all required fields');
      return;
    }

    try {
      setFormLoading(true);
      setFormError(null);
      await createDatabaseSource({
        title: formState.title,
        description: formState.description || undefined,
        source_type: 'database',
        db_url: formState.db_url,
        db_engine_type: formState.db_engine_type,
      });
      setModalType(null);
      resetForm();
      loadDataSources();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to create data source');
    } finally {
      setFormLoading(false);
    }
  };

  // ============================================
  // File Upload Handlers
  // ============================================

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      if (!formState.title) {
        setFormState(prev => ({ ...prev, title: file.name.replace(/\.[^/.]+$/, '') }));
      }
    }
  };

  const handleUploadFile = async () => {
    if (!selectedFile) {
      setFormError('Please select a file');
      return;
    }

    try {
      setFormLoading(true);
      setFormError(null);
      setUploadProgress('Uploading...');

      await uploadDataSourceFile(
        selectedFile,
        formState.title || undefined,
        formState.description || undefined
      );

      setUploadProgress('Processing complete!');
      setTimeout(() => {
        setModalType(null);
        resetForm();
        loadDataSources();
      }, 1000);
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Upload failed');
      setUploadProgress(null);
    } finally {
      setFormLoading(false);
    }
  };

  // ============================================
  // Delete Handlers
  // ============================================

  const handleDeleteClick = (source: DataSource) => {
    setDeleteConfirm({ show: true, id: source.id, title: source.title });
  };

  const confirmDelete = async () => {
    if (!deleteConfirm.id) return;

    try {
      await deleteDataSource(deleteConfirm.id);
      setDeleteConfirm({ show: false, id: null, title: '' });
      loadDataSources();
    } catch (err: any) {
      // Handle both error structures:
      // 1. FastAPI HTTPException: err.response.data.detail
      // 2. Wrapped error: err.response.data.message
      const errorDetail = err.response?.data?.detail;
      const errorMessage = err.response?.data?.message;
      
      // Try to get reason from either structure
      const reason = errorDetail?.reason || errorMessage?.reason;
      
      if (err.response?.status === 409 && reason) {
        errorToast('Cannot Delete', reason);
      } else {
        // Fallback to message or generic error
        const fallbackMsg = errorDetail?.message || errorMessage?.message || 
                           (typeof errorDetail === 'string' ? errorDetail : null) ||
                           (typeof errorMessage === 'string' ? errorMessage : null) ||
                           'Failed to delete data source';
        errorToast('Error', fallbackMsg);
      }
      setDeleteConfirm({ show: false, id: null, title: '' });
    }
  };

  // ============================================
  // Edit Handlers
  // ============================================

  const handleEditClick = (source: DataSource) => {
    setEditingSource(source);
    setFormState({
      title: source.title,
      description: source.description || '',
      // Don't pre-fill db_url - it's no longer returned for security
      // User must re-enter if they want to change it
      db_url: '',
      db_engine_type: source.db_engine_type || 'postgresql',
    });
    setFormError(null);
    // Open the appropriate modal based on source type
    setModalType(source.source_type as 'database' | 'file');
  };

  const handleUpdateDataSource = async () => {
    if (!editingSource) return;
    if (!formState.title.trim()) {
      setFormError('Name is required');
      return;
    }

    try {
      setFormLoading(true);
      setFormError(null);

      const updateData: { title?: string; description?: string; db_url?: string; db_engine_type?: string } = {};

      // Only send changed fields
      if (formState.title !== editingSource.title) {
        updateData.title = formState.title;
      }
      if (formState.description !== (editingSource.description || '')) {
        updateData.description = formState.description || undefined;
      }
      if (editingSource.source_type === 'database') {
        // Only update db_url if user provided a new one
        if (formState.db_url.trim()) {
          updateData.db_url = formState.db_url;
        }
        if (formState.db_engine_type !== editingSource.db_engine_type) {
          updateData.db_engine_type = formState.db_engine_type;
        }
      }

      if (Object.keys(updateData).length === 0) {
        setModalType(null);
        resetForm();
        return;
      }

      await updateDataSource(editingSource.id, updateData);
      setModalType(null);
      resetForm();
      loadDataSources();
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 409) {
        // Data source is in use by an active agent configuration
        setFormError(detail || 'This data source is currently in use by an active agent configuration and cannot be modified.');
      } else {
        setFormError(detail || 'Failed to update data source');
      }
    } finally {
      setFormLoading(false);
    }
  };

  // ============================================
  // Helpers
  // ============================================

  const resetForm = () => {
    setFormState({
      title: '',
      description: '',
      db_url: '',
      db_engine_type: 'postgresql',
    });
    setFormError(null);
    setSelectedFile(null);
    setUploadProgress(null);
    setEditingSource(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const openModal = (type: ModalType) => {
    resetForm();
    setModalType(type);
  };

  const getSourceTypeIcon = (type: string) => {
    if (type === 'database') {
      return (
        <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
        </svg>
      );
    }
    return (
      <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    );
  };

  // Using formatDateTime from utils/datetime for consistent local timezone display
  const formatDate = formatDateTime;

  // ============================================
  // Render
  // ============================================

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

      <div className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto px-4 py-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Data Sources</h1>
              <p className="text-gray-600 mt-1">
                Manage database connections and file uploads for your agents
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => openModal('database')}
                className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add Database
              </button>
              <button
                onClick={() => openModal('file')}
                className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Upload File
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
            {(['all', 'database', 'file'] as TabType[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === tab
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
                  }`}
              >
                {tab === 'all' ? 'All Sources' : tab === 'database' ? 'Databases' : 'Files'}
              </button>
            ))}
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-gray-500">Loading data sources...</span>
            </div>
          )}

          {/* Empty State */}
          {!loading && dataSources.length === 0 && (
            <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
              <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900">No data sources</h3>
              <p className="mt-1 text-sm text-gray-500">
                Get started by adding a database connection or uploading a file.
              </p>
              <div className="mt-6 flex justify-center gap-3">
                <button
                  onClick={() => openModal('database')}
                  className="inline-flex items-center px-4 py-2 border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50"
                >
                  Add Database
                </button>
                <button
                  onClick={() => openModal('file')}
                  className="inline-flex items-center px-4 py-2 border border-green-600 text-green-600 rounded-lg hover:bg-green-50"
                >
                  Upload File
                </button>
              </div>
            </div>
          )}

          {/* Data Sources List */}
          {!loading && dataSources.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Details
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Used By
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {dataSources.map((source) => (
                    <tr key={source.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {getSourceTypeIcon(source.source_type)}
                          <div className="ml-3">
                            <div className="text-sm font-medium text-gray-900">{source.title}</div>
                            {source.description && (
                              <div className="text-sm text-gray-500 truncate max-w-xs">
                                {source.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${source.source_type === 'database'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-green-100 text-green-800'
                          }`}>
                          {source.source_type === 'database' ? source.db_engine_type || 'Database' : source.file_type?.toUpperCase() || 'File'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {source.source_type === 'database' ? (
                          <span className="text-sm text-gray-500 font-mono truncate max-w-xs block">
                            {source.db_url || '-'}
                          </span>
                        ) : (
                          <div className="text-sm text-gray-500">
                            {source.duckdb_table_name && (
                              <span className="font-mono">{source.duckdb_table_name}</span>
                            )}
                            {source.row_count !== undefined && (
                              <span className="ml-2 text-gray-400">
                                ({source.row_count.toLocaleString()} rows)
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDate(source.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {source.dependent_config_count && source.dependent_config_count > 0 ? (
                          <div className="flex flex-col">
                            <span className="text-sm font-medium text-orange-600">
                              {source.dependent_config_count} Agent{source.dependent_config_count > 1 ? 's' : ''}
                            </span>
                            <span
                              className="text-xs text-gray-500 truncate max-w-[150px] cursor-help"
                              title={source.dependent_agents?.join(', ')}
                            >
                              {source.dependent_agents?.join(', ')}
                            </span>
                          </div>
                        ) : (
                          <span className="text-sm text-gray-400 italic">Not in use</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => handleEditClick(source)}
                          className="text-blue-600 hover:text-blue-900 mr-4"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteClick(source)}
                          className="text-red-600 hover:text-red-900"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Database Modal */}
      {modalType === 'database' && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">
                  {editingSource ? 'Edit Database Connection' : 'Add Database Connection'}
                </h2>
                <button
                  onClick={() => { setModalType(null); resetForm(); }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {formError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {formError}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={formState.title}
                    onChange={(e) => setFormState(prev => ({ ...prev, title: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="e.g., Production FHIR Database"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formState.description}
                    onChange={(e) => setFormState(prev => ({ ...prev, description: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows={2}
                    placeholder="Optional description"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Database Engine <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formState.db_engine_type}
                    onChange={(e) => setFormState(prev => ({ ...prev, db_engine_type: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="postgresql">PostgreSQL</option>
                    <option value="mysql">MySQL</option>
                    <option value="sqlite">SQLite</option>
                    <option value="mssql">SQL Server</option>
                    <option value="oracle">Oracle</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Connection URL <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={formState.db_url}
                    onChange={(e) => setFormState(prev => ({ ...prev, db_url: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                    placeholder="postgresql://user:password@host:5432/database"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Format: engine://user:password@host:port/database
                  </p>
                </div>

                <div className="flex gap-3 pt-4">
                  <button
                    onClick={() => { setModalType(null); resetForm(); }}
                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={editingSource ? handleUpdateDataSource : handleCreateDatabase}
                    disabled={formLoading || !formState.title || !formState.db_url}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {formLoading ? (editingSource ? 'Saving...' : 'Creating...') : (editingSource ? 'Save Changes' : 'Create')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* File Upload Modal */}
      {modalType === 'file' && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">
                  {editingSource ? 'Edit File Source' : 'Upload File'}
                </h2>
                <button
                  onClick={() => { setModalType(null); resetForm(); }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {formError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {formError}
                </div>
              )}

              <div className="space-y-4">
                {/* File Drop Zone - only show when creating */}
                {!editingSource && (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${selectedFile
                        ? 'border-green-300 bg-green-50'
                        : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50'
                      }`}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      onChange={handleFileSelect}
                      accept=".csv,.xlsx,.xls,.pdf,.json"
                      className="hidden"
                    />
                    {selectedFile ? (
                      <div className="flex flex-col items-center">
                        <svg className="w-12 h-12 text-green-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <p className="text-sm font-medium text-gray-900">{selectedFile.name}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedFile(null);
                            if (fileInputRef.current) fileInputRef.current.value = '';
                          }}
                          className="mt-2 text-sm text-red-600 hover:text-red-800"
                        >
                          Remove
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center">
                        <svg className="w-12 h-12 text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                        <p className="text-sm text-gray-600">
                          <span className="font-medium text-blue-600">Click to upload</span> or drag and drop
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          CSV, Excel (.xlsx), PDF, or JSON
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* File info when editing (read-only) */}
                {editingSource && (
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <div className="text-sm text-gray-600">
                      <p><span className="font-medium">File Type:</span> {editingSource.file_type?.toUpperCase()}</p>
                      {editingSource.duckdb_table_name && (
                        <p><span className="font-medium">Table:</span> <code className="text-xs bg-gray-200 px-1 rounded">{editingSource.duckdb_table_name}</code></p>
                      )}
                      {editingSource.row_count !== undefined && (
                        <p><span className="font-medium">Rows:</span> {editingSource.row_count.toLocaleString()}</p>
                      )}
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name {editingSource && <span className="text-red-500">*</span>}
                  </label>
                  <input
                    type="text"
                    value={formState.title}
                    onChange={(e) => setFormState(prev => ({ ...prev, title: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder={editingSource ? "Data source name" : "Data source name (optional)"}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formState.description}
                    onChange={(e) => setFormState(prev => ({ ...prev, description: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows={2}
                    placeholder="Optional description"
                  />
                </div>

                {/* Upload Progress - only when creating */}
                {!editingSource && uploadProgress && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex items-center gap-2 text-blue-700">
                      {formLoading && (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-700"></div>
                      )}
                      <span>{uploadProgress}</span>
                    </div>
                  </div>
                )}

                <div className="flex gap-3 pt-4">
                  <button
                    onClick={() => { setModalType(null); resetForm(); }}
                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={editingSource ? handleUpdateDataSource : handleUploadFile}
                    disabled={formLoading || (editingSource ? !formState.title.trim() : !selectedFile)}
                    className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {formLoading
                      ? (editingSource ? 'Saving...' : 'Uploading...')
                      : (editingSource ? 'Save Changes' : 'Upload')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        show={deleteConfirm.show}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm({ show: false, id: null, title: '' })}
        title="Delete Data Source"
        message={`Are you sure you want to delete "${deleteConfirm.title}"? This action cannot be undone.`}
        confirmText="Delete"
        type="danger"
      />
    </div>
  );
}
