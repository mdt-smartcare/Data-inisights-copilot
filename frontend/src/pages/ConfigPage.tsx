import React, { useState, useEffect } from 'react';
import { generateSystemPrompt, publishSystemPrompt, getActivePrompt, handleApiError } from '../services/api';

const ConfigPage: React.FC = () => {
    const [dataDictionary, setDataDictionary] = useState('');
    const [draftPrompt, setDraftPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Fetch active prompt on mount
    useEffect(() => {
        const fetchActive = async () => {
            try {
                const result = await getActivePrompt();
                if (result.prompt_text) {
                    setDraftPrompt(result.prompt_text); // Pre-fill with active prompt
                }
            } catch (err) {
                console.error("Failed to fetch active prompt", err);
                // Don't block the UI, just log it
            }
        };
        fetchActive();
    }, []);

    const handleGenerate = async () => {
        if (!dataDictionary.trim()) {
            setError('Please enter a Data Dictionary first.');
            return;
        }
        setLoading(true);
        setError(null);
        setSuccessMessage(null);
        try {
            const result = await generateSystemPrompt(dataDictionary);
            setDraftPrompt(result.draft_prompt);
            setSuccessMessage('Draft prompt generated successfully!');
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setLoading(false);
        }
    };

    const handlePublish = async () => {
        if (!draftPrompt.trim()) {
            setError('Cannot publish an empty prompt.');
            return;
        }
        setPublishing(true);
        setError(null);
        setSuccessMessage(null);
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
        <div className="p-6 h-full flex flex-col">
            <h1 className="text-2xl font-bold mb-6 text-gray-800">System Prompt Configuration</h1>

            {error && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4" role="alert">
                    <span className="block sm:inline">{error}</span>
                </div>
            )}

            {successMessage && (
                <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4" role="alert">
                    <span className="block sm:inline">{successMessage}</span>
                </div>
            )}

            <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-12rem)]">
                {/* Left Panel: Data Dictionary Input */}
                <div className="flex-1 flex flex-col bg-white rounded-lg shadow-md p-4">
                    <label className="text-sm font-semibold text-gray-700 mb-2">Data Dictionary / Schema Info</label>
                    <textarea
                        className="flex-1 p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm resize-none"
                        placeholder="Paste your database schema, column descriptions, or rules here..."
                        value={dataDictionary}
                        onChange={(e) => setDataDictionary(e.target.value)}
                    />
                    <button
                        onClick={handleGenerate}
                        disabled={loading}
                        className={`mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium flex items-center justify-center ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {loading ? (
                            <>
                                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Generating...
                            </>
                        ) : 'Generate Draft Prompt'}
                    </button>
                </div>

                {/* Right Panel: Prompt Editor */}
                <div className="flex-1 flex flex-col bg-white rounded-lg shadow-md p-4">
                    <label className="text-sm font-semibold text-gray-700 mb-2">System Prompt (Draft)</label>
                    <textarea
                        className="flex-1 p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-green-500 focus:border-transparent font-mono text-sm resize-none"
                        placeholder="Generated prompt will appear here. You can edit it manually."
                        value={draftPrompt}
                        onChange={(e) => setDraftPrompt(e.target.value)}
                    />
                    <button
                        onClick={handlePublish}
                        disabled={publishing}
                        className={`mt-4 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors font-medium flex items-center justify-center ${publishing ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {publishing ? (
                            <>
                                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Publishing...
                            </>
                        ) : 'Publish to Production'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfigPage;
