import React from 'react';
import AdvancedSettings from '../../AdvancedSettings';
import { canEditPrompt } from '../../../utils/permissions';
import { useAuth } from '../../../contexts/AuthContext';
import type { AdvancedSettings as AdvancedSettingsType } from '../../../contexts/AgentContext';

interface AdvancedSettingsStepProps {
    advancedSettings: AdvancedSettingsType;
    setAdvancedSettings: (settings: AdvancedSettingsType) => void;
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

    const dataSourceName = dataSourceType === 'file' && fileName
        ? fileName.split('.')[0]
        : (connectionName || `db_connection_${connectionId || 'default'}`);

    return (
        <div className="h-full flex flex-col">
            <AdvancedSettings
                settings={advancedSettings}
                onChange={setAdvancedSettings}
                readOnly={!canEdit}
                dataSourceName={dataSourceName}
            />
        </div>
    );
};

export default AdvancedSettingsStep;
