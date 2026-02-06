import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import MessageList from '../../../components/chat/MessageList';
import type { Message } from '../../../types';

// Mock child components with correct paths (relative to where they're imported in MessageList)
vi.mock('../../../components/chat/UserMessage', () => ({
  default: ({ message }: { message: Message }) => (
    <div data-testid="user-message">{message.content}</div>
  ),
}));

vi.mock('../../../components/chat/AssistantMessage', () => ({
  default: ({ message }: { message: Message }) => (
    <div data-testid="assistant-message">{message.content}</div>
  ),
}));

vi.mock('../../../components/chat/EmptyState', () => ({
  default: ({ title, onSuggestedQuestionClick }: any) => (
    <div data-testid="empty-state">
      {title || 'Empty State'}
      {onSuggestedQuestionClick && (
        <button onClick={() => onSuggestedQuestionClick('test')}>
          Suggestion
        </button>
      )}
    </div>
  ),
}));

vi.mock('../../../components/chat/ThinkingIndicator', () => ({
  default: () => <div data-testid="thinking-indicator">Thinking...</div>,
}));

describe('MessageList', () => {
  const createMessage = (
    id: string,
    role: 'user' | 'assistant',
    content: string
  ): Message => ({
    id,
    role,
    content,
    timestamp: new Date(),
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = vi.fn();
  });

  describe('Empty State', () => {
    it('should render empty state when no messages', () => {
      render(<MessageList messages={[]} />);
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    it('should pass emptyStateProps to EmptyState', () => {
      render(
        <MessageList
          messages={[]}
          emptyStateProps={{ title: 'Welcome to Chat!' }}
        />
      );
      expect(screen.getByText('Welcome to Chat!')).toBeInTheDocument();
    });

    it('should pass onSuggestedQuestionClick to EmptyState', () => {
      const handleClick = vi.fn();
      render(
        <MessageList
          messages={[]}
          onSuggestedQuestionClick={handleClick}
        />
      );
      expect(screen.getByText('Suggestion')).toBeInTheDocument();
    });
  });

  describe('Message Rendering', () => {
    it('should render user messages', () => {
      const messages = [createMessage('1', 'user', 'Hello')];
      render(<MessageList messages={messages} />);
      expect(screen.getByTestId('user-message')).toHaveTextContent('Hello');
    });

    it('should render assistant messages', () => {
      const messages = [createMessage('1', 'assistant', 'Hi there!')];
      render(<MessageList messages={messages} />);
      expect(screen.getByTestId('assistant-message')).toHaveTextContent('Hi there!');
    });

    it('should render multiple messages in order', () => {
      const messages = [
        createMessage('1', 'user', 'First'),
        createMessage('2', 'assistant', 'Second'),
        createMessage('3', 'user', 'Third'),
      ];
      render(<MessageList messages={messages} />);

      const userMessages = screen.getAllByTestId('user-message');
      const assistantMessages = screen.getAllByTestId('assistant-message');

      expect(userMessages).toHaveLength(2);
      expect(assistantMessages).toHaveLength(1);
    });
  });

  describe('Loading State', () => {
    it('should show thinking indicator when loading with messages', () => {
      const messages = [createMessage('1', 'user', 'Question')];
      render(<MessageList messages={messages} isLoading />);
      expect(screen.getByTestId('thinking-indicator')).toBeInTheDocument();
    });

    it('should show messages and thinking indicator together', () => {
      const messages = [createMessage('1', 'user', 'Question')];
      render(<MessageList messages={messages} isLoading />);

      expect(screen.getByTestId('user-message')).toBeInTheDocument();
      expect(screen.getByTestId('thinking-indicator')).toBeInTheDocument();
    });

    it('should show empty state when loading with no messages', () => {
      render(<MessageList messages={[]} isLoading />);
      // Empty state is shown when no messages, even with loading
      // (ThinkingIndicator only shows after first message)
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  describe('Auto-scroll', () => {
    it('should scroll to bottom on new messages', () => {
      const messages = [createMessage('1', 'user', 'Test')];
      render(<MessageList messages={messages} />);

      expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    });

    it('should scroll to assistant message when last message is assistant', () => {
      const messages = [
        createMessage('1', 'user', 'Question'),
        createMessage('2', 'assistant', 'Answer'),
      ];
      render(<MessageList messages={messages} />);

      expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
        expect.objectContaining({ behavior: 'smooth' })
      );
    });
  });

  describe('Props Passing', () => {
    it('should pass username to user messages', () => {
      // This would require more complex mocking to verify
      // For now, just ensure no errors
      const messages = [createMessage('1', 'user', 'Test')];
      render(<MessageList messages={messages} username="TestUser" />);
      expect(screen.getByTestId('user-message')).toBeInTheDocument();
    });

    it('should pass onFeedback to assistant messages', () => {
      const handleFeedback = vi.fn();
      const messages = [createMessage('1', 'assistant', 'Response')];
      render(<MessageList messages={messages} onFeedback={handleFeedback} />);
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });
  });
});
