import React, { useState } from 'react';
import { MessageList, ChatInput } from '../../chat';
import { CommandLineIcon } from '@heroicons/react/24/outline';
import { chatService } from '../../../services/chatService';
import { useAuth } from '../../../contexts/AuthContext';
import type { Agent } from '../../../types/agent';
import type { Message } from '../../../types';
import type { ActiveConfig } from '../../../contexts/AgentContext';

interface SandboxTabProps {
    agent: Agent;
    activeConfig: ActiveConfig;
}

export const SandboxTab: React.FC<SandboxTabProps> = ({
    agent,
    activeConfig
}) => {
    const { user } = useAuth();
    const [messages, setMessages] = useState<Message[]>([]);
    const [isTyping, setIsTyping] = useState(false);

    const handleSend = async (content: string) => {
        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content,
            timestamp: new Date()
        };

        setMessages(prev => [...prev, userMsg]);
        setIsTyping(true);

        try {
            const response = await chatService.sendMessage({
                query: content,
                agent_id: agent.id,
                session_id: 'sandbox-' + agent.id
            });

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: response.answer,
                timestamp: new Date(response.timestamp),
                sources: response.sources,
                sqlQuery: response.sql_query,
                chartData: response.chart_data,
                traceId: response.trace_id,
                processingTime: response.processing_time
            };
            setMessages(prev => [...prev, aiMsg]);
        } catch (err: any) {
            console.error("Sandbox chat error", err);
            const errorMsg: Message = {
                id: Date.now().toString(),
                role: 'assistant',
                content: `Error: ${err.message || 'Failed to get response from agent'}`,
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setIsTyping(false);
        }
    };

    const getExampleQuestions = (): string[] => {
        try {
            if (activeConfig.example_questions) {
                return JSON.parse(activeConfig.example_questions);
            }
        } catch {
            // Ignore parse errors
        }
        return [
            "What can you do?",
            "Show me the available data",
            "Summarize the recent records"
        ];
    };

    return (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-xl overflow-hidden flex flex-col h-[700px] animate-in zoom-in-95 duration-300">
            <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                <div>
                    <h3 className="font-bold text-gray-900 flex items-center gap-2">
                        <CommandLineIcon className="w-5 h-5 text-indigo-600" />
                        Agent Sandbox
                    </h3>
                    <p className="text-xs text-gray-500">Test the current configuration in real-time</p>
                </div>
                <button
                    onClick={() => setMessages([])}
                    className="text-xs font-semibold text-gray-500 hover:text-red-600 transition-colors"
                >
                    Clear Session
                </button>
            </div>
            <div className="flex-1 overflow-hidden flex flex-col relative bg-gray-50/30">
                <MessageList
                    messages={messages}
                    isLoading={isTyping}
                    username={user?.username}
                    emptyStateProps={{
                        title: `Testing ${agent.name}`,
                        subtitle: 'Type a message to see how the agent responds with its current settings.',
                        suggestions: getExampleQuestions()
                    }}
                />
            </div>
            <div className="p-4 bg-white border-t border-gray-100">
                <ChatInput
                    onSendMessage={handleSend}
                    isDisabled={isTyping}
                    placeholder="Test the agent..."
                />
            </div>
        </div>
    );
};

export default SandboxTab;
