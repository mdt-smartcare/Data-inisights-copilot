import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { chatService } from '../services/chatService';
import { getActiveConfigMetadata } from '../services/api';
import type { Message, QueryMode, AgenticHybridResult } from '../types';
import {
  ChatHeader,
  MessageList,
  ChatInput
} from '../components/chat';
import AgenticHybridResultsDisplay from '../components/AgenticHybridResultsDisplay';
import { useAuth } from '../contexts/AuthContext';
import { canExecuteQuery } from '../utils/permissions';
import { APP_CONFIG } from '../config';

export default function ChatPage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const canChat = canExecuteQuery(user);

  const [messages, setMessages] = useState<Message[]>([]);
  // Session ID for conversation continuity - can be reset via Clear Chat
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // AbortController for canceling in-flight requests
  const abortControllerRef = useRef<AbortController | null>(null);
  // Track which agent we sent the request to
  const requestAgentIdRef = useRef<number | undefined>(undefined);

  // Default suggestions shown when no agent is selected
  const DEFAULT_SUGGESTIONS = [
    "How many male patients are over the age of 50?",
    "Which patients have a family history of heart disease mentioned in their records?",
    "What is the average glucose level for patients who are described as 'smokers' in their clinical notes?"
  ];

  // Agent selection state
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<number | undefined>(undefined);
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  
  // RAG availability state
  const [ragAvailable, setRagAvailable] = useState(false);
  const [agenticHybridAvailable, setAgenticHybridAvailable] = useState(false);

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

        // Check for agent ID in URL query param
        const agentIdParam = searchParams.get('agent');
        if (agentIdParam) {
          const agentId = parseInt(agentIdParam, 10);
          // Verify agent exists in the list (user has access)
          if (agentList.some((a: any) => a.id === agentId)) {
            setSelectedAgentId(agentId);
            return;
          }
        }
        
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
  }, []);

  // Load agent-specific example questions when agent changes
  useEffect(() => {
    const loadAgentSuggestions = async () => {
      if (!selectedAgentId) {
        // No agent selected - show default suggestions
        setSuggestions(DEFAULT_SUGGESTIONS);
        return;
      }

      try {
        // Fetch agent-specific config including example questions
        const config = await getActiveConfigMetadata(selectedAgentId);
        
        if (config && config.example_questions) {
          try {
            const parsed = typeof config.example_questions === 'string' 
              ? JSON.parse(config.example_questions) 
              : config.example_questions;
            
            if (Array.isArray(parsed) && parsed.length > 0) {
              setSuggestions(parsed);
              console.log(`Loaded ${parsed.length} example questions for agent ${selectedAgentId}`);
              return;
            }
          } catch (e) {
            console.warn("Failed to parse example questions", e);
          }
        }
        
        // Fallback to defaults if no agent-specific questions
        setSuggestions(DEFAULT_SUGGESTIONS);
      } catch (err) {
        console.warn("Failed to load agent config for suggestions", err);
        setSuggestions(DEFAULT_SUGGESTIONS);
      }
    };
    
    loadAgentSuggestions();
  }, [selectedAgentId]);

  // Reset session and abort requests when agent changes (Approach 1 & 3)
  useEffect(() => {
    if (selectedAgentId !== undefined) {
      // Agent selected or changed
      
      // 1. Abort any in-flight request from previous agent (Approach 3)
      if (abortControllerRef.current) {
        console.log('Aborting previous request due to agent switch');
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      
      // 2. Reset session ID for new agent (Approach 1)
      console.log(`Agent ${selectedAgentId} selected - creating new session`);
      setSessionId(crypto.randomUUID());
      
      // 3. Optional: Clear messages for clean slate
      // Uncomment if you want messages to clear on agent switch
      // setMessages([]);
    }
  }, [selectedAgentId]);

  // Check RAG availability when agent changes
  useEffect(() => {
    const checkRagAvailability = async () => {
      if (!selectedAgentId) {
        setRagAvailable(false);
        setAgenticHybridAvailable(false);
        return;
      }

      try {
        // Check if the selected agent has RAG capabilities
        const selectedAgent = agents.find(a => a.id === selectedAgentId);
        if (selectedAgent) {
          // RAG is available if agent has embeddings configured or is a RAG-type agent
          const hasRag = selectedAgent.type === 'rag' || selectedAgent.has_embeddings || selectedAgent.rag_enabled;
          setRagAvailable(hasRag);
          // Agentic hybrid requires both SQL and RAG capabilities
          setAgenticHybridAvailable(hasRag && selectedAgent.type === 'sql');
        }
      } catch (err) {
        console.error('Failed to check RAG availability', err);
      }
    };
    
    checkRagAvailability();
  }, [selectedAgentId, agents]);

  const chatMutation = useMutation({
    mutationFn: (data: { query: string; session_id: string; query_mode?: QueryMode; signal: AbortSignal }) => {
      // Store which agent this request is for
      requestAgentIdRef.current = selectedAgentId;
      
      return chatService.sendMessage({ 
        ...data, 
        agent_id: selectedAgentId,
        signal: data.signal
      });
    },
    onSuccess: (data) => {
      // Validate: Only process response if it matches current agent
      if (data.agent_id !== undefined && data.agent_id !== selectedAgentId) {
        console.warn(
          `Discarding response from agent ${data.agent_id} - current agent is ${selectedAgentId}`
        );
        return;  // Ignore mismatched response
      }

      // Validate: Check if this response is for the request we sent
      if (requestAgentIdRef.current !== undefined && requestAgentIdRef.current !== selectedAgentId) {
        console.warn(
          `Discarding response for agent ${requestAgentIdRef.current} - current agent is ${selectedAgentId}`
        );
        return;  // Ignore stale response
      }

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
        queryMode: data.query_mode as QueryMode,
        agenticHybridResult: data.agentic_hybrid_result as AgenticHybridResult,
      };
      setMessages((prev) => [...prev, assistantMessage]);
      
      // Clear abort controller after successful response
      abortControllerRef.current = null;
    },
    onError: (error: any) => {
      // Don't show error if request was aborted
      if (error.name === 'CanceledError' || error.code === 'ERR_CANCELED') {
        console.log('Request cancelled - no error shown');
        return;
      }
      
      console.error('Chat error:', error);
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      
      // Clear abort controller on error
      abortControllerRef.current = null;
    },
  });

  const handleSendMessage = (content: string, queryMode: QueryMode = 'auto') => {
    // Create new AbortController for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
      queryMode,
    };

    setMessages((prev) => [...prev, userMessage]);
    chatMutation.mutate({
      query: content,
      session_id: sessionId,
      query_mode: queryMode,
      signal: abortController.signal
    });
  };

  const handleClearChat = () => {
    // Abort any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    
    setMessages([]);
    setSessionId(crypto.randomUUID()); // Generate new session for fresh start
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      console.log('User manually stopped generation');
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
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
        <div className="flex-1 overflow-auto p-6 pt-12 flex flex-col items-center">
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
          <div className="px-4 py-2 bg-white border-b border-gray-200 flex items-center justify-between shadow-sm z-10">
            <div className="flex items-center gap-4">
              {/* Active Agent Info */}
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${agents.find(a => a.id === selectedAgentId)?.type === 'sql' ? 'bg-indigo-50 text-indigo-600' : 'bg-orange-50 text-orange-600'}`}>
                  {agents.find(a => a.id === selectedAgentId)?.type === 'sql' ? (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  )}
                </div>
                <div>
                  <span className="text-xs text-gray-500 block uppercase tracking-wider font-semibold">Current Assistant</span>
                  <span className="text-sm font-bold text-gray-900">{agents.find(a => a.id === selectedAgentId)?.name}</span>
                </div>
              </div>
            </div>

            {agents.length > 1 && (
              <button
                onClick={() => {
                  setSelectedAgentId(undefined);
                  setMessages([]); // Optional: clear messages when switching? Or keep them? User didn't specify, but switching context usually implies fresh start or at least leaving the view.
                  // Keeping messages might be confusing if they belong to another agent.
                  // For now, let's NOT clear messages automatically unless user explicitly clears, but navigating back usually implies "I'm done with this agent".
                  // Actually, if I go back and select the SAME agent, I might expect history.
                  // Does `selectedAgentId(undefined)` clear history? No, `messages` state is in ChatPage.
                  // If I switch agents, the `chatMutation` payload changes `agent_id`.
                  // It is safer to clear messages on switch to avoid sending previous context to new agent?
                  // The prompt says "go back and select a new agent".
                  // Let's just go back for now.
                }}
                className="text-sm text-gray-600 hover:text-indigo-600 font-medium px-3 py-1.5 rounded-md hover:bg-gray-50 border border-transparent hover:border-gray-200 transition-all"
              >
                Change Assistant
              </button>
            )}
          </div>

          {messages.length > 0 && (
            <div className="absolute top-[110px] right-4 z-10"> {/* Floating or specific placement if not in header */}
              {/* Re-evaluating placement. Putting it back into normal flow might be better or keeping it where it was.
                   The previous code had it as a separate div block. Let's keep the logic simple:
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
            onSuggestedQuestionClick={(question) => handleSendMessage(question, 'auto')}
            onFeedback={handleFeedback}
            emptyStateProps={{
              title: 'Ask me anything about healthcare data!',
              subtitle: 'Start a conversation by typing a message below',
              suggestions: suggestions
            }}
            renderMessageExtra={(message) => {
              // Render AgenticHybridResultsDisplay for messages with agentic hybrid results
              if (message.agenticHybridResult) {
                return (
                  <AgenticHybridResultsDisplay
                    result={message.agenticHybridResult}
                    isLoading={false}
                  />
                );
              }
              return null;
            }}
          />

          <ChatInput
            onSendMessage={handleSendMessage}
            onCancel={handleStopGeneration}
            isDisabled={!canChat || chatMutation.isPending}
            isCancellable={chatMutation.isPending}
            placeholder={canChat ? "Type your message..." : "Read-only access"}
            maxLength={2000}
            sqlAvailable={true}
            ragAvailable={ragAvailable}
            agenticHybridAvailable={agenticHybridAvailable}
            showModeSelector={true}
          />
        </>
      )}
    </div>
  );
}
