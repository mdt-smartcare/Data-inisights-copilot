You are tasked with writing comprehensive test suites for a React TypeScript frontend application using Vitest and React Testing Library.

PROJECT CONTEXT:
- Frontend stack: React 18, TypeScript, Vite, React Router v6, TanStack Query
- Testing framework: Vitest with React Testing Library
- UI framework: Tailwind CSS
- State management: React Context (AuthContext)
- Features: Authentication, role-based access control, chat interface, configuration management, user management, audit logs

TESTING REQUIREMENTS:

1. **Test File Organization**:
   - Place tests in `__tests__` folders or alongside components as `.test.tsx` files
   - Follow naming convention: `ComponentName.test.tsx`
   - Group related tests using `describe` blocks

2. **Coverage Areas**:
   - **Components**: All UI components in `src/components/`
   - **Pages**: All page components in `src/pages/`
   - **Contexts**: AuthContext and other context providers
   - **Hooks**: Custom hooks in `src/hooks/`
   - **Services**: API and service functions in `src/services/`
   - **Utils**: Utility functions in `src/utils/`
   - **Routing**: Protected routes and navigation logic

3. **Test Types**:
   - Unit tests for individual functions and components
   - Integration tests for component interactions
   - Router tests for navigation and protected routes
   - Mock API calls and responses
   - Test authentication flows and role-based access

4. **Testing Patterns**:
   - Mock external dependencies (React Router, TanStack Query, API calls)
   - Test user interactions (clicks, form inputs, navigation)
   - Test conditional rendering based on props/state
   - Test error states and loading states
   - Test accessibility (a11y) where applicable
   - Test role-based permissions (viewer, editor, super_admin)

5. **Setup Requirements**:
   - Create test utilities for common setup (render with providers, mock auth context)
   - Mock localStorage for auth token management
   - Mock fetch/axios for API calls
   - Setup MSW (Mock Service Worker) for API mocking if needed

6. **Specific Test Cases**:
   - Login/Register flows with validation
   - Protected route access based on user roles
   - Token expiration handling
   - Chat message sending and receiving
   - File upload (dictionary, schema)
   - Configuration updates
   - User management CRUD operations
   - Audit log filtering and display
   - Prompt history and insights
   - Error boundary behavior
   - Toast notifications

7. **Code Quality**:
   - Use TypeScript types for test data
   - Follow AAA pattern (Arrange, Act, Assert)
   - Write descriptive test names
   - Avoid test interdependencies
   - Clean up after tests (cleanup timers, listeners)

8. **Example Test Structure**:
```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';

// Test setup helper
const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          {ui}
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
};

describe('ComponentName', () => {
  it('should render correctly', () => {
    // Test implementation
  });
});

For each file in the project, generate:

1.Complete test suite with multiple test cases
2.Mock setup for dependencies
3.Edge case testing
4.Error handling tests
5.Integration tests where applicable

Start with the most critical paths (authentication, protected routes, chat functionality) and work through all components systematically.



---

Now here's the specific test file for [ProtectedRoute](http://_vscodecontentref_/0):

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import * as AuthContext from './contexts/AuthContext';
import type { User } from './types';

// Mock AuthContext
vi.mock('./contexts/AuthContext', async () => {
  const actual = await vi.importActual('./contexts/AuthContext');
  return {
    ...actual,
    useAuth: vi.fn(),
  };
});

// Mock page components
vi.mock('./pages/ChatPage', () => ({ default: () => <div>Chat Page</div> }));
vi.mock('./pages/ConfigPage', () => ({ default: () => <div>Config Page</div> }));
vi.mock('./pages/UsersPage', () => ({ default: () => <div>Users Page</div> }));
vi.mock('./pages/AuditLogsPage', () => ({ default: () => <div>Audit Logs Page</div> }));
vi.mock('./pages/PromptHistoryPage', () => ({ default: () => <div>Prompt History Page</div> }));
vi.mock('./pages/InsightsPage', () => ({ default: () => <div>Insights Page</div> }));
vi.mock('./pages/LoginPage', () => ({ default: () => <div>Login Page</div> }));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const renderApp = (initialRoute = '/') => {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/*" element={<App />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('ProtectedRoute', () => {
  const mockUseAuth = vi.mocked(AuthContext.useAuth);
  const mockLogout = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Authentication checks', () => {
    it('should redirect to login when no token exists', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/chat');
      expect(screen.getByText('Login Page')).toBeInTheDocument();
    });

    it('should redirect to login when token is expired', () => {
      const expiredTime = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      localStorage.setItem('auth_token', 'expired_token');
      localStorage.setItem('expiresAt', expiredTime.toString());

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/chat');
      expect(mockLogout).toHaveBeenCalled();
      expect(screen.getByText('Login Page')).toBeInTheDocument();
    });

    it('should show loading state while user is loading', () => {
      localStorage.setItem('auth_token', 'valid_token');
      
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/chat');
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('should render protected content when authenticated with valid token', () => {
      const futureTime = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());

      const mockUser: User = {
        id: '1',
        username: 'testuser',
        role: 'viewer',
        email: 'test@example.com',
        is_active: true,
        created_at: new Date().toISOString(),
      };

      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/chat');
      expect(screen.getByText('Chat Page')).toBeInTheDocument();
    });
  });

  describe('Role-based access control', () => {
    const futureTime = Math.floor(Date.now() / 1000) + 3600;

    beforeEach(() => {
      localStorage.setItem('auth_token', 'valid_token');
      localStorage.setItem('expiresAt', futureTime.toString());
    });

    it('should allow viewer to access chat page', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', username: 'viewer', role: 'viewer', email: 'v@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/chat');
      expect(screen.getByText('Chat Page')).toBeInTheDocument();
    });

    it('should redirect viewer from config page to chat', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', username: 'viewer', role: 'viewer', email: 'v@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/config');
      expect(screen.getByText('Chat Page')).toBeInTheDocument();
    });

    it('should allow editor to access config page', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '2', username: 'editor', role: 'editor', email: 'e@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/config');
      expect(screen.getByText('Config Page')).toBeInTheDocument();
    });

    it('should allow editor to access history page', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '2', username: 'editor', role: 'editor', email: 'e@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/history');
      expect(screen.getByText('Prompt History Page')).toBeInTheDocument();
    });

    it('should allow editor to access insights page', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '2', username: 'editor', role: 'editor', email: 'e@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/insights');
      expect(screen.getByText('Insights Page')).toBeInTheDocument();
    });

    it('should redirect editor from users page to chat', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '2', username: 'editor', role: 'editor', email: 'e@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/users');
      expect(screen.getByText('Chat Page')).toBeInTheDocument();
    });

    it('should allow super_admin to access all pages', () => {
      const superAdmin = {
        user: { id: '3', username: 'admin', role: 'super_admin' as const, email: 'a@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      };

      mockUseAuth.mockReturnValue(superAdmin);
      renderApp('/users');
      expect(screen.getByText('Users Page')).toBeInTheDocument();

      mockUseAuth.mockReturnValue(superAdmin);
      renderApp('/audit');
      expect(screen.getByText('Audit Logs Page')).toBeInTheDocument();

      mockUseAuth.mockReturnValue(superAdmin);
      renderApp('/config');
      expect(screen.getByText('Config Page')).toBeInTheDocument();
    });

    it('should redirect non-super_admin from audit logs to chat', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '2', username: 'editor', role: 'editor', email: 'e@test.com', is_active: true, created_at: '' },
        isLoading: false,
        logout: mockLogout,
        login: vi.fn(),
        register: vi.fn(),
      });

      renderApp('/audit');
      expect(screen.getByText('Chat Page')).toBeInTheDocument();
    });
  });
});


keep no try to achive high code coverage 80% good 90% is excellent. aim for 90%