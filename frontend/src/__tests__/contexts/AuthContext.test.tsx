import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { User } from '../../types';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { setupAuthState, clearAuthState, mockUsers } from '../test-utils';

vi.mock('../../services/api', () => ({ getUserProfile: vi.fn() }));
import { getUserProfile } from '../../services/api';

function TestConsumer() {
  const { user, isAuthenticated, isLoading, logout, setUser } = useAuth();
  return (
    <div>
      <div data-testid="loading">{isLoading ? 'loading' : 'loaded'}</div>
      <div data-testid="authenticated">{isAuthenticated ? 'yes' : 'no'}</div>
      <div data-testid="username">{user?.username || 'none'}</div>
      <div data-testid="role">{user?.role || 'none'}</div>
      <button onClick={logout} data-testid="logout-btn">Logout</button>
      <button onClick={() => setUser(mockUsers.editor)} data-testid="set-user-btn">Set User</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => { vi.clearAllMocks(); clearAuthState(); });

  it('starts unauthenticated without token and skips profile fetch', async () => {
    vi.mocked(getUserProfile).mockResolvedValue(undefined as unknown as User);
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('loaded'));
    expect(screen.getByTestId('username')).toHaveTextContent('none');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
    expect(getUserProfile).not.toHaveBeenCalled();
  });

  it('restores session from valid token', async () => {
    setupAuthState(mockUsers.editor);
    vi.mocked(getUserProfile).mockResolvedValue(mockUsers.editor);
    
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('loaded'));
    
    expect(screen.getByTestId('username')).toHaveTextContent(mockUsers.editor.username);
    expect(screen.getByTestId('role')).toHaveTextContent(mockUsers.editor.role!);
    expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
  });

  it('clears invalid token and localStorage on session restore failure', async () => {
    setupAuthState(mockUsers.editor);
    vi.mocked(getUserProfile).mockRejectedValue(new Error('Invalid token'));
    
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('loaded'));
    
    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(localStorage.getItem('expiresAt')).toBeNull();
    expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
  });

  it('setUser updates state and logout clears everything', async () => {
    vi.mocked(getUserProfile).mockResolvedValue(undefined as unknown as User);
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('loaded'));

    // Set user
    screen.getByTestId('set-user-btn').click();
    await waitFor(() => expect(screen.getByTestId('username')).toHaveTextContent(mockUsers.editor.username));

    // No token = not authenticated even with user
    expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
  });

  it('logout clears user state and localStorage', async () => {
    setupAuthState(mockUsers.superAdmin);
    vi.mocked(getUserProfile).mockResolvedValue(mockUsers.superAdmin);
    
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('username')).toHaveTextContent(mockUsers.superAdmin.username));

    screen.getByTestId('logout-btn').click();
    
    await waitFor(() => {
      expect(screen.getByTestId('username')).toHaveTextContent('none');
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
    });
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('throws error when useAuth used outside AuthProvider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<TestConsumer />)).toThrow('useAuth must be used within an AuthProvider');
    consoleSpy.mockRestore();
  });
});
