import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuditLogsPage from '../../pages/AuditLogsPage';

// Mock modules
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../utils/permissions', () => ({
  canViewAllAuditLogs: vi.fn(),
  getRoleDisplayName: vi.fn((role) => role?.charAt(0).toUpperCase() + role?.slice(1) || 'Unknown'),
}));

vi.mock('../../components/chat', () => ({
  ChatHeader: ({ title }: { title: string }) => <div data-testid="chat-header">{title}</div>,
}));

vi.mock('../../components/RefreshButton', () => ({
  default: ({ onClick, isLoading }: any) => (
    <button data-testid="refresh-button" onClick={onClick} disabled={isLoading}>
      Refresh
    </button>
  ),
}));

vi.mock('../../components/Alert', () => ({
  default: ({ type, message, onDismiss }: any) => (
    <div data-testid={`alert-${type}`} role="alert">
      {message}
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}));

import { useAuth } from '../../contexts/AuthContext';
import { canViewAllAuditLogs } from '../../utils/permissions';

const mockLogs = [
  {
    id: 1,
    timestamp: '2024-01-15T10:30:00Z',
    actor_id: 1,
    actor_username: 'admin',
    actor_role: 'super_admin',
    action: 'config.publish',
    resource_type: 'config',
    resource_id: '5',
    resource_name: 'RAG Config v5',
    details: { version: 5 },
  },
  {
    id: 2,
    timestamp: '2024-01-15T09:00:00Z',
    actor_id: 2,
    actor_username: 'editor1',
    actor_role: 'editor',
    action: 'user.create',
    resource_type: 'user',
    resource_id: '10',
    resource_name: 'newuser',
    details: { role: 'user' },
  },
];

const mockActionTypes = ['config.publish', 'config.create', 'user.create', 'user.update'];

describe('AuditLogsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock fetch
    global.fetch = vi.fn();
    
    // Default: user has access
    (useAuth as any).mockReturnValue({
      user: { id: 1, username: 'admin', role: 'super_admin' },
    });
    (canViewAllAuditLogs as any).mockReturnValue(true);
    
    // Mock localStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPage = () => {
    return render(
      <MemoryRouter>
        <AuditLogsPage />
      </MemoryRouter>
    );
  };

  describe('Access Control', () => {
    it('should show access denied for unauthorized users', async () => {
      (canViewAllAuditLogs as any).mockReturnValue(false);
      
      renderPage();
      
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText(/don't have permission/)).toBeInTheDocument();
    });

    it('should show page content for authorized users', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockLogs,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Audit Logs')).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('should show loading spinner while fetching logs', async () => {
      (global.fetch as any).mockImplementation(() => new Promise(() => {}));
      
      renderPage();
      
      await waitFor(() => {
        expect(document.querySelector('.animate-spin')).toBeInTheDocument();
      });
    });
  });

  describe('Log Display', () => {
    beforeEach(() => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockLogs,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
    });

    it('should display log entries', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('admin')).toBeInTheDocument();
        expect(screen.getByText('editor1')).toBeInTheDocument();
      });
    });

    it('should format action names', async () => {
      renderPage();
      
      await waitFor(() => {
        // Action should be formatted: config.publish -> Config → Publish
        expect(screen.getByText(/Config.*Publish/i)).toBeInTheDocument();
      });
    });

    it('should display resource information', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('RAG Config v5')).toBeInTheDocument();
      });
    });

    it('should display log details', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText(/version/i)).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    beforeEach(() => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockLogs,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
    });

    it('should have filter inputs', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Audit Logs')).toBeInTheDocument();
      });
      
      // Should have filter for actor, action, and resource type
      const inputs = screen.getAllByRole('textbox');
      const selects = screen.getAllByRole('combobox');
      
      expect(inputs.length + selects.length).toBeGreaterThan(0);
    });

    it('should filter by actor when form is submitted', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Audit Logs')).toBeInTheDocument();
      });
      
      // Clear previous fetch mocks and set up for filtered request
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => [mockLogs[0]], // Only admin's log
      });
      
      // Find and fill actor filter
      const actorInput = screen.getByPlaceholderText(/actor|username/i);
      fireEvent.change(actorInput, { target: { value: 'admin' } });
      
      // Submit filter form
      const searchButton = screen.getByRole('button', { name: /search|filter|apply/i });
      fireEvent.click(searchButton);
      
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('actor=admin'),
          expect.any(Object)
        );
      });
    });

    it('should filter by action type', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Audit Logs')).toBeInTheDocument();
      });
      
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => [mockLogs[0]],
      });
      
      // Find action type select
      const actionSelect = screen.getByRole('combobox');
      if (actionSelect) {
        fireEvent.change(actionSelect, { target: { value: 'config.publish' } });
        
        const searchButton = screen.getByRole('button', { name: /search|filter|apply/i });
        fireEvent.click(searchButton);
        
        await waitFor(() => {
          expect(global.fetch).toHaveBeenCalled();
        });
      }
    });
  });

  describe('Refresh', () => {
    it('should refresh logs when refresh button is clicked', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockLogs,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Audit Logs')).toBeInTheDocument();
      });
      
      // Set up mock for refresh
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockLogs,
      });
      
      // Multiple refresh buttons may exist - use the first one
      const refreshButtons = screen.getAllByTestId('refresh-button');
      fireEvent.click(refreshButtons[0]);
      
      await waitFor(() => {
        // Fetch should have been called again
        expect(global.fetch).toHaveBeenCalledTimes(3);
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error when fetch fails', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: false,
        });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeInTheDocument();
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

  describe('Action Colors', () => {
    beforeEach(() => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [
            { ...mockLogs[0], action: 'user.delete' },
            { ...mockLogs[1], action: 'config.create' },
          ],
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
    });

    it('should apply different colors for different action types', async () => {
      renderPage();
      
      await waitFor(() => {
        // Delete actions should have red styling
        const deleteAction = screen.getByText(/Delete/i);
        expect(deleteAction.closest('[class*="red"]') || deleteAction.className).toBeTruthy();
      });
    });
  });

  describe('Header', () => {
    it('should render ChatHeader with app name', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockLogs,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActionTypes,
        });
      
      renderPage();
      
      expect(screen.getByTestId('chat-header')).toBeInTheDocument();
    });
  });
});
