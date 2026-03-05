/**
 * AgenticHybridResultsDisplay - Display results from Agentic Hybrid Query workflow
 * 
 * Shows the 3-stage workflow:
 * 1. RAG Stage: Semantic search finds relevant context
 * 2. SQL Stage: Generated SQL aggregates data
 * 3. Synthesis Stage: LLM combines everything into final answer
 */
import { useState } from 'react';
import type { AgenticHybridResult } from '../services/api';

interface AgenticHybridResultsDisplayProps {
  result: AgenticHybridResult;
  isLoading?: boolean;
}

interface StageInfo {
  id: number;
  name: string;
  icon: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

const stages: StageInfo[] = [
  {
    id: 1,
    name: 'RAG Search',
    icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  {
    id: 2,
    name: 'SQL Aggregation',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4',
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  {
    id: 3,
    name: 'LLM Synthesis',
    icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
  },
];

export default function AgenticHybridResultsDisplay({
  result,
  isLoading = false,
}: AgenticHybridResultsDisplayProps) {
  const [expandedStage, setExpandedStage] = useState<number | null>(null);
  const [showSqlQuery, setShowSqlQuery] = useState(false);

  const toggleStage = (stageId: number) => {
    setExpandedStage(expandedStage === stageId ? null : stageId);
  };

  const formatTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-amber-600" />
            <h3 className="font-semibold text-gray-900">Processing Agentic Hybrid Query...</h3>
          </div>
          
          {/* Loading stages */}
          <div className="space-y-4">
            {stages.map((stage, index) => (
              <div key={stage.id} className="flex items-center gap-4">
                <div className={`
                  w-10 h-10 rounded-full flex items-center justify-center
                  ${index === 0 ? 'bg-purple-100 animate-pulse' : 'bg-gray-100'}
                `}>
                  <svg className={`w-5 h-5 ${index === 0 ? 'text-purple-600' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={stage.icon} />
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="font-medium text-gray-700">{stage.name}</div>
                  <div className="text-sm text-gray-500">
                    {index === 0 ? 'Searching for relevant context...' : 'Waiting...'}
                  </div>
                </div>
                {index === 0 && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-600" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (result.error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <svg className="w-6 h-6 text-red-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div>
            <h3 className="font-medium text-red-800">Query Failed</h3>
            <p className="text-sm text-red-600 mt-1">{result.error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-b border-amber-100 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Agentic Hybrid Result</h3>
              <p className="text-sm text-gray-500">Multi-stage intelligent query workflow</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-sm font-medium text-gray-700">Total Time</div>
            <div className="text-lg font-bold text-amber-600">{formatTime(result.total_time_ms)}</div>
          </div>
        </div>
      </div>

      {/* Final Answer */}
      <div className="p-6 bg-gradient-to-r from-green-50 to-emerald-50 border-b border-green-100">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="flex-1">
            <h4 className="font-medium text-green-800 mb-2">Final Answer</h4>
            <p className="text-gray-800 leading-relaxed">{result.final_answer}</p>
          </div>
        </div>
      </div>

      {/* Workflow Stages */}
      <div className="p-6">
        <h4 className="font-medium text-gray-700 mb-4">Workflow Stages</h4>
        
        {/* Stage Timeline */}
        <div className="relative">
          {/* Connecting line */}
          <div className="absolute left-5 top-10 bottom-10 w-0.5 bg-gray-200" />

          <div className="space-y-4">
            {/* Stage 1: RAG */}
            <div className={`relative ${expandedStage === 1 ? '' : ''}`}>
              <button
                onClick={() => toggleStage(1)}
                className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                  expandedStage === 1
                    ? 'border-purple-300 bg-purple-50'
                    : 'border-gray-200 hover:border-purple-200 hover:bg-purple-25'
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center z-10 relative">
                    <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={stages[0].icon} />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Stage 1: RAG Search</span>
                      <span className="text-sm text-purple-600 font-medium">{formatTime(result.rag_time_ms)}</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-0.5">
                      Found {result.stage_1_rag.matches_found} relevant matches
                      {result.stage_1_rag.patient_ids && ` across ${result.stage_1_rag.patient_ids.length} records`}
                    </p>
                  </div>
                  <svg className={`w-5 h-5 text-gray-400 transition-transform ${expandedStage === 1 ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {expandedStage === 1 && (
                <div className="mt-2 ml-14 p-4 bg-purple-50 rounded-lg border border-purple-200">
                  <div className="space-y-3">
                    <div>
                      <span className="text-xs font-medium text-purple-700 uppercase tracking-wide">Search Query</span>
                      <p className="text-sm text-gray-700 mt-1">{result.stage_1_rag.query}</p>
                    </div>
                    {result.stage_1_rag.patient_ids && result.stage_1_rag.patient_ids.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-purple-700 uppercase tracking-wide">Matching IDs</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {result.stage_1_rag.patient_ids.slice(0, 10).map((id, i) => (
                            <span key={i} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">{id}</span>
                          ))}
                          {result.stage_1_rag.patient_ids.length > 10 && (
                            <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                              +{result.stage_1_rag.patient_ids.length - 10} more
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                    {result.stage_1_rag.sample_contexts && result.stage_1_rag.sample_contexts.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-purple-700 uppercase tracking-wide">Sample Contexts</span>
                        <div className="mt-1 space-y-2">
                          {result.stage_1_rag.sample_contexts.slice(0, 3).map((ctx, i) => (
                            <div key={i} className="text-xs text-gray-600 bg-white p-2 rounded border border-purple-100 line-clamp-2">
                              {ctx}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Stage 2: SQL */}
            <div className="relative">
              <button
                onClick={() => toggleStage(2)}
                className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                  expandedStage === 2
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-200 hover:bg-blue-25'
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center z-10 relative">
                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={stages[1].icon} />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Stage 2: SQL Aggregation</span>
                      <span className="text-sm text-blue-600 font-medium">{formatTime(result.sql_time_ms)}</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-0.5">
                      Returned {result.stage_2_sql.rows_returned} rows with {result.stage_2_sql.columns.length} columns
                    </p>
                  </div>
                  <svg className={`w-5 h-5 text-gray-400 transition-transform ${expandedStage === 2 ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {expandedStage === 2 && (
                <div className="mt-2 ml-14 p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <div className="space-y-3">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-blue-700 uppercase tracking-wide">Generated SQL</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowSqlQuery(!showSqlQuery);
                          }}
                          className="text-xs text-blue-600 hover:text-blue-800"
                        >
                          {showSqlQuery ? 'Hide' : 'Show'} Query
                        </button>
                      </div>
                      {showSqlQuery && (
                        <pre className="mt-2 p-3 bg-gray-900 text-green-400 rounded-lg text-xs overflow-x-auto">
                          {result.stage_2_sql.generated_sql}
                        </pre>
                      )}
                    </div>
                    <div>
                      <span className="text-xs font-medium text-blue-700 uppercase tracking-wide">Columns</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {result.stage_2_sql.columns.map((col, i) => (
                          <span key={i} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">{col}</span>
                        ))}
                      </div>
                    </div>
                    {result.stage_2_sql.sample_rows && result.stage_2_sql.sample_rows.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-blue-700 uppercase tracking-wide">Sample Results</span>
                        <div className="mt-2 overflow-x-auto">
                          <table className="min-w-full text-xs">
                            <thead>
                              <tr className="bg-blue-100">
                                {result.stage_2_sql.columns.map((col, i) => (
                                  <th key={i} className="px-3 py-2 text-left font-medium text-blue-800">{col}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="bg-white">
                              {result.stage_2_sql.sample_rows.slice(0, 5).map((row, i) => (
                                <tr key={i} className="border-t border-blue-100">
                                  {result.stage_2_sql.columns.map((col, j) => (
                                    <td key={j} className="px-3 py-2 text-gray-700">{String(row[col] ?? '')}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Stage 3: Synthesis */}
            <div className="relative">
              <button
                onClick={() => toggleStage(3)}
                className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                  expandedStage === 3
                    ? 'border-amber-300 bg-amber-50'
                    : 'border-gray-200 hover:border-amber-200 hover:bg-amber-25'
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center z-10 relative">
                    <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={stages[2].icon} />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Stage 3: LLM Synthesis</span>
                      <span className="text-sm text-amber-600 font-medium">{formatTime(result.synthesis_time_ms)}</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-0.5">
                      Model: {result.stage_3_synthesis.model_used}
                    </p>
                  </div>
                  <svg className={`w-5 h-5 text-gray-400 transition-transform ${expandedStage === 3 ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {expandedStage === 3 && (
                <div className="mt-2 ml-14 p-4 bg-amber-50 rounded-lg border border-amber-200">
                  <div className="space-y-3">
                    <div>
                      <span className="text-xs font-medium text-amber-700 uppercase tracking-wide">Model Used</span>
                      <p className="text-sm text-gray-700 mt-1">{result.stage_3_synthesis.model_used}</p>
                    </div>
                    <div>
                      <span className="text-xs font-medium text-amber-700 uppercase tracking-wide">Context Provided</span>
                      <div className="mt-1 p-3 bg-white rounded border border-amber-100 text-xs text-gray-600 max-h-32 overflow-y-auto">
                        {result.stage_3_synthesis.prompt_context}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Performance Summary */}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500">Performance Breakdown</span>
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-purple-500" />
                <span className="text-gray-600">RAG: {formatTime(result.rag_time_ms)}</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="text-gray-600">SQL: {formatTime(result.sql_time_ms)}</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                <span className="text-gray-600">LLM: {formatTime(result.synthesis_time_ms)}</span>
              </span>
            </div>
          </div>
          
          {/* Visual progress bar */}
          <div className="mt-2 h-2 bg-gray-100 rounded-full overflow-hidden flex">
            <div 
              className="bg-purple-500" 
              style={{ width: `${(result.rag_time_ms / result.total_time_ms) * 100}%` }} 
            />
            <div 
              className="bg-blue-500" 
              style={{ width: `${(result.sql_time_ms / result.total_time_ms) * 100}%` }} 
            />
            <div 
              className="bg-amber-500" 
              style={{ width: `${(result.synthesis_time_ms / result.total_time_ms) * 100}%` }} 
            />
          </div>
        </div>
      </div>
    </div>
  );
}
