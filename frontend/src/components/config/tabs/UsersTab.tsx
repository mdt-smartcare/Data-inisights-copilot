import React from 'react';
import AgentUsersTab from '../AgentUsersTab';
import { UserGroupIcon } from '@heroicons/react/24/outline';

interface UsersTabProps {
    agentId: number;
    agentName: string;
}

export const UsersTab: React.FC<UsersTabProps> = ({
    agentId,
    agentName
}) => {
    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-lg font-bold mb-4 text-gray-900 flex items-center gap-2">
                <UserGroupIcon className="w-5 h-5 text-indigo-600" />
                User Management
            </h2>
            <AgentUsersTab
                agentId={agentId}
                agentName={agentName}
            />
        </div>
    );
};

export default UsersTab;
