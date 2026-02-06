import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UsersPage from '../../pages/UsersPage';
import type { Mock } from 'vitest';

interface RefreshButtonProps {
  onClick: () => void;
  isLoading?: boolean;
}

interface AlertProps {
  type: string;
  message: string;
  onDismiss?: () => void;
}

interface ConfirmationModalProps {
  show: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
}

// Mock modules
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../utils/permissions', () => ({
  canManageUsers: vi.fn(),
  getRoleDisplayName: vi.fn((role: string) => {
    const names: Record<string, string> = {
      super_admin: 'Super Admin',
      editor: 'Editor',
      user: 'User',
    };
    return names[role] || role;
  }),
  ROLE_HIERARCHY: ['super_admin', 'editor', 'user'],
}));

vi.mock('../../components/chat', () => ({
  ChatHeader: ({ title }: { title: string }) => <div data-testid="chat-header">{title}</div>,
}));

vi.mock('../../components/RefreshButton', () => ({
  default: ({ onClick, isLoading }: RefreshButtonProps) => (
    <button data-testid="refresh-button" onClick={onClick} disabled={isLoading}>
      Refresh
    </button>
  ),
}));

vi.mock('../../components/Alert', () => ({
  default: ({ type, message, onDismiss }: AlertProps) => (
    <div data-testid={`alert-${type}`} role="alert">
      {message}
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}));

vi.mock('../../components/ConfirmationModal', () => ({
  default: ({ show, title, message, onConfirm, onCancel, confirmText }: ConfirmationModalProps) =>
    show ? (
      <div data-testid="confirmation-modal">
        <h2>{title}</h2>
        <p>{message}</p>
        <button data-testid="cancel-button" onClick={onCancel}>Cancel</button>
        <button data-testid="confirm-button" onClick={onConfirm}>{confirmText || 'Confirm'}</button>
      </div>
    ) : null,
}));

import { useAuth } from '../../contexts/AuthContext';
import { canManageUsers } from '../../utils/permissions';

const mockUsers = [
  {
    id: 1,
    username: 'admin',
    email: 'admin@example.com',
    full_name: 'System Admin',
    role: 'super_admin',
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    username: 'editor1',
    email: 'editor@example.com',
    full_name: 'Editor One',
    role: 'editor',
    is_active: true,
    created_at: '2024-01-10T00:00:00Z',
  },
  {
    id: 3,
    username: 'user1',
    email: 'user@example.com',
    full_name: 'Regular User',
    role: 'user',
    is_active: false,
    created_at: '2024-01-15T00:00:00Z',
  },
];

describe('UsersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock fetch
    global.fetch = vi.fn();
    
    // Default: user has access
    (useAuth as Mock).mockReturnValue({
      user: { id: 1, username: 'admin', role: 'super_admin' },
    });
    (canManageUsers as Mock).mockReturnValue(true);
    
    // Mock localStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPage = () => {
    return render(
      <MemoryRouter>
        <UsersPage />
      </MemoryRouter>
    );
  };

  describe('Access Control', () => {
    it('should show access denied for unauthorized users', async () => {
      (canManageUsers as Mock).mockReturnValue(false);
      
      renderPage();
      
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText(/don't have permission/)).toBeInTheDocument();
      expect(screen.getByText(/Only Super Admin/)).toBeInTheDocument();
    });

    it('should show page content for authorized users', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('User Management')).toBeInTheDocument();
      });
    });
  });

  describe('User List Display', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
    });

    it('should display all users', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('admin')).toBeInTheDocument();
        expect(screen.getByText('editor1')).toBeInTheDocument();
        expect(screen.getByText('user1')).toBeInTheDocument();
      });
    });

    it('should display user emails', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('admin@example.com')).toBeInTheDocument();
      });
    });

    it('should display role names', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Super Admin')).toBeInTheDocument();
        expect(screen.getByText('Editor')).toBeInTheDocument();
        // "User" appears in both the header column and as a role, so use getAllByText
        const userElements = screen.getAllByText('User');
        expect(userElements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('should show active/inactive status', async () => {
      renderPage();
      
      await waitFor(() => {
        // Should have active and inactive indicators
        const statusIndicators = screen.getAllByText(/active|inactive/i);
        expect(statusIndicators.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Add User', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
    });

    it('should show Add User button', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Add User')).toBeInTheDocument();
      });
    });

    it('should open add user form when button is clicked', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Add User')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Add User'));
      
      await waitFor(() => {
        expect(screen.getByPlaceholderText('jdoe')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('********')).toBeInTheDocument();
      });
    });

    it('should show validation error when username/password missing', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Add User')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Add User'));
      
      await waitFor(() => {
        expect(screen.getByText('Add New User')).toBeInTheDocument();
      });
      
      // Try to submit without filling form
      const createButton = screen.getByText('Create User');
      fireEvent.click(createButton);
      
      await waitFor(() => {
        expect(screen.getByText(/username and password are required/i)).toBeInTheDocument();
      });
    });

    it('should create user when form is submitted', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Add User')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Add User'));
      
      await waitFor(() => {
        expect(screen.getByPlaceholderText('jdoe')).toBeInTheDocument();
      });
      
      // Fill form
      fireEvent.change(screen.getByPlaceholderText('jdoe'), { target: { value: 'newuser' } });
      fireEvent.change(screen.getByPlaceholderText('********'), { target: { value: 'password123' } });
      
      // Mock create user response
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 4, username: 'newuser' }),
      }).mockResolvedValueOnce({
        ok: true,
        json: async () => [...mockUsers, { id: 4, username: 'newuser', role: 'user', is_active: true }],
      });
      
      const createButton = screen.getByText('Create User');
      fireEvent.click(createButton);
      
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/v1/users',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('newuser'),
          })
        );
      });
    });
  });

  describe('Edit User', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
    });

    it('should show edit option for users', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      // Find edit buttons
      const editButtons = screen.getAllByText('Edit');
      expect(editButtons.length).toBeGreaterThan(0);
    });

    it('should open edit form when edit button is clicked', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const editButtons = screen.getAllByText('Edit');
      fireEvent.click(editButtons[0]); // Edit editor user
      
      await waitFor(() => {
        // Edit form should show role dropdown
        expect(screen.getByLabelText(/role/i)).toBeInTheDocument();
      });
    });

    it('should save user changes', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const editButtons = screen.getAllByText('Edit');
      fireEvent.click(editButtons[0]); // Edit first editable user (editor1)
      
      // Mock update response
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockUsers[1], role: 'super_admin' }),
      }).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
      
      const saveButton = screen.getByText('Save Changes');
      fireEvent.click(saveButton);
      
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/v1/users/2'),
          expect.objectContaining({
            method: 'PATCH',
          })
        );
      });
    });
  });

  describe('Deactivate User', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
    });

    it('should show deactivate option for active users', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const deactivateButtons = screen.getAllByText('Deactivate');
      expect(deactivateButtons.length).toBeGreaterThan(0);
    });

    it('should show confirmation modal when deactivate is clicked', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const deactivateButtons = screen.getAllByText('Deactivate');
      fireEvent.click(deactivateButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
      });
    });

    it('should deactivate user after confirmation', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const deactivateButtons = screen.getAllByText('Deactivate');
      fireEvent.click(deactivateButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
      });
      
      // Mock delete response
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      }).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers.filter(u => u.id !== 2),
      });
      
      // Click confirm in modal
      const confirmButton = screen.getByTestId('confirm-button');
      fireEvent.click(confirmButton);
      
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/v1/users/'),
          expect.objectContaining({
            method: 'DELETE',
          })
        );
      });
    });

    it('should cancel deactivation when cancel is clicked', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
      
      const deactivateButtons = screen.getAllByText('Deactivate');
      fireEvent.click(deactivateButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByTestId('confirmation-modal')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByTestId('cancel-button'));
      
      await waitFor(() => {
        expect(screen.queryByTestId('confirmation-modal')).not.toBeInTheDocument();
      });
    });
  });

  describe('Refresh', () => {
    it('should refresh user list when refresh button is clicked', async () => {
      (global.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => mockUsers,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('User Management')).toBeInTheDocument();
      });
      
      const refreshButton = screen.getByTestId('refresh-button');
      fireEvent.click(refreshButton);
      
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error when fetch fails', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeInTheDocument();
      });
    });

    it('should display error when user creation fails', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Add User')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Add User'));
      
      await waitFor(() => {
        expect(screen.getByPlaceholderText('jdoe')).toBeInTheDocument();
      });
      
      fireEvent.change(screen.getByPlaceholderText('jdoe'), { target: { value: 'duplicate' } });
      fireEvent.change(screen.getByPlaceholderText('********'), { target: { value: 'pass123' } });
      
      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Username already exists' }),
      });
      
      const createButton = screen.getByText('Create User');
      fireEvent.click(createButton);
      
      await waitFor(() => {
        expect(screen.getByText(/already exists/i)).toBeInTheDocument();
      });
    });

    it('should allow dismissing error', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Dismiss'));
      
      await waitFor(() => {
        expect(screen.queryByTestId('alert-error')).not.toBeInTheDocument();
      });
    });
  });

  describe('Header', () => {
    it('should render ChatHeader with app name', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
      
      renderPage();
      
      expect(screen.getByTestId('chat-header')).toBeInTheDocument();
    });

    it('should show page description', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText(/Manage user accounts/)).toBeInTheDocument();
      });
    });
  });
});
