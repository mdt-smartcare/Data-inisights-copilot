import React, { useState, useEffect } from 'react';
import type { Agent } from '../../types/agent';
import { getAgents, createAgent, handleApiError } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../Toast';
import Alert from '../Alert';
import { PlusIcon, UserGroupIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';

interface AgentsTabProps {
    onSelectAgent: (agent: Agent) => void;
}

const AgentsTab: React.FC<AgentsTabProps> = ({ onSelectAgent }) => {
    const { user } = useAuth();
    const { success, error: showError } = useToast();
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Create Modal State
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newAgentData, setNewAgentData] = useState({ name: '', description: '' });
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        loadAgents();
    }, []);

    const loadAgents = async () => {
        setLoading(true);
        try {
            const data = await getAgents();
            setAgents(data);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    const handleCreateAgent = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreating(true);
        try {
            const newAgent = await createAgent(newAgentData);
            setAgents([...agents, newAgent]);
            success('Agent Created', `${newAgent.name} has been created.`);
            setShowCreateModal(false);
            setNewAgentData({ name: '', description: '' });
        } catch (err) {
            showError('Failed to create agent', handleApiError(err));
        } finally {
            setCreating(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-gray-50">
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
                    <p className="text-gray-500 text-sm mt-1">Manage AI agents and their configurations.</p>
                </div>
                {user?.role === 'admin' && (
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm font-medium"
                    >
                        <PlusIcon className="w-5 h-5" />
                        New Agent
                    </button>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-6">
                {error && <Alert type="error" message={error} className="mb-6" />}

                {loading ? (
                    <div className="flex justify-center items-center h-64">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                ) : agents.length === 0 ? (
                    <div className="text-center py-20 bg-white rounded-lg border border-gray-200 border-dashed">
                        <UserGroupIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                        <h3 className="text-lg font-medium text-gray-900">No Agents Found</h3>
                        <p className="text-gray-500 mt-2">Get started by creating your first agent.</p>
                        {user?.role === 'admin' && (
                            <button
                                onClick={() => setShowCreateModal(true)}
                                className="mt-6 px-4 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 font-medium"
                            >
                                Create Agent
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {agents.map((agent) => (
                            <div
                                key={agent.id}
                                onClick={() => onSelectAgent(agent)}
                                className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group flex flex-col"
                            >
                                <div className="p-6 flex-1">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-blue-50 text-blue-600">
                                                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                                </svg>
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-900 text-lg">{agent.name}</h3>
                                            </div>
                                        </div>
                                    </div>
                                    <p className="text-gray-600 text-sm line-clamp-2 mb-4">
                                        {agent.description || "No description provided."}
                                    </p>
                                </div>
                                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 rounded-b-xl flex justify-end items-center">
                                    <div className="flex gap-2">
                                        <button className="flex items-center text-blue-600 text-sm font-medium hover:underline">
                                            Configure <Cog6ToothIcon className="w-4 h-4 ml-1" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Create Agent Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
                        <div className="p-6 border-b border-gray-200">
                            <h2 className="text-xl font-semibold text-gray-900">Create New Agent</h2>
                        </div>
                        <form onSubmit={handleCreateAgent} className="p-6">
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Agent Name</label>
                                    <input
                                        type="text"
                                        required
                                        value={newAgentData.name}
                                        onChange={(e) => setNewAgentData({ ...newAgentData, name: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        placeholder="e.g., Sales Analyst"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                                    <textarea
                                        value={newAgentData.description}
                                        onChange={(e) => setNewAgentData({ ...newAgentData, description: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        rows={3}
                                        placeholder="What does this agent do?"
                                    />
                                </div>
                            </div>
                            <div className="mt-6 flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateModal(false)}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={creating}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                                >
                                    {creating ? 'Creating...' : 'Create Agent'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AgentsTab;
