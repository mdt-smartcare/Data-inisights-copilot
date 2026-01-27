import React, { useState } from 'react';
import { generateSystemPrompt, publishSystemPrompt, getPromptHistory, handleApiError } from '../services/api';
import ConnectionManager from '../components/ConnectionManager';
import SchemaSelector from '../components/SchemaSelector';
import DictionaryUploader from '../components/DictionaryUploader';
import PromptEditor from '../components/PromptEditor';
import PromptHistory from '../components/PromptHistory';
import ConfigSummary from '../components/ConfigSummary';

const steps = [
    { id: 1, name: 'Connect Database' },
    { id: 2, name: 'Select Schema' },
    { id: 3, name: 'Data Dictionary' },
    { id: 4, name: 'Review & Publish' },
    { id: 5, name: 'Summary' }
];

const ConfigPage: React.FC = () => {
    const [currentStep, setCurrentStep] = useState(1);
    const [connectionId, setConnectionId] = useState<number | null>(null);
    // Changed to map of Table -> Columns
    const [selectedSchema, setSelectedSchema] = useState<Record<string, string[]>>({});
    const [dataDictionary, setDataDictionary] = useState('');
    const [draftPrompt, setDraftPrompt] = useState('');
    const [history, setHistory] = useState<any[]>([]);
    const [showHistory, setShowHistory] = useState(false);

    // Status
    const [generating, setGenerating] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

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
        if (currentStep < 5) setCurrentStep(currentStep + 1);
    };

    const handleBack = () => {
        setError(null);
        if (currentStep > 1) setCurrentStep(currentStep - 1);
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
            setCurrentStep(4); // Move to final step
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
            const result = await publishSystemPrompt(draftPrompt);
            setSuccessMessage(`Prompt published successfully! Version: ${result.version}`);
            loadHistory(); // Refresh history
            setCurrentStep(5); // Move to Summary
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

    // Load history when entering step 4
    React.useEffect(() => {
        if (currentStep === 4) {
            loadHistory();
        }
    }, [currentStep]);

    return (
        <div className="max-w-5xl mx-auto py-8 px-4 h-full flex flex-col">
            {/* Header & Steps */}
            <div className="mb-8">
                <h1 className="text-2xl font-bold text-gray-900 mb-6">Data Setup Wizard</h1>
                <div className="flex items-center justify-between relative">
                    <div className="absolute left-0 top-1/2 w-full h-0.5 bg-gray-200 -z-10"></div>
                    {steps.map((step) => (
                        <div key={step.id} className="flex flex-col items-center bg-white px-2">
                            <div
                                className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm transition-colors ${currentStep >= step.id
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-gray-200 text-gray-500'
                                    }`}
                            >
                                {step.id}
                            </div>
                            <span className={`text-xs mt-2 font-medium ${currentStep >= step.id ? 'text-blue-600' : 'text-gray-500'}`}>
                                {step.name}
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6 flex flex-col overflow-hidden">
                {error && (
                    <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-4 mb-4" role="alert">
                        <p>{error}</p>
                    </div>
                )}

                {successMessage && (
                    <div className="bg-green-50 border-l-4 border-green-500 text-green-700 p-4 mb-4" role="alert">
                        <p>{successMessage}</p>
                    </div>
                )}

                <div className="flex-1 overflow-y-auto">
                    {currentStep === 1 && (
                        <div className="max-w-2xl mx-auto">
                            <h2 className="text-xl font-semibold mb-4">Select Database Connection</h2>
                            <p className="text-gray-500 text-sm mb-6">
                                Choose the database you want to generate insights from. You can add multiple connections (e.g., Staging, Production).
                            </p>
                            <ConnectionManager
                                onSelect={setConnectionId}
                                selectedId={connectionId}
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
                                        />
                                        {dataDictionary && (
                                            <button
                                                onClick={() => {
                                                    if (window.confirm('Clear dictionary content?')) setDataDictionary('');
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
                                    className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none"
                                    placeholder="# Users Table\n- role: 'admin' | 'user'\n- status: 1=active, 0=inactive..."
                                    value={dataDictionary}
                                    onChange={(e) => setDataDictionary(e.target.value)}
                                    spellCheck={false}
                                />
                            </div>
                        </div>
                    )}

                    {currentStep === 4 && (
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
                                    />
                                </div>

                                {showHistory && (
                                    <div className="w-64 min-w-[250px] h-full">
                                        <PromptHistory
                                            history={history}
                                            onSelect={(item) => {
                                                const shouldLoad = !draftPrompt.trim() || window.confirm("Replace current content with this version?");
                                                if (shouldLoad) {
                                                    setDraftPrompt(item.prompt_text);
                                                }
                                            }}
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {currentStep === 5 && (
                        <div className="h-full flex flex-col">
                            <h2 className="text-xl font-semibold mb-4">Configuration Summary</h2>
                            <ConfigSummary
                                connectionId={connectionId}
                                schema={selectedSchema}
                                dataDictionary={dataDictionary}
                                activePromptVersion={history.find(p => p.is_active)?.version || null}
                                totalPromptVersions={history.length}
                            />
                        </div>
                    )}
                </div>
            </div>

            {/* Footer / Actions */}
            <div className="flex justify-between items-center py-4 border-t border-gray-100">
                <button
                    onClick={handleBack}
                    disabled={currentStep === 1}
                    className="px-6 py-2 border border-gray-300 rounded-md text-gray-700 font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Back
                </button>

                {currentStep < 3 && (
                    <button
                        onClick={handleNext}
                        disabled={!connectionId}
                        className="px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700 disabled:opacity-50"
                    >
                        Next Step
                    </button>
                )}

                {currentStep === 3 && (
                    <button
                        onClick={handleGenerate}
                        disabled={generating}
                        className="px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center"
                    >
                        {generating ? (
                            <>Generating...</>
                        ) : 'Generate Prompt'}
                    </button>
                )}

                {currentStep === 4 && (
                    <button
                        onClick={handlePublish}
                        disabled={publishing}
                        className="px-6 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700 disabled:opacity-50 flex items-center"
                    >
                        {publishing ? 'Publishing...' : 'Publish to Production'}
                    </button>
                )}
            </div>
        </div>
    );
};

export default ConfigPage;
