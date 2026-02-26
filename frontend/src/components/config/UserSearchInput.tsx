import React, { useState, useRef, useEffect, useCallback } from 'react';
import { searchUsers, lookupUsersByEmails, handleApiError } from '../../services/api';
import type { SearchUser } from '../../services/api';
import { XMarkIcon } from '@heroicons/react/24/outline';

interface UserSearchInputProps {
    selectedUsers: SearchUser[];
    onSelectionChange: (users: SearchUser[]) => void;
    excludeUserIds?: number[];
    placeholder?: string;
    disabled?: boolean;
}

// Email validation regex
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const UserSearchInput: React.FC<UserSearchInputProps> = ({
    selectedUsers,
    onSelectionChange,
    excludeUserIds = [],
    placeholder = "Search users by name or email, or paste emails...",
    disabled = false
}) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<SearchUser[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [showDropdown, setShowDropdown] = useState(false);
    const [focusedIndex, setFocusedIndex] = useState(-1);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const debounceTimer = useRef<NodeJS.Timeout | null>(null);

    // Filter out already selected and excluded users
    const filteredResults = searchResults.filter(
        user => !selectedUsers.some(s => s.id === user.id) && !excludeUserIds.includes(user.id)
    );

    // Debounced search
    const performSearch = useCallback(async (query: string) => {
        if (!query.trim()) {
            setSearchResults([]);
            setShowDropdown(false);
            return;
        }

        setIsLoading(true);
        try {
            const results = await searchUsers(query, 10);
            setSearchResults(results);
            setShowDropdown(true);
            setFocusedIndex(-1);
        } catch (err) {
            console.error('Search failed:', handleApiError(err));
            setSearchResults([]);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        if (debounceTimer.current) {
            clearTimeout(debounceTimer.current);
        }

        if (searchQuery.trim()) {
            debounceTimer.current = setTimeout(() => {
                performSearch(searchQuery);
            }, 300);
        } else {
            setSearchResults([]);
            setShowDropdown(false);
        }

        return () => {
            if (debounceTimer.current) {
                clearTimeout(debounceTimer.current);
            }
        };
    }, [searchQuery, performSearch]);

    // Handle paste - extract emails and look them up
    const handlePaste = async (e: React.ClipboardEvent<HTMLInputElement>) => {
        const pastedText = e.clipboardData.getData('text');
        
        // Extract potential emails from pasted text (split by comma, semicolon, newline, space)
        const potentialEmails = pastedText
            .split(/[,;\n\s]+/)
            .map(s => s.trim().toLowerCase())
            .filter(s => EMAIL_REGEX.test(s));

        if (potentialEmails.length > 0) {
            e.preventDefault();
            setIsLoading(true);
            
            try {
                const users = await lookupUsersByEmails(potentialEmails);
                // Add users that aren't already selected or excluded
                const newUsers = users.filter(
                    user => !selectedUsers.some(s => s.id === user.id) && !excludeUserIds.includes(user.id)
                );
                
                if (newUsers.length > 0) {
                    onSelectionChange([...selectedUsers, ...newUsers]);
                }
                
                // Clear search
                setSearchQuery('');
                setShowDropdown(false);
            } catch (err) {
                console.error('Email lookup failed:', handleApiError(err));
            } finally {
                setIsLoading(false);
            }
        }
    };

    const handleSelect = (user: SearchUser) => {
        onSelectionChange([...selectedUsers, user]);
        setSearchQuery('');
        setShowDropdown(false);
        setFocusedIndex(-1);
        inputRef.current?.focus();
    };

    const handleRemove = (userId: number) => {
        onSelectionChange(selectedUsers.filter(u => u.id !== userId));
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (!showDropdown || filteredResults.length === 0) {
            // Handle backspace to remove last chip
            if (e.key === 'Backspace' && !searchQuery && selectedUsers.length > 0) {
                handleRemove(selectedUsers[selectedUsers.length - 1].id);
            }
            return;
        }

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                setFocusedIndex(prev => Math.min(prev + 1, filteredResults.length - 1));
                break;
            case 'ArrowUp':
                e.preventDefault();
                setFocusedIndex(prev => Math.max(prev - 1, 0));
                break;
            case 'Enter':
                e.preventDefault();
                if (focusedIndex >= 0 && focusedIndex < filteredResults.length) {
                    handleSelect(filteredResults[focusedIndex]);
                }
                break;
            case 'Escape':
                setShowDropdown(false);
                setFocusedIndex(-1);
                break;
        }
    };

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (
                dropdownRef.current && 
                !dropdownRef.current.contains(e.target as Node) &&
                inputRef.current &&
                !inputRef.current.contains(e.target as Node)
            ) {
                setShowDropdown(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div className="relative">
            {/* Input with chips */}
            <div 
                className={`flex flex-wrap items-center gap-2 p-2 min-h-[42px] border rounded-lg bg-white transition-colors
                    ${disabled ? 'bg-gray-100 cursor-not-allowed' : 'focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500'}
                    ${showDropdown ? 'border-blue-500 ring-2 ring-blue-500' : 'border-gray-300'}
                `}
                onClick={() => inputRef.current?.focus()}
            >
                {/* Selected user chips */}
                {selectedUsers.map(user => (
                    <span
                        key={user.id}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium"
                    >
                        <span className="w-5 h-5 bg-blue-200 rounded-full flex items-center justify-center text-xs font-semibold">
                            {user.username.charAt(0).toUpperCase()}
                        </span>
                        <span className="max-w-[150px] truncate">
                            {user.full_name || user.username}
                        </span>
                        <button
                            type="button"
                            onClick={(e) => {
                                e.stopPropagation();
                                handleRemove(user.id);
                            }}
                            className="ml-0.5 p-0.5 hover:bg-blue-200 rounded-full transition-colors"
                            disabled={disabled}
                        >
                            <XMarkIcon className="w-3.5 h-3.5" />
                        </button>
                    </span>
                ))}
                
                {/* Search input */}
                <input
                    ref={inputRef}
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onPaste={handlePaste}
                    onKeyDown={handleKeyDown}
                    onFocus={() => searchQuery && setShowDropdown(true)}
                    placeholder={selectedUsers.length === 0 ? placeholder : "Add more..."}
                    className="flex-1 min-w-[200px] outline-none bg-transparent text-sm"
                    disabled={disabled}
                />
                
                {/* Loading indicator */}
                {isLoading && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-200 border-t-blue-600"></div>
                    </div>
                )}
            </div>

            {/* Dropdown results */}
            {showDropdown && filteredResults.length > 0 && (
                <div 
                    ref={dropdownRef}
                    className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto"
                >
                    {filteredResults.map((user, index) => (
                        <button
                            key={user.id}
                            type="button"
                            onClick={() => handleSelect(user)}
                            className={`w-full px-4 py-3 text-left flex items-center gap-3 hover:bg-gray-50 transition-colors
                                ${index === focusedIndex ? 'bg-blue-50' : ''}
                                ${index !== filteredResults.length - 1 ? 'border-b border-gray-100' : ''}
                            `}
                        >
                            <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-semibold text-sm">
                                {user.username.charAt(0).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-gray-900 truncate">
                                    {user.full_name || user.username}
                                </div>
                                <div className="text-xs text-gray-500 truncate">
                                    {user.email || user.username}
                                </div>
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                                ${user.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}
                            `}>
                                {user.role}
                            </span>
                        </button>
                    ))}
                </div>
            )}

            {/* No results message */}
            {showDropdown && searchQuery && !isLoading && filteredResults.length === 0 && searchResults.length === 0 && (
                <div 
                    ref={dropdownRef}
                    className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg p-4 text-center text-gray-500 text-sm"
                >
                    No users found matching "{searchQuery}"
                </div>
            )}

            {/* Help text */}
            <p className="mt-2 text-xs text-gray-500">
                Search by name or email. You can also paste multiple emails (comma or newline separated) to add users in bulk.
            </p>
        </div>
    );
};

export default UserSearchInput;
