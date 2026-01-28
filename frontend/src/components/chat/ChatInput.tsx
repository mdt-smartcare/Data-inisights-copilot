import { useState, useRef } from 'react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isDisabled?: boolean;
  placeholder?: string;
  maxLength?: number;
}

export default function ChatInput({
  onSendMessage,
  isDisabled = false,
  placeholder = 'Type your message...',
  maxLength = 2000
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedInput = input.trim();

    if (!trimmedInput || isDisabled) return;

    onSendMessage(trimmedInput);
    setInput('');

    // Reset textarea height after sending
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter, but allow Shift+Enter for new lines
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const charCount = input.length;
  const isOverLimit = charCount > maxLength;

  return (
    <div className="bg-white border-t border-gray-200 px-4 py-3 shadow-lg">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="flex flex-col gap-1.5">
          <div className="flex gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none bg-gray-50 focus:bg-white transition-colors"
              disabled={isDisabled}
              style={{
                minHeight: '2.25rem',
                maxHeight: '8rem',
                height: 'auto'
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = 'auto';
                target.style.height = target.scrollHeight + 'px';
              }}
            />
            <button
              type="submit"
              disabled={isDisabled || !input.trim() || isOverLimit}
              className="bg-blue-600 hover:bg-blue-700 hover:scale-105 disabled:bg-gray-300 disabled:hover:scale-100 disabled:cursor-not-allowed text-white font-medium px-4 py-2 text-sm rounded-lg transition-all duration-200 h-10 flex items-center gap-1.5 shadow-sm hover:shadow-md"
              title={isDisabled ? 'Please wait...' : 'Send message (Enter)'}
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
              Send
            </button>
          </div>

          <div className="flex justify-between items-center text-[10px] text-gray-500 px-1">
            <span>Enter to send • Shift+Enter for new line</span>
            <span className={isOverLimit ? 'text-red-500 font-medium' : ''}>
              {charCount}/{maxLength}
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}
