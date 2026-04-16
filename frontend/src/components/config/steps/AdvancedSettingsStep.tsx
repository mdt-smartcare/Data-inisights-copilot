import React, { useEffect } from 'react';
import AdvancedSettings from '../../AdvancedSettings';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';
import { useSystemSettings } from '../../../contexts/SystemSettingsContext';
import type { AdvancedSettings as AdvancedSettingsType } from '../../../contexts/AgentContext';

interface AdvancedSettingsStepProps {
    advancedSettings: AdvancedSettingsType;
    setAdvancedSettings: React.Dispatch<React.SetStateAction<AdvancedSettingsType>>;
    dataSourceType: 'database' | 'file';
    connectionName: string;
    connectionId: number | null;
    fileName?: string;
}

export const AdvancedSettingsStep: React.FC<AdvancedSettingsStepProps> = ({
    advancedSettings,
    setAdvancedSettings,
    dataSourceType,
    connectionName,
    connectionId,
    fileName
}) => {
    const { user } = useAuth();
    const canEdit = canEditPrompt(user);
    const { advancedSettings: systemSettings, isLoading: isLoadingDefaults, isLoaded, ensureLoaded } = useSystemSettings();

    // Load system defaults on mount via context (lazy loading)
    useEffect(() => {
        ensureLoaded();
    }, [ensureLoaded]);

    // Apply system defaults when loaded
    useEffect(() => {
        if (!isLoaded) return;

        setAdvancedSettings((prev: AdvancedSettingsType) => {
            const next = { ...prev };
            // Only apply defaults if values haven't been set yet (using default values as check)
            if (systemSettings.embedding.model && !prev.embedding.model) {
                next.embedding = { ...next.embedding, model: systemSettings.embedding.model };
            }
            if (prev.chunking.parentChunkSize === 512 && systemSettings.chunking.parentChunkSize !== 512) {
                next.chunking = { ...next.chunking, parentChunkSize: systemSettings.chunking.parentChunkSize };
            }
            if (prev.chunking.parentChunkOverlap === 100 && systemSettings.chunking.parentChunkOverlap !== 100) {
                next.chunking = { ...next.chunking, parentChunkOverlap: systemSettings.chunking.parentChunkOverlap };
            }
            if (prev.retriever.topKInitial === 50 && systemSettings.retriever.topKInitial !== 50) {
                next.retriever = { ...next.retriever, topKInitial: systemSettings.retriever.topKInitial };
            }
            if (prev.retriever.topKFinal === 10 && systemSettings.retriever.topKFinal !== 10) {
                next.retriever = { ...next.retriever, topKFinal: systemSettings.retriever.topKFinal };
            }
            if (systemSettings.retriever.hybridWeights) {
                next.retriever = { ...next.retriever, hybridWeights: systemSettings.retriever.hybridWeights };
            }
            if (systemSettings.retriever.rerankEnabled !== undefined) {
                next.retriever = { ...next.retriever, rerankEnabled: systemSettings.retriever.rerankEnabled };
            }
            if (systemSettings.retriever.rerankerModel) {
                next.retriever = { ...next.retriever, rerankerModel: systemSettings.retriever.rerankerModel };
            }
            if (prev.llm.temperature === 0.0 && systemSettings.llm.temperature !== 0.0) {
                next.llm = { ...next.llm, temperature: systemSettings.llm.temperature };
            }
            if (prev.llm.maxTokens === 4096 && systemSettings.llm.maxTokens !== 4096) {
                next.llm = { ...next.llm, maxTokens: systemSettings.llm.maxTokens };
            }
            return next;
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isLoaded]); // Only run when settings are loaded

    // Show loading only during active fetch, not initially
    if (isLoadingDefaults && !isLoaded) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-500">Loading settings...</span>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col">
            <AdvancedSettings
                settings={advancedSettings}
                onChange={setAdvancedSettings}
                readOnly={!canEdit}
            />
        </div>
    );
};

export default AdvancedSettingsStep;
