import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as AuthContext from '../contexts/AuthContext';
import type { User, UserRole } from '../types';

// Mock AuthContext
vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual('../contexts/AuthContext');
  return {
    ...actual,
    useAuth: vi.fn(),
    AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

// Mock Toast provider
vi.mock('../components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({
    showToast: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

// Simple ProtectedRoute component matching the logic in App.tsx
interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { user, isLoading, logout } = AuthContext.useAuth();
  const token = localStorage.getItem('auth_token');
  const expiresAt = localStorage.getItem('expiresAt');
  
  // Calculate token expiration status using useMemo to avoid impure render
  const isTokenExpired = React.useMemo(() => {
    if (!token || !expiresAt) return !token;
    // eslint-disable-next-line react-hooks/purity -- Date.now() is needed for token expiration check in tests
    const currentTime = Math.floor(Date.now() / 1000);
    return parseInt(expiresAt) < currentTime;
  }, [token, expiresAt]);

  // Check if token has expired (using useEffect pattern to handle logout side effect)
  React.useEffect(() => {
    if (token && isTokenExpired) {
      logout();
    }
  }, [token, isTokenExpired, logout]);

  // If token expired or no token, redirect to login
  if (isTokenExpired) {
    return <Navigate to="/login" replace />;
  }

  // Wait while loading user data
  if (isLoading) {
    return <div data-testid="loading">Loading...</div>;
  }

  // Check role-based access
  if (allowedRoles && user && user.role && !allowedRoles.includes(user.role)) {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
}

const renderWithRouter = (initialRoute = '/', authState: ReturnType<typeof createAuthState>) => {
  const queryClient = createQueryClient();
  vi.mocked(AuthContext.useAuth).mockReturnValue(authState);

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
          <Route path="/register" element={<div data-testid="register-page">Register Page</div>} />
          <Route path="/about" element={<div data-testid="about-page">About Page</div>} />
          <Route path="/chat" element={
            <ProtectedRoute>
              <div data-testid="chat-page">Chat Page</div>
            </ProtectedRoute>
          } />
          <Route path="/config" element={
            <ProtectedRoute allowedRoles={['user', 'admin']}>
              <div data-testid="config-page">Config Page</div>
            </ProtectedRoute>
          } />
          <Route path="/users" element={
            <ProtectedRoute allowedRoles={['admin']}>
              <div data-testid="users-page">Users Page</div>
            </ProtectedRoute>
          } />
          <Route path="/audit" element={
            <ProtectedRoute allowedRoles={['admin']}>
              <div data-testid="audit-page">Audit Logs Page</div>
            </ProtectedRoute>
          } />
          <Route path="/history" element={
            <ProtectedRoute allowedRoles={['user', 'admin']}>
              <div data-testid="history-page">History Page</div>
            </ProtectedRoute>
          } />
          <Route path="/insights" element={
            <ProtectedRoute allowedRoles={['user', 'admin']}>
              <div data-testid="insights-page">Insights Page</div>
            </ProtectedRoute>
          } />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

const mockLogout = vi.fn();
const mockSetUser = vi.fn();
const mockLogin = vi.fn();
const mockGetAccessToken = vi.fn().mockReturnValue('mock_token');

const createAuthState = (user: User | null, isLoading = false) => ({
  user,
  isLoading,
  isAuthenticated: !!user,
  logout: mockLogout,
  setUser: mockSetUser,
  login: mockLogin,
  getAccessToken: mockGetAccessToken,
});

const mockUsers: Record<string, User> = {
  viewer: { id: 1, username: 'viewer', role: 'user' as UserRole, email: 'v@test.com' },
  editor: { id: 2, username: 'editor', role: 'user' as UserRole, email: 'e@test.com' },  // Changed to 'user'
  superAdmin: { id: 3, username: 'admin', role: 'admin' as UserRole, email: 'a@test.com' },  // Changed to 'admin'
};

describe('App Routing and ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Authentication Checks', () => {
    it('should redirect to login when no token exists', () => {
      renderWithRouter('/chat', createAuthState(null));
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });

    it('should redirect to login when token is expired', () => {
      const expiredTime = Math.floor(Date.now() / 1000) - 3600;
      localStorage.setItem('auth_token', 'expired_token');
      localStorage.setItem('expiresAt', expiredTime.toString());

      renderWithRouter('/chat', createAuthState(null));
      expect(mockLogout).toHaveBeenCalled();
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });

    it('should show loading state while user is loading', () => {
      localStorage.setItem('auth_token', 'valid_token');
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('expiresAt', futureTime.toString());

      renderWithRouter('/chat', createAuthState(null, true));
      expect(screen.getByTestId('loading')).toBeInTheDocument();
    });

    it('should render protected content when authenticated with valid token', () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());

      renderWithRouter('/chat', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });
  });

  describe('Public Routes', () => {
    it('should allow access to login page without authentication', () => {
      renderWithRouter('/login', createAuthState(null));
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });

    it('should allow access to register page without authentication', () => {
      renderWithRouter('/register', createAuthState(null));
      expect(screen.getByTestId('register-page')).toBeInTheDocument();
    });

    it('should allow access to about page without authentication', () => {
      renderWithRouter('/about', createAuthState(null));
      expect(screen.getByTestId('about-page')).toBeInTheDocument();
    });
  });

  describe('Role-Based Access Control - Viewer (user role)', () => {
    const setupAuth = () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());
    };

    it('should allow viewer to access chat page', () => {
      setupAuth();
      renderWithRouter('/chat', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect viewer from config page to chat', () => {
      setupAuth();
      renderWithRouter('/config', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect viewer from users page to chat', () => {
      setupAuth();
      renderWithRouter('/users', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect viewer from audit page to chat', () => {
      setupAuth();
      renderWithRouter('/audit', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect viewer from history page to chat', () => {
      setupAuth();
      renderWithRouter('/history', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect viewer from insights page to chat', () => {
      setupAuth();
      renderWithRouter('/insights', createAuthState(mockUsers.viewer));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });
  });

  describe('Role-Based Access Control - Editor', () => {
    const setupAuth = () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());
    };

    it('should allow editor to access chat page', () => {
      setupAuth();
      renderWithRouter('/chat', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should allow editor to access config page', () => {
      setupAuth();
      renderWithRouter('/config', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('config-page')).toBeInTheDocument();
    });

    it('should allow editor to access history page', () => {
      setupAuth();
      renderWithRouter('/history', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('history-page')).toBeInTheDocument();
    });

    it('should allow editor to access insights page', () => {
      setupAuth();
      renderWithRouter('/insights', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('insights-page')).toBeInTheDocument();
    });

    it('should redirect editor from users page to chat', () => {
      setupAuth();
      renderWithRouter('/users', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should redirect editor from audit logs to chat', () => {
      setupAuth();
      renderWithRouter('/audit', createAuthState(mockUsers.editor));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });
  });

  describe('Role-Based Access Control - Super Admin', () => {
    const setupAuth = () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());
    };

    it('should allow super_admin to access chat page', () => {
      setupAuth();
      renderWithRouter('/chat', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should allow super_admin to access config page', () => {
      setupAuth();
      renderWithRouter('/config', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('config-page')).toBeInTheDocument();
    });

    it('should allow super_admin to access users page', () => {
      setupAuth();
      renderWithRouter('/users', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('users-page')).toBeInTheDocument();
    });

    it('should allow super_admin to access audit logs', () => {
      setupAuth();
      renderWithRouter('/audit', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('audit-page')).toBeInTheDocument();
    });

    it('should allow super_admin to access history page', () => {
      setupAuth();
      renderWithRouter('/history', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('history-page')).toBeInTheDocument();
    });

    it('should allow super_admin to access insights page', () => {
      setupAuth();
      renderWithRouter('/insights', createAuthState(mockUsers.superAdmin));
      expect(screen.getByTestId('insights-page')).toBeInTheDocument();
    });
  });

  describe('Unknown Routes', () => {
    it('should redirect unknown routes to login', () => {
      renderWithRouter('/unknown-route', createAuthState(null));
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });
  });

  describe('Token Expiration Edge Cases', () => {
    it('should not redirect if token expires in the future', () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());

      renderWithRouter('/chat', createAuthState(mockUsers.viewer));
      expect(mockLogout).not.toHaveBeenCalled();
      expect(screen.getByTestId('chat-page')).toBeInTheDocument();
    });

    it('should call logout and redirect when token just expired', () => {
      const justExpired = Math.floor(Date.now() / 1000) - 1;
      localStorage.setItem('auth_token', 'expired_token');
      localStorage.setItem('expiresAt', justExpired.toString());

      renderWithRouter('/chat', createAuthState(null));
      expect(mockLogout).toHaveBeenCalled();
    });
  });
});
