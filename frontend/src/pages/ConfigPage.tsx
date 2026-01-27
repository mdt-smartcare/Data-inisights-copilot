import React, { useState } from 'react';
import { generateSystemPrompt, publishSystemPrompt, handleApiError } from '../services/api';
import ConnectionManager from '../components/ConnectionManager';
import SchemaSelector from '../components/SchemaSelector';

const steps = [
    { id: 1, name: 'Connect Database' },
    { id: 2, name: 'Select Schema' },
    { id: 3, name: 'Data Dictionary' },
    { id: 4, name: 'Review & Publish' }
];

const ConfigPage: React.FC = () => {
    const [currentStep, setCurrentStep] = useState(1);
    const [connectionId, setConnectionId] = useState<number | null>(null);
    const [selectedTables, setSelectedTables] = useState<string[]>([]);
    const [dataDictionary, setDataDictionary] = useState('');
    const [draftPrompt, setDraftPrompt] = useState('');

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
        if (currentStep === 2 && selectedTables.length === 0) {
            setError("Please select at least one table.");
            return;
        }
        setError(null);
        if (currentStep < 4) setCurrentStep(currentStep + 1);
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
            const schemaContext = `Selected Tables: ${selectedTables.join(', ')}\n\n`;
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
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setPublishing(false);
        }
    };

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
                                onSelectionChange={setSelectedTables}
                            />
                        </div>
                    )}

                    {currentStep === 3 && (
                        <div className="h-full flex flex-col">
                            <h2 className="text-xl font-semibold mb-4">Add Data Dictionary (Optional)</h2>
                            <p className="text-gray-500 text-sm mb-4">
                                Paste any additional context, column descriptions, or business rules here. This helps the AI understand your schema better.
                            </p>
                            <textarea
                                className="flex-1 p-4 border rounded-md font-mono text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                placeholder="e.g. 'users.role' values can be 'admin', 'viewer', 'editor'..."
                                value={dataDictionary}
                                onChange={(e) => setDataDictionary(e.target.value)}
                            />
                        </div>
                    )}

                    {currentStep === 4 && (
                        <div className="h-full flex flex-col">
                            <h2 className="text-xl font-semibold mb-4">Review & Configuration</h2>
                            <div className="flex-1 flex flex-col">
                                <label className="text-sm font-medium text-gray-700 mb-2">Generated System Prompt</label>
                                <textarea
                                    className="flex-1 p-4 border border-gray-300 rounded-md font-mono text-sm resize-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                    value={draftPrompt}
                                    onChange={(e) => setDraftPrompt(e.target.value)}
                                />
                            </div>
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
