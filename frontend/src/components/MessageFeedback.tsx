import React, { useState } from 'react';
import { chatService } from '../services/chatService';
import type { FeedbackRequest } from '../types/feedback';

interface MessageFeedbackProps {
  traceId: string;
  query: string;
  selectedSuggestion?: string;
  onFeedbackSubmitted?: (success: boolean) => void;
}

/**
 * MessageFeedback Component
 * 
 * Displays thumbs up/down buttons for user feedback on chat responses.
 * Automatically sends feedback with trace_id to backend for Langfuse integration.
 */
export const MessageFeedback: React.FC<MessageFeedbackProps> = ({
  traceId,
  query,
  selectedSuggestion,
  onFeedbackSubmitted
}) => {
  const [feedbackState, setFeedbackState] = useState<'none' | 'positive' | 'negative'>('none');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState('');

  const submitFeedback = async (rating: number) => {
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      const feedbackRequest: FeedbackRequest = {
        trace_id: traceId,
        query: query,
        selected_suggestion: selectedSuggestion,
        rating: rating,
        comment: comment || undefined
      };

      const response = await chatService.submitFeedback(feedbackRequest);
      
      if (response.status === 'success') {
        setFeedbackState(rating > 0 ? 'positive' : 'negative');
        setShowComment(false);
        onFeedbackSubmitted?.(true);
      } else {
        onFeedbackSubmitted?.(false);
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      onFeedbackSubmitted?.(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleThumbsUp = () => {
    if (feedbackState === 'none') {
      submitFeedback(1);
    }
  };

  const handleThumbsDown = () => {
    if (feedbackState === 'none') {
      setShowComment(true);
    } else if (feedbackState === 'negative') {
      setShowComment(false);
      setComment('');
      setFeedbackState('none');
    }
  };

  const handleCommentSubmit = () => {
    submitFeedback(-1);
  };

  return (
    <div className="flex flex-col gap-2 mt-2">
      {/* Thumbs up/down buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleThumbsUp}
          disabled={isSubmitting || feedbackState !== 'none'}
          className={`p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
            feedbackState === 'positive' ? 'text-green-600 bg-green-50' : 'text-gray-500'
          }`}
          title="This response was helpful"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
        </button>

        <button
          onClick={handleThumbsDown}
          disabled={isSubmitting}
          className={`p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
            feedbackState === 'negative' ? 'text-red-600 bg-red-50' : 'text-gray-500'
          }`}
          title="This response was not helpful"
        >
          <svg className="w-4 h-4 rotate-180" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
        </button>

        {feedbackState !== 'none' && (
          <span className="text-xs text-gray-600">
            {feedbackState === 'positive' ? 'Thank you for your feedback!' : 'Feedback submitted'}
          </span>
        )}
      </div>

      {/* Comment input for negative feedback */}
      {showComment && (
        <div className="bg-gray-50 p-3 rounded-lg border">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Help us improve (optional):
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What could be better about this response?"
            className="w-full p-2 border border-gray-300 rounded text-sm resize-none"
            rows={3}
            maxLength={500}
          />
          <div className="flex justify-end gap-2 mt-2">
            <button
              onClick={() => {
                setShowComment(false);
                setComment('');
              }}
              className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-200 rounded"
            >
              Cancel
            </button>
            <button
              onClick={handleCommentSubmit}
              disabled={isSubmitting}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};