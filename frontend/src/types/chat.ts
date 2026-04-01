/**
 * Chat-related types and interfaces
 * 
 * This file contains all type definitions for chat functionality,
 * including messages, chart data, sources, and API request/response types.
 */

/**
 * Query execution mode
 */
export type QueryMode = 'auto' | 'sql' | 'rag' | 'hybrid' | 'agentic_hybrid';

/**
 * Reasoning step taken by the agent
 */
export interface ReasoningStep {
  tool: string;              // Name of the tool used
  thought?: string;          // Optional LLM thinking process/thought
  input: string;             // Tool input/query
  output?: string;           // Tool execution result
}

/**
 * Unified QA debug information
 */
export interface QADebugInfo {
  sql_query?: string;
  reasoning_steps: ReasoningStep[];
  trace_id: string;
  trace_url?: string;
  processing_time_ms: number;
  agent_config?: Record<string, any>;
}


/**
 * Agentic Hybrid Result structure
 * Contains the full workflow results from RAG → SQL → LLM synthesis
 * Matches the backend API response structure
 */
export interface AgenticHybridResult {
  status: string;
  question: string;

  // Workflow stages
  stage_1_rag: {
    query: string;
    matches_found: number;
    patient_ids?: string[];
    sample_contexts?: string[];
  };
  stage_2_sql: {
    generated_sql: string;
    rows_returned: number;
    columns: string[];
    sample_rows?: Record<string, any>[];
  };
  stage_3_synthesis: {
    prompt_context: string;
    model_used: string;
  };

  // Final answer
  final_answer: string;

  // Performance metrics
  total_time_ms: number;
  rag_time_ms: number;
  sql_time_ms: number;
  synthesis_time_ms: number;

  error?: string;
}

/**
 * Chat message interface
 * Represents a single message in the conversation
 */
export interface Message {
  id: string;                          // Unique message identifier
  role: 'user' | 'assistant';          // Message sender (user or AI assistant)
  content: string;                     // Message text content
  timestamp: Date;                     // When the message was created
  sources?: Source[];                  // Optional sources used to generate response
  suggestedQuestions?: string[];       // Optional follow-up questions
  chartData?: ChartData;               // Optional visualization data
  queryMode?: QueryMode;               // Query mode used for this message
  agenticHybridResult?: AgenticHybridResult; // Optional agentic hybrid workflow result
  traceId?: string;                    // Optional trace ID for feedback
  qaDebug?: QADebugInfo;               // Optional unified QA debug information
}

/**
 * Chart data interface
 * Defines the structure for data visualizations
 */
export interface ChartData {
  type: 'line' | 'bar' | 'pie' | 'area';  // Chart type
  title?: string;                          // Optional chart title
  data: any[] | { labels?: string[]; values?: number[] };  // Chart data points (array or labels/values format)
  xKey?: string;                           // Key for x-axis data
  yKey?: string;                           // Key for y-axis data
  colors?: string[];                       // Optional custom color scheme
}

/**
 * Source document interface
 * Represents a reference document used in RAG retrieval
 */
export interface Source {
  id?: string;                        // Optional document identifier
  content: string;                    // Document content/snippet
  metadata?: Record<string, any>;     // Optional metadata (e.g., document type, date)
  score?: number;                     // Optional relevance score (0-1)
}

/**
 * Chat request payload
 * Sent to backend for generating a response
 */
export interface ChatRequest {
  query: string;              // User's question or prompt
  session_id?: string;        // Optional session ID for conversation tracking
  agent_id?: string;          // Optional target agent ID (UUID)
  signal?: AbortSignal;       // Optional signal for request cancellation
  query_mode?: QueryMode;     // Optional query mode
  debug?: boolean;            // Optional debug flag for QA info
}

/**
 * Chat response from backend API
 * Returned after processing user query
 */
export interface ChatResponse {
  answer: string;
  sources?: Source[];
  suggested_questions?: string[];
  chart_data?: ChartData;
  conversation_id: string;
  session_id?: string;
  agent_id?: string;
  timestamp: string;
  query_mode?: QueryMode;
  agentic_hybrid_result?: AgenticHybridResult;
  trace_id: string;
  qa_debug?: QADebugInfo;
}
