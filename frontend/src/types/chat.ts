/**
 * Chat-related types and interfaces
 * 
 * This file contains all type definitions for chat functionality,
 * including messages, chart data, sources, and API request/response types.
 */

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
}

/**
 * Chart data interface
 * Defines the structure for data visualizations
 */
export interface ChartData {
  type: 'line' | 'bar' | 'pie' | 'area';  // Chart type
  title?: string;                          // Optional chart title
  data: any[];                             // Chart data points
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
  conversation_id?: string;   // Optional conversation thread ID
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
  timestamp: string;                   // Response generation timestamp
  trace_id?: string;                   // Optional trace ID for debugging
  processing_time?: number;            // Optional processing time in ms
}
