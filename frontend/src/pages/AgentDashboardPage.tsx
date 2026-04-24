import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ChatHeader } from '../components/chat';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';
import { ArrowLeftIcon, CommandLineIcon, UserGroupIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import { getAgent, getDraftConfig } from '../services/api';
import { canEditPrompt } from '../utils/permissions';
import type { Agent } from '../types/agent';
import type { ActiveConfig } from '../contexts/AgentContext';

// Import tab components
import { OverviewTab, KnowledgeTab, SandboxTab, UsersTab, MonitoringTab, ConfigHistoryTab } from '../components/config/tabs';

// Import hooks for data fetching
import { getActiveConfigMetadata, getConnections } from '../services/api';


const AgentDashboardPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const { user, isLoading: isAuthLoading } = useAuth();
    const { error: showError } = useToast();
    const canEdit = canEditPrompt(user);

    // Agent state
    const [agent, setAgent] = useState<Agent | null>(null);
    const [isLoadingAgent, setIsLoadingAgent] = useState(true);

    // Config state
    const [activeConfig, setActiveConfig] = useState<ActiveConfig | null>(null);
    const [connectionName, setConnectionName] = useState('');

    // Dashboard tab state - persist in URL query string
    const validTabs = ['overview', 'knowledge', 'sandbox', 'config-history', 'users', 'monitoring'];
    const tabFromUrl = searchParams.get('tab');
    const initialTab = tabFromUrl && validTabs.includes(tabFromUrl) ? tabFromUrl : 'overview';
    const [dashboardTab, setDashboardTabState] = useState(initialTab);

    // Update URL when tab changes
    const setDashboardTab = (tab: string) => {
        setDashboardTabState(tab);
        const newParams = new URLSearchParams(searchParams);
        if (tab === 'overview') {
            newParams.delete('tab'); // Don't clutter URL for default tab
        } else {
            newParams.set('tab', tab);
        }
        setSearchParams(newParams, { replace: true });
    };

    // Draft state - track if a draft config exists
    const [draftConfig, setDraftConfig] = useState<{ id: number } | null>(null);
    const [isCheckingDraft, setIsCheckingDraft] = useState(true); // Start true to check on load

    /**
     * Check for existing draft config on agent load.
     */
    const checkForDraft = useCallback(async (agentId: string) => {
        setIsCheckingDraft(true);
        try {
            const existingDraft = await getDraftConfig(agentId);
            setDraftConfig(existingDraft?.id ? { id: existingDraft.id } : null);
        } catch (err) {
            console.error('Failed to check for draft:', err);
            setDraftConfig(null);
        } finally {
            setIsCheckingDraft(false);
        }
    }, []); // getDraftConfig is an import

    /**
     * Handle Edit/Create Config button click.
     * Navigates to config page - with versionId if draft exists.
     */
    const handleEditConfig = () => {
        if (!agent?.id) return;

        if (draftConfig?.id) {
            // Navigate to edit existing draft
            navigate(`/agents/${agent.id}/config?versionId=${draftConfig.id}`);
        } else {
            // Navigate to create new config
            navigate(`/agents/${agent.id}/config`);
        }
    };

    /**
     * Get button text based on draft state and user permissions.
     */
    const getConfigButtonText = () => {
        if (isCheckingDraft) return 'Loading...';
        if (!canEdit) return 'View Configuration';
        return draftConfig ? 'Edit Draft Config' : 'Create New Config';
    };

    // Load agent
    useEffect(() => {
        let isMounted = true;

        const loadAgent = async () => {
            if (!id) return;
            setIsLoadingAgent(true);
            try {
                const foundAgent = await getAgent(id);
                if (!isMounted) return;
                setAgent(foundAgent);
            } catch (err) {
                if (!isMounted) return;
                console.error('Failed to load agent', err);
                showError('Agent Not Found', 'The requested agent could not be found.');
                navigate('/agents');
            } finally {
                if (isMounted) {
                    setIsLoadingAgent(false);
                }
            }
        };
        loadAgent();

        return () => {
            isMounted = false;
        };
    }, [id, navigate, showError]);

    // Function to reload agent data (called after update)
    const reloadAgent = async () => {
        if (!id) return;
        try {
            const foundAgent = await getAgent(id);
            setAgent(foundAgent);
        } catch (err) {
            console.error('Failed to reload agent', err);
        }
    };

    // Load config when agent is loaded
    useEffect(() => {
        let isMounted = true;

        const loadConfig = async () => {
            if (!agent) return;

            // Check for existing draft
            checkForDraft(agent.id);

            try {
                const config = await getActiveConfigMetadata(agent.id);
                if (!isMounted) return;

                if (config) {
                    setActiveConfig(config);

                    // Set connection name from data_source title (no separate lookup needed)
                    if (config.data_source?.title) {
                        setConnectionName(config.data_source.title);
                    } else if (config.connection_id) {
                        // Legacy fallback: fetch from connections API
                        try {
                            const conns = await getConnections();
                            if (!isMounted) return;
                            const c = conns.find((x: { id: number }) => x.id === config.connection_id);
                            if (c) setConnectionName(c.name);
                        } catch (e) {
                            console.error("Failed to fetch connection name", e);
                        }
                    }
                }
            } catch (e) {
                console.error("Failed to load config", e);
            }
        };
        loadConfig();

        return () => {
            isMounted = false;
        };
    }, [agent?.id, checkForDraft]);

    if (isAuthLoading || isLoadingAgent) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    <span className="ml-3 text-gray-500">Loading...</span>
                </div>
            </div>
        );
    }

    if (!agent) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <ChatHeader title={APP_CONFIG.APP_NAME} />
                <div className="flex-1 flex items-center justify-center">
                    <p className="text-gray-500">Agent not found</p>
                </div>
            </div>
        );
    }

    const tabs = [
        { id: 'overview', name: 'Overview', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg> },
        { id: 'knowledge', name: 'Vector DB', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg> },
        { id: 'sandbox', name: 'Sandbox', icon: (props: any) => <CommandLineIcon {...props} /> },
        { id: 'config-history', name: 'Config History', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
        { id: 'users', name: 'Users', icon: (props: any) => <UserGroupIcon {...props} /> },
        { id: 'monitoring', name: 'Monitoring', icon: (props: any) => <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg> }
    ];

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="h-full flex flex-col overflow-y-auto">
                    <header className="bg-white px-4 sm:px-8 pt-4 sm:pt-8 pb-4 border-b border-gray-200">
                        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-4 sm:mb-6">
                            <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                                <button
                                    onClick={() => navigate('/agents')}
                                    className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors flex-shrink-0"
                                    title="Back to Agents"
                                >
                                    <ArrowLeftIcon className="w-5 h-5 sm:w-6 sm:h-6" />
                                </button>
                                <div className="min-w-0">
                                    <h1 className="text-lg sm:text-2xl font-bold text-gray-900 truncate">{agent.name}</h1>
                                    <p className="text-xs sm:text-sm text-gray-500 truncate">Agent Configuration & Insights Dashboard</p>
                                </div>
                            </div>
                            <div className="flex gap-2 flex-shrink-0">
                                <button
                                    onClick={handleEditConfig}
                                    disabled={isCheckingDraft}
                                    className="px-3 sm:px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm transition-all focus:ring-2 focus:ring-blue-200 text-sm sm:text-base whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {getConfigButtonText()}
                                </button>
                            </div>
                        </div>

                        {/* Tabs - Scrollable on mobile */}
                        <div className="overflow-x-auto -mx-4 sm:-mx-8 px-4 sm:px-8 scrollbar-hide">
                            <div className="flex gap-4 sm:gap-8 border-t border-gray-100 pt-2 min-w-max">
                                {tabs.map(tab => (
                                    <button
                                        key={tab.id}
                                        onClick={() => setDashboardTab(tab.id)}
                                        className={`flex items-center gap-1 sm:gap-2 py-3 sm:py-4 px-1 border-b-2 font-medium text-xs sm:text-sm transition-all whitespace-nowrap
                                            ${dashboardTab === tab.id
                                                ? 'border-blue-600 text-blue-600'
                                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                            }`}
                                    >
                                        <tab.icon className={`w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 ${dashboardTab === tab.id ? 'text-blue-600' : 'text-gray-400'}`} />
                                        <span className="hidden sm:inline">{tab.name}</span>
                                        <span className="sm:hidden">{tab.name.split(' ')[0]}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </header>

                    <div className="p-4 sm:p-8 pb-16">
                        {activeConfig ? (
                            <div className="flex-1 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                {dashboardTab === 'overview' && (
                                    <OverviewTab
                                        activeConfig={activeConfig}
                                        connectionName={connectionName}
                                        agent={agent || undefined}
                                        canEdit={canEdit}
                                        onAgentUpdate={reloadAgent}
                                    />
                                )}

                                {dashboardTab === 'knowledge' && (
                                    <KnowledgeTab configId={activeConfig.id || activeConfig.prompt_id} />
                                )}

                                {dashboardTab === 'sandbox' && (
                                    <SandboxTab agent={agent} activeConfig={activeConfig} />
                                )}

                                {dashboardTab === 'users' && (
                                    <UsersTab agentId={agent.id} agentName={agent.name} />
                                )}

                                {dashboardTab === 'monitoring' && (
                                    <MonitoringTab />
                                )}

                                {dashboardTab === 'config-history' && (
                                    <ConfigHistoryTab
                                        agentId={agent.id}
                                        onRollback={reloadAgent}
                                    />
                                )}
                            </div>
                        ) : dashboardTab === 'users' ? (
                            <UsersTab agentId={agent.id} agentName={agent.name} />
                        ) : (
                            <div className="min-h-[400px] flex flex-col items-center justify-center text-center p-12 bg-white rounded-2xl border-2 border-dashed border-gray-200 shadow-sm">
                                <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mb-6">
                                    <Cog6ToothIcon className="w-10 h-10 text-blue-500" />
                                </div>
                                <h2 className="text-2xl font-bold text-gray-900 mb-3">No Active Configuration</h2>
                                <p className="text-gray-500 max-w-sm mx-auto mb-8">
                                    This agent has not been configured yet. Start the setup wizard to connect a data source and define behavior.
                                </p>
                                <button
                                    onClick={() => navigate(`/agents/${agent.id}/config`)}
                                    className="px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-bold shadow-lg shadow-blue-200 transition-all hover:-translate-y-1 active:translate-y-0"
                                >
                                    Start Setup Wizard
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AgentDashboardPage;
