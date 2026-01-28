import type { Message } from '../../types';
import SourceList from './SourceList';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChartRenderer from './ChartRenderer';
import { useState } from 'react';

interface AssistantMessageProps {
  message: Message;
  onSuggestedQuestionClick?: (question: string) => void;
  onFeedback?: (messageId: string, rating: 'positive' | 'negative') => void;
}

export default function AssistantMessage({ message, onSuggestedQuestionClick, onFeedback }: AssistantMessageProps) {
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null);

  const handleFeedback = (rating: 'positive' | 'negative') => {
    setFeedback(rating);
    onFeedback?.(message.id, rating);
  };

  return (
    <div className="flex justify-start w-full animate-fadeSlideUp">
      <div className="w-full">
        <div className="flex items-start gap-2 mb-1">
          <div className="flex-shrink-0 w-5 h-5 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-[10px] font-bold">
            AI
          </div>
          <div className="text-[10px] text-gray-400">
            {message.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </div>
        </div>

        <div className="pl-7">
          <div className="prose prose-sm max-w-none text-gray-900">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ node, ...props }) => <h1 className="text-base font-bold mt-2 mb-1" {...props} />,
                h2: ({ node, ...props }) => <h2 className="text-sm font-bold mt-2 mb-1" {...props} />,
                h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mt-1.5 mb-0.5" {...props} />,
                p: ({ node, ...props }) => <p className="my-1 leading-relaxed" {...props} />,
                ul: ({ node, ...props }) => <ul className="list-disc list-inside my-1 space-y-0.5" {...props} />,
                ol: ({ node, ...props }) => <ol className="list-decimal list-inside my-1 space-y-0.5" {...props} />,
                li: ({ node, ...props }) => <li className="my-0.5" {...props} />,
                code: ({ node, className, children, ...props }) => {
                  const match = /language-(\w+)/.exec(className || '');
                  const isInline = !match;
                  return isInline ? (
                    <code className="bg-gray-200 px-1 py-0.5 rounded text-xs font-mono" {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className="block bg-gray-100 p-2 rounded my-1 text-xs font-mono overflow-x-auto" {...props}>
                      {children}
                    </code>
                  );
                },
                pre: ({ node, ...props }) => <pre className="my-1" {...props} />,
                blockquote: ({ node, ...props }) => (
                  <blockquote className="border-l-2 border-gray-300 pl-2 my-1 italic" {...props} />
                ),
                a: ({ node, ...props }) => (
                  <a className="text-blue-600 hover:text-blue-700 underline" target="_blank" rel="noopener noreferrer" {...props} />
                ),
                table: ({ node, ...props }) => (
                  <div className="overflow-x-auto my-1">
                    <table className="min-w-full divide-y divide-gray-200 text-xs" {...props} />
                  </div>
                ),
                th: ({ node, ...props }) => (
                  <th className="px-2 py-1 bg-gray-100 font-semibold text-left" {...props} />
                ),
                td: ({ node, ...props }) => (
                  <td className="px-2 py-1 border-t border-gray-200" {...props} />
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Render chart if present */}
          {message.chartData && <ChartRenderer chartData={message.chartData} />}

          {/* Render SQL query if present */}
          {message.sqlQuery && (
            <div className="my-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
                <span className="text-xs font-semibold text-gray-700">SQL Query</span>
              </div>
              <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto font-mono text-gray-800">
                {message.sqlQuery}
              </pre>
            </div>
          )}

          {/* Render sources */}
          {message.sources && <SourceList sources={message.sources} />}

          {/* Render suggested questions */}
          {message.suggestedQuestions && message.suggestedQuestions.length > 0 && (
            <div className="my-3">
              <p className="text-xs font-semibold text-gray-700 mb-2">💡 Follow-up questions:</p>
              <div className="space-y-1.5">
                {message.suggestedQuestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSuggestedQuestionClick?.(question)}
                    className="w-full text-left text-xs bg-white border border-gray-200 hover:border-blue-400 hover:bg-blue-50 rounded-md p-2.5 transition-all group"
                  >
                    <span className="text-gray-700 group-hover:text-blue-700">{question}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Debug info (trace_id and processing_time) */}
          {(message.traceId || message.processingTime) && (
            <div className="mt-2 text-[10px] text-gray-400 flex items-center gap-3">
              {message.processingTime && (
                <span>⏱️ {message.processingTime.toFixed(2)}s</span>
              )}
              {message.traceId && (
                <span title="Trace ID">🔍 {message.traceId.substring(0, 8)}</span>
              )}
            </div>
          )}

          {/* Feedback buttons */}
          <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-3">
            <span className="text-[10px] text-gray-500">Was this helpful?</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => handleFeedback('positive')}
                disabled={feedback !== null}
                className={`p-1.5 rounded transition-all ${feedback === 'positive'
                    ? 'bg-green-100 text-green-600'
                    : 'hover:bg-gray-100 text-gray-400 hover:text-green-600'
                  } disabled:cursor-not-allowed`}
                title="Good response"
              >
                <svg className="w-4 h-4" fill={feedback === 'positive' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
              </button>
              <button
                onClick={() => handleFeedback('negative')}
                disabled={feedback !== null}
                className={`p-1.5 rounded transition-all ${feedback === 'negative'
                    ? 'bg-red-100 text-red-600'
                    : 'hover:bg-gray-100 text-gray-400 hover:text-red-600'
                  } disabled:cursor-not-allowed`}
                title="Bad response"
              >
                <svg className="w-4 h-4" fill={feedback === 'negative' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" />
                </svg>
              </button>
            </div>
            {feedback && (
              <span className="text-[10px] text-gray-500 italic">Thank you for your feedback!</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
