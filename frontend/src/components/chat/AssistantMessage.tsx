import type { Message } from '../../types';
import SourceList from './SourceList';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChartRenderer from './ChartRenderer';
import { useState } from 'react';
import { chatService } from '../../services/chatService';

interface AssistantMessageProps {
  message: Message;
  onSuggestedQuestionClick?: (question: string) => void;
  onFeedback?: (messageId: string, rating: 'positive' | 'negative') => void;
  /** The original user query that prompted this response */
  userQuery?: string;
}

export default function AssistantMessage({ message, onSuggestedQuestionClick, onFeedback, userQuery }: AssistantMessageProps) {
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSqlExpanded, setIsSqlExpanded] = useState(false);
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(false);

  const handleFeedback = async (rating: 'positive' | 'negative') => {
    if (isSubmitting || feedback !== null) return;

    setIsSubmitting(true);
    setFeedback(rating);

    // Call parent callback
    onFeedback?.(message.id, rating);

    // Send feedback to Langfuse via backend API
    if (message.traceId) {
      try {
        await chatService.submitFeedback({
          trace_id: message.traceId,
          query: userQuery || message.content,
          rating: rating === 'positive' ? 1 : -1,
        });
        console.log(`Feedback submitted to Langfuse: trace_id=${message.traceId}, rating=${rating}`);
      } catch (error) {
        console.error('Failed to submit feedback to Langfuse:', error);
        // Don't revert UI state - feedback is still shown locally
      }
    } else {
      console.warn('No trace_id available for feedback submission');
    }

    setIsSubmitting(false);
  };

  return (
    <div className="flex gap-4">
      {/* Avatar */}
      <div className="flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm ring-1 ring-white/20">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>
      </div>

      <div className="flex-1 min-w-0">
        <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm relative group overflow-hidden">
          {/* Main Content */}
          <div className="prose prose-sm max-w-none prose-indigo prose-p:leading-relaxed prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-800">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ ...props }) => <h1 className="text-xl font-bold mb-4" {...props} />,
                h2: ({ ...props }) => <h2 className="text-lg font-bold mb-3" {...props} />,
                h3: ({ ...props }) => <h3 className="text-md font-bold mb-2" {...props} />,
                p: ({ ...props }) => <p className="mb-4 last:mb-0" {...props} />,
                ul: ({ ...props }) => <ul className="list-disc pl-5 mb-4" {...props} />,
                ol: ({ ...props }) => <ol className="list-decimal pl-5 mb-4" {...props} />,
                code: ({ className, children, ...props }) => {
                  const match = /language-(\w+)/.exec(className || '');
                  return match ? (
                    <div className="relative group/code">
                      <div className="absolute right-2 top-2 text-[10px] text-gray-500 font-mono opacity-0 group-hover/code:opacity-100 transition-opacity">
                        {match[1]}
                      </div>
                      <code className="block bg-gray-900 text-gray-100 p-4 rounded-xl overflow-x-auto text-[11px] font-mono leading-relaxed" {...props}>
                        {children}
                      </code>
                    </div>
                  ) : (
                    <code className="bg-gray-100 text-indigo-600 px-1.5 py-0.5 rounded-md text-[11px] font-mono border border-gray-200/50" {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Render chart if present */}
          {message.chartData && <ChartRenderer chartData={message.chartData} />}

          {/* QA Debug Intelligence Section */}
          {message.qaDebug && (
            <div className="mt-4 bg-amber-50/50 border border-amber-200/50 rounded-xl p-3.5 shadow-sm">
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-amber-200/50">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-amber-100 rounded-lg">
                    <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                  </div>
                  <h4 className="text-xs font-bold text-amber-900 uppercase tracking-widest">QA Debug Intelligence</h4>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-amber-600 font-mono font-medium">
                    {(message.qaDebug.processing_time_ms / 1000).toFixed(2)}s
                  </span>
                </div>
              </div>

              {/* Sub-section: Reasoning Steps */}
              {message.qaDebug.reasoning_steps && message.qaDebug.reasoning_steps.length > 0 && (
                <div className="mb-3">
                  <button
                    onClick={() => setIsReasoningExpanded(!isReasoningExpanded)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-amber-100 transition-colors w-full text-left"
                  >
                    <div className={`transition-transform duration-200 ${isReasoningExpanded ? 'rotate-90' : ''}`}>
                      <svg className="w-3 h-3 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                    <span className="text-[10px] font-semibold text-amber-800 uppercase tracking-wider">
                      {isReasoningExpanded ? 'Hide' : 'Show'} Thought Process ({message.qaDebug.reasoning_steps.length})
                    </span>
                  </button>

                  {isReasoningExpanded && (
                    <div className="mt-2 ml-1 pl-3 border-l-2 border-amber-200 space-y-3">
                      {message.qaDebug.reasoning_steps.map((step, idx) => (
                        <div key={idx} className="relative">
                          <div className="flex items-center gap-2 mb-1">
                            <div className="w-4 h-4 rounded-full bg-amber-100 flex items-center justify-center text-amber-600">
                              <span className="text-[8px] font-bold">{idx + 1}</span>
                            </div>
                            <span className="text-[10px] font-mono font-bold text-amber-500 uppercase">
                              {step.tool.replace(/_/g, ' ')}
                            </span>
                          </div>
                          {step.thought && (
                            <div className="mb-2 text-[10px] text-amber-800 leading-relaxed bg-amber-100/30 p-2 rounded italic border-l-2 border-amber-300">
                              {step.thought}
                            </div>
                          )}
                          <div className="pl-0 space-y-1">
                            <div className="text-[10px] bg-white/50 p-1.5 rounded border border-amber-100/50">
                              <span className="font-semibold text-amber-400 block mb-0.5 uppercase text-[7px]">Action Input:</span>
                              <span className="text-amber-900 italic font-mono">"{step.input}"</span>
                            </div>
                            {step.output && (
                              <div className="text-[10px] bg-amber-200/20 p-1.5 rounded border border-amber-100/50">
                                <span className="font-semibold text-amber-400 block mb-0.5 uppercase text-[7px]">Output Preview:</span>
                                <div className="text-amber-800 line-clamp-3 italic">
                                  {step.output}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Sub-section: SQL Query */}
              {message.qaDebug.sql_query && (
                <div className="mb-3">
                  <button
                    onClick={() => setIsSqlExpanded(!isSqlExpanded)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-amber-100 transition-colors w-full text-left"
                  >
                    <div className={`transition-transform duration-200 ${isSqlExpanded ? 'rotate-90' : ''}`}>
                      <svg className="w-3 h-3 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                    <span className="text-[10px] font-semibold text-amber-800 uppercase tracking-wider">
                      {isSqlExpanded ? 'Hide' : 'Show'} SQL Query
                    </span>
                  </button>

                  {isSqlExpanded && (
                    <div className="mt-2 ml-1 pl-3 border-l-2 border-amber-200">
                      <pre className="text-[10px] bg-gray-900 text-gray-100 p-2.5 rounded-md overflow-x-auto font-mono border border-gray-800 shadow-inner">
                        {message.qaDebug.sql_query}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Performance & Config Metadata */}
              <div className="mt-4 pt-3 border-t border-amber-200/50 flex flex-wrap gap-x-6 gap-y-2">
                <div className="flex flex-col">
                  <span className="text-[8px] uppercase font-bold text-amber-500/70">Latency</span>
                  <span className="text-[10px] text-amber-600 font-mono font-medium">
                    {(message.qaDebug.processing_time_ms / 1000).toFixed(2)}s
                  </span>
                </div>
                {message.qaDebug.agent_config && (
                  <>
                    <div className="flex flex-col">
                      <span className="text-[8px] uppercase font-bold text-amber-500/70">Model</span>
                      <span className="text-[10px] font-mono text-amber-900">{message.qaDebug.agent_config.model}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[8px] uppercase font-bold text-amber-500/70">Intent</span>
                      <span className="text-[10px] font-mono text-amber-900 font-bold uppercase">{message.qaDebug.agent_config.intent}</span>
                    </div>
                  </>
                )}
                {message.qaDebug.trace_url && (
                  <div className="flex flex-col ml-auto">
                    <a
                      href={message.qaDebug.trace_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[9px] bg-amber-600 text-white px-2.5 py-1 rounded hover:bg-amber-700 transition-colors flex items-center gap-1 font-bold shadow-sm"
                    >
                      <span>VIEW TRACE</span>
                      <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Render sources */}
          {message.sources && message.sources.length > 0 && (
            <div className="mt-4">
              <SourceList sources={message.sources} />
            </div>
          )}

          {/* Render suggested questions */}
          {message.suggestedQuestions && message.suggestedQuestions.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Suggested Questions</p>
              <div className="flex flex-wrap gap-2">
                {message.suggestedQuestions.map((question: string, idx: number) => (
                  <button
                    key={idx}
                    onClick={() => onSuggestedQuestionClick?.(question)}
                    className="text-[11px] font-medium bg-indigo-50 text-indigo-700 px-3 py-1.5 rounded-full border border-indigo-100 hover:bg-indigo-600 hover:text-white hover:border-indigo-600 transition-all duration-200"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Feedback buttons */}
          <div className="mt-6 pt-4 border-t border-gray-100 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-medium text-gray-500">Was this helpful?</span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleFeedback('positive')}
                  disabled={feedback !== null || isSubmitting}
                  className={`p-1.5 rounded-lg transition-all ${feedback === 'positive'
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
                  disabled={feedback !== null || isSubmitting}
                  className={`p-1.5 rounded-lg transition-all ${feedback === 'negative'
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
                <span className="text-[11px] font-medium text-gray-500 italic">
                  {isSubmitting ? 'Submitting...' : 'Thank you!'}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
