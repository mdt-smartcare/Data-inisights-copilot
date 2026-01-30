import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider, useToast } from '../../components/Toast';

// Test component to trigger toasts
function ToastTrigger() {
  const { success, error, info, warning, showToast } = useToast();

  return (
    <div>
      <button onClick={() => success('Success title', 'Success message')}>
        Show Success
      </button>
      <button onClick={() => error('Error title', 'Error message')}>
        Show Error
      </button>
      <button onClick={() => info('Info title', 'Info message')}>Show Info</button>
      <button onClick={() => warning('Warning title', 'Warning message')}>
        Show Warning
      </button>
      <button
        onClick={() =>
          showToast({
            type: 'success',
            title: 'Custom Toast',
            message: 'Custom message',
            duration: 10000,
            action: {
              label: 'Undo',
              onClick: vi.fn(),
            },
          })
        }
      >
        Show Custom
      </button>
    </div>
  );
}

const renderWithToastProvider = () => {
  return render(
    <ToastProvider>
      <ToastTrigger />
    </ToastProvider>
  );
};

describe('Toast', () => {
  describe('ToastProvider', () => {
    it('should render children', () => {
      render(
        <ToastProvider>
          <div data-testid="child">Child content</div>
        </ToastProvider>
      );
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });

    it('should render toast container', () => {
      render(
        <ToastProvider>
          <div>Content</div>
        </ToastProvider>
      );
      expect(document.querySelector('.toast-container')).toBeInTheDocument();
    });
  });

  describe('useToast hook', () => {
    it('should throw error when used outside ToastProvider', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const InvalidComponent = () => {
        useToast();
        return null;
      };

      expect(() => render(<InvalidComponent />)).toThrow(
        'useToast must be used within a ToastProvider'
      );

      consoleSpy.mockRestore();
    });
  });

  describe('Toast Types', () => {
    it('should show success toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Success'));

      await waitFor(() => {
        expect(screen.getByText('Success title')).toBeInTheDocument();
        expect(screen.getByText('Success message')).toBeInTheDocument();
        expect(document.querySelector('.toast--success')).toBeInTheDocument();
      });
    });

    it('should show error toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Error'));

      await waitFor(() => {
        expect(screen.getByText('Error title')).toBeInTheDocument();
        expect(document.querySelector('.toast--error')).toBeInTheDocument();
      });
    });

    it('should show info toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Info'));

      await waitFor(() => {
        expect(screen.getByText('Info title')).toBeInTheDocument();
        expect(document.querySelector('.toast--info')).toBeInTheDocument();
      });
    });

    it('should show warning toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Warning'));

      await waitFor(() => {
        expect(screen.getByText('Warning title')).toBeInTheDocument();
        expect(document.querySelector('.toast--warning')).toBeInTheDocument();
      });
    });
  });

  describe('Toast Auto-dismiss', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should auto-dismiss after default duration', async () => {
      renderWithToastProvider();

      // Use fireEvent instead of userEvent with fake timers
      const button = screen.getByText('Show Success');
      await act(async () => {
        button.click();
      });
      
      expect(screen.getByText('Success title')).toBeInTheDocument();

      // Fast forward past the default duration (5000ms) + exit animation (300ms)
      await act(async () => {
        vi.advanceTimersByTime(5300);
      });

      expect(screen.queryByText('Success title')).not.toBeInTheDocument();
    });

    it('should have longer duration for error toasts', async () => {
      renderWithToastProvider();

      const button = screen.getByText('Show Error');
      await act(async () => {
        button.click();
      });
      
      expect(screen.getByText('Error title')).toBeInTheDocument();

      // Error toasts have 8000ms duration
      await act(async () => {
        vi.advanceTimersByTime(5000); // Still visible after default duration
      });

      expect(screen.getByText('Error title')).toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(3300); // Total 8300ms
      });

      expect(screen.queryByText('Error title')).not.toBeInTheDocument();
    });
  });

  describe('Toast Manual Close', () => {
    it('should close when close button is clicked', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Success'));
      
      await waitFor(() => {
        expect(screen.getByText('Success title')).toBeInTheDocument();
      });

      const closeButton = screen.getByLabelText('Close');
      await user.click(closeButton);

      await waitFor(() => {
        expect(screen.queryByText('Success title')).not.toBeInTheDocument();
      }, { timeout: 1000 });
    });
  });

  describe('Toast Action', () => {
    it('should render action button when provided', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Custom'));

      await waitFor(() => {
        expect(screen.getByText('Undo')).toBeInTheDocument();
      });
    });
  });

  describe('Multiple Toasts', () => {
    it('should support multiple toasts at once', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Success'));
      await user.click(screen.getByText('Show Error'));
      await user.click(screen.getByText('Show Info'));

      await waitFor(() => {
        expect(screen.getByText('Success title')).toBeInTheDocument();
        expect(screen.getByText('Error title')).toBeInTheDocument();
        expect(screen.getByText('Info title')).toBeInTheDocument();
      });
    });
  });

  describe('Toast Icons', () => {
    it('should display correct icon for success toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Success'));

      await waitFor(() => {
        const toast = document.querySelector('.toast--success');
        expect(toast?.querySelector('.toast__icon')).toHaveTextContent('✓');
      });
    });

    it('should display correct icon for error toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Error'));

      await waitFor(() => {
        const toast = document.querySelector('.toast--error');
        expect(toast?.querySelector('.toast__icon')).toHaveTextContent('✕');
      });
    });

    it('should display correct icon for info toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Info'));

      await waitFor(() => {
        const toast = document.querySelector('.toast--info');
        expect(toast?.querySelector('.toast__icon')).toHaveTextContent('ℹ');
      });
    });

    it('should display correct icon for warning toast', async () => {
      const user = userEvent.setup();
      renderWithToastProvider();

      await user.click(screen.getByText('Show Warning'));

      await waitFor(() => {
        const toast = document.querySelector('.toast--warning');
        expect(toast?.querySelector('.toast__icon')).toHaveTextContent('⚠');
      });
    });
  });
});
