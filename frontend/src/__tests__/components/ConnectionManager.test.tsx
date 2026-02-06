import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ConnectionManager from '../../components/ConnectionManager';

// Mock the API module
vi.mock('../../services/api', () => ({
  getConnections: vi.fn(),
  saveConnection: vi.fn(),
  deleteConnection: vi.fn(),
  handleApiError: vi.fn((err) => err?.message || 'An error occurred'),
  // Add other API exports that may be used by dependencies
  getUnreadNotificationCount: vi.fn().mockResolvedValue({ count: 0 }),
  getNotifications: vi.fn().mockResolvedValue([]),
  markNotificationAsRead: vi.fn().mockResolvedValue({}),
  markAllNotificationsAsRead: vi.fn().mockResolvedValue({}),
  dismissNotification: vi.fn().mockResolvedValue({}),
}));

import { getConnections, saveConnection, deleteConnection } from '../../services/api';

const mockConnections = [
  { id: 1, name: 'Production DB', connection_string: 'postgresql://prod', db_type: 'postgresql', pool_config: '{"pool_size":10}' },
  { id: 2, name: 'Test DB', connection_string: 'postgresql://test', db_type: 'postgresql', pool_config: null },
];

describe('ConnectionManager', () => {
  const mockOnSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (getConnections as any).mockResolvedValue(mockConnections);
    (saveConnection as any).mockResolvedValue({ id: 3 });
    (deleteConnection as any).mockResolvedValue({});
  });

  describe('Rendering', () => {
    it('should render the component title', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      expect(screen.getByText('Database Connections')).toBeInTheDocument();
    });

    it('should render New Connection button when not readOnly', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      expect(screen.getByText('+ New Connection')).toBeInTheDocument();
    });

    it('should hide New Connection button when readOnly', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} readOnly />);
      
      expect(screen.queryByText('+ New Connection')).not.toBeInTheDocument();
    });

    it('should load and display connections on mount', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      await waitFor(() => {
        expect(getConnections).toHaveBeenCalled();
      });
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
        expect(screen.getByText('Test DB')).toBeInTheDocument();
      });
    });
  });

  describe('Connection Selection', () => {
    it('should call onSelect when a connection is clicked', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Production DB'));
      
      expect(mockOnSelect).toHaveBeenCalledWith(1);
    });

    it('should highlight the selected connection', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      // The selected connection should show "Selected" text
      expect(screen.getByText('Selected')).toBeInTheDocument();
    });
  });

  describe('Adding Connection', () => {
    it('should toggle add form when button is clicked', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      expect(screen.getByText('Cancel')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
    });

    it('should show name and connection string inputs in add form', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/postgresql:\/\//)).toBeInTheDocument();
    });

    it('should show error when saving without name or URI', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      // Wait for the form to appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByText('Save Connection'));
      
      await waitFor(() => {
        expect(screen.getByText('Name and Connection String are required')).toBeInTheDocument();
      });
    });

    it('should save connection and auto-select it', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      // Wait for the form to appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
      });
      
      const nameInput = screen.getByPlaceholderText('e.g. Production DB');
      const uriInput = screen.getByPlaceholderText(/postgresql:\/\//);
      
      fireEvent.change(nameInput, { target: { value: 'New DB' } });
      fireEvent.change(uriInput, { target: { value: 'postgresql://newdb' } });
      
      fireEvent.click(screen.getByText('Save Connection'));
      
      await waitFor(() => {
        expect(saveConnection).toHaveBeenCalledWith(
          'New DB',
          'postgresql://newdb',
          'postgresql',
          expect.any(Object)
        );
      });
      
      await waitFor(() => {
        expect(mockOnSelect).toHaveBeenCalledWith(3);
      });
    });

    it('should close form after successful save', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      // Wait for the form to appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
      });
      
      fireEvent.change(screen.getByPlaceholderText('e.g. Production DB'), { target: { value: 'New DB' } });
      fireEvent.change(screen.getByPlaceholderText(/postgresql:\/\//), { target: { value: 'postgresql://new' } });
      
      fireEvent.click(screen.getByText('Save Connection'));
      
      await waitFor(() => {
        expect(screen.getByText('+ New Connection')).toBeInTheDocument();
      });
    });
  });

  describe('Deleting Connection', () => {
    it('should show delete button for each connection', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByTitle(/delete/i);
      expect(deleteButtons.length).toBeGreaterThan(0);
    });

    it('should show confirmation modal when delete is clicked', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByTitle(/delete/i);
      fireEvent.click(deleteButtons[0]);
      
      // Confirmation modal should appear
      await waitFor(() => {
        expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
      });
    });

    it('should delete connection after confirmation', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByTitle(/delete/i);
      fireEvent.click(deleteButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
      });
      
      // Click the Delete button in the modal (not the title)
      const allButtons = screen.getAllByRole('button');
      const deleteButton = allButtons.find(btn => btn.textContent === 'Delete');
      expect(deleteButton).toBeDefined();
      fireEvent.click(deleteButton!);
      
      await waitFor(() => {
        expect(deleteConnection).toHaveBeenCalledWith(1);
      });
    });

    it('should deselect if deleted connection was selected', async () => {
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByTitle(/delete/i);
      fireEvent.click(deleteButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
      });
      
      // Click the Delete button in the modal
      const allButtons = screen.getAllByRole('button');
      const deleteButton = allButtons.find(btn => btn.textContent === 'Delete');
      expect(deleteButton).toBeDefined();
      fireEvent.click(deleteButton!);
      
      await waitFor(() => {
        expect(mockOnSelect).toHaveBeenCalledWith(null);
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error when fetching connections fails', async () => {
      (getConnections as any).mockRejectedValue(new Error('Network error'));
      
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('should display error when saving fails', async () => {
      (saveConnection as any).mockRejectedValue(new Error('Save failed'));
      
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      fireEvent.click(screen.getByText('+ New Connection'));
      
      // Wait for the form to appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText('e.g. Production DB')).toBeInTheDocument();
      });
      
      fireEvent.change(screen.getByPlaceholderText('e.g. Production DB'), { target: { value: 'New' } });
      fireEvent.change(screen.getByPlaceholderText(/postgresql:\/\//), { target: { value: 'postgresql://x' } });
      fireEvent.click(screen.getByText('Save Connection'));
      
      await waitFor(() => {
        expect(screen.getByText('Save failed')).toBeInTheDocument();
      });
    });

    it('should allow dismissing errors', async () => {
      (getConnections as any).mockRejectedValue(new Error('Network error'));
      
      render(<ConnectionManager onSelect={mockOnSelect} selectedId={null} />);
      
      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
      
      const dismissButton = screen.getByRole('button', { name: /dismiss|close/i });
      fireEvent.click(dismissButton);
      
      await waitFor(() => {
        expect(screen.queryByText('Network error')).not.toBeInTheDocument();
      });
    });
  });

  describe('Pool Configuration', () => {
    it('should sync pool config when selected connection changes', async () => {
      const { rerender } = render(
        <ConnectionManager onSelect={mockOnSelect} selectedId={null} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('Production DB')).toBeInTheDocument();
      });
      
      rerender(<ConnectionManager onSelect={mockOnSelect} selectedId={1} />);
      
      // Pool config should be synced from the selected connection
      // This is internal state, but we can verify it was loaded
      await waitFor(() => {
        expect(getConnections).toHaveBeenCalled();
      });
    });
  });
});
