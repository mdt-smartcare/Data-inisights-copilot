import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatHeader } from '../components/chat';
import AgentsTab from '../components/config/AgentsTab';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import type { Agent } from '../types/agent';

const AgentsPage: React.FC = () => {
    const { isLoading } = useAuth();
    const navigate = useNavigate();

    const handleSelectAgent = (agent: Agent) => {
        navigate(`/agents/${agent.id}`);
    };

    if (isLoading) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading user profile...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-hidden">
                <AgentsTab onSelectAgent={handleSelectAgent} />
            </div>
        </div>
    );
};

export default AgentsPage;
