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
  sqlQuery?: string;                   // Optional SQL query executed for response
  suggestedQuestions?: string[];       // Optional follow-up questions
  chartData?: ChartData;               // Optional visualization data
  traceId?: string;                    // Optional trace ID for debugging
  processingTime?: number;             // Optional response generation time in ms
  queryMode?: QueryMode;               // Query mode used for this message
  agenticHybridResult?: AgenticHybridResult; // Optional agentic hybrid workflow result
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
  agent_id?: number;          // Optional target agent ID
  signal?: AbortSignal;       // Optional signal for request cancellation
}

/**
 * Chat response from backend API
 * Returned after processing user query
 */
export interface ChatResponse {
  answer: string;                      // Generated response text
  sources?: Source[];                  // Optional retrieved documents
  sql_query?: string;                  // Optional executed SQL query
  suggested_questions?: string[];      // Optional follow-up questions
  chart_data?: ChartData;              // Optional chart visualization
  conversation_id: string;             // Conversation thread ID
  session_id?: string;                 // Session ID for conversation tracking
  agent_id?: number;                   // Agent ID that generated this response
  timestamp: string;                   // Response generation timestamp
  trace_id?: string;                   // Optional trace ID for debugging
  processing_time?: number;            // Optional processing time in ms
  query_mode?: QueryMode;              // Query mode used for processing
  agentic_hybrid_result?: AgenticHybridResult; // Optional agentic hybrid workflow result
}
