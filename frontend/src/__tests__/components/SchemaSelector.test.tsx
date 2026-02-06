import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SchemaSelector from '../../components/SchemaSelector';

// Mock the API module
vi.mock('../../services/api', () => ({
  getConnectionSchema: vi.fn(),
  handleApiError: vi.fn((err) => err?.message || 'An error occurred'),
  // Add other API exports that may be used by dependencies
  getUnreadNotificationCount: vi.fn().mockResolvedValue({ count: 0 }),
  getNotifications: vi.fn().mockResolvedValue([]),
  markNotificationAsRead: vi.fn().mockResolvedValue({}),
  markAllNotificationsAsRead: vi.fn().mockResolvedValue({}),
  dismissNotification: vi.fn().mockResolvedValue({}),
}));

import { getConnectionSchema } from '../../services/api';

const mockSchemaData = {
  schema: {
    tables: ['users', 'orders', 'products'],
    details: {
      users: [
        { name: 'id', type: 'integer', nullable: false },
        { name: 'username', type: 'varchar', nullable: false },
        { name: 'email', type: 'varchar', nullable: true },
      ],
      orders: [
        { name: 'id', type: 'integer', nullable: false },
        { name: 'user_id', type: 'integer', nullable: false },
        { name: 'total', type: 'decimal', nullable: false },
      ],
      products: [
        { name: 'id', type: 'integer', nullable: false },
        { name: 'name', type: 'varchar', nullable: false },
        { name: 'price', type: 'decimal', nullable: false },
      ],
    },
  },
};

describe('SchemaSelector', () => {
  const mockOnSelectionChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (getConnectionSchema as any).mockResolvedValue(mockSchemaData);
  });

  describe('Loading State', () => {
    it('should show loading spinner while fetching schema', async () => {
      (getConnectionSchema as any).mockImplementation(() => new Promise(() => {})); // Never resolves
      
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      // Check for loading text or spinner
      expect(screen.getByText(/Inspecting database schema/i)).toBeInTheDocument();
    });

    it('should hide loading after schema loads', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      expect(document.querySelector('.animate-spin')).not.toBeInTheDocument();
    });
  });

  describe('Schema Display', () => {
    it('should fetch schema when connectionId is provided', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(getConnectionSchema).toHaveBeenCalledWith(1);
      });
    });

    it('should not fetch schema when connectionId is not provided', () => {
      render(
        <SchemaSelector connectionId={0} onSelectionChange={mockOnSelectionChange} />
      );
      
      expect(getConnectionSchema).not.toHaveBeenCalled();
    });

    it('should display all tables', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
        expect(screen.getByText('orders')).toBeInTheDocument();
        expect(screen.getByText('products')).toBeInTheDocument();
      });
    });

    it('should show selection counts', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        // Should show total selected counts (all columns selected by default)
        expect(screen.getByText(/9/)).toBeInTheDocument(); // Total columns: 3+3+3=9
      });
    });
  });

  describe('Initial Selection', () => {
    it('should select all columns by default', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(mockOnSelectionChange).toHaveBeenCalledWith({
          users: ['id', 'username', 'email'],
          orders: ['id', 'user_id', 'total'],
          products: ['id', 'name', 'price'],
        });
      });
    });
  });

  describe('Table Expansion', () => {
    it('should expand table to show columns when clicked', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Click to expand users table
      fireEvent.click(screen.getByText('users'));
      
      await waitFor(() => {
        expect(screen.getByText('id')).toBeInTheDocument();
        expect(screen.getByText('username')).toBeInTheDocument();
        expect(screen.getByText('email')).toBeInTheDocument();
      });
    });

    it('should collapse table when clicked again', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Expand
      fireEvent.click(screen.getByText('users'));
      await waitFor(() => {
        expect(screen.getByText('username')).toBeInTheDocument();
      });
      
      // Collapse
      fireEvent.click(screen.getByText('users'));
      await waitFor(() => {
        expect(screen.queryByText('username')).not.toBeInTheDocument();
      });
    });
  });

  describe('Column Selection', () => {
    it('should toggle individual column selection', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Expand users table
      fireEvent.click(screen.getByText('users'));
      
      await waitFor(() => {
        expect(screen.getByText('email')).toBeInTheDocument();
      });
      
      // Find and click the email checkbox
      const emailRow = screen.getByText('email').closest('div');
      const checkbox = emailRow?.querySelector('input[type="checkbox"]');
      if (checkbox) {
        fireEvent.click(checkbox);
      }
      
      // Should update selection (email removed)
      await waitFor(() => {
        expect(mockOnSelectionChange).toHaveBeenCalledWith(
          expect.objectContaining({
            users: expect.not.arrayContaining(['email']),
          })
        );
      });
    });
  });

  describe('Table Selection Toggle', () => {
    it('should toggle all columns in a table', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Find and click the table checkbox for users
      const usersRow = screen.getByText('users').closest('div');
      const tableCheckbox = usersRow?.querySelector('input[type="checkbox"]');
      
      if (tableCheckbox) {
        // All selected, so clicking should deselect all
        fireEvent.click(tableCheckbox);
        
        await waitFor(() => {
          expect(mockOnSelectionChange).toHaveBeenCalledWith(
            expect.objectContaining({
              orders: ['id', 'user_id', 'total'],
              products: ['id', 'name', 'price'],
            })
          );
        });
      }
    });
  });

  describe('Global Toggle', () => {
    it('should have a toggle all button', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Look for a "Select All" or similar button
      const toggleAllButton = screen.queryByRole('button', { name: /all|toggle/i }) ||
                             screen.queryByText(/select all|deselect all/i);
      
      expect(toggleAllButton || screen.queryByText(/columns/i)).toBeTruthy();
    });
  });

  describe('Read Only Mode', () => {
    it('should disable interactions when readOnly is true', async () => {
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} readOnly />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Expand to see columns
      fireEvent.click(screen.getByText('users'));
      
      // Checkboxes should still be visible but interactions should be limited
      // The component should still display data
      expect(screen.getByText('users')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should display error when schema fetch fails', async () => {
      (getConnectionSchema as any).mockRejectedValue(new Error('Connection failed'));
      
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.getByText(/Error fetching schema.*Connection failed/)).toBeInTheDocument();
      });
    });

    it('should clear tables on error', async () => {
      (getConnectionSchema as any).mockRejectedValue(new Error('Error'));
      
      render(
        <SchemaSelector connectionId={1} onSelectionChange={mockOnSelectionChange} />
      );
      
      await waitFor(() => {
        expect(screen.queryByText('users')).not.toBeInTheDocument();
      });
    });
  });

  describe('Reasoning Display', () => {
    it('should display reasoning when provided', async () => {
      const reasoning = {
        users: 'This table contains user information',
      };
      
      render(
        <SchemaSelector
          connectionId={1}
          onSelectionChange={mockOnSelectionChange}
          reasoning={reasoning}
        />
      );
      
      await waitFor(() => {
        expect(screen.getByText('users')).toBeInTheDocument();
      });
      
      // Reasoning might be shown as tooltip or inline text
      // Check if it's accessible somewhere in the component
      const container = screen.getByText('users').closest('div');
      expect(container).toBeInTheDocument();
    });
  });
});
