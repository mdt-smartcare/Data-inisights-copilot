import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LoadingIndicator from '../../../components/chat/LoadingIndicator';

describe('LoadingIndicator', () => {
  it('should render with default text', () => {
    render(<LoadingIndicator />);
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('should render with custom text', () => {
    render(<LoadingIndicator text="Processing..." />);
    expect(screen.getByText('Processing...')).toBeInTheDocument();
  });

  it('should render animated dots', () => {
    const { container } = render(<LoadingIndicator />);
    const dots = container.querySelectorAll('.animate-bounce');
    expect(dots.length).toBe(3);
  });

  it('should have staggered animation delays', () => {
    const { container } = render(<LoadingIndicator />);
    const dots = container.querySelectorAll('.animate-bounce');
    expect(dots[0]).toHaveStyle({ animationDelay: '0ms' });
    expect(dots[1]).toHaveStyle({ animationDelay: '150ms' });
    expect(dots[2]).toHaveStyle({ animationDelay: '300ms' });
  });
});
