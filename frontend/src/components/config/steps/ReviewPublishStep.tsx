import React from 'react';
import PromptEditor from '../../PromptEditor';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface ReviewPublishStepProps {
    draftPrompt: string;
    setDraftPrompt: (value: string) => void;
    exampleQuestions: string[];
    onGeneratePrompt?: () => Promise<void>;
    isGenerating?: boolean;
}

export const ReviewPublishStep: React.FC<ReviewPublishStepProps> = ({
    draftPrompt,
    setDraftPrompt,
    exampleQuestions,
    onGeneratePrompt,
    isGenerating = false,
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);

    // If no prompt exists yet, show the generate prompt UI
    if (!draftPrompt) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8">
                <div className="max-w-lg w-full text-center">
                    {/* Icon */}
                    <div className="mx-auto w-20 h-20 rounded-full bg-gradient-to-br from-blue-100 to-purple-100 flex items-center justify-center mb-6">
                        <svg className="w-10 h-10 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                    </div>

                    {/* Title */}
                    <h2 className="text-2xl font-bold text-gray-900 mb-3">Generate System Prompt</h2>
                    
                    {/* Description */}
                    <p className="text-gray-600 mb-8 leading-relaxed">
                        Based on your data dictionary and settings, we'll use AI to generate 
                        a production-ready system prompt tailored for your agent. You can 
                        edit and refine it before publishing.
                    </p>

                    {/* What will be generated */}
                    <div className="bg-gray-50 rounded-lg p-4 mb-8 text-left">
                        <h4 className="text-sm font-semibold text-gray-700 mb-3">This will generate:</h4>
                        <ul className="space-y-2">
                            <li className="flex items-start gap-2 text-sm text-gray-600">
                                <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                <span><strong>System Prompt</strong> - Instructions for the AI based on your schema</span>
                            </li>
                            <li className="flex items-start gap-2 text-sm text-gray-600">
                                <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                <span><strong>Example Questions</strong> - Sample queries users can ask</span>
                            </li>
                            <li className="flex items-start gap-2 text-sm text-gray-600">
                                <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                <span><strong>Schema Context</strong> - Table and field explanations</span>
                            </li>
                        </ul>
                    </div>

                    {/* Generate Button */}
                    <button
                        onClick={onGeneratePrompt}
                        disabled={isGenerating || !canEdit}
                        className={`w-full px-6 py-3 rounded-lg font-semibold text-white transition-all duration-200 flex items-center justify-center gap-3
                            ${isGenerating 
                                ? 'bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse cursor-wait' 
                                : !canEdit 
                                    ? 'bg-gray-400 cursor-not-allowed' 
                                    : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 shadow-lg hover:shadow-xl'
                            }`}
                    >
                        {isGenerating ? (
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

                    {!canEdit && (
                        <p className="mt-3 text-sm text-gray-500 italic">
                            You have read-only access. Contact an admin to generate prompts.
                        </p>
                    )}
                </div>
            </div>
        );
    }

    // Once prompt exists, show the editor view with Generate Prompt button for regeneration
    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-3 sm:mb-4">
                <div>
                    <h2 className="text-lg sm:text-xl font-semibold text-gray-900">Review & Edit Prompt</h2>
                    <p className="text-sm text-gray-500 mt-0.5">Review the generated prompt, make edits, and publish when ready.</p>
                </div>
                {onGeneratePrompt && canEdit && (
                    <button
                        onClick={onGeneratePrompt}
                        disabled={isGenerating}
                        className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all duration-200
                            ${isGenerating 
                                ? 'bg-gradient-to-r from-blue-500 to-purple-500 text-white cursor-wait' 
                                : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white shadow-md hover:shadow-lg'
                            }`}
                    >
                        {isGenerating ? (
                            <>
                                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                <span>Generating...</span>
                            </>
                        ) : (
                            <>
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                                <span>Generate Prompt</span>
                            </>
                        )}
                    </button>
                )}
            </div>

            {/* Editor - Takes remaining space */}
            <div className="flex-1 min-h-[400px] sm:min-h-[500px]">
                <PromptEditor
                    value={draftPrompt}
                    onChange={setDraftPrompt}
                    readOnly={!canEdit}
                />
            </div>

            {/* Example Questions Preview */}
            {exampleQuestions.length > 0 && (
                <div className="mt-3 sm:mt-4 bg-gradient-to-r from-blue-50 to-indigo-50 p-3 sm:p-5 rounded-lg border border-blue-100">
                    <h3 className="text-xs sm:text-sm font-bold text-blue-900 mb-2 sm:mb-3 flex items-center">
                        <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Example Questions (Preview)
                    </h3>
                    <div className="flex gap-2 flex-wrap">
                        {exampleQuestions.map((q, idx) => (
                            <span key={idx} className="inline-flex items-center px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg text-xs sm:text-sm font-medium bg-white text-blue-700 shadow-sm border border-blue-100">
                                {q}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ReviewPublishStep;
