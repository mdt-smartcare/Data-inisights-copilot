import React from 'react';
import PromptEditor from '../../PromptEditor';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';
import type { Agent } from '../../../types/agent';
import type { DataSourceSchemaResponse } from '../../../services/api';
import type { AdvancedSettings } from '../../../contexts/AgentContext';

interface ReviewPublishStepProps {
    draftPrompt: string;
    setDraftPrompt: (value: string) => void;
    exampleQuestions: string[];
    onGeneratePrompt?: () => Promise<void>;
    isGenerating?: boolean;
    agent?: Agent | null;
    dataDictionary?: string;
    schema?: DataSourceSchemaResponse | null;
    selectedSchema?: Record<string, string[]>;
    advancedSettings?: AdvancedSettings;
    dataSourceType?: 'database' | 'file';
}

export const ReviewPublishStep: React.FC<ReviewPublishStepProps> = ({
    draftPrompt,
    setDraftPrompt,
    exampleQuestions,
    onGeneratePrompt,
    isGenerating = false,
    agent,
    dataDictionary,
    selectedSchema,
    advancedSettings,
    dataSourceType,
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    // Use display name from advancedSettings (set by AdvancedSettings component)
    // Fallback to model_id string if display name not available
    const llmDisplayName = advancedSettings?.llmDisplayName 
        || advancedSettings?.llm?.model 
        || 'Not configured';

    // If no prompt exists yet, show the generate prompt UI
    if (!draftPrompt) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-4 sm:p-8 bg-gradient-to-br from-gray-50 to-blue-50/30">
                <div className="max-w-2xl w-full text-center">
                    {/* Header Section */}
                    <div className="relative mb-8 sm:mb-12">
                        <div className="absolute inset-0 -top-4 bg-blue-500/10 blur-3xl rounded-full"></div>
                        <div className="relative">
                            <h2 className="text-2xl sm:text-3xl font-extrabold text-gray-900 mb-4 tracking-tight">
                                Generate System Prompt
                            </h2>
                            <p className="max-w-md mx-auto text-gray-600 text-sm sm:text-base leading-relaxed">
                                We'll use AI to craft a specialized system prompt for your agent based on your database structure and context.
                            </p>
                        </div>
                    </div>

                    {/* Pre-flight Layout Container */}
                    <div className="flex flex-col md:flex-row items-stretch justify-center gap-6 mb-10 w-full max-w-4xl mx-auto text-left">
                        {/* What we generate (Left side) */}
                        <div className="flex-1 bg-white/40 backdrop-blur-md rounded-2xl p-6 border border-white shadow-[0_8px_30px_rgb(0,0,0,0.04)] relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-100/50 rounded-full blur-3xl -mr-16 -mt-16"></div>

                            <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-5 flex items-center gap-2">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
                                AI Engine Output
                            </h3>

                            <div className="space-y-4">
                                <div className="flex items-start gap-3">
                                    <div className="p-1.5 bg-blue-100 rounded-lg text-blue-600">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                    </div>
                                    <div>
                                        <h4 className="text-sm font-bold text-gray-900">System Prompt</h4>
                                        <p className="text-xs text-gray-500 mt-0.5">Custom logic derived directly from your schema bounds.</p>
                                    </div>
                                </div>
                                <div className="flex items-start gap-3">
                                    <div className="p-1.5 bg-purple-100 rounded-lg text-purple-600">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    </div>
                                    <div>
                                        <h4 className="text-sm font-bold text-gray-900">Example Questions</h4>
                                        <p className="text-xs text-gray-500 mt-0.5">3-5 sample queries to seamlessly guide your end-users.</p>
                                    </div>
                                </div>
                                <div className="flex items-start gap-3">
                                    <div className="p-1.5 bg-indigo-100 rounded-lg text-indigo-600">
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 4a2 2 0 114 0v1a2 2 0 11-4 0V4zM11 13a2 2 0 114 0v1a2 2 0 11-4 0v-1zM4 11a2 2 0 100 4h1a2 2 0 100-4H4zM19 11a2 2 0 100 4h1a2 2 0 100-4h-1z" /></svg>
                                    </div>
                                    <div>
                                        <h4 className="text-sm font-bold text-gray-900">Schema Context</h4>
                                        <p className="text-xs text-gray-500 mt-0.5">Deep awareness of your table structures and relationships.</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Pre-flight Snapshot (Right side) */}
                        <div className="flex-1 bg-white rounded-2xl p-6 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.06)] relative overflow-hidden">
                            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-5 flex items-center gap-2">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                                Using Settings
                            </h3>

                            <div className="grid grid-cols-2 gap-x-4 gap-y-5">
                                <div>
                                    <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Agent Name</span>
                                    <p className="text-sm font-bold text-gray-800 mt-0.5 truncate">{agent?.name || 'Unnamed'}</p>
                                </div>
                                <div>
                                    <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">AI   Engine</span>
                                    <p className="text-sm font-bold text-gray-800 mt-0.5 truncate">{llmDisplayName}</p>
                                </div>
                                <div>
                                    <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Schema Scope</span>
                                    <p className="text-sm font-bold text-gray-800 mt-0.5">
                                        {selectedSchema && Object.keys(selectedSchema).length > 0
                                            ? `${Object.keys(selectedSchema).length} ${dataSourceType === 'file' ? 'doc(s)' : 'table(s)'}`
                                            : 'Full scope'}
                                    </p>
                                </div>
                                <div>
                                    <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Data Dictionary</span>
                                    <p className="text-sm font-bold text-gray-800 mt-0.5">
                                        {dataDictionary ? 'Active' : 'Not Configured'}
                                    </p>
                                </div>
                            </div>
                            {dataDictionary ? (
                                <div className="mt-4 pt-4 border-t border-gray-50">
                                    <p className="text-[10px] text-gray-400 italic line-clamp-2 leading-relaxed">
                                        "{dataDictionary}"
                                    </p>
                                </div>
                            ) : (
                                <div className="mt-4 pt-4 border-t border-gray-50">
                                    <p className="text-[10px] text-black-400 italic line-clamp-2 leading-relaxed">
                                        No manual context provided. The LLM will rely on schema definitions.
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Generate Button Section */}
                    <div className="max-w-md mx-auto w-full">
                        <button
                            onClick={onGeneratePrompt}
                            disabled={isGenerating || !canEdit}
                            className={`group relative w-full px-8 py-4 rounded-2xl font-bold text-white transition-all duration-300 transform active:scale-95
                                ${isGenerating
                                    ? 'bg-gray-400 cursor-wait'
                                    : !canEdit
                                        ? 'bg-gray-300 cursor-not-allowed opacity-50'
                                        : 'bg-indigo-600 hover:bg-indigo-700 shadow-[0_10px_30px_-10px_rgba(79,70,229,0.5)] hover:shadow-[0_15px_40px_-10px_rgba(79,70,229,0.6)]'
                                }`}
                        >
                            {isGenerating ? (
                                <div className="flex items-center justify-center gap-3">
                                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                    <span className="tracking-wide">AI is thinking...</span>
                                </div>
                            ) : (
                                <div className="flex items-center justify-center gap-2">
                                    <svg className="w-5 h-5 group-hover:animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    <span className="tracking-wide uppercase text-sm">Generate Engine Prompt</span>
                                </div>
                            )}
                        </button>

                        {!canEdit && (
                            <div className="mt-4 flex items-center justify-center gap-2 text-xs text-gray-400 italic">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                                Read-only mode active
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    // Once prompt exists, show the editor view with Generate Prompt button for regeneration
    return (
        <div className="h-full flex flex-col overflow-hidden bg-white animate-in fade-in duration-500">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4 mb-6 pt-2">
                <div>
                    <h2 className="text-xl sm:text-2xl font-bold text-gray-900 tracking-tight">Review & Refine</h2>
                    <p className="text-sm text-gray-500 mt-1 max-w-lg">The AI has generated a prompt based on your data. You can manually adjust the instructions below before final publication.</p>
                </div>
                {onGeneratePrompt && canEdit && (
                    <button
                        onClick={onGeneratePrompt}
                        disabled={isGenerating}
                        className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm transition-all duration-300 shadow-sm
                            ${isGenerating
                                ? 'bg-indigo-100 text-indigo-400 cursor-wait'
                                : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-100 hover:border-indigo-200'
                            }`}
                    >
                        {isGenerating ? (
                            <>
                                <div className="w-3.5 h-3.5 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
                                <span>Regenerating...</span>
                            </>
                        ) : (
                            <>
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                                <span>Regenerate AI Prompt</span>
                            </>
                        )}
                    </button>
                )}
            </div>

            {/* Editor Container */}
            <div className="flex-1 min-h-[400px] sm:min-h-[500px] rounded-2xl border border-gray-200 shadow-inner bg-gray-50/30 overflow-hidden relative group">
                <PromptEditor
                    value={draftPrompt}
                    onChange={setDraftPrompt}
                    readOnly={!canEdit}
                />
            </div>

            {/* Example Questions Preview */}
            {exampleQuestions.length > 0 && (
                <div className="mt-6 bg-indigo-50/50 rounded-2xl p-4 sm:p-6 border border-indigo-100/50">
                    <div className="flex items-center gap-2 mb-4">
                        <div className="p-1.5 bg-indigo-100 rounded-lg">
                            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <h3 className="text-sm font-bold text-indigo-900">Example Questions</h3>
                        <span className="text-[10px] bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full font-medium">Auto-generated</span>
                    </div>
                    <div className="flex gap-3 flex-wrap">
                        {exampleQuestions.map((q, idx) => (
                            <div key={idx} className="group relative">
                                <div className="absolute inset-0 bg-white rounded-xl blur-sm group-hover:blur-md transition-all duration-300 opacity-50"></div>
                                <span className="relative inline-flex items-center px-4 py-2 rounded-xl text-sm font-medium bg-white text-indigo-700 shadow-sm border border-indigo-100 hover:border-indigo-300 hover:shadow-md transition-all duration-300 cursor-default">
                                    {q}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ReviewPublishStep;
