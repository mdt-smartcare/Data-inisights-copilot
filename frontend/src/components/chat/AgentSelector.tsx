import React, { useState, useRef, useEffect } from 'react';
import type { Agent } from '../../types/agent'; // Explicit type import
import {
    ChevronDownIcon,
    CheckIcon,
    CpuChipIcon,
    CircleStackIcon,
    PlusIcon
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';

interface AgentSelectorProps {
    agents: Agent[];
    selectedAgentId: number | undefined;
    onSelect: (agentId: number) => void;
    isLoading: boolean;
}

export const AgentSelector: React.FC<AgentSelectorProps> = ({
    agents,
    selectedAgentId,
    onSelect,
    isLoading
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();

    const selectedAgent = agents.find(a => a.id === selectedAgentId);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const getAgentIcon = (type: string) => {
        switch (type.toLowerCase()) {
            case 'sql':
                return <CircleStackIcon className="w-5 h-5" />;
            default:
                return <CpuChipIcon className="w-5 h-5" />;
        }
    };

    const handleSelect = (agentId: number) => {
        onSelect(agentId);
        setIsOpen(false);
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                type="button"
                className={`
          flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200
          ${isOpen
                        ? 'bg-indigo-50 text-indigo-700 ring-2 ring-indigo-500 ring-offset-1'
                        : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 hover:border-gray-400 shadow-sm'
                    }
          ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
                onClick={() => !isLoading && setIsOpen(!isOpen)}
                disabled={isLoading}
            >
                {selectedAgent ? (
                    <>
                        <span className={isOpen ? 'text-indigo-600' : 'text-gray-500'}>
                            {getAgentIcon(selectedAgent.type)}
                        </span>
                        <span>{selectedAgent.name}</span>
                    </>
                ) : (
                    <span>{isLoading ? 'Loading Agents...' : 'Select an Agent'}</span>
                )}
                <ChevronDownIcon
                    className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                />
            </button>

            {isOpen && (
                <div className="absolute z-50 mt-2 w-64 bg-white rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 animate-in fade-in zoom-in-95 duration-100 origin-top-left">
                    <div className="p-1 max-h-60 overflow-y-auto">
                        {agents.length === 0 ? (
                            <div className="px-4 py-3 text-sm text-gray-500 text-center">
                                No agents found
                            </div>
                        ) : (
                            agents.map((agent) => {
                                const isSelected = agent.id === selectedAgentId;
                                return (
                                    <button
                                        key={agent.id}
                                        onClick={() => handleSelect(agent.id)}
                                        className={`
                      w-full flex items-center justify-between px-3 py-2 text-sm rounded-md transition-colors
                      ${isSelected
                                                ? 'bg-indigo-50 text-indigo-700'
                                                : 'text-gray-700 hover:bg-gray-100'
                                            }
                    `}
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className={isSelected ? 'text-indigo-500' : 'text-gray-400'}>
                                                {getAgentIcon(agent.type)}
                                            </span>
                                            <div className="text-left">
                                                <div className="font-medium">{agent.name}</div>
                                                {agent.description && (
                                                    <div className="text-xs text-gray-400 truncate max-w-[140px]">
                                                        {agent.description}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        {isSelected && <CheckIcon className="w-4 h-4 text-indigo-600" />}
                                    </button>
                                );
                            })
                        )}
                    </div>

                    <div className="border-t border-gray-100 p-1">
                        <button
                            onClick={() => {
                                setIsOpen(false);
                                navigate('/agents');
                            }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:text-indigo-600 rounded-md transition-colors"
                        >
                            <PlusIcon className="w-4 h-4" />
                            <span>Create New Agent</span>
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
