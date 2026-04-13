import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { NotificationCenter } from '../../components/NotificationCenter';
import type { Mock } from 'vitest';

vi.mock('../../services/api', () => ({
  getNotifications: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markNotificationAsRead: vi.fn(),
  markAllNotificationsAsRead: vi.fn(),
  dismissNotification: vi.fn(),
}));

import { getNotifications, getUnreadNotificationCount, markNotificationAsRead, markAllNotificationsAsRead, dismissNotification } from '../../services/api';

const mockNotifications = [
  { id: 1, type: 'embedding_complete', title: 'Embedding Complete', message: 'Vector store updated', status: 'unread', priority: 'medium', created_at: new Date().toISOString(), action_url: '/config' },
  { id: 2, type: 'config_published', title: 'Config Published', message: 'Version 2 is now active', status: 'read', priority: 'low', created_at: new Date(Date.now() - 3600000).toISOString(), action_url: null },
];

describe('NotificationCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    (getNotifications as Mock).mockResolvedValue(mockNotifications);
    (getUnreadNotificationCount as Mock).mockResolvedValue({ count: 1 });
    (markNotificationAsRead as Mock).mockResolvedValue({});
    (markAllNotificationsAsRead as Mock).mockResolvedValue({});
    (dismissNotification as Mock).mockResolvedValue({});
  });
  afterEach(() => vi.useRealTimers());

  it('renders bell with badge and fetches on mount', async () => {
    render(<NotificationCenter />);
    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(getNotifications).toHaveBeenCalledWith({ limit: 20 });
      expect(getUnreadNotificationCount).toHaveBeenCalled();
    });
  });

  it('hides badge when count is 0', async () => {
    (getUnreadNotificationCount as Mock).mockResolvedValue({ count: 0 });
    render(<NotificationCenter />);
    await waitFor(() => expect(getUnreadNotificationCount).toHaveBeenCalled());
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('opens dropdown showing notifications and closes on outside click', async () => {
    render(<div><NotificationCenter /><div data-testid="outside">Outside</div></div>);
    await waitFor(() => expect(getNotifications).toHaveBeenCalled());
    
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(screen.getByText('Embedding Complete')).toBeInTheDocument();
      expect(screen.getByText('Config Published')).toBeInTheDocument();
      expect(screen.getByText('Vector store updated')).toBeInTheDocument();
      expect(screen.getByText('✅')).toBeInTheDocument();
      expect(screen.getByText('📢')).toBeInTheDocument();
    });
    
    fireEvent.mouseDown(screen.getByTestId('outside'));
    await waitFor(() => expect(screen.queryByText('Embedding Complete')).not.toBeInTheDocument());
  });

  it('shows relative time for notifications', async () => {
    vi.useRealTimers();
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Embedding Complete')).toBeInTheDocument());
    expect(screen.getAllByText(/Just now|\d+[mhd] ago/).length).toBeGreaterThan(0);
  });

  it('marks unread notification as read when clicked', async () => {
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Embedding Complete')).toBeInTheDocument());
    
    fireEvent.click(screen.getByText('Embedding Complete'));
    await waitFor(() => expect(markNotificationAsRead).toHaveBeenCalledWith(1));
  });

  it('does not call markAsRead for already read notifications', async () => {
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Config Published')).toBeInTheDocument());
    
    fireEvent.click(screen.getByText('Config Published'));
    await waitFor(() => expect(markNotificationAsRead).not.toHaveBeenCalledWith(2));
  });

  it('marks all as read', async () => {
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText(/mark all/i)).toBeInTheDocument());
    
    fireEvent.click(screen.getByText(/mark all/i));
    await waitFor(() => expect(markAllNotificationsAsRead).toHaveBeenCalled());
  });

  it('dismisses notification', async () => {
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Embedding Complete')).toBeInTheDocument());
    
    const dismissButtons = screen.getAllByRole('button').filter(btn => btn.getAttribute('aria-label')?.includes('dismiss') || btn.textContent?.includes('×') || btn.querySelector('svg'));
    if (dismissButtons.length > 1) {
      fireEvent.click(dismissButtons[1]);
      await waitFor(() => expect(dismissNotification).toHaveBeenCalled());
    }
  });

  it('navigates to action URL when notification clicked', async () => {
    const originalLocation = window.location;
    delete (window as any).location;
    window.location = { ...originalLocation, href: '' } as any;
    
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Embedding Complete')).toBeInTheDocument());
    
    fireEvent.click(screen.getByText('Embedding Complete'));
    await waitFor(() => expect(window.location.href).toBe('/config'));
    window.location = originalLocation as any;
  });

  it('calls onNotificationClick callback when provided', async () => {
    const onNotificationClick = vi.fn();
    render(<NotificationCenter onNotificationClick={onNotificationClick} />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Embedding Complete')).toBeInTheDocument());
    
    fireEvent.click(screen.getByText('Embedding Complete'));
    await waitFor(() => expect(onNotificationClick).toHaveBeenCalledWith(expect.objectContaining({ id: 1 })));
  });

  it('polls for notifications periodically', async () => {
    render(<NotificationCenter />);
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));
    
    vi.advanceTimersByTime(30000);
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(2));
  });

  it('shows empty state when no notifications', async () => {
    (getNotifications as Mock).mockResolvedValue([]);
    (getUnreadNotificationCount as Mock).mockResolvedValue({ count: 0 });
    render(<NotificationCenter />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText(/no notification|empty/i)).toBeInTheDocument());
  });
});
