import React, { useRef, useState } from 'react';

interface DictionaryUploaderProps {
    onUpload: (content: string) => void;
    disabled?: boolean;
}

const DictionaryUploader: React.FC<DictionaryUploaderProps> = ({ onUpload, disabled = false }) => {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [error, setError] = useState<string | null>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setError(null);
        const reader = new FileReader();

        reader.onload = (event) => {
            try {
                let content = event.target?.result as string;

                // Basic validation/formatting based on extension
                if (file.name.endsWith('.json')) {
                    // Validate JSON
                    const json = JSON.parse(content);
                    content = JSON.stringify(json, null, 2);
                } else if (file.name.endsWith('.csv')) {
                    // Ensure basic CSV structure (just simple check)
                    if (!content.includes(',')) {
                        console.warn("File doesn't look like standard CSV");
                    }
                }

                onUpload(content);
                // Reset input so same file can be selected again if needed
                if (fileInputRef.current) fileInputRef.current.value = '';
            } catch (err) {
                setError("Failed to parse file. Please ensure it is valid text/JSON/CSV.");
            }
        };

        reader.onerror = () => {
            setError("Error reading file.");
        };

        reader.readAsText(file);
    };

    return (
        <div className="flex items-center">
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                className="hidden"
                accept=".csv,.json,.txt,.md"
            />

            <button
                onClick={() => !disabled && fileInputRef.current?.click()}
                disabled={disabled}
                className={`text-xs font-medium px-2 py-1 rounded flex items-center gap-1 ${disabled ? 'text-gray-400 cursor-not-allowed' : 'text-blue-600 hover:text-blue-800 hover:bg-blue-100'}`}
            >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Import File
            </button>

            {error && <span className="ml-2 text-xs text-red-500">{error}</span>}
        </div>
    );
};

export default DictionaryUploader;
