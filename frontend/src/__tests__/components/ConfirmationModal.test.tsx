import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfirmationModal from '../../components/ConfirmationModal';

describe('ConfirmationModal', () => {
  const defaultProps = {
    show: true,
    title: 'Confirm Action',
    message: 'Are you sure you want to proceed?',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Visibility', () => {
    it('should not render when show is false', () => {
      render(<ConfirmationModal {...defaultProps} show={false} />);
      expect(screen.queryByText('Confirm Action')).not.toBeInTheDocument();
    });

    it('should render when show is true', () => {
      render(<ConfirmationModal {...defaultProps} />);
      expect(screen.getByText('Confirm Action')).toBeInTheDocument();
    });
  });

  describe('Content', () => {
    it('should display title', () => {
      render(<ConfirmationModal {...defaultProps} />);
      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Confirm Action');
    });

    it('should display message', () => {
      render(<ConfirmationModal {...defaultProps} />);
      expect(screen.getByText('Are you sure you want to proceed?')).toBeInTheDocument();
    });

    it('should display custom button text', () => {
      render(
        <ConfirmationModal
          {...defaultProps}
          confirmText="Delete"
          cancelText="Keep"
        />
      );
      expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Keep' })).toBeInTheDocument();
    });

    it('should display default button text', () => {
      render(<ConfirmationModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });
  });

  describe('Types', () => {
    it('should render danger type with correct styles', () => {
      render(<ConfirmationModal {...defaultProps} type="danger" />);
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton).toHaveClass('bg-red-600');
    });

    it('should render warning type with correct styles', () => {
      render(<ConfirmationModal {...defaultProps} type="warning" />);
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton).toHaveClass('bg-yellow-600');
    });

    it('should render info type with correct styles', () => {
      render(<ConfirmationModal {...defaultProps} type="info" />);
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton).toHaveClass('bg-blue-600');
    });
  });

  describe('User Interactions', () => {
    it('should call onConfirm when confirm button is clicked', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      render(<ConfirmationModal {...defaultProps} onConfirm={onConfirm} />);

      await user.click(screen.getByRole('button', { name: 'Confirm' }));
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('should call onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<ConfirmationModal {...defaultProps} onCancel={onCancel} />);

      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(onCancel).toHaveBeenCalledTimes(1);
    });
  });

  describe('Loading State', () => {
    it('should disable both buttons when loading', () => {
      render(<ConfirmationModal {...defaultProps} isLoading />);

      expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    });

    it('should show loading spinner on confirm button', () => {
      render(<ConfirmationModal {...defaultProps} isLoading />);

      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton.querySelector('svg')).toBeInTheDocument();
    });

    it('should not call callbacks when loading', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const onCancel = vi.fn();

      render(
        <ConfirmationModal
          {...defaultProps}
          onConfirm={onConfirm}
          onCancel={onCancel}
          isLoading
        />
      );

      await user.click(screen.getByRole('button', { name: 'Confirm' }));
      await user.click(screen.getByRole('button', { name: 'Cancel' }));

      expect(onConfirm).not.toHaveBeenCalled();
      expect(onCancel).not.toHaveBeenCalled();
    });
  });

  describe('Icons', () => {
    it('should display trash icon for danger type', () => {
      render(<ConfirmationModal {...defaultProps} type="danger" />);
      const iconContainer = document.querySelector('.bg-red-100');
      expect(iconContainer).toBeInTheDocument();
      expect(iconContainer?.querySelector('svg')).toBeInTheDocument();
    });

    it('should display warning icon for warning type', () => {
      render(<ConfirmationModal {...defaultProps} type="warning" />);
      const iconContainer = document.querySelector('.bg-yellow-100');
      expect(iconContainer).toBeInTheDocument();
    });

    it('should display info icon for info type', () => {
      render(<ConfirmationModal {...defaultProps} type="info" />);
      const iconContainer = document.querySelector('.bg-blue-100');
      expect(iconContainer).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper button types', () => {
      render(<ConfirmationModal {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      const cancelButton = screen.getByRole('button', { name: 'Cancel' });

      expect(confirmButton).toHaveAttribute('type', 'button');
      expect(cancelButton).toHaveAttribute('type', 'button');
    });
  });
});
