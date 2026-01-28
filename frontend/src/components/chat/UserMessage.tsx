import type { Message } from '../../types';

interface UserMessageProps {
  message: Message;
}

export default function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end animate-fadeSlideUp">
      <div className="flex flex-col items-end max-w-2xl">
        {/* Header with timestamp and avatar */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-gray-400">
            {message.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </span>
          <div className="flex-shrink-0 w-5 h-5 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-[10px] font-bold">
            U
          </div>
        </div>

        {/* Message bubble */}
        <div className="px-3 py-2 rounded-lg text-sm bg-blue-600 text-white shadow-sm">
          <p className="whitespace-pre-wrap break-words leading-relaxed">
            {message.content}
          </p>
        </div>
      </div>
    </div>
  );
}
