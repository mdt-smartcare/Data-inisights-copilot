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
import { AgentSelector } from '../components/chat/AgentSelector';
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

  // Agent selection state
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<number | undefined>(undefined);
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);

  useEffect(() => {
    // Load agents on mount
    const loadAgents = async () => {
      try {
        setIsLoadingAgents(true);
        // We need to import getAgents from api.ts. 
        // Note: ensure getAgents is exported in api.ts
        const { getAgents } = await import('../services/api');
        const agentList = await getAgents();
        setAgents(agentList);

        // Auto-select ONLY if there is exactly 1 agent
        if (agentList.length === 1) {
          setSelectedAgentId(agentList[0].id);
        }
      } catch (err) {
        console.error("Failed to load agents", err);
      } finally {
        setIsLoadingAgents(false);
      }
    };
    loadAgents();

    const loadSuggestions = async () => {
      try {
        const config = await getActiveConfigMetadata();
        // ... existing suggestion loading code ...
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
    mutationFn: (data: any) => chatService.sendMessage({ ...data, agent_id: selectedAgentId }),
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

      {!selectedAgentId ? (
        // Agent Landing Page State
        <div className="flex-1 overflow-auto p-6 flex flex-col items-center justify-center">
          <div className="max-w-4xl w-full">
            <div className="text-center mb-10">
              <h1 className="text-3xl font-bold text-gray-900 mb-4">Welcome to {APP_CONFIG.APP_NAME}</h1>
              <p className="text-lg text-gray-600">Select an assistant to start your session.</p>
            </div>

            {isLoadingAgents ? (
              <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
              </div>
            ) : agents.length === 0 ? (
              <div className="text-center p-10 bg-white rounded-xl shadow-sm border border-gray-200">
                <p className="text-gray-500">No agents found. Please ask an admin to configure an agent.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {agents.map(agent => (
                  <button
                    key={agent.id}
                    onClick={() => setSelectedAgentId(agent.id)}
                    className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-indigo-300 hover:ring-1 hover:ring-indigo-300 transition-all text-left group"
                  >
                    <div className="flex items-start gap-4">
                      <div className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${agent.type === 'sql' ? 'bg-indigo-50 text-indigo-600' : 'bg-orange-50 text-orange-600'}`}>
                        {agent.type === 'sql' ? (
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                          </svg>
                        ) : (
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                          </svg>
                        )}
                      </div>
                      <div>
                        <h3 className="font-semibold text-gray-900 text-lg group-hover:text-indigo-600 transition-colors">{agent.name}</h3>
                        <p className="text-sm text-gray-500 mt-1 line-clamp-2">{agent.description || "No description available."}</p>
                        <span className="inline-block mt-3 text-xs font-medium px-2 py-0.5 rounded bg-gray-100 text-gray-600 uppercase tracking-wide">
                          {agent.type}
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        // Chat Interface State
        <>
          <div className="px-4 py-2 bg-white border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">Active Agent:</span>
              <AgentSelector
                agents={agents}
                selectedAgentId={selectedAgentId}
                onSelect={setSelectedAgentId}
                isLoading={isLoadingAgents}
              />
            </div>
            {/* Can add styling to Clear Chat button here if needed to align */}
          </div>

          {messages.length > 0 && (
            <div className="absolute top-[110px] right-4 z-10"> {/* Floating or specific placement if not in header */}
              {/* Re-evaluating placement. Putting it back into normal flow might be better or keeping it where it was.
                   The previous code had it as a separate div block. Let's keep the logic simple:
                   If we are in Chat Interface, we render the header bars.
               */}
            </div>
          )}

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
            username={user?.username}
            onSuggestedQuestionClick={handleSendMessage}
            onFeedback={handleFeedback}
            emptyStateProps={{
              title: 'Ask me anything about healthcare data!',
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
        </>
      )}
    </div>
  );
}
