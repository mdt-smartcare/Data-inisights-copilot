import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import InsightsPage from '../../pages/InsightsPage';

// Mock modules
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../utils/permissions', () => ({
  canViewConfig: vi.fn(),
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
import { canViewConfig } from '../../utils/permissions';

const mockActiveConfig = {
  id: 5,
  version: 5,
  connection_name: 'Production DB',
  connection_type: 'postgresql',
  schema_selection: JSON.stringify({ users: ['id', 'name'], orders: ['id', 'total'] }),
  created_at: '2024-01-15 10:30:00',
  created_by_username: 'admin',
  prompt_text: '# System Prompt\n\nYou are a helpful assistant that answers questions about the database.',
};

describe('InsightsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock fetch
    global.fetch = vi.fn();
    
    // Default: user has access
    (useAuth as any).mockReturnValue({
      user: { id: 1, username: 'admin', role: 'super_admin' },
    });
    (canViewConfig as any).mockReturnValue(true);
    
    // Mock localStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPage = () => {
    return render(
      <MemoryRouter>
        <InsightsPage />
      </MemoryRouter>
    );
  };

  describe('Access Control', () => {
    it('should show access denied for unauthorized users', async () => {
      (canViewConfig as any).mockReturnValue(false);
      
      renderPage();
      
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText(/don't have permission/)).toBeInTheDocument();
    });

    it('should show page content for authorized users', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Insights')).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('should show loading spinner while fetching data', async () => {
      (global.fetch as any).mockImplementation(() => new Promise(() => {}));
      
      renderPage();
      
      await waitFor(() => {
        expect(document.querySelector('.animate-spin')).toBeInTheDocument();
        expect(screen.getByText('Loading insights...')).toBeInTheDocument();
      });
    });

    it('should hide loading after data loads', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(document.querySelector('.animate-spin')).not.toBeInTheDocument();
      });
    });
  });

  describe('Active Configuration Display', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
    });

    it('should display Active Configuration section', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Active Configuration')).toBeInTheDocument();
      });
    });

    it('should show status as Active', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Active')).toBeInTheDocument();
      });
    });

    it('should show version number', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText(/v5/)).toBeInTheDocument();
      });
    });

    it('should show connection name', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
    });

    it('should show schema table count', async () => {
      renderPage();
      
      await waitFor(() => {
        // 2 tables selected
        expect(screen.getByText('2')).toBeInTheDocument();
        expect(screen.getByText('tables selected')).toBeInTheDocument();
      });
    });

    it('should show last updated date', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Last Updated')).toBeInTheDocument();
      });
    });

    it('should show created by username', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText(/by admin/)).toBeInTheDocument();
      });
    });
  });

  describe('Prompt Preview', () => {
    it('should display prompt preview when prompt_text exists', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Active Prompt Preview')).toBeInTheDocument();
        expect(screen.getByText(/System Prompt/)).toBeInTheDocument();
      });
    });

    it('should truncate long prompts', async () => {
      const longPrompt = 'A'.repeat(600);
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockActiveConfig, prompt_text: longPrompt }),
      });
      
      renderPage();
      
      await waitFor(() => {
        // Should show ellipsis for truncated content
        expect(screen.getByText(/\.\.\.$/)).toBeInTheDocument();
      });
    });
  });

  describe('No Configuration', () => {
    it('should show message when no active configuration', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => null,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('No active configuration')).toBeInTheDocument();
        expect(screen.getByText(/Go to Config page/)).toBeInTheDocument();
      });
    });
  });

  describe('Quick Actions', () => {
    beforeEach(() => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
    });

    it('should display Quick Actions section', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Quick Actions')).toBeInTheDocument();
      });
    });

    it('should have link to chat page', async () => {
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Start Chatting')).toBeInTheDocument();
      });
      
      const chatLink = screen.getByText('Start Chatting').closest('a');
      expect(chatLink).toHaveAttribute('href', '/chat');
    });
  });

  describe('Refresh', () => {
    it('should refresh data when refresh button is clicked', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActiveConfig,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockActiveConfig,
        });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('Insights')).toBeInTheDocument();
      });
      
      // Wait for initial load
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(1);
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
        json: async () => mockActiveConfig,
      });
      
      renderPage();
      
      expect(screen.getByTestId('chat-header')).toBeInTheDocument();
    });

    it('should show page description', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockActiveConfig,
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText(/System overview and configuration status/)).toBeInTheDocument();
      });
    });
  });

  describe('Schema Parsing', () => {
    it('should handle schema as object (not string)', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockActiveConfig,
          schema_selection: { users: ['id'], orders: ['id'], products: ['id'] },
        }),
      });
      
      renderPage();
      
      await waitFor(() => {
        // Should show 3 tables
        expect(screen.getByText('3')).toBeInTheDocument();
      });
    });

    it('should handle array schema format', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockActiveConfig,
          schema_selection: JSON.stringify(['users', 'orders']),
        }),
      });
      
      renderPage();
      
      await waitFor(() => {
        // Should show 2 tables
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });

    it('should show 0 tables if schema is invalid', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...mockActiveConfig,
          schema_selection: 'invalid-json{',
        }),
      });
      
      renderPage();
      
      await waitFor(() => {
        expect(screen.getByText('0')).toBeInTheDocument();
      });
    });
  });
});
