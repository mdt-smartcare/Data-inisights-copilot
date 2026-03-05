/**
 * RAGConfigPanel - Configure which columns get embedded for semantic search
 * 
 * Features:
 * - Display column classification results (text vs structured)
 * - Select text columns for embedding
 * - Configure chunking parameters
 * - Start and monitor RAG processing status
 * - Show recommendations for optimal embedding
 */
import React, { useState, useEffect } from 'react';
import {
  classifyTableColumns,
  startRAGEmbedding,
  getRAGStatus,
  deleteRAGEmbeddings,
  type ColumnClassificationResult,
  type RAGStatus,
  type RAGConfig,
} from '../services/api';

interface RAGConfigPanelProps {
  tableName: string;
  onStatusChange?: (status: RAGStatus | null) => void;
  onError?: (error: string) => void;
}

type ProcessingState = 'idle' | 'classifying' | 'embedding' | 'completed' | 'failed';

const RAGConfigPanel: React.FC<RAGConfigPanelProps> = ({
  tableName,
  onStatusChange,
  onError,
}) => {
  // Classification state
  const [classification, setClassification] = useState<ColumnClassificationResult | null>(null);
  const [classificationLoading, setClassificationLoading] = useState(false);
  
  // Selection state
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [idColumn, setIdColumn] = useState<string>('');
  
  // Advanced config
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [parentChunkSize, setParentChunkSize] = useState(800);
  const [childChunkSize, setChildChunkSize] = useState(200);
  
  // Processing state
  const [processingState, setProcessingState] = useState<ProcessingState>('idle');
  const [ragStatus, setRagStatus] = useState<RAGStatus | null>(null);
  const [statusPolling, setStatusPolling] = useState(false);
  
  // Error state
  const [error, setError] = useState<string | null>(null);

  // Load classification on mount or table change
  useEffect(() => {
    if (tableName) {
      loadClassification();
      loadRAGStatus();
    }
  }, [tableName]);

  // Poll for status while processing
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    
    if (statusPolling && processingState === 'embedding') {
      intervalId = setInterval(async () => {
        try {
          const status = await getRAGStatus(tableName);
          setRagStatus(status);
          onStatusChange?.(status);
          
          if (status.status === 'completed' || status.status === 'ready') {
            setProcessingState('completed');
            setStatusPolling(false);
          } else if (status.status === 'failed' || status.error) {
            setProcessingState('failed');
            setStatusPolling(false);
            setError(status.error || 'RAG processing failed');
          }
        } catch (err) {
          console.error('Status poll error:', err);
        }
      }, 3000);
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [statusPolling, processingState, tableName, onStatusChange]);

  const loadClassification = async () => {
    setClassificationLoading(true);
    setError(null);
    
    try {
      const result = await classifyTableColumns(tableName);
      setClassification(result);
      
      // Auto-select recommended columns
      if (result.recommendation?.embed_for_rag) {
        setSelectedColumns(result.recommendation.embed_for_rag);
      }
      
      // Auto-select ID column if available
      if (result.structured_columns?.length > 0) {
        const idCandidates = result.structured_columns.filter(
          col => col.toLowerCase().includes('id') || col.toLowerCase().includes('key')
        );
        if (idCandidates.length > 0) {
          setIdColumn(idCandidates[0]);
        } else {
          setIdColumn(result.structured_columns[0]);
        }
      }
    } catch (err: any) {
      const message = err.response?.data?.detail || 'Failed to classify columns';
      setError(message);
      onError?.(message);
    } finally {
      setClassificationLoading(false);
    }
  };

  const loadRAGStatus = async () => {
    try {
      const status = await getRAGStatus(tableName);
      setRagStatus(status);
      onStatusChange?.(status);
      
      if (status.status === 'completed' || status.status === 'ready') {
        setProcessingState('completed');
        if (status.text_columns) {
          setSelectedColumns(status.text_columns);
        }
        if (status.id_column) {
          setIdColumn(status.id_column);
        }
      } else if (status.status === 'processing') {
        setProcessingState('embedding');
        setStatusPolling(true);
      }
    } catch (err) {
      // Table might not have RAG configured yet, which is fine
      console.log('No existing RAG config for table');
    }
  };

  const handleColumnToggle = (column: string) => {
    setSelectedColumns(prev => 
      prev.includes(column)
        ? prev.filter(c => c !== column)
        : [...prev, column]
    );
  };

  const handleSelectAll = () => {
    if (classification?.classifications) {
      setSelectedColumns(Object.keys(classification.classifications));
    }
  };

  const handleSelectAllText = () => {
    if (classification?.text_columns && classification.text_columns.length > 0) {
      setSelectedColumns(classification.text_columns);
    }
  };

  const handleClearSelection = () => {
    setSelectedColumns([]);
  };

  const handleStartEmbedding = async () => {
    if (selectedColumns.length === 0) {
      setError('Please select at least one text column to embed');
      return;
    }
    
    setProcessingState('embedding');
    setError(null);
    
    try {
      const config: RAGConfig = {
        table_name: tableName,
        text_columns: selectedColumns,
        id_column: idColumn || undefined,
        parent_chunk_size: parentChunkSize,
        child_chunk_size: childChunkSize,
      };
      
      const result = await startRAGEmbedding(config);
      
      if (result.status === 'success' || result.status === 'completed') {
        setProcessingState('completed');
        await loadRAGStatus();
      } else if (result.status === 'processing') {
        setStatusPolling(true);
      } else if (result.error) {
        setProcessingState('failed');
        setError(result.error);
      }
    } catch (err: any) {
      setProcessingState('failed');
      const message = err.response?.data?.detail || 'Failed to start RAG embedding';
      setError(message);
      onError?.(message);
    }
  };

  const handleDeleteEmbeddings = async () => {
    if (!confirm(`Are you sure you want to delete RAG embeddings for "${tableName}"? This cannot be undone.`)) {
      return;
    }
    
    try {
      await deleteRAGEmbeddings(tableName);
      setRagStatus(null);
      setProcessingState('idle');
      onStatusChange?.(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || 'Failed to delete embeddings';
      setError(message);
      onError?.(message);
    }
  };

  const getColumnTypeIcon = (type: string) => {
    switch (type) {
      case 'text':
      case 'long_text':
        return (
          <svg className="w-4 h-4 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
          </svg>
        );
      case 'numeric':
        return (
          <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
          </svg>
        );
      case 'categorical':
        return (
          <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
          </svg>
        );
      case 'date':
      case 'datetime':
        return (
          <svg className="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        );
      default:
        return (
          <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
          </svg>
        );
    }
  };

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.8) {
      return <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">High</span>;
    } else if (confidence >= 0.5) {
      return <span className="px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-700 rounded-full">Medium</span>;
    } else {
      return <span className="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded-full">Low</span>;
    }
  };

  const renderStatusBadge = () => {
    if (!ragStatus) return null;
    
    const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
      ready: { bg: 'bg-green-100', text: 'text-green-700', label: 'Ready' },
      completed: { bg: 'bg-green-100', text: 'text-green-700', label: 'Completed' },
      processing: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Processing' },
      pending: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Pending' },
      failed: { bg: 'bg-red-100', text: 'text-red-700', label: 'Failed' },
      not_configured: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Not Configured' },
    };
    
    const config = statusConfig[ragStatus.status] || statusConfig.not_configured;
    
    return (
      <span className={`px-3 py-1 text-sm font-medium ${config.bg} ${config.text} rounded-full`}>
        {config.label}
      </span>
    );
  };

  // Loading state
  if (classificationLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mr-3"></div>
          <span className="text-gray-600">Analyzing column types...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-purple-50 to-indigo-50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              RAG Configuration
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              Configure semantic search embeddings for <span className="font-medium">{tableName}</span>
            </p>
          </div>
          {renderStatusBadge()}
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">Error</p>
            <p className="text-sm text-red-600">{error}</p>
          </div>
          <button 
            onClick={() => setError(null)} 
            className="text-red-400 hover:text-red-600"
            title="Dismiss error"
            aria-label="Dismiss error"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      )}

      {/* Processing Status */}
      {processingState === 'embedding' && (
        <div className="mx-6 mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
            <div>
              <p className="text-sm font-medium text-blue-800">Processing Embeddings</p>
              <p className="text-sm text-blue-600">
                {ragStatus?.stats?.embeddings_created 
                  ? `${ragStatus.stats.embeddings_created} embeddings created...`
                  : 'Generating embeddings for selected columns...'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Completed Status */}
      {processingState === 'completed' && ragStatus && (
        <div className="mx-6 mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-green-500 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="text-sm font-medium text-green-800">RAG Embeddings Ready</p>
                <div className="text-sm text-green-600 mt-1 space-y-0.5">
                  {ragStatus.stats && (
                    <>
                      {ragStatus.stats.parent_chunks && (
                        <p>• {ragStatus.stats.parent_chunks} parent chunks</p>
                      )}
                      {ragStatus.stats.child_chunks && (
                        <p>• {ragStatus.stats.child_chunks} child chunks</p>
                      )}
                      {ragStatus.stats.embeddings_created && (
                        <p>• {ragStatus.stats.embeddings_created} total embeddings</p>
                      )}
                    </>
                  )}
                  {ragStatus.updated_at && (
                    <p className="text-green-500 text-xs mt-1">
                      Last updated: {new Date(ragStatus.updated_at).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
            </div>
            <button
              onClick={handleDeleteEmbeddings}
              className="text-red-600 hover:text-red-700 text-sm font-medium"
            >
              Delete
            </button>
          </div>
        </div>
      )}

      {/* Column Classification Results */}
      {classification && (
        <div className="p-6 space-y-6">
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-purple-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-purple-700">{classification.text_columns?.length || 0}</div>
              <div className="text-sm text-purple-600">Text Columns</div>
              <div className="text-xs text-purple-500 mt-1">Suitable for embedding</div>
            </div>
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-blue-700">{classification.structured_columns?.length || 0}</div>
              <div className="text-sm text-blue-600">Structured Columns</div>
              <div className="text-xs text-blue-500 mt-1">Best for SQL queries</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-700">{classification.total_columns || 0}</div>
              <div className="text-sm text-gray-600">Total Columns</div>
              <div className="text-xs text-gray-500 mt-1">
                ~{classification.recommendation?.estimated_rag_rows || 'N/A'} rows
              </div>
            </div>
          </div>

          {/* Recommendation Banner */}
          {classification.recommendation?.embed_for_rag && classification.recommendation.embed_for_rag.length > 0 && (
            <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-lg p-4 border border-indigo-100">
              <div className="flex items-start gap-3">
                <svg className="w-5 h-5 text-indigo-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-indigo-800">Recommended for Embedding</p>
                  <p className="text-sm text-indigo-600 mt-1">
                    Based on content analysis, we recommend embedding these columns: {' '}
                    <span className="font-medium">{classification.recommendation.embed_for_rag.join(', ')}</span>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Column Selection */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-gray-900">Select Columns for Embedding</h4>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSelectAllText}
                  className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  Select All Text
                </button>
                <span className="text-gray-300">|</span>
                <button
                  onClick={handleClearSelection}
                  className="text-sm text-gray-600 hover:text-gray-700 font-medium"
                >
                  Clear
                </button>
                <span className="text-gray-300">|</span>
                <button
                  onClick={handleSelectAll}
                  className="text-sm text-gray-600 hover:text-gray-700 font-medium"
                >
                  Select All
                </button>
              </div>
            </div>

            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-80 overflow-y-auto">
              {Object.entries(classification.classifications || {}).map(([column, info]) => {
                const isText = classification.text_columns?.includes(column);
                const isSelected = selectedColumns.includes(column);
                const isRecommended = classification.recommendation?.embed_for_rag?.includes(column);
                
                return (
                  <div
                    key={column}
                    className={`p-4 hover:bg-gray-50 transition-colors ${isSelected ? 'bg-indigo-50' : ''}`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleColumnToggle(column)}
                        className="mt-1 h-4 w-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500"
                        title={`Select ${column} for embedding`}
                        aria-label={`Select ${column} for embedding`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {getColumnTypeIcon(info.type)}
                          <span className="font-medium text-gray-900">{column}</span>
                          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                            {info.type}
                          </span>
                          {getConfidenceBadge(info.confidence)}
                          {isRecommended && (
                            <span className="text-xs text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded-full">
                              Recommended
                            </span>
                          )}
                          {isText && !isRecommended && (
                            <span className="text-xs text-purple-600 bg-purple-100 px-2 py-0.5 rounded-full">
                              Text
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-500 mt-1">{info.reason}</p>
                        {info.sample_values && info.sample_values.length > 0 && (
                          <div className="mt-2">
                            <p className="text-xs text-gray-400 mb-1">Sample values:</p>
                            <div className="flex flex-wrap gap-1">
                              {info.sample_values.slice(0, 3).map((val, i) => (
                                <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded truncate max-w-48">
                                  {val.length > 50 ? val.substring(0, 50) + '...' : val}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {info.avg_length > 0 && (
                          <p className="text-xs text-gray-400 mt-1">
                            Avg. length: {Math.round(info.avg_length)} characters
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ID Column Selection */}
          {classification.structured_columns && classification.structured_columns.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                ID Column (for linking results)
              </label>
              <select
                value={idColumn}
                onChange={(e) => setIdColumn(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                title="Select ID column"
                aria-label="Select ID column for linking results"
              >
                <option value="">Select ID column...</option>
                {classification.structured_columns.map(col => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                This column will be used to link semantic search results back to your data
              </p>
            </div>
          )}

          {/* Advanced Settings */}
          <div>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800"
            >
              <svg
                className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Advanced Settings
            </button>
            
            {showAdvanced && (
              <div className="mt-4 p-4 bg-gray-50 rounded-lg space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Parent Chunk Size
                    </label>
                    <input
                      type="number"
                      value={parentChunkSize}
                      onChange={(e) => setParentChunkSize(Number(e.target.value))}
                      min={100}
                      max={2000}
                      step={100}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      title="Parent chunk size"
                      aria-label="Parent chunk size"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Larger chunks for context (default: 800)
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Child Chunk Size
                    </label>
                    <input
                      type="number"
                      value={childChunkSize}
                      onChange={(e) => setChildChunkSize(Number(e.target.value))}
                      min={50}
                      max={500}
                      step={50}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      title="Child chunk size"
                      aria-label="Child chunk size"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Smaller chunks for precision (default: 200)
                    </p>
                  </div>
                </div>
                <div className="text-xs text-gray-500 bg-white p-3 rounded border border-gray-200">
                  <strong>How it works:</strong> Text is split into parent and child chunks. 
                  Child chunks are used for precise semantic matching, while parent chunks 
                  provide fuller context in results.
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-between pt-4 border-t border-gray-200">
            <div className="text-sm text-gray-500">
              {selectedColumns.length > 0 ? (
                <span>{selectedColumns.length} column{selectedColumns.length !== 1 ? 's' : ''} selected</span>
              ) : (
                <span>No columns selected</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={loadClassification}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Re-analyze
              </button>
              <button
                onClick={handleStartEmbedding}
                disabled={selectedColumns.length === 0 || processingState === 'embedding'}
                className="px-6 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {processingState === 'embedding' ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Processing...
                  </>
                ) : processingState === 'completed' ? (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Re-embed
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Start Embedding
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* No Classification State */}
      {!classification && !classificationLoading && (
        <div className="p-8 text-center">
          <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <p className="text-gray-500 mb-4">Unable to load column classification</p>
          <button
            onClick={loadClassification}
            className="px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
};

export default RAGConfigPanel;
