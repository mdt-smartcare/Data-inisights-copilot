import type { Message } from '../../types';

interface UserMessageProps {
  message: Message;
}

export default function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end animate-fadeSlideUp">
      <div className="max-w-2xl px-3 py-2 rounded-lg text-sm bg-blue-600 text-white shadow-sm">
        <p className="whitespace-pre-wrap break-words leading-relaxed">
          {message.content}
        </p>

        <div className="text-[10px] mt-1.5 text-blue-100">
          {message.timestamp.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
          })}
        </div>
      </div>
    </div>
  );
}
