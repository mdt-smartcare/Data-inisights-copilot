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
  conversation_id: string;    // ID of the conversation thread
  message_id: string;         // ID of the specific message being rated
  rating: number;             // User rating (e.g., 1-5 stars or thumbs up/down)
  comment?: string;           // Optional text feedback from user
}
