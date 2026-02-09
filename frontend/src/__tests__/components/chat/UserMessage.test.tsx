import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import UserMessage from '../../../components/chat/UserMessage';
import type { Message } from '../../../types';

describe('UserMessage', () => {
  const createMessage = (overrides: Partial<Message> = {}): Message => ({
    id: 'msg-1',
    role: 'user',
    content: 'Test message content',
    timestamp: new Date('2025-01-30T10:30:00'),
    ...overrides,
  });

  describe('Rendering', () => {
    it('should render message content', () => {
      render(<UserMessage message={createMessage()} />);
      expect(screen.getByText('Test message content')).toBeInTheDocument();
    });

    it('should render timestamp', () => {
      const message = createMessage({ timestamp: new Date('2025-01-30T14:30:00') });
      render(<UserMessage message={message} />);
      // Timestamp format may vary by locale, just check it exists
      expect(document.querySelector('.text-gray-400')).toBeInTheDocument();
    });

    it('should display user initial from username', () => {
      render(<UserMessage message={createMessage()} username="JohnDoe" />);
      expect(screen.getByText('J')).toBeInTheDocument();
    });

    it('should display uppercase initial', () => {
      render(<UserMessage message={createMessage()} username="john" />);
      expect(screen.getByText('J')).toBeInTheDocument();
    });

    it('should display default initial when no username', () => {
      render(<UserMessage message={createMessage()} />);
      expect(screen.getByText('U')).toBeInTheDocument();
    });

    it('should display default initial for empty username', () => {
      render(<UserMessage message={createMessage()} username="" />);
      expect(screen.getByText('U')).toBeInTheDocument();
    });
  });

  describe('Styling', () => {
    it('should have blue background for message bubble', () => {
      render(<UserMessage message={createMessage()} />);
      const bubble = screen.getByText('Test message content').closest('div');
      expect(bubble).toHaveClass('bg-blue-600');
    });

    it('should have white text color', () => {
      render(<UserMessage message={createMessage()} />);
      const bubble = screen.getByText('Test message content').closest('div');
      expect(bubble).toHaveClass('text-white');
    });

    it('should be right-aligned', () => {
      const { container } = render(<UserMessage message={createMessage()} />);
      const wrapper = container.firstChild;
      expect(wrapper).toHaveClass('justify-end');
    });
  });

  describe('Long Content', () => {
    it('should preserve whitespace in message', () => {
      const message = createMessage({
        content: 'Line 1\nLine 2\nLine 3',
      });
      render(<UserMessage message={message} />);
      const paragraph = screen.getByText(/Line 1/);
      expect(paragraph).toHaveClass('whitespace-pre-wrap');
    });

    it('should break long words', () => {
      const message = createMessage({
        content: 'A very long word: supercalifragilisticexpialidocious',
      });
      render(<UserMessage message={message} />);
      const paragraph = screen.getByText(/supercalifragilisticexpialidocious/);
      expect(paragraph).toHaveClass('break-words');
    });
  });

  describe('Animation', () => {
    it('should have fade animation class', () => {
      const { container } = render(<UserMessage message={createMessage()} />);
      expect(container.firstChild).toHaveClass('animate-fadeSlideUp');
    });
  });

  describe('Avatar', () => {
    it('should render avatar with gradient background', () => {
      render(<UserMessage message={createMessage()} username="Alice" />);
      const avatar = screen.getByText('A').closest('div');
      expect(avatar).toHaveClass('bg-gradient-to-br', 'from-blue-500', 'to-blue-600');
    });

    it('should render avatar as circular', () => {
      render(<UserMessage message={createMessage()} username="Bob" />);
      const avatar = screen.getByText('B').closest('div');
      expect(avatar).toHaveClass('rounded-full');
    });
  });
});
