import React, { useRef, useState } from 'react';

interface DictionaryUploaderProps {
    onUpload: (content: string) => void;
}

const DictionaryUploader: React.FC<DictionaryUploaderProps> = ({ onUpload }) => {
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
        <div className="flex flex-col items-start gap-2">
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                className="hidden"
                accept=".csv,.json,.txt,.md"
            />

            <div className="flex gap-2 items-center">
                <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded text-sm text-gray-700 hover:bg-gray-200 flex items-center gap-2"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    Upload Dictionary File
                </button>
                <span className="text-xs text-gray-400">(CSV, JSON, TXT)</span>
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
    );
};

export default DictionaryUploader;
