import React, { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface PromptEditorProps {
    value: string;
    onChange: (value: string) => void;
}

const PromptEditor: React.FC<PromptEditorProps> = ({ value, onChange }) => {
    const [activeTab, setActiveTab] = useState<'write' | 'preview'>('write');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const insertFormat = (prefix: string, suffix: string = '') => {
        if (!textareaRef.current) return;

        const start = textareaRef.current.selectionStart;
        const end = textareaRef.current.selectionEnd;
        const text = textareaRef.current.value;
        const selectedText = text.substring(start, end);

        const newText = text.substring(0, start) + prefix + selectedText + suffix + text.substring(end);

        onChange(newText);

        // Restore focus and selection
        setTimeout(() => {
            if (textareaRef.current) {
                textareaRef.current.focus();
                textareaRef.current.setSelectionRange(start + prefix.length, end + prefix.length);
            }
        }, 0);
    };

    const copyToClipboard = () => {
        navigator.clipboard.writeText(value);
    };

    return (
        <div className="flex flex-col h-full border border-gray-300 rounded-md overflow-hidden bg-white shadow-sm">
            {/* Top Bar: Tabs & Actions */}
            <div className="bg-gray-50 border-b border-gray-200 px-2 flex justify-between items-center">
                <div className="flex">
                    <button
                        onClick={() => setActiveTab('write')}
                        className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'write' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                    >
                        Write
                    </button>
                    <button
                        onClick={() => setActiveTab('preview')}
                        className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'preview' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                    >
                        Preview
                    </button>
                </div>

                <div className="flex items-center gap-2 pr-2">
                    <span className="text-xs text-gray-400 mr-2">
                        {value.length} chars
                    </span>
                    <button
                        onClick={copyToClipboard}
                        className="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded"
                        title="Copy to clipboard"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                    </button>
                </div>
            </div>

            {/* Toolbar (Visible only in Write mode) */}
            {activeTab === 'write' && (
                <div className="bg-white border-b border-gray-100 flex items-center px-2 py-1 gap-1">
                    <ToolbarButton onClick={() => insertFormat('**', '**')} label="B" title="Bold" />
                    <ToolbarButton onClick={() => insertFormat('*', '*')} label="I" title="Italic" />
                    <div className="w-px h-4 bg-gray-200 mx-1"></div>
                    <ToolbarButton onClick={() => insertFormat('### ')} label="H3" title="Heading 3" />
                    <ToolbarButton onClick={() => insertFormat('- ')} icon="List" title="Bullet List" />
                    <div className="w-px h-4 bg-gray-200 mx-1"></div>
                    <ToolbarButton onClick={() => insertFormat('`', '`')} icon="Code" title="Inline Code" />
                </div>
            )}

            {/* Content Area */}
            <div className="flex-1 flex overflow-hidden min-h-[700px] relative">
                {activeTab === 'write' ? (
                    <textarea
                        ref={textareaRef}
                        className="flex-1 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none bg-gray-50 text-gray-800 w-full h-full"
                        placeholder="Enter your prompt here..."
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        spellCheck={false}
                    />
                ) : (
                    <div className="flex-1 p-6 prose prose-sm max-w-none overflow-y-auto bg-white w-full h-full">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {value || '*No content to preview*'}
                        </ReactMarkdown>
                    </div>
                )}
            </div>
        </div>
    );
};

// Simple helper component for toolbar icons
const ToolbarButton = ({ onClick, icon, label, title }: { onClick: () => void, icon?: string, label?: string, title: string }) => (
    <button
        onClick={onClick}
        className="p-1.5 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded text-xs font-bold min-w-[24px] flex items-center justify-center"
        title={title}
    >
        {icon === 'List' ? (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
        ) : icon === 'Code' ? (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
        ) : label}
    </button>
);

export default PromptEditor;
