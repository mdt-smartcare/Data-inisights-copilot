import { render, type RenderOptions } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../contexts/AuthContext';
import { ToastProvider } from '../components/Toast';
import type { ReactElement, ReactNode } from 'react';
import type { User } from '../types';

// Create a new QueryClient for each test to prevent state leakage
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// All providers wrapper for testing
interface AllProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
}

export function AllProviders({ children, queryClient }: AllProvidersProps) {
  const client = queryClient || createTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>{children}</BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

// Custom render function with all providers
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient;
  initialEntries?: string[];
  useMemoryRouter?: boolean;
}

export function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions = {}
) {
  const {
    queryClient = createTestQueryClient(),
    initialEntries = ['/'],
    useMemoryRouter = false,
    ...renderOptions
  } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    const Router = useMemoryRouter ? MemoryRouter : BrowserRouter;
    const routerProps = useMemoryRouter ? { initialEntries } : {};

    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ToastProvider>
            <Router {...routerProps}>{children}</Router>
          </ToastProvider>
        </AuthProvider>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  };
}

// Render with memory router for testing navigation
export function renderWithRouter(
  ui: ReactElement,
  {
    initialEntries = ['/'],
    ...options
  }: CustomRenderOptions & { initialEntries?: string[] } = {}
) {
  return renderWithProviders(ui, {
    ...options,
    useMemoryRouter: true,
    initialEntries,
  });
}

// Mock user factories
export const mockUsers = {
  viewer: {
    id: 1,
    username: 'viewer_user',
    email: 'viewer@test.com',
    full_name: 'Viewer User',
    role: 'user' as const,
  },
  editor: {
    id: 2,
    username: 'editor_user',
    email: 'editor@test.com',
    full_name: 'Editor User',
    role: 'user' as const,  // Changed from 'editor' to 'user'
  },
  superAdmin: {
    id: 3,
    username: 'super_admin_user',
    email: 'admin@test.com',
    full_name: 'Super Admin',
    role: 'admin' as const,  // Changed from 'super_admin' to 'admin'
  },
  admin: {
    id: 3,
    username: 'admin_user',
    email: 'admin@test.com',
    full_name: 'Admin User',
    role: 'admin' as const,
  },
} satisfies Record<string, User>;

// Mock login response factory
export function createMockLoginResponse(user: User, expiresIn = 3600) {
  return {
    access_token: 'mock_jwt_token_' + Date.now(),
    token_type: 'bearer',
    user,
    expires_in: expiresIn,
  };
}

// Setup authenticated state in localStorage
export function setupAuthState(_user: User, expiresIn = 3600) {
  const futureTime = Math.floor(Date.now() / 1000) + expiresIn;
  localStorage.setItem('auth_token', 'valid_test_token');
  localStorage.setItem('expiresAt', futureTime.toString());
  return { token: 'valid_test_token', expiresAt: futureTime };
}

// Setup expired token state
export function setupExpiredAuthState() {
  const pastTime = Math.floor(Date.now() / 1000) - 3600;
  localStorage.setItem('auth_token', 'expired_token');
  localStorage.setItem('expiresAt', pastTime.toString());
  return { token: 'expired_token', expiresAt: pastTime };
}

// Clear auth state
export function clearAuthState() {
  localStorage.removeItem('auth_token');
  localStorage.removeItem('expiresAt');
}

// Wait for async operations
export const waitFor = async (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

// Mock API error factory
export function createApiError(
  status: number,
  message: string,
  details?: string[]
) {
  return {
    response: {
      status,
      data: {
        detail: message,
        details,
      },
    },
    message,
  };
}

// Re-export testing utilities
export { screen, fireEvent, waitFor as waitForElement } from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';
