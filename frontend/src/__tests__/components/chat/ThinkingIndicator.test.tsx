import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import ThinkingIndicator from '../../../components/chat/ThinkingIndicator';

describe('ThinkingIndicator', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should render initial state', () => {
    render(<ThinkingIndicator />);
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.getByText(/analyzing query/i)).toBeInTheDocument();
  });

  it('should show progress percentage', () => {
    render(<ThinkingIndicator />);
    expect(screen.getByText(/0%/)).toBeInTheDocument();
  });

  it('should update progress over time', async () => {
    render(<ThinkingIndicator estimatedTime={5000} />);
    
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    
    // Progress should be > 0 after 1 second
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });

  it('should show elapsed time', async () => {
    render(<ThinkingIndicator />);
    
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    
    expect(screen.getByText(/2s/)).toBeInTheDocument();
  });

  it('should transition through stages', async () => {
    render(<ThinkingIndicator estimatedTime={10000} />);
    
    // Advance time to see stage changes
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    
    // Should be past the first stage
    const text = screen.getByText(/searching|processing|generating|almost/i);
    expect(text).toBeInTheDocument();
  });

  it('should have stage indicator dots', () => {
    render(<ThinkingIndicator />);
    // Should have 4 stage dots
    const container = document.querySelector('.flex.items-center.gap-1\\.5');
    expect(container?.querySelectorAll('div').length).toBeGreaterThanOrEqual(4);
  });

  it('should cap progress at 95%', async () => {
    render(<ThinkingIndicator estimatedTime={1000} />);
    
    await act(async () => {
      vi.advanceTimersByTime(5000); // Well past estimated time
    });
    
    expect(screen.getByText(/95%/)).toBeInTheDocument();
  });
});
