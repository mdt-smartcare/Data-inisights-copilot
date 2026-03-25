/**
 * Feedback-related types and interfaces
 * 
 * This file contains type definitions for user feedback functionality,
 * including feedback submission requests.
 */

/**
 * Feedback request payload
 * Sent to backend when user provides feedback on a chat response
 */
export interface FeedbackRequest {
  trace_id: string;              // Langfuse trace ID from chat response
  query: string;                 // Original user query
  selected_suggestion?: string;  // Optional suggestion that was selected
  rating: number;                // User rating: 1 for thumbs up, -1 for thumbs down, 0 for neutral
  comment?: string;              // Optional text feedback from user
}

/**
 * Feedback response from backend
 */
export interface FeedbackResponse {
  status: string;
  message: string;
  feedback_id?: string;
}

/**
 * Legacy interface for backward compatibility
 * @deprecated Use FeedbackRequest instead
 */
export interface LegacyFeedbackRequest {
  conversation_id: string;
  message_id: string;
  rating: number;
  comment?: string;
}
