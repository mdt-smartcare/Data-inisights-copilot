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
import { APP_CONFIG } from '../config';

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string>();
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
      setConversationId(data.conversation_id);
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
      conversation_id: conversationId,
    });
  };

  const handleFeedback = (messageId: string, rating: 'positive' | 'negative') => {
    console.log('Feedback:', { messageId, rating });
    // TODO: Send feedback to backend API
    // feedbackService.submitFeedback({ message_id: messageId, rating });
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <ChatHeader title={APP_CONFIG.APP_NAME} />

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
        isDisabled={chatMutation.isPending}
        placeholder="Type your message..."
        maxLength={2000}
      />
    </div>
  );
}
