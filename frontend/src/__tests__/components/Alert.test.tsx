import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Alert from '../../components/Alert';

describe('Alert', () => {
  describe('Rendering', () => {
    it('should render with message', () => {
      render(<Alert type="info" message="Test message" />);
      expect(screen.getByRole('alert')).toHaveTextContent('Test message');
    });

    it('should render error type with correct styles', () => {
      render(<Alert type="error" message="Error message" />);
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('bg-red-50', 'border-red-400', 'text-red-700');
    });

    it('should render success type with correct styles', () => {
      render(<Alert type="success" message="Success message" />);
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('bg-green-50', 'border-green-400', 'text-green-700');
    });

    it('should render warning type with correct styles', () => {
      render(<Alert type="warning" message="Warning message" />);
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('bg-yellow-50', 'border-yellow-400', 'text-yellow-700');
    });

    it('should render info type with correct styles', () => {
      render(<Alert type="info" message="Info message" />);
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('bg-blue-50', 'border-blue-400', 'text-blue-700');
    });
  });

  describe('Icon', () => {
    it('should show icon by default', () => {
      render(<Alert type="error" message="Error" />);
      const alert = screen.getByRole('alert');
      expect(alert.querySelector('svg')).toBeInTheDocument();
    });

    it('should hide icon when showIcon is false', () => {
      render(<Alert type="error" message="Error" showIcon={false} />);
      const alert = screen.getByRole('alert');
      expect(alert.querySelector('svg')).not.toBeInTheDocument();
    });
  });

  describe('Dismiss Button', () => {
    it('should show dismiss button when onDismiss is provided', () => {
      render(<Alert type="info" message="Dismissible" onDismiss={() => {}} />);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('should call onDismiss when dismiss button is clicked', async () => {
      const user = userEvent.setup();
      const handleDismiss = vi.fn();
      render(<Alert type="info" message="Dismissible" onDismiss={handleDismiss} />);

      await user.click(screen.getByRole('button'));
      expect(handleDismiss).toHaveBeenCalledTimes(1);
    });

    it('should not show dismiss button when dismissible is false', () => {
      render(
        <Alert
          type="info"
          message="Not dismissible"
          onDismiss={() => {}}
          dismissible={false}
        />
      );
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });

    it('should not show dismiss button when onDismiss is not provided', () => {
      render(<Alert type="info" message="No dismiss handler" />);
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have role="alert"', () => {
      render(<Alert type="info" message="Accessible alert" />);
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should have aria-live="polite"', () => {
      render(<Alert type="info" message="Polite alert" />);
      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'polite');
    });
  });

  describe('Custom Styling', () => {
    it('should apply custom className', () => {
      render(<Alert type="info" message="Custom" className="custom-class" />);
      expect(screen.getByRole('alert')).toHaveClass('custom-class');
    });
  });
});
