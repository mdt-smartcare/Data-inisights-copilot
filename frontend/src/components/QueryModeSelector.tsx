/**
 * QueryModeSelector - Select query execution mode
 * 
 * Supports:
 * - Auto: Let the system decide (intent routing)
 * - SQL: Direct SQL queries on structured data
 * - RAG: Semantic search on text columns
 * - Hybrid: Combine SQL and RAG results
 * - Agentic Hybrid: RAG → SQL → LLM synthesis workflow
 */
import { useState } from 'react';

export type QueryMode = 'auto' | 'sql' | 'rag' | 'hybrid' | 'agentic_hybrid';

interface QueryModeOption {
  id: QueryMode;
  name: string;
  description: string;
  icon: string;
  color: string;
  bgColor: string;
  available: boolean;
}

interface QueryModeSelectorProps {
  selectedMode: QueryMode;
  onModeChange: (mode: QueryMode) => void;
  sqlAvailable: boolean;
  ragAvailable: boolean;
  agenticHybridAvailable: boolean;
  compact?: boolean;
}

export default function QueryModeSelector({
  selectedMode,
  onModeChange,
  sqlAvailable,
  ragAvailable,
  agenticHybridAvailable,
  compact = false,
}: QueryModeSelectorProps) {
  const [showTooltip, setShowTooltip] = useState<QueryMode | null>(null);

  const modes: QueryModeOption[] = [
    {
      id: 'auto',
      name: 'Auto',
      description: 'Let AI decide the best approach based on your question',
      icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
      color: 'text-indigo-700',
      bgColor: 'bg-indigo-100',
      available: sqlAvailable || ragAvailable,
    },
    {
      id: 'sql',
      name: 'SQL',
      description: 'Direct database queries on structured columns (fast, precise)',
      icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
      color: 'text-blue-700',
      bgColor: 'bg-blue-100',
      available: sqlAvailable,
    },
    {
      id: 'rag',
      name: 'RAG',
      description: 'Semantic search on text columns using embeddings',
      icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
      color: 'text-purple-700',
      bgColor: 'bg-purple-100',
      available: ragAvailable,
    },
    {
      id: 'hybrid',
      name: 'Hybrid',
      description: 'Combine SQL precision with RAG semantic understanding',
      icon: 'M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z',
      color: 'text-emerald-700',
      bgColor: 'bg-emerald-100',
      available: sqlAvailable && ragAvailable,
    },
    {
      id: 'agentic_hybrid',
      name: 'Agentic',
      description: 'Multi-step workflow: RAG finds context → SQL aggregates → LLM synthesizes',
      icon: 'M13 10V3L4 14h7v7l9-11h-7z',
      color: 'text-amber-700',
      bgColor: 'bg-amber-100',
      available: agenticHybridAvailable,
    },
  ];

  if (compact) {
    return (
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
        {modes.map((mode) => (
          <button
            key={mode.id}
            onClick={() => mode.available && onModeChange(mode.id)}
            disabled={!mode.available}
            title={mode.available ? mode.description : `${mode.name} not available`}
            className={`
              relative px-3 py-1.5 text-xs font-medium rounded-md transition-all
              ${selectedMode === mode.id
                ? `${mode.bgColor} ${mode.color} shadow-sm`
                : mode.available
                  ? 'text-gray-600 hover:bg-gray-200'
                  : 'text-gray-400 cursor-not-allowed'
              }
            `}
          >
            {mode.name}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-gray-700">Query Mode</label>
      <div className="grid grid-cols-5 gap-3">
        {modes.map((mode) => (
          <div
            key={mode.id}
            className="relative"
            onMouseEnter={() => setShowTooltip(mode.id)}
            onMouseLeave={() => setShowTooltip(null)}
          >
            <button
              onClick={() => mode.available && onModeChange(mode.id)}
              disabled={!mode.available}
              className={`
                w-full p-3 rounded-lg border-2 transition-all text-center
                ${selectedMode === mode.id
                  ? `border-indigo-500 ${mode.bgColor} ring-2 ring-indigo-200`
                  : mode.available
                    ? 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    : 'border-gray-100 bg-gray-50 cursor-not-allowed opacity-50'
                }
              `}
            >
              <svg
                className={`w-6 h-6 mx-auto mb-2 ${selectedMode === mode.id ? mode.color : mode.available ? 'text-gray-500' : 'text-gray-300'}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={mode.icon} />
              </svg>
              <span className={`text-sm font-medium ${selectedMode === mode.id ? mode.color : mode.available ? 'text-gray-700' : 'text-gray-400'}`}>
                {mode.name}
              </span>
            </button>

            {/* Tooltip */}
            {showTooltip === mode.id && (
              <div className="absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg">
                <div className="font-medium mb-1">{mode.name}</div>
                <div className="text-gray-300">{mode.description}</div>
                {!mode.available && (
                  <div className="mt-1 text-amber-400">Not available - enable RAG first</div>
                )}
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 rotate-45 w-2 h-2 bg-gray-900" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
