import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface PromptEditorProps {
    value: string;
    onChange: (value: string) => void;
}

const PromptEditor: React.FC<PromptEditorProps> = ({ value, onChange }) => {
    const [viewMode, setViewMode] = useState<'split' | 'edit' | 'preview'>('split');

    return (
        <div className="flex flex-col h-full border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
            {/* Toolbar */}
            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex justify-between items-center">
                <div className="flex gap-1 bg-gray-200 p-0.5 rounded text-xs font-medium">
                    <button
                        onClick={() => setViewMode('edit')}
                        className={`px-3 py-1 rounded transition-colors ${viewMode === 'edit' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                    >
                        Edit
                    </button>
                    <button
                        onClick={() => setViewMode('split')}
                        className={`px-3 py-1 rounded transition-colors ${viewMode === 'split' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                    >
                        Split
                    </button>
                    <button
                        onClick={() => setViewMode('preview')}
                        className={`px-3 py-1 rounded transition-colors ${viewMode === 'preview' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                    >
                        Preview
                    </button>
                </div>

                <div className="text-xs text-gray-400">
                    {value.length} chars
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 flex overflow-hidden min-h-[500px]">
                {/* Editor Pane */}
                {(viewMode === 'edit' || viewMode === 'split') && (
                    <div className={`flex flex-col h-full ${viewMode === 'split' ? 'w-1/2 border-r border-gray-200' : 'w-full'}`}>
                        <textarea
                            className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none bg-gray-50 text-gray-800"
                            placeholder="Enter your prompt here..."
                            value={value}
                            onChange={(e) => onChange(e.target.value)}
                            spellCheck={false}
                        />
                    </div>
                )}

                {/* Preview Pane */}
                {(viewMode === 'preview' || viewMode === 'split') && (
                    <div className={`flex flex-col h-full bg-white overflow-y-auto ${viewMode === 'split' ? 'w-1/2' : 'w-full'}`}>
                        <div className="p-6 prose prose-sm max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {value || '*No content to preview*'}
                            </ReactMarkdown>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PromptEditor;
