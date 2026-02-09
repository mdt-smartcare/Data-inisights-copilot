import React, { useState, useEffect } from 'react';

interface AdvancedSettingsProps {
    settings: {
        embedding: {
            model: string;
            chunkSize: number;
            chunkOverlap: number;
        };
        retriever: {
            topKInitial: number;
            topKFinal: number;
            hybridWeights: [number, number];
        };
    };
    onChange: (settings: any) => void;
    readOnly?: boolean;
}

const AdvancedSettings: React.FC<AdvancedSettingsProps> = ({ settings, onChange, readOnly = false }) => {
    // Local state for form handling
    const [localSettings, setLocalSettings] = useState(settings);

    useEffect(() => {
        setLocalSettings(settings);
    }, [settings]);

    const handleChange = (section: 'embedding' | 'retriever', field: string, value: any) => {
        if (readOnly) return;

        const newSettings = {
            ...localSettings,
            [section]: {
                ...localSettings[section],
                [field]: value
            }
        };
        setLocalSettings(newSettings);
        onChange(newSettings);
    };

    return (
        <div className="h-full overflow-y-auto p-1">
            <h2 className="text-xl font-semibold mb-4 text-gray-900">Advanced Configuration</h2>
            <p className="text-sm text-gray-500 mb-6">
                Fine-tune the RAG pipeline parameters. These settings control how data is processed, indexed, and retrieved.
            </p>

            <div className="space-y-6">
                {/* Embedding Configuration */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-indigo-100 rounded-full">
                            <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Embedding Strategy</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Model Name</label>
                            <input
                                type="text"
                                value={localSettings.embedding.model}
                                onChange={(e) => handleChange('embedding', 'model', e.target.value)}
                                disabled={readOnly}
                                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                            />
                            <p className="mt-1 text-xs text-gray-500">HuggingFace model ID (e.g., BAAI/bge-m3)</p>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Chunk Size</label>
                                <input
                                    type="number"
                                    value={localSettings.embedding.chunkSize}
                                    onChange={(e) => handleChange('embedding', 'chunkSize', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Overlap</label>
                                <input
                                    type="number"
                                    value={localSettings.embedding.chunkOverlap}
                                    onChange={(e) => handleChange('embedding', 'chunkOverlap', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Retrieval Configuration */}
                <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-emerald-100 rounded-full">
                            <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900">Retrieval Parameters</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Initial)</label>
                                <input
                                    type="number"
                                    value={localSettings.retriever.topKInitial}
                                    onChange={(e) => handleChange('retriever', 'topKInitial', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                                <p className="mt-1 text-xs text-gray-500">Candidates before reranking</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Top K (Final)</label>
                                <input
                                    type="number"
                                    value={localSettings.retriever.topKFinal}
                                    onChange={(e) => handleChange('retriever', 'topKFinal', parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                />
                                <p className="mt-1 text-xs text-gray-500">Results sent to LLM</p>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Hybrid Search Weights (Dense / Sparse)</label>
                            <div className="flex items-center gap-4">
                                <div className="flex-1">
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.05"
                                        value={localSettings.retriever.hybridWeights[0]}
                                        onChange={(e) => {
                                            const val = parseFloat(e.target.value);
                                            handleChange('retriever', 'hybridWeights', [val, parseFloat((1 - val).toFixed(2))]);
                                        }}
                                        disabled={readOnly}
                                        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                                    />
                                </div>
                            </div>
                            <div className="flex justify-between text-xs text-gray-500 mt-2">
                                <span>Vector: {localSettings.retriever.hybridWeights[0]}</span>
                                <span>Keyword: {localSettings.retriever.hybridWeights[1]}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AdvancedSettings;
