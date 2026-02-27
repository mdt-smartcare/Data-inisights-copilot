import React, { useState } from 'react';
import PromptHistory from '../../PromptHistory';
import type { PromptVersion } from '../../PromptHistory';
import { CheckCircleIcon, ArrowPathRoundedSquareIcon } from '@heroicons/react/24/outline';

interface HistoryTabProps {
    history: PromptVersion[];
    onRollback: (version: PromptVersion) => Promise<void>;
    isRollingBack: boolean;
}

export const HistoryTab: React.FC<HistoryTabProps> = ({
    history,
    onRollback,
    isRollingBack
}) => {
    const [compareVersions, setCompareVersions] = useState<{ v1: PromptVersion; v2: PromptVersion } | null>(null);

    const handleCompare = (v1: PromptVersion, v2: PromptVersion) => {
        setCompareVersions({ v1, v2 });
    };

    const handleCloseCompare = () => {
        setCompareVersions(null);
    };

    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                <svg className="w-5 h-5 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                System Prompt History
            </h2>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <PromptHistory
                    history={history}
                    onRollback={onRollback}
                    onCompare={handleCompare}
                />
            </div>

            {/* Comparison Modal */}
            {compareVersions && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                            <div>
                                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                    Configuration Comparison
                                </h3>
                                <p className="text-xs text-gray-500">Comparing Version {compareVersions.v1.version} with Version {compareVersions.v2.version}</p>
                            </div>
                            <button onClick={handleCloseCompare} className="p-2 hover:bg-white rounded-full transition-colors">
                                <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 md:p-8">
                            <div className="grid grid-cols-2 gap-8 h-full">
                                {/* Version 1 */}
                                <div className="space-y-6">
                                    <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                                        <div className="flex items-center gap-3">
                                            <span className="w-10 h-10 rounded-xl bg-gray-100 text-gray-700 flex items-center justify-center font-bold">V{compareVersions.v1.version}</span>
                                            <div>
                                                <p className="text-sm font-bold text-gray-900">Historical Version</p>
                                                <p className="text-xs text-gray-500">{new Date(compareVersions.v1.created_at).toLocaleString()}</p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => { onRollback(compareVersions.v1); handleCloseCompare(); }}
                                            disabled={isRollingBack}
                                            className={`px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-colors flex items-center gap-2 ${isRollingBack ? 'opacity-50 cursor-not-allowed' : ''}`}
                                        >
                                            <ArrowPathRoundedSquareIcon className="w-4 h-4" />
                                            {isRollingBack ? 'Rolling back...' : 'Rollback'}
                                        </button>
                                    </div>

                                    <section>
                                        <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">System Prompt</h4>
                                        <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 text-[11px] font-mono whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
                                            {compareVersions.v1.prompt_text}
                                        </div>
                                    </section>
                                </div>

                                {/* Version 2 (Active) */}
                                <div className="space-y-6">
                                    <div className="flex items-center justify-between pb-4 border-b border-blue-100">
                                        <div className="flex items-center gap-3">
                                            <span className="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-bold">V{compareVersions.v2.version}</span>
                                            <div>
                                                <p className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
                                                    Active Version
                                                    <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                                </p>
                                                <p className="text-xs text-gray-500">{new Date(compareVersions.v2.created_at).toLocaleString()}</p>
                                            </div>
                                        </div>
                                        <span className="px-4 py-2 bg-green-50 text-green-700 rounded-lg text-xs font-bold border border-green-100 flex items-center gap-2">
                                            <CheckCircleIcon className="w-4 h-4" />
                                            Active Production
                                        </span>
                                    </div>

                                    <section>
                                        <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">System Prompt</h4>
                                        <div className="bg-blue-50/30 p-4 rounded-xl border border-blue-100 text-[11px] font-mono whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
                                            {compareVersions.v2.prompt_text}
                                        </div>
                                    </section>
                                </div>
                            </div>
                        </div>
                        <div className="px-8 py-4 bg-gray-50 border-t border-gray-100 flex justify-end">
                            <button onClick={handleCloseCompare} className="px-6 py-2 bg-white border border-gray-200 text-gray-700 rounded-xl text-sm font-bold shadow-sm hover:bg-gray-100 transition-all">
                                Close Comparison
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default HistoryTab;
