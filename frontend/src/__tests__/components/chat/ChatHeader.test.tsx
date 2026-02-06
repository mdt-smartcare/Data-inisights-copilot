import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ChatHeader from '../../../components/chat/ChatHeader';
import * as AuthContext from '../../../contexts/AuthContext';
import type { User, UserRole } from '../../../types';

vi.mock('../../../contexts/AuthContext', async () => {
  const actual = await vi.importActual('../../../contexts/AuthContext');
  return { ...actual, useAuth: vi.fn() };
});
vi.mock('../../../components/NotificationCenter', () => ({ default: () => <div data-testid="notification-center">Notifications</div> }));
vi.mock('../../../assets/logo.svg', () => ({ default: 'logo.svg' }));

const mockLogout = vi.fn();
const createMockAuth = (user: User | null) => ({ user, isLoading: false, isAuthenticated: !!user, logout: mockLogout, setUser: vi.fn() });

const mockUsers: Record<string, User> = {
  viewer: { id: 1, username: 'viewer', role: 'user' as UserRole, email: 'v@test.com' },
  editor: { id: 2, username: 'editor', role: 'editor' as UserRole, email: 'e@test.com' },
  superAdmin: { id: 3, username: 'admin', role: 'super_admin' as UserRole, email: 'a@test.com' },
};

const renderWithRouter = (user: User, initialPath = '/chat') => {
  vi.mocked(AuthContext.useAuth).mockReturnValue(createMockAuth(user));
  return render(<MemoryRouter initialEntries={[initialPath]}><ChatHeader title="Test App" /></MemoryRouter>);
};

describe('ChatHeader', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders basic elements: title, logo, notifications, user avatar', () => {
    renderWithRouter(mockUsers.viewer);
    expect(screen.getByText('Test App')).toBeInTheDocument();
    expect(screen.getByAltText('Logo')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByText('V')).toBeInTheDocument();
  });

  it.each([
    ['viewer', ['Chat'], ['Config', 'Users', 'Audit']],
    ['editor', ['Chat', 'Config', 'Insights', 'History'], ['Users', 'Audit']],
    ['superAdmin', ['Chat', 'Config', 'Users', 'Audit', 'Insights', 'History'], []],
  ])('shows correct nav links for %s role', (userKey, visible, hidden) => {
    renderWithRouter(mockUsers[userKey]);
    visible.forEach(link => expect(screen.getByRole('link', { name: link })).toBeInTheDocument());
    hidden.forEach(link => expect(screen.queryByRole('link', { name: link })).not.toBeInTheDocument());
  });

  it.each([
    ['/chat', 'Chat', 'viewer'],
    ['/config', 'Config', 'editor'],
    ['/audit', 'Audit', 'superAdmin'],
  ])('highlights active link for %s path', (path, linkName, userKey) => {
    renderWithRouter(mockUsers[userKey], path);
    expect(screen.getByRole('link', { name: linkName })).toHaveClass('bg-blue-100', 'text-blue-700');
  });

  it('user menu shows info and handles logout flow', async () => {
    const user = userEvent.setup();
    renderWithRouter(mockUsers.editor);
    
    await user.click(screen.getByLabelText('User menu'));
    expect(screen.getByText('Logout')).toBeInTheDocument();
    expect(screen.getByText('e@test.com')).toBeInTheDocument();
    expect(screen.getAllByText('Editor')).toHaveLength(2);
    
    // Show confirmation
    await user.click(screen.getByText('Logout'));
    expect(screen.getByText('Are you sure you want to logout?')).toBeInTheDocument();
    
    // Cancel
    await user.click(screen.getByText('Cancel'));
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it('confirms logout when Yes clicked', async () => {
    const user = userEvent.setup();
    renderWithRouter(mockUsers.viewer);
    
    await user.click(screen.getByLabelText('User menu'));
    await user.click(screen.getByText('Logout'));
    await user.click(screen.getByText('Yes, Logout'));
    expect(mockLogout).toHaveBeenCalled();
  });

  it('menu toggle and aria-expanded', async () => {
    const user = userEvent.setup();
    renderWithRouter(mockUsers.viewer);
    
    const menuButton = screen.getByLabelText('User menu');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    
    await user.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-expanded', 'true');
  });

  it('back button visibility', () => {
    // No back button by default
    renderWithRouter(mockUsers.viewer);
    expect(screen.getAllByRole('link').find(l => l.getAttribute('href') === '/')).toBeUndefined();
    
    // With showBackButton
    vi.mocked(AuthContext.useAuth).mockReturnValue(createMockAuth(mockUsers.viewer));
    render(<MemoryRouter><ChatHeader title="Test" showBackButton={true} /></MemoryRouter>);
    expect(screen.getByRole('link', { name: '' })).toHaveAttribute('href', '/');
  });
});
