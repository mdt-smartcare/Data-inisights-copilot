import React, { useState } from 'react';
import { Cog6ToothIcon, XMarkIcon, InformationCircleIcon, PencilIcon } from '@heroicons/react/24/outline';
import type { ChunkingConfig, ParallelizationConfig } from '../types/rag';

interface EmbeddingSettings {
    batch_size: number;
    max_concurrent: number;
    chunking: ChunkingConfig;
    parallelization: ParallelizationConfig;
    max_consecutive_failures: number;
    retry_attempts: number;
}

interface EmbeddingSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (settings: EmbeddingSettings, incremental: boolean) => void;
    defaultSettings?: Partial<EmbeddingSettings>;
}

const defaultConfig: EmbeddingSettings = {
    batch_size: 50,
    max_concurrent: 5,
    chunking: {
        parent_chunk_size: 800,
        parent_chunk_overlap: 150,
        child_chunk_size: 200,
        child_chunk_overlap: 50,
    },
    parallelization: {
        num_workers: undefined, // auto
        chunking_batch_size: undefined, // auto
        delta_check_batch_size: 50000,
    },
    max_consecutive_failures: 5,
    retry_attempts: 3,
};

const Tooltip: React.FC<{ text: string }> = ({ text }) => (
    <div className="group relative inline-block ml-1">
        <InformationCircleIcon className="w-4 h-4 text-gray-400 cursor-help" />
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 max-w-xs">
            {text}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
        </div>
    </div>
);

const EmbeddingSettingsModal: React.FC<EmbeddingSettingsModalProps> = ({
    isOpen,
    onClose,
    onConfirm,
    defaultSettings,
}) => {
    const [settings, setSettings] = useState<EmbeddingSettings>({
        ...defaultConfig,
        ...defaultSettings,
    });
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [editChunking, setEditChunking] = useState(false);
    const [incremental, setIncremental] = useState(true);

    if (!isOpen) return null;

    const handleConfirm = () => {
        onConfirm(settings, incremental);
        onClose();
    };

    const resetToDefaults = () => {
        setSettings({
            ...defaultConfig,
            // Keep chunking from defaultSettings since it comes from main page
            chunking: defaultSettings?.chunking || defaultConfig.chunking,
        });
        setEditChunking(false);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gradient-to-r from-indigo-50 to-purple-50">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center">
                            <Cog6ToothIcon className="w-5 h-5 text-indigo-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-gray-900">Start Embedding Job</h3>
                            <p className="text-xs text-gray-500">Configure job execution parameters</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white rounded-full transition-colors" title="Close modal" aria-label="Close">
                        <XMarkIcon className="w-5 h-5 text-gray-400" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    {/* Mode Selection */}
                    <div>
                        <label className="text-sm font-semibold text-gray-700 mb-3 block">Sync Mode</label>
                        <div className="flex gap-3">
                            <label className="flex-1 cursor-pointer">
                                <input
                                    type="radio"
                                    name="syncMode"
                                    checked={incremental}
                                    onChange={() => setIncremental(true)}
                                    className="sr-only"
                                />
                                <div className={`p-3 rounded-lg border-2 transition-all ${incremental ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'}`}>
                                    <div className="font-semibold text-gray-900 text-sm">Incremental</div>
                                    <div className="text-xs text-gray-500 mt-0.5">Process new/changed only</div>
                                </div>
                            </label>
                            <label className="flex-1 cursor-pointer">
                                <input
                                    type="radio"
                                    name="syncMode"
                                    checked={!incremental}
                                    onChange={() => setIncremental(false)}
                                    className="sr-only"
                                />
                                <div className={`p-3 rounded-lg border-2 transition-all ${!incremental ? 'border-red-500 bg-red-50' : 'border-gray-200 hover:border-gray-300'}`}>
                                    <div className="font-semibold text-gray-900 text-sm">Full Rebuild</div>
                                    <div className="text-xs text-gray-500 mt-0.5">Recreate entire DB</div>
                                </div>
                            </label>
                        </div>
                    </div>

                    {/* Basic Settings */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="text-sm font-medium text-gray-700 flex items-center">
                                Batch Size
                                <Tooltip text="Documents per embedding batch. Higher = faster but more memory." />
                            </label>
                            <input
                                type="number"
                                min={10}
                                max={500}
                                value={settings.batch_size}
                                onChange={(e) => setSettings({ ...settings, batch_size: parseInt(e.target.value) || 50 })}
                                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                            />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-gray-700 flex items-center">
                                Concurrency
                                <Tooltip text="Parallel embedding batches. Higher = faster but more API calls." />
                            </label>
                            <input
                                type="number"
                                min={1}
                                max={20}
                                value={settings.max_concurrent}
                                onChange={(e) => setSettings({ ...settings, max_concurrent: parseInt(e.target.value) || 5 })}
                                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                            />
                        </div>
                    </div>

                    {/* Chunking Section - Collapsible & Editable */}
                    <div className={`rounded-lg border transition-all ${editChunking ? 'border-blue-200 bg-blue-50/30' : 'border-gray-200 bg-gray-50'}`}>
                        <div className="p-3 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Chunking</span>
                                {!editChunking && (
                                    <span className="text-[10px] text-gray-400 bg-gray-200 px-1.5 py-0.5 rounded">from Advanced Settings</span>
                                )}
                            </div>
                            <button
                                onClick={() => setEditChunking(!editChunking)}
                                className={`text-xs font-medium flex items-center gap-1 px-2 py-1 rounded transition-colors ${
                                    editChunking 
                                        ? 'text-blue-700 bg-blue-100 hover:bg-blue-200' 
                                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'
                                }`}
                            >
                                <PencilIcon className="w-3 h-3" />
                                {editChunking ? 'Editing' : 'Edit'}
                            </button>
                        </div>
                        
                        {editChunking ? (
                            // Editable Mode
                            <div className="px-3 pb-3 grid grid-cols-2 gap-3 animate-in fade-in duration-200">
                                <div>
                                    <label className="text-xs font-medium text-gray-600">Parent Chunk Size</label>
                                    <input
                                        type="number"
                                        min={200}
                                        max={2000}
                                        value={settings.chunking.parent_chunk_size}
                                        onChange={(e) => setSettings({
                                            ...settings,
                                            chunking: { ...settings.chunking, parent_chunk_size: parseInt(e.target.value) || 800 }
                                        })}
                                        className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-gray-600">Parent Overlap</label>
                                    <input
                                        type="number"
                                        min={0}
                                        max={500}
                                        value={settings.chunking.parent_chunk_overlap}
                                        onChange={(e) => setSettings({
                                            ...settings,
                                            chunking: { ...settings.chunking, parent_chunk_overlap: parseInt(e.target.value) || 150 }
                                        })}
                                        className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-gray-600">Child Chunk Size</label>
                                    <input
                                        type="number"
                                        min={50}
                                        max={500}
                                        value={settings.chunking.child_chunk_size}
                                        onChange={(e) => setSettings({
                                            ...settings,
                                            chunking: { ...settings.chunking, child_chunk_size: parseInt(e.target.value) || 200 }
                                        })}
                                        className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-gray-600">Child Overlap</label>
                                    <input
                                        type="number"
                                        min={0}
                                        max={100}
                                        value={settings.chunking.child_chunk_overlap}
                                        onChange={(e) => setSettings({
                                            ...settings,
                                            chunking: { ...settings.chunking, child_chunk_overlap: parseInt(e.target.value) || 50 }
                                        })}
                                        className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    />
                                </div>
                                <div className="col-span-2">
                                    <button
                                        onClick={() => {
                                            setSettings({
                                                ...settings,
                                                chunking: defaultSettings?.chunking || defaultConfig.chunking
                                            });
                                        }}
                                        className="text-xs text-gray-500 hover:text-gray-700"
                                    >
                                        ↩ Reset to saved values
                                    </button>
                                </div>
                            </div>
                        ) : (
                            // Read-only Summary Mode
                            <div className="px-3 pb-3 grid grid-cols-4 gap-2 text-center">
                                <div>
                                    <div className="text-lg font-bold text-gray-900">{settings.chunking.parent_chunk_size}</div>
                                    <div className="text-[10px] text-gray-500">Parent Size</div>
                                </div>
                                <div>
                                    <div className="text-lg font-bold text-gray-900">{settings.chunking.parent_chunk_overlap}</div>
                                    <div className="text-[10px] text-gray-500">Parent Overlap</div>
                                </div>
                                <div>
                                    <div className="text-lg font-bold text-gray-900">{settings.chunking.child_chunk_size}</div>
                                    <div className="text-[10px] text-gray-500">Child Size</div>
                                </div>
                                <div>
                                    <div className="text-lg font-bold text-gray-900">{settings.chunking.child_chunk_overlap}</div>
                                    <div className="text-[10px] text-gray-500">Child Overlap</div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Advanced Settings Toggle */}
                    <button
                        onClick={() => setShowAdvanced(!showAdvanced)}
                        className="flex items-center gap-2 text-sm font-medium text-indigo-600 hover:text-indigo-700"
                    >
                        <svg className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        {showAdvanced ? 'Hide' : 'Show'} Advanced Options
                    </button>

                    {showAdvanced && (
                        <div className="space-y-4 animate-in slide-in-from-top-2 duration-200">
                            {/* Parallelization Settings */}
                            <div className="bg-purple-50/50 rounded-lg p-4 border border-purple-100">
                                <h4 className="text-xs font-semibold text-purple-900 mb-3 uppercase tracking-wider">Parallelization</h4>
                                <div className="grid grid-cols-3 gap-3">
                                    <div>
                                        <label className="text-xs font-medium text-gray-600">Workers</label>
                                        <input
                                            type="number"
                                            min={1}
                                            max={16}
                                            placeholder="Auto"
                                            value={settings.parallelization.num_workers || ''}
                                            onChange={(e) => setSettings({
                                                ...settings,
                                                parallelization: {
                                                    ...settings.parallelization,
                                                    num_workers: e.target.value ? parseInt(e.target.value) : undefined
                                                }
                                            })}
                                            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-gray-600">Chunk Batch</label>
                                        <input
                                            type="number"
                                            min={100}
                                            max={50000}
                                            placeholder="Auto"
                                            value={settings.parallelization.chunking_batch_size || ''}
                                            onChange={(e) => setSettings({
                                                ...settings,
                                                parallelization: {
                                                    ...settings.parallelization,
                                                    chunking_batch_size: e.target.value ? parseInt(e.target.value) : undefined
                                                }
                                            })}
                                            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-gray-600">Delta Batch</label>
                                        <input
                                            type="number"
                                            min={1000}
                                            max={100000}
                                            value={settings.parallelization.delta_check_batch_size}
                                            onChange={(e) => setSettings({
                                                ...settings,
                                                parallelization: {
                                                    ...settings.parallelization,
                                                    delta_check_batch_size: parseInt(e.target.value) || 50000
                                                }
                                            })}
                                            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Reliability Settings */}
                            <div className="bg-amber-50/50 rounded-lg p-4 border border-amber-100">
                                <h4 className="text-xs font-semibold text-amber-900 mb-3 uppercase tracking-wider">Reliability</h4>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="text-xs font-medium text-gray-600">Max Failures</label>
                                        <input
                                            type="number"
                                            min={1}
                                            max={20}
                                            value={settings.max_consecutive_failures}
                                            onChange={(e) => setSettings({
                                                ...settings,
                                                max_consecutive_failures: parseInt(e.target.value) || 5
                                            })}
                                            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
                                        />
                                        <span className="text-[10px] text-gray-400">Abort threshold</span>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-gray-600">Retry Attempts</label>
                                        <input
                                            type="number"
                                            min={1}
                                            max={10}
                                            value={settings.retry_attempts}
                                            onChange={(e) => setSettings({
                                                ...settings,
                                                retry_attempts: parseInt(e.target.value) || 3
                                            })}
                                            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
                                        />
                                        <span className="text-[10px] text-gray-400">Per failed batch</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-between items-center">
                    <button
                        onClick={resetToDefaults}
                        className="text-xs text-gray-500 hover:text-gray-700 font-medium"
                    >
                        Reset Defaults
                    </button>
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium text-sm"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleConfirm}
                            className={`px-5 py-2 rounded-lg font-semibold text-white transition-all text-sm ${
                                incremental
                                    ? 'bg-indigo-600 hover:bg-indigo-700'
                                    : 'bg-red-600 hover:bg-red-700'
                            }`}
                        >
                            {incremental ? 'Start Update' : 'Rebuild DB'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default EmbeddingSettingsModal;
