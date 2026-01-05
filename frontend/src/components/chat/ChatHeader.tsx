import { Link } from 'react-router-dom';

interface ChatHeaderProps {
  title?: string;
  showBackButton?: boolean;
}

export default function ChatHeader({ 
  title = 'FHIR RAG Chat',
  showBackButton = false 
}: ChatHeaderProps) {
  return (
    <header className="bg-white shadow-sm border-b border-gray-200 px-4 py-2.5">
      <div className="flex items-center gap-3">
        {showBackButton && (
          <Link 
            to="/" 
            className="text-gray-600 hover:text-gray-900 transition-colors"
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
                d="M10 19l-7-7m0 0l7-7m-7 7h18" 
              />
            </svg>
          </Link>
        )}
        <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
      </div>
    </header>
  );
}
