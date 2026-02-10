import React, { useState } from 'react';
import { generateSystemPrompt, publishSystemPrompt, getPromptHistory, getActiveConfigMetadata, handleApiError, startEmbeddingJob } from '../services/api';
import ConnectionManager from '../components/ConnectionManager';
import SchemaSelector from '../components/SchemaSelector';
import DictionaryUploader from '../components/DictionaryUploader';
import PromptEditor from '../components/PromptEditor';
import PromptHistory from '../components/PromptHistory';
import ConfigSummary from '../components/ConfigSummary';
import AdvancedSettings from '../components/AdvancedSettings';
import ObservabilityPanel from '../components/ObservabilityPanel';
import Alert from '../components/Alert';
import EmbeddingProgress from '../components/EmbeddingProgress';
import { ChatHeader } from '../components/chat';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../components/Toast';


const steps = [
    { id: 0, name: 'Dashboard' },
    { id: 1, name: 'Connect Database' },
    { id: 2, name: 'Select Schema' },
    { id: 3, name: 'Data Dictionary' },
    { id: 4, name: 'Advanced Settings' },
    { id: 5, name: 'Review & Publish' },
    { id: 6, name: 'Summary' }
];

import { canEditPrompt, canManageConnections, canPublishPrompt, getRoleDisplayName } from '../utils/permissions';

const ConfigPage: React.FC = () => {
    const { user, isLoading } = useAuth();
    const { success: showSuccess, error: showError } = useToast();
    const canEdit = canEditPrompt(user);
    const canPublish = canPublishPrompt(user);
    const isViewer = !canEdit;

    // MOVED HOOKS UP BEFORE CONDITIONAL RETURN
    const [currentStep, setCurrentStep] = useState(1);
    const [embeddingJobId, setEmbeddingJobId] = useState<string | null>(null);
    const [connectionId, setConnectionId] = useState<number | null>(null);
    const [selectedSchema, setSelectedSchema] = useState<Record<string, string[]>>({});
    const [dataDictionary, setDataDictionary] = useState('');
    const [reasoning, setReasoning] = useState<Record<string, string>>({});
    const [exampleQuestions, setExampleQuestions] = useState<string[]>([]);
    const [draftPrompt, setDraftPrompt] = useState('');
    const [history, setHistory] = useState<any[]>([]);
    const [showHistory, setShowHistory] = useState(false);
    const [showClearConfirm, setShowClearConfirm] = useState(false);
    const [replaceConfirm, setReplaceConfirm] = useState<{ show: boolean; version: any | null }>({ show: false, version: null });

    // Advanced Settings State
    const [advancedSettings, setAdvancedSettings] = useState({
        embedding: {
            model: 'BAAI/bge-m3',
            chunkSize: 800,
            chunkOverlap: 150
        },
        retriever: {
            topKInitial: 50,
            topKFinal: 10,
            hybridWeights: [0.75, 0.25] as [number, number]
        }
    });

    // Config Metadata for Dashboard
    const [activeConfig, setActiveConfig] = useState<any>(null);

    // Status
    const [generating, setGenerating] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Initial Load - moved into effect
    React.useEffect(() => {
        if (!isLoading) {
            loadDashboard();
        }
    }, [isLoading]);

    // Sync state to window for API use (temporary solution for simple passing)
    React.useEffect(() => {
        (window as any).__config_connectionId = connectionId;
        (window as any).__config_schema = selectedSchema;
        (window as any).__config_dictionary = dataDictionary;
    }, [connectionId, selectedSchema, dataDictionary]);

    // Load history when entering step 4
    React.useEffect(() => {
        if (currentStep === 4) {
            loadHistory();
        }
    }, [currentStep]);

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



    const loadDashboard = async () => {
        try {
            const config = await getActiveConfigMetadata();
            if (config) {
                setActiveConfig(config);
                // Pre-fill state
                if (config.connection_id) setConnectionId(config.connection_id);
                if (config.schema_selection) {
                    try {
                        setSelectedSchema(JSON.parse(config.schema_selection));
                    } catch (e) {
                        console.error("Failed to parse schema", e);
                    }
                }
                if (config.data_dictionary) setDataDictionary(config.data_dictionary);
                if (config.prompt_text) setDraftPrompt(config.prompt_text);
                if (config.reasoning) {
                    try {
                        setReasoning(JSON.parse(config.reasoning));
                    } catch (e) {
                        // ignore if not json string or already obj?
                        // config.reasoning might be string if coming from DB
                        setReasoning(typeof config.reasoning === 'string' ? JSON.parse(config.reasoning) : config.reasoning);
                    }
                }

                // If we have config, stay on Dashboard (Step 0)
                // If not, go to Step 1
                setCurrentStep(0);
            } else {
                setCurrentStep(1);
            }
            // Load history for total versions count
            loadHistory();
        } catch (e) {
            console.error("Failed to load active config", e);
            setCurrentStep(1);
        }
    };



    const handleNext = () => {
        if (currentStep === 1 && !connectionId) {
            setError("Please select a database connection.");
            return;
        }
        if (currentStep === 2 && Object.keys(selectedSchema).length === 0) {
            setError("Please select at least one table/column.");
            return;
        }
        setError(null);
        if (currentStep < 6) setCurrentStep(currentStep + 1);
    };

    const handleBack = () => {
        if (currentStep > 0) setCurrentStep(currentStep - 1);
    };

    const handleStartNew = () => {
        // Reset state for fresh config
        setConnectionId(null);
        setSelectedSchema({});
        setDataDictionary('');
        setDraftPrompt('');
        setCurrentStep(1);
    };

    const handleEditCurrent = () => {
        // State is already pre-filled from loadDashboard
        setCurrentStep(1);
    };

    const handleGenerate = async () => {
        setGenerating(true);
        setError(null);
        try {
            // Create a context string that includes selected schema
            // Create a context string that includes selected schema
            let schemaContext = "Selected Tables and Columns:\n";
            Object.entries(selectedSchema).forEach(([table, cols]) => {
                schemaContext += `- ${table}: [${cols.join(', ')}]\n`;
            });
            schemaContext += "\n";

            const fullContext = schemaContext + dataDictionary;

            const result = await generateSystemPrompt(fullContext);
            setDraftPrompt(result.draft_prompt);
            if (result.reasoning) setReasoning(result.reasoning);
            if (result.example_questions) setExampleQuestions(result.example_questions);
            setCurrentStep(4); // Move to Advanced Settings
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setGenerating(false);
        }
    };

    const handlePublish = async () => {
        if (!draftPrompt.trim()) return;
        setPublishing(true);
        setError(null);
        try {
            const result = await publishSystemPrompt(
                draftPrompt,
                reasoning,
                exampleQuestions,
                advancedSettings.embedding,
                advancedSettings.retriever
            );
            setSuccessMessage(`Prompt published successfully! Version: ${result.version}`);
            loadHistory(); // Refresh history
            loadDashboard(); // Refresh config metadata
            setCurrentStep(6); // Move to Summary
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setPublishing(false);
        }
    };

    const loadHistory = async () => {
        try {
            const data = await getPromptHistory();
            setHistory(data);
        } catch (err) {
            console.error("Failed to load history", err);
        }
    };

    const handleStartEmbedding = async () => {
        const configId = activeConfig?.id || activeConfig?.prompt_id;
        if (!configId) return;

        try {
            const result = await startEmbeddingJob({
                config_id: configId,
                batch_size: 50,
                max_concurrent: 5
            });
            setEmbeddingJobId(result.job_id);
            showSuccess('Embedding Job Started', result.message);
        } catch (err) {
            showError('Failed to start embedding job', handleApiError(err));
        }
    };



    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <ChatHeader title={APP_CONFIG.APP_NAME} />
            <div className="flex-1 overflow-auto">
                <div className="max-w-7xl mx-auto py-8 px-4 flex flex-col">
                    {/* Header & Steps - Hide steps on Dashboard */}
                    {currentStep > 0 && (
                        <div className="mb-8">
                            <div className="flex justify-between items-center mb-6">
                                <h1 className="text-2xl font-bold text-gray-900">
                                    Configure AI Agent
                                    <span className="ml-2 text-xs font-normal text-gray-500 bg-gray-100 px-2 py-1 rounded">Role: {getRoleDisplayName(user?.role)}</span>
                                </h1>
                                <span className="text-sm text-gray-500">Step {currentStep} of 5</span>
                            </div>

                            {/* Progress Bar */}
                            <div className="w-full bg-gray-200 rounded-full h-2 mb-6">
                                <div
                                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                    style={{ width: `${(currentStep / 5) * 100}%` }}
                                ></div>
                            </div>

                            {/* Step Indicators */}
                            <div className="flex justify-between relative">
                                {steps.filter(s => s.id > 0).map((step) => (
                                    <div key={step.id} className="flex flex-col items-center z-10">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors duration-200 
                                    ${currentStep >= step.id ? 'bg-blue-600 text-white' : 'bg-white border-2 border-gray-300 text-gray-400'}`}>
                                            {step.id}
                                        </div>
                                        <span className={`text-xs mt-2 font-medium ${currentStep >= step.id ? 'text-blue-600' : 'text-gray-400'}`}>
                                            {step.name}
                                        </span>
                                    </div>
                                ))}
                                {/* Connecting Line */}
                                <div className="absolute top-4 left-0 w-full h-0.5 bg-gray-200 -z-0"></div>
                            </div>
                        </div>
                    )}

                    {/* Content Area */}
                    <div className={`flex-1 min-h-0 bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden ${currentStep === 0 ? 'bg-gray-50 border-none shadow-none' : ''}`}>
                        {currentStep === 0 ? (
                            // DASHBOARD VIEW
                            <div className="h-full flex flex-col overflow-y-auto p-6">
                                <header className="flex justify-between items-center mb-8 px-1">
                                    <div>
                                        <h1 className="text-3xl font-bold text-gray-900">AI Agent Dashboard</h1>
                                        <p className="text-gray-500 mt-1">Manage your Data Intelligence Agent configuration</p>
                                        {isViewer && (
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 mt-2">
                                                Read-Only Mode
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex gap-3">
                                        {canEdit && (
                                            <button
                                                onClick={handleStartNew}
                                                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium shadow-sm"
                                            >
                                                New Configuration
                                            </button>
                                        )}
                                        <button
                                            onClick={handleEditCurrent}
                                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm"
                                        >
                                            {canEdit ? 'Edit Active Config' : 'View Configuration'}
                                        </button>
                                    </div>
                                </header>

                                {activeConfig ? (
                                    <div className="flex-1">
                                        <ConfigSummary
                                            connectionId={activeConfig.connection_id}
                                            schema={activeConfig.schema_selection ? JSON.parse(activeConfig.schema_selection) : {}}
                                            dataDictionary={activeConfig.data_dictionary || ''}
                                            activePromptVersion={activeConfig.version}
                                            totalPromptVersions={history.length}
                                            lastUpdatedBy={activeConfig.created_by_username}
                                        />

                                        {/* Embedding Section */}
                                        <div className="mt-8">
                                            <h2 className="text-xl font-semibold mb-4 text-gray-900">Embedding Status</h2>
                                            {embeddingJobId ? (
                                                <EmbeddingProgress
                                                    jobId={embeddingJobId}
                                                    onComplete={() => {
                                                        showSuccess('Embeddings Generated', 'Knowledge base updated successfully');
                                                        // Optional: clear job ID after delay or kept for display
                                                    }}
                                                    onError={(err) => showError('Embedding Failed', err)}
                                                    onCancel={() => {
                                                        showError('Job Cancelled', 'Embedding generation cancelled');
                                                        setEmbeddingJobId(null);
                                                    }}
                                                />
                                            ) : (
                                                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm flex items-center justify-between">
                                                    <div>
                                                        <h3 className="font-medium text-gray-900">Generate Embeddings</h3>
                                                        <p className="text-sm text-gray-500 mt-1">
                                                            Update the vector knowledge base with the current schema and dictionary.
                                                        </p>
                                                    </div>
                                                    <button
                                                        onClick={handleStartEmbedding}
                                                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium transition-colors"
                                                    >
                                                        Start Generation
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        {/* Observability Section */}
                                        <div className="mt-8 mb-8">
                                            <ObservabilityPanel />
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex-1 flex flex-col items-center justify-center text-gray-400 border-2 border-dashed border-gray-300 rounded-xl">
                                        <p className="text-lg font-medium mb-2">No active configuration found</p>
                                        <p className="text-sm">Get started by creating a new configuration</p>
                                        <button
                                            onClick={handleStartNew}
                                            className="mt-6 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                                        >
                                            Start Setup Wizard
                                        </button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="p-6 h-full flex flex-col">
                                {successMessage && (
                                    <Alert
                                        type="success"
                                        message={successMessage}
                                        onDismiss={() => setSuccessMessage(null)}
                                    />
                                )}

                                {error && (
                                    <Alert
                                        type="error"
                                        message={error}
                                        onDismiss={() => setError(null)}
                                    />
                                )}
                                {currentStep === 1 && (
                                    <div className="max-w-2xl mx-auto">
                                        <h2 className="text-xl font-semibold mb-4">Select Database Connection</h2>
                                        <p className="text-gray-500 text-sm mb-6">
                                            Choose the database you want to generate insights from. You can add multiple connections (e.g., Staging, Production).
                                        </p>
                                        <ConnectionManager
                                            onSelect={setConnectionId}
                                            selectedId={connectionId}
                                            readOnly={!canManageConnections(user)}
                                        />
                                    </div>
                                )}

                                {currentStep === 2 && connectionId && (
                                    <div className="max-w-4xl mx-auto">
                                        <h2 className="text-xl font-semibold mb-4">Select Tables</h2>
                                        <p className="text-gray-500 text-sm mb-6">
                                            Select which tables contain relevant data for analysis. The AI will only be aware of the tables you select.
                                        </p>
                                        <SchemaSelector
                                            connectionId={connectionId}
                                            onSelectionChange={setSelectedSchema}
                                            readOnly={!canEdit}
                                            reasoning={reasoning}
                                        />
                                    </div>
                                )}

                                {currentStep === 3 && (
                                    <div className="h-full flex flex-col">
                                        <h2 className="text-xl font-semibold mb-2">Add Data Dictionary</h2>
                                        <p className="text-gray-500 text-sm mb-4">
                                            Provide context to help the AI understand your data. Upload a file or paste definitions below.
                                        </p>

                                        <div className="flex-1 flex flex-col min-h-0 border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
                                            {/* Toolbar */}
                                            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex justify-between items-center">
                                                <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                                    Context Editor
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    <DictionaryUploader
                                                        onUpload={(content) => setDataDictionary(prev => prev ? prev + "\n\n" + content : content)}
                                                        disabled={!canEdit}
                                                    />
                                                    {dataDictionary && canEdit && (
                                                        <button
                                                            type="button"
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                e.stopPropagation();
                                                                setShowClearConfirm(true);
                                                            }}
                                                            className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1 rounded hover:bg-red-50"
                                                        >
                                                            Clear
                                                        </button>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Editor Area */}
                                            <textarea
                                                className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none disabled:bg-gray-50 disabled:text-gray-500"
                                                placeholder="# Users Table\n- role: 'admin' | 'user'\n- status: 1=active, 0=inactive..."
                                                value={dataDictionary}
                                                onChange={(e) => setDataDictionary(e.target.value)}
                                                spellCheck={false}
                                                disabled={!canEdit}
                                            />
                                        </div>
                                    </div>
                                )}



                                {currentStep === 4 && (
                                    <div className="h-full flex flex-col">
                                        <AdvancedSettings
                                            settings={advancedSettings}
                                            onChange={setAdvancedSettings}
                                            readOnly={!canEdit}
                                        />
                                    </div>
                                )}

                                {currentStep === 5 && (
                                    <div className="h-full flex flex-col">
                                        <h2 className="text-xl font-semibold mb-4 flex justify-between items-center">
                                            <span>Review & Configuration</span>
                                            <button
                                                onClick={() => setShowHistory(!showHistory)}
                                                className={`text-sm px-3 py-1 rounded border ${showHistory ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'}`}
                                            >
                                                {showHistory ? 'Hide History' : 'Show History'}
                                            </button>
                                        </h2>
                                        <div className="flex-1 flex gap-4 min-h-0">
                                            <div className="flex-1 min-h-0">
                                                <PromptEditor
                                                    value={draftPrompt}
                                                    onChange={setDraftPrompt}
                                                    readOnly={!canEdit}
                                                />
                                            </div>

                                            {showHistory && (
                                                <div className="w-64 min-w-[250px] h-full">
                                                    <PromptHistory
                                                        history={history}
                                                        onSelect={(item) => {
                                                            if (!draftPrompt.trim()) {
                                                                setDraftPrompt(item.prompt_text);
                                                            } else {
                                                                setReplaceConfirm({ show: true, version: item });
                                                            }
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </div>

                                        {/* Example Questions Preview */}
                                        {exampleQuestions.length > 0 && (
                                            <div className="mt-4 bg-gradient-to-r from-blue-50 to-indigo-50 p-5 rounded-lg border border-blue-100">
                                                <h3 className="text-sm font-bold text-blue-900 mb-3 flex items-center">
                                                    <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                    Example Questions (Preview)
                                                </h3>
                                                <div className="flex gap-2 flex-wrap">
                                                    {exampleQuestions.map((q, idx) => (
                                                        <span key={idx} className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium bg-white text-blue-700 shadow-sm border border-blue-100">
                                                            {q}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {currentStep === 6 && (
                                    <div className="h-full flex flex-col overflow-y-auto p-6">
                                        <h2 className="text-xl font-semibold mb-4">Configuration Summary</h2>
                                        <div className="bg-blue-50 p-4 rounded-md mb-6 border border-blue-100 flex justify-between items-center">
                                            <div>
                                                <h3 className="font-bold text-blue-900">Setup Complete!</h3>
                                                <p className="text-sm text-blue-700">Your agent is now configured with this prompt version.</p>
                                            </div>
                                            <button
                                                onClick={() => setCurrentStep(0)}
                                                className="px-4 py-2 bg-white text-blue-600 border border-blue-200 rounded font-medium shadow-sm hover:bg-gray-50"
                                            >
                                                Go to Dashboard
                                            </button>
                                        </div>

                                        <ConfigSummary
                                            connectionId={connectionId}
                                            schema={selectedSchema}
                                            dataDictionary={dataDictionary}
                                            activePromptVersion={history.find(p => p.is_active)?.version || null}
                                            totalPromptVersions={history.length}
                                            lastUpdatedBy={history.find(p => p.is_active)?.created_by_username}
                                        />

                                        {/* Embedding Section */}
                                        <div className="mt-8">
                                            <h2 className="text-xl font-semibold mb-4 text-gray-900">Embedding Status</h2>
                                            {embeddingJobId ? (
                                                <EmbeddingProgress
                                                    jobId={embeddingJobId}
                                                    onComplete={React.useCallback(() => {
                                                        showSuccess('Embeddings Generated', 'Knowledge base updated successfully');
                                                    }, [showSuccess])}
                                                    onError={React.useCallback((err: string) => showError('Embedding Failed', err), [showError])}
                                                    onCancel={React.useCallback(() => {
                                                        showError('Job Cancelled', 'Embedding generation cancelled');
                                                        setEmbeddingJobId(null);
                                                    }, [showError])}
                                                />
                                            ) : (
                                                <div className="bg-white p-6 rounded-lg border border-blue-100 shadow-sm flex items-center justify-between">
                                                    <div>
                                                        <h3 className="font-medium text-gray-900">Generate Embeddings</h3>
                                                        <p className="text-sm text-gray-500 mt-1">
                                                            Required to make your new configuration searchable.
                                                        </p>
                                                    </div>
                                                    <button
                                                        onClick={handleStartEmbedding}
                                                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium transition-colors"
                                                    >
                                                        Start Generation
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Footer Navigation */}
                    {
                        currentStep > 0 && (
                            <div className="mt-8 flex justify-between">
                                <button
                                    onClick={handleBack}
                                    className={`px-6 py-2 rounded-md font-medium ${currentStep === 1 ? 'text-gray-400 cursor-not-allowed' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                                    disabled={currentStep === 1}
                                >
                                    Back
                                </button>

                                {currentStep === 3 ? (
                                    <button
                                        onClick={handleGenerate}
                                        disabled={generating || !canEdit}
                                        className={`px-6 py-2 rounded-md font-medium text-white transition-all duration-200 flex items-center gap-2
                                ${generating ? 'bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse' : !canEdit ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                        title={!canEdit ? "Read-only mode" : "Generate Prompt"}
                                    >
                                        {generating ? (
                                            <>
                                                <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                </svg>
                                                <span>Generating with AI...</span>
                                            </>
                                        ) : (
                                            <>
                                                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                </svg>
                                                <span>Generate Prompt</span>
                                            </>
                                        )}
                                    </button>
                                ) : currentStep === 5 ? (
                                    canPublish ? (
                                        <button
                                            onClick={handlePublish}
                                            disabled={publishing}
                                            className="px-6 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700 disabled:opacity-50 flex items-center"
                                        >
                                            {publishing ? 'Publishing...' : 'Publish to Production'}
                                        </button>
                                    ) : (
                                        <div className="text-gray-500 italic text-sm border border-gray-200 rounded px-4 py-2 bg-gray-50">
                                            Publish restricted: Requires Super Admin
                                        </div>
                                    )
                                ) : (
                                    <button
                                        onClick={handleNext}
                                        disabled={generating || publishing || (currentStep === 1 && !connectionId)}
                                        className={`px-6 py-2 rounded-md font-medium text-white transition-colors duration-200 flex items-center
                                ${generating || publishing || (currentStep === 1 && !connectionId) ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-md'}`}
                                    >
                                        {publishing ? 'Publishing...' : currentStep === 6 ? 'Done' : 'Next'}
                                    </button>
                                )}
                            </div>
                        )
                    }
                </div>
            </div>

            {/* Clear Confirmation Modal */}
            {
                showClearConfirm && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 mx-4">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                                    <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold text-gray-900">Clear Data Dictionary</h3>
                                    <p className="text-sm text-gray-500">This action cannot be undone</p>
                                </div>
                            </div>
                            <p className="text-gray-600 mb-6">
                                Are you sure you want to clear all the data dictionary content? You'll need to re-enter or upload it again.
                            </p>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setShowClearConfirm(false)}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setDataDictionary('');
                                        setShowClearConfirm(false);
                                    }}
                                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium"
                                >
                                    Clear Content
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Replace Version Confirmation Modal */}
            {
                replaceConfirm.show && replaceConfirm.version && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 mx-4">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold text-gray-900">Replace Current Draft</h3>
                                    <p className="text-sm text-gray-500">Load version {replaceConfirm.version.version}</p>
                                </div>
                            </div>
                            <p className="text-gray-600 mb-6">
                                This will replace your current draft with the content from <strong>v{replaceConfirm.version.version}</strong>.
                                Any unsaved changes will be lost.
                            </p>
                            <div className="flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setReplaceConfirm({ show: false, version: null })}
                                    className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setDraftPrompt(replaceConfirm.version.prompt_text);
                                        setReplaceConfirm({ show: false, version: null });
                                    }}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium"
                                >
                                    Replace Draft
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }
        </div >
    );
};

export default ConfigPage;
