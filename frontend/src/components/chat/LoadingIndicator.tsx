interface LoadingIndicatorProps {
  text?: string;
}

export default function LoadingIndicator({ 
  text = 'Thinking...' 
}: LoadingIndicatorProps) {
  return (
    <div className="flex justify-start">
      <div className="bg-white px-3 py-2 rounded-md shadow-sm border border-gray-200">
        <div className="flex items-center gap-2">
          <div className="flex gap-0.5">
            <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
            <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
            <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
          </div>
          <span className="text-gray-600 text-xs">{text}</span>
        </div>
      </div>
    </div>
  );
}
