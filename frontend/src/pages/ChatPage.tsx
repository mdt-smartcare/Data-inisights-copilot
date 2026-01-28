import { useState, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { chatService } from '../services/chatService';
import { getActiveConfigMetadata } from '../services/api';
import type { Message } from '../types';
import {
  ChatHeader,
  MessageList,
  ChatInput
} from '../components/chat';
import { useAuth } from '../contexts/AuthContext';
import { canExecuteQuery } from '../utils/permissions';
import { APP_CONFIG } from '../config';

export default function ChatPage() {
  const { user } = useAuth();
  const canChat = canExecuteQuery(user);

  const [messages, setMessages] = useState<Message[]>([]);
  // Session ID for conversation continuity - can be reset via Clear Chat
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [suggestions, setSuggestions] = useState<string[]>([
    "How many male patients are over the age of 50?",
    "Which patients have a family history of heart disease mentioned in their records?",
    "What is the average glucose level for patients who are described as 'smokers' in their clinical notes?"
  ]);

  useEffect(() => {
    const loadSuggestions = async () => {
      try {
        const config = await getActiveConfigMetadata();
        if (config && config.example_questions) {
          try {
            const parsed = JSON.parse(config.example_questions);
            if (Array.isArray(parsed) && parsed.length > 0) {
              setSuggestions(parsed);
            }
          } catch (e) {
            console.warn("Failed to parse example questions", e);
          }
        }
      } catch (err) {
        console.warn("Failed to load active config for suggestions", err);
      }
    };
    loadSuggestions();
  }, []);

  const chatMutation = useMutation({
    mutationFn: chatService.sendMessage,
    onSuccess: (data) => {
      const assistantMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: data.answer,
        timestamp: new Date(data.timestamp),
        sources: data.sources,
        sqlQuery: data.sql_query,
        suggestedQuestions: data.suggested_questions,
        chartData: data.chart_data,
        traceId: data.trace_id,
        processingTime: data.processing_time,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    },
    onError: (error) => {
      console.error('Chat error:', error);
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    },
  });

  const handleSendMessage = (content: string) => {
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    chatMutation.mutate({
      query: content,
      session_id: sessionId,
    });
  };

  const handleClearChat = () => {
    setMessages([]);
    setSessionId(crypto.randomUUID()); // Generate new session for fresh start
  };

  const handleFeedback = (messageId: string, rating: 'positive' | 'negative') => {
    console.log('Feedback:', { messageId, rating });
    // TODO: Send feedback to backend API
    // feedbackService.submitFeedback({ message_id: messageId, rating });
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

      {/* Clear Chat Button - shown when messages exist */}
      {messages.length > 0 && (
        <div className="flex justify-end px-4 py-2 bg-gray-50 border-b border-gray-200">
          <button
            onClick={handleClearChat}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
            title="Start a new conversation"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Clear Chat
          </button>
        </div>
      )}

      <MessageList
        messages={messages}
        isLoading={chatMutation.isPending}
        onSuggestedQuestionClick={handleSendMessage}
        onFeedback={handleFeedback}
        emptyStateProps={{
          title: 'Ask me anything about FHIR healthcare data!',
          subtitle: 'Start a conversation by typing a message below',
          suggestions: suggestions
        }}
      />

      <ChatInput
        onSendMessage={handleSendMessage}
        isDisabled={!canChat || chatMutation.isPending}
        placeholder={canChat ? "Type your message..." : "Read-only access"}
        maxLength={2000}
      />
    </div>
  );
}
