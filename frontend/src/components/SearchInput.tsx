import React, { useState, useEffect, useRef } from 'react';

export interface SearchInputProps {
    /** Current search value (controlled) */
    value: string;
    /** Callback when search value changes (after debounce) */
    onChange: (value: string) => void;
    /** Placeholder text */
    placeholder?: string;
    /** Debounce delay in milliseconds */
    debounceMs?: number;
    /** Whether the input is disabled */
    disabled?: boolean;
    /** Additional CSS classes for the container */
    className?: string;
}

/**
 * Reusable search input with debounce support.
 * 
 * @example
 * const [search, setSearch] = useState('');
 * 
 * <SearchInput
 *   value={search}
 *   onChange={setSearch}
 *   placeholder="Search users..."
 * />
 */
const SearchInput: React.FC<SearchInputProps> = ({
    value,
    onChange,
    placeholder = 'Search...',
    debounceMs = 300,
    disabled = false,
    className = '',
}) => {
    // Local state for immediate input response
    const [localValue, setLocalValue] = useState(value);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Sync local value when external value changes
    useEffect(() => {
        setLocalValue(value);
    }, [value]);

    // Debounced onChange handler
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const newValue = e.target.value;
        setLocalValue(newValue);

        // Clear existing timeout
        if (debounceRef.current) {
            clearTimeout(debounceRef.current);
        }

        // Set new timeout for debounced callback
        debounceRef.current = setTimeout(() => {
            onChange(newValue);
        }, debounceMs);
    };

    // Clear search
    const handleClear = () => {
        setLocalValue('');
        onChange('');
        // Clear any pending debounce
        if (debounceRef.current) {
            clearTimeout(debounceRef.current);
        }
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (debounceRef.current) {
                clearTimeout(debounceRef.current);
            }
        };
    }, []);

    return (
        <div className={`relative ${className}`}>
            {/* Search Icon */}
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                    className="h-5 w-5 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                </svg>
            </div>

            {/* Input */}
            <input
                type="text"
                value={localValue}
                onChange={handleChange}
                placeholder={placeholder}
                disabled={disabled}
                className={`
                    block w-full pl-10 pr-10 py-2 
                    border border-gray-300 rounded-lg
                    text-sm text-gray-900 placeholder-gray-500
                    focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                    disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed
                    transition-colors
                `}
            />

            {/* Clear Button */}
            {localValue && !disabled && (
                <button
                    type="button"
                    onClick={handleClear}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 transition-colors"
                    aria-label="Clear search"
                >
                    <svg
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                        />
                    </svg>
                </button>
            )}
        </div>
    );
};

export default SearchInput;
