import { useRef, useEffect } from 'react';
import type { Message } from '../../types';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';
import EmptyState from './EmptyState';
import LoadingIndicator from './LoadingIndicator';

interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  onSuggestedQuestionClick?: (question: string) => void;
  onFeedback?: (messageId: string, rating: 'positive' | 'negative') => void;
  emptyStateProps?: {
    title?: string;
    subtitle?: string;
    suggestions?: string[];
  };
}

export default function MessageList({ 
  messages, 
  isLoading = false,
  onSuggestedQuestionClick,
  onFeedback,
  emptyStateProps 
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <div className="max-w-4xl mx-auto space-y-2.5">
        {messages.length === 0 ? (
          <EmptyState {...emptyStateProps} />
        ) : (
          <>
            {messages.map((message) => (
              message.role === 'user' ? (
                <UserMessage key={message.id} message={message} />
              ) : (
                <AssistantMessage 
                  key={message.id} 
                  message={message}
                  onSuggestedQuestionClick={onSuggestedQuestionClick}
                  onFeedback={onFeedback}
                />
              )
            ))}
            {isLoading && <LoadingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
