import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RefreshButton from '../../components/RefreshButton';

describe('RefreshButton', () => {
  const mockOnClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render with default text', () => {
      render(<RefreshButton onClick={mockOnClick} />);
      expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });

    it('should have aria-label for accessibility', () => {
      render(<RefreshButton onClick={mockOnClick} />);
      expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Refresh');
    });
  });

  describe('Loading State', () => {
    it('should show loading text when isLoading is true', () => {
      render(<RefreshButton onClick={mockOnClick} isLoading />);
      expect(screen.getByText('Refreshing...')).toBeInTheDocument();
    });

    it('should be disabled when loading', () => {
      render(<RefreshButton onClick={mockOnClick} isLoading />);
      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('should have spinner animation when loading', () => {
      render(<RefreshButton onClick={mockOnClick} isLoading />);
      const svg = document.querySelector('svg');
      expect(svg).toHaveClass('animate-spin');
    });
  });

  describe('Disabled State', () => {
    it('should be disabled when disabled prop is true', () => {
      render(<RefreshButton onClick={mockOnClick} disabled />);
      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('should have disabled styling', () => {
      render(<RefreshButton onClick={mockOnClick} disabled />);
      expect(screen.getByRole('button')).toHaveClass('cursor-not-allowed');
    });
  });

  describe('Sizes', () => {
    it('should apply small size classes', () => {
      render(<RefreshButton onClick={mockOnClick} size="sm" />);
      expect(screen.getByRole('button')).toHaveClass('px-3', 'py-1.5', 'text-sm');
    });

    it('should apply medium size classes by default', () => {
      render(<RefreshButton onClick={mockOnClick} />);
      expect(screen.getByRole('button')).toHaveClass('px-4', 'py-2');
    });

    it('should apply large size classes', () => {
      render(<RefreshButton onClick={mockOnClick} size="lg" />);
      expect(screen.getByRole('button')).toHaveClass('px-5', 'py-2.5', 'text-base');
    });
  });

  describe('Interactions', () => {
    it('should call onClick when clicked', async () => {
      const user = userEvent.setup();
      render(<RefreshButton onClick={mockOnClick} />);
      
      await user.click(screen.getByRole('button'));
      expect(mockOnClick).toHaveBeenCalledTimes(1);
    });

    it('should not call onClick when disabled', async () => {
      const user = userEvent.setup();
      render(<RefreshButton onClick={mockOnClick} disabled />);
      
      await user.click(screen.getByRole('button'));
      expect(mockOnClick).not.toHaveBeenCalled();
    });

    it('should not call onClick when loading', async () => {
      const user = userEvent.setup();
      render(<RefreshButton onClick={mockOnClick} isLoading />);
      
      await user.click(screen.getByRole('button'));
      expect(mockOnClick).not.toHaveBeenCalled();
    });
  });

  describe('Custom className', () => {
    it('should apply custom className', () => {
      render(<RefreshButton onClick={mockOnClick} className="custom-class" />);
      expect(screen.getByRole('button')).toHaveClass('custom-class');
    });
  });
});
