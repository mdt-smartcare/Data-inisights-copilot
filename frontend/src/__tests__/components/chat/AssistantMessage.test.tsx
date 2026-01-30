import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AssistantMessage from '../../../components/chat/AssistantMessage';
import type { Message } from '../../../types';

// Mock ReactMarkdown to simplify testing
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}));

vi.mock('remark-gfm', () => ({
  default: () => {},
}));

// Mock ChartRenderer
vi.mock('../../../components/chat/ChartRenderer', () => ({
  default: ({ chartData }: { chartData: any }) => (
    <div data-testid="chart-renderer">Chart: {chartData.title}</div>
  ),
}));

describe('AssistantMessage', () => {
  const createMessage = (overrides: Partial<Message> = {}): Message => ({
    id: '1',
    role: 'assistant',
    content: 'This is a test response',
    timestamp: new Date('2024-01-15T10:30:00'),
    ...overrides,
  });

  describe('Basic Rendering', () => {
    it('should render the message content', () => {
      render(<AssistantMessage message={createMessage()} />);
      expect(screen.getByText('This is a test response')).toBeInTheDocument();
    });

    it('should render the AI avatar', () => {
      render(<AssistantMessage message={createMessage()} />);
      expect(screen.getByText('AI')).toBeInTheDocument();
    });

    it('should render the timestamp', () => {
      render(<AssistantMessage message={createMessage()} />);
      expect(screen.getByText(/10:30/)).toBeInTheDocument();
    });
  });

  describe('SQL Query', () => {
    it('should render SQL query when present', () => {
      const message = createMessage({ sqlQuery: 'SELECT * FROM patients' });
      render(<AssistantMessage message={message} />);
      expect(screen.getByText('SQL Query')).toBeInTheDocument();
      expect(screen.getByText('SELECT * FROM patients')).toBeInTheDocument();
    });

    it('should not render SQL section when no query', () => {
      render(<AssistantMessage message={createMessage()} />);
      expect(screen.queryByText('SQL Query')).not.toBeInTheDocument();
    });
  });

  describe('Suggested Questions', () => {
    it('should render suggested questions when present', () => {
      const message = createMessage({
        suggestedQuestions: ['Question 1', 'Question 2'],
      });
      render(<AssistantMessage message={message} />);
      expect(screen.getByText('Follow-up questions:')).toBeInTheDocument();
      expect(screen.getByText('Question 1')).toBeInTheDocument();
      expect(screen.getByText('Question 2')).toBeInTheDocument();
    });

    it('should call onSuggestedQuestionClick when clicked', async () => {
      const user = userEvent.setup();
      const onSuggestedQuestionClick = vi.fn();
      const message = createMessage({ suggestedQuestions: ['Click me'] });
      
      render(
        <AssistantMessage
          message={message}
          onSuggestedQuestionClick={onSuggestedQuestionClick}
        />
      );
      
      await user.click(screen.getByText('Click me'));
      expect(onSuggestedQuestionClick).toHaveBeenCalledWith('Click me');
    });

    it('should not render suggested questions section when empty', () => {
      render(<AssistantMessage message={createMessage({ suggestedQuestions: [] })} />);
      expect(screen.queryByText('Follow-up questions:')).not.toBeInTheDocument();
    });
  });

  describe('Chart Data', () => {
    it('should render chart when chartData is present', () => {
      const message = createMessage({
        chartData: { title: 'Test Chart', type: 'bar', data: [] },
      });
      render(<AssistantMessage message={message} />);
      expect(screen.getByTestId('chart-renderer')).toBeInTheDocument();
    });
  });

  describe('Debug Info', () => {
    it('should render processing time when present', () => {
      const message = createMessage({ processingTime: 2.5 });
      render(<AssistantMessage message={message} />);
      expect(screen.getByText('⏱️ 2.50s')).toBeInTheDocument();
    });

    it('should render trace ID when present', () => {
      const message = createMessage({ traceId: 'abc123def456' });
      render(<AssistantMessage message={message} />);
      expect(screen.getByText('abc123de')).toBeInTheDocument(); // First 8 chars
    });
  });

  describe('Feedback', () => {
    it('should render feedback buttons', () => {
      render(<AssistantMessage message={createMessage()} />);
      expect(screen.getByText('Was this helpful?')).toBeInTheDocument();
      expect(screen.getByTitle('Good response')).toBeInTheDocument();
      expect(screen.getByTitle('Bad response')).toBeInTheDocument();
    });

    it('should call onFeedback with positive rating', async () => {
      const user = userEvent.setup();
      const onFeedback = vi.fn();
      render(<AssistantMessage message={createMessage()} onFeedback={onFeedback} />);
      
      await user.click(screen.getByTitle('Good response'));
      expect(onFeedback).toHaveBeenCalledWith('1', 'positive');
    });

    it('should call onFeedback with negative rating', async () => {
      const user = userEvent.setup();
      const onFeedback = vi.fn();
      render(<AssistantMessage message={createMessage()} onFeedback={onFeedback} />);
      
      await user.click(screen.getByTitle('Bad response'));
      expect(onFeedback).toHaveBeenCalledWith('1', 'negative');
    });

    it('should show thank you message after feedback', async () => {
      const user = userEvent.setup();
      render(<AssistantMessage message={createMessage()} onFeedback={vi.fn()} />);
      
      await user.click(screen.getByTitle('Good response'));
      expect(screen.getByText('Thank you for your feedback!')).toBeInTheDocument();
    });

    it('should disable buttons after feedback', async () => {
      const user = userEvent.setup();
      render(<AssistantMessage message={createMessage()} onFeedback={vi.fn()} />);
      
      await user.click(screen.getByTitle('Good response'));
      expect(screen.getByTitle('Good response')).toBeDisabled();
      expect(screen.getByTitle('Bad response')).toBeDisabled();
    });
  });
});
