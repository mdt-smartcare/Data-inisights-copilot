import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatInput from '../../../components/chat/ChatInput';

describe('ChatInput', () => {
  const defaultProps = {
    onSendMessage: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render textarea', () => {
      render(<ChatInput {...defaultProps} />);
      expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument();
    });

    it('should render send button', () => {
      render(<ChatInput {...defaultProps} />);
      expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
    });

    it('should render character count', () => {
      render(<ChatInput {...defaultProps} maxLength={100} />);
      expect(screen.getByText('0/100')).toBeInTheDocument();
    });

    it('should render helper text', () => {
      render(<ChatInput {...defaultProps} />);
      expect(screen.getByText(/enter to send/i)).toBeInTheDocument();
      expect(screen.getByText(/shift\+enter for new line/i)).toBeInTheDocument();
    });

    it('should use custom placeholder', () => {
      render(<ChatInput {...defaultProps} placeholder="Ask a question..." />);
      expect(screen.getByPlaceholderText('Ask a question...')).toBeInTheDocument();
    });
  });

  describe('Text Input', () => {
    it('should update value when typing', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Hello world');

      expect(textarea).toHaveValue('Hello world');
    });

    it('should update character count when typing', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} maxLength={2000} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Hello');

      expect(screen.getByText('5/2000')).toBeInTheDocument();
    });

    it('should show warning when over character limit', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} maxLength={10} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'This is a very long message');

      expect(screen.getByText(/27\/10/)).toHaveClass('text-red-500');
    });
  });

  describe('Form Submission', () => {
    it('should call onSendMessage with trimmed input on submit', async () => {
      const user = userEvent.setup();
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, '  Hello world  ');
      await user.click(screen.getByRole('button', { name: /send/i }));

      expect(onSendMessage).toHaveBeenCalledWith('Hello world');
    });

    it('should clear input after submission', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      expect(textarea).toHaveValue('');
    });

    it('should not call onSendMessage with empty input', async () => {
      const user = userEvent.setup();
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);

      await user.click(screen.getByRole('button', { name: /send/i }));

      expect(onSendMessage).not.toHaveBeenCalled();
    });

    it('should not call onSendMessage with whitespace only', async () => {
      const user = userEvent.setup();
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, '   ');
      await user.click(screen.getByRole('button', { name: /send/i }));

      expect(onSendMessage).not.toHaveBeenCalled();
    });
  });

  describe('Keyboard Shortcuts', () => {
    it('should submit on Enter key', async () => {
      const user = userEvent.setup();
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Test message');
      await user.keyboard('{Enter}');

      expect(onSendMessage).toHaveBeenCalledWith('Test message');
    });

    it('should allow new line with Shift+Enter', async () => {
      const user = userEvent.setup();
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Line 1');
      await user.keyboard('{Shift>}{Enter}{/Shift}');
      await user.type(textarea, 'Line 2');

      expect(textarea).toHaveValue('Line 1\nLine 2');
      expect(onSendMessage).not.toHaveBeenCalled();
    });
  });

  describe('Disabled State', () => {
    it('should disable textarea when isDisabled is true', () => {
      render(<ChatInput {...defaultProps} isDisabled />);
      expect(screen.getByPlaceholderText(/type your message/i)).toBeDisabled();
    });

    it('should disable send button when isDisabled is true', () => {
      render(<ChatInput {...defaultProps} isDisabled />);
      expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    });

    it('should not submit when disabled', () => {
      const onSendMessage = vi.fn();
      render(<ChatInput {...defaultProps} onSendMessage={onSendMessage} isDisabled />);

      // Textarea is disabled, so we can't actually type
      // Just verify the button is disabled
      expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    });
  });

  describe('Send Button State', () => {
    it('should disable send button when input is empty', () => {
      render(<ChatInput {...defaultProps} />);
      expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    });

    it('should enable send button when input has content', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Hello');

      expect(screen.getByRole('button', { name: /send/i })).not.toBeDisabled();
    });

    it('should disable send button when over character limit', async () => {
      const user = userEvent.setup();
      render(<ChatInput {...defaultProps} maxLength={5} />);

      const textarea = screen.getByPlaceholderText(/type your message/i);
      await user.type(textarea, 'Hello World');

      expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    });
  });

  describe('Auto-resize', () => {
    it('should have minimum height', () => {
      render(<ChatInput {...defaultProps} />);
      const textarea = screen.getByPlaceholderText(/type your message/i);
      expect(textarea).toHaveStyle({ minHeight: '2.25rem' });
    });

    it('should have maximum height', () => {
      render(<ChatInput {...defaultProps} />);
      const textarea = screen.getByPlaceholderText(/type your message/i);
      expect(textarea).toHaveStyle({ maxHeight: '8rem' });
    });
  });

  describe('Accessibility', () => {
    it('should have accessible button title when enabled', () => {
      render(<ChatInput {...defaultProps} />);
      expect(screen.getByRole('button', { name: /send/i })).toHaveAttribute(
        'title',
        'Send message (Enter)'
      );
    });

    it('should have accessible button title when disabled', () => {
      render(<ChatInput {...defaultProps} isDisabled />);
      expect(screen.getByRole('button', { name: /send/i })).toHaveAttribute(
        'title',
        'Please wait...'
      );
    });
  });
});
