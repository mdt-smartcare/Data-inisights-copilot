interface EmptyStateProps {
  title?: string;
  subtitle?: string;
  suggestions?: string[];
  onSuggestedQuestionClick?: (suggestion: string) => void;
}

export default function EmptyState({
  title = 'Ask me anything about FHIR healthcare data!',
  subtitle = 'Start a conversation by typing a message below',
  suggestions = [
    'What are the key components of a FHIR Patient resource?',
    'Explain FHIR resource references',
    'How do I implement FHIR search parameters?'
  ],
  onSuggestedQuestionClick
}: EmptyStateProps) {
  return (
    <div className="text-center text-gray-500 mt-8 px-4 animate-fadeSlideUp">
      <div className="mb-6">
        {/* Floating icon */}
        <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg animate-float">
          <svg
            className="w-7 h-7 text-white"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        <p className="text-sm mt-1.5 text-gray-500">{subtitle}</p>
      </div>

      {suggestions && suggestions.length > 0 && (
        <div className="mt-6 max-w-xl mx-auto">
          <p className="text-xs font-medium text-gray-500 mb-3">Try asking:</p>
          <div className="space-y-2">
            {suggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => onSuggestedQuestionClick?.(suggestion)}
                className="w-full text-sm text-left bg-white border border-gray-200 rounded-lg px-4 py-3 hover:border-blue-400 hover:bg-blue-50 hover:shadow-md transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-300 group"
              >
                <span className="text-gray-600 group-hover:text-blue-700">{suggestion}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

