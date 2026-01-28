import { useRef, useEffect } from 'react';
import type { Message } from '../../types';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';
import EmptyState from './EmptyState';
import ThinkingIndicator from './ThinkingIndicator';

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
  const lastAssistantMessageRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the start of the latest assistant message
  useEffect(() => {
    // If we have messages and the last one is from assistant, scroll to it
    if (messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
      lastAssistantMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      // Otherwise scroll to bottom (for user messages or loading state)
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <div className="max-w-4xl mx-auto space-y-2.5">
        {messages.length === 0 ? (
          <EmptyState {...emptyStateProps} onSuggestedQuestionClick={onSuggestedQuestionClick} />
        ) : (
          <>
            {messages.map((message, index) => {
              const isLastAssistantMessage =
                index === messages.length - 1 && message.role === 'assistant';

              return message.role === 'user' ? (
                <UserMessage key={message.id} message={message} />
              ) : (
                <div
                  key={message.id}
                  ref={isLastAssistantMessage ? lastAssistantMessageRef : null}
                >
                  <AssistantMessage
                    message={message}
                    onSuggestedQuestionClick={onSuggestedQuestionClick}
                    onFeedback={onFeedback}
                  />
                </div>
              );
            })}
            {isLoading && <ThinkingIndicator />}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
