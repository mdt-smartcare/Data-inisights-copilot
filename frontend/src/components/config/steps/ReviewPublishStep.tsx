import React, { useState } from 'react';
import PromptEditor from '../../PromptEditor';
import PromptHistory from '../../PromptHistory';
import type { PromptVersion } from '../../PromptHistory';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';

interface ReviewPublishStepProps {
    draftPrompt: string;
    setDraftPrompt: (value: string) => void;
    exampleQuestions: string[];
    history: PromptVersion[];
}

export const ReviewPublishStep: React.FC<ReviewPublishStepProps> = ({
    draftPrompt,
    setDraftPrompt,
    exampleQuestions,
    history
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);
    const [showHistory, setShowHistory] = useState(false);
    const [replaceConfirm, setReplaceConfirm] = useState<{ show: boolean; version: PromptVersion | null }>({ show: false, version: null });

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-3 sm:mb-4">
                <h2 className="text-lg sm:text-xl font-semibold">Review & Configuration</h2>
                <button
                    onClick={() => setShowHistory(!showHistory)}
                    className={`text-xs sm:text-sm px-3 py-1.5 rounded border self-start sm:self-auto ${showHistory ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'}`}
                >
                    {showHistory ? 'Hide History' : 'Show History'}
                </button>
            </div>

            {/* History Panel - Shows below header when expanded */}
            {showHistory && (
                <div className="mb-3 sm:mb-4 max-h-[200px] sm:max-h-[250px] overflow-hidden rounded-lg border border-gray-200">
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

            {/* Replace Version Confirmation Modal */}
            {replaceConfirm.show && replaceConfirm.version && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-4 sm:p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                                <svg className="w-4 h-4 sm:w-5 sm:h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                            </div>
                            <div className="min-w-0">
                                <h3 className="text-base sm:text-lg font-semibold text-gray-900">Replace Current Draft</h3>
                                <p className="text-xs sm:text-sm text-gray-500">Load version {replaceConfirm.version.version}</p>
                            </div>
                        </div>
                        <p className="text-sm text-gray-600 mb-4 sm:mb-6">
                            This will replace your current draft with the content from <strong>v{replaceConfirm.version.version}</strong>.
                            Any unsaved changes will be lost.
                        </p>
                        <div className="flex justify-end gap-2 sm:gap-3">
                            <button
                                type="button"
                                onClick={() => setReplaceConfirm({ show: false, version: null })}
                                className="px-3 sm:px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium text-sm"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    if (replaceConfirm.version) {
                                        setDraftPrompt(replaceConfirm.version.prompt_text);
                                    }
                                    setReplaceConfirm({ show: false, version: null });
                                }}
                                className="px-3 sm:px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium text-sm"
                            >
                                Replace Draft
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ReviewPublishStep;
