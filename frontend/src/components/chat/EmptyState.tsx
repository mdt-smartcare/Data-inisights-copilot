interface EmptyStateProps {
  title?: string;
  subtitle?: string;
  suggestions?: string[];
}

export default function EmptyState({ 
  title = 'Ask me anything about FHIR healthcare data!',
  subtitle = 'Start a conversation by typing a message below',
  suggestions = [
    'What are the key components of a FHIR Patient resource?',
    'Explain FHIR resource references',
    'How do I implement FHIR search parameters?'
  ]
}: EmptyStateProps) {
  return (
    <div className="text-center text-gray-500 mt-4 px-4">
      <div className="mb-4">
        <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <svg 
            className="w-6 h-6 text-white" 
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
        <p className="text-base font-medium text-gray-700">{title}</p>
        <p className="text-xs mt-1.5 text-gray-500">{subtitle}</p>
      </div>

      {suggestions && suggestions.length > 0 && (
        <div className="mt-4 max-w-2xl mx-auto">
          <p className="text-xs font-medium text-gray-600 mb-2">Try asking:</p>
          <div className="space-y-1.5">
            {suggestions.map((suggestion, idx) => (
              <div 
                key={idx}
                className="text-xs text-left bg-white border border-gray-200 rounded-md p-2 hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer"
              >
                💡 {suggestion}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
