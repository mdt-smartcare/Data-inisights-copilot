import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './components/Toast';
import { SystemSettingsProvider } from './contexts/SystemSettingsContext';
import ChatPage from './pages/ChatPage';
import AboutPage from './pages/AboutPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import AgentsPage from './pages/AgentsPage';
import AgentDashboardPage from './pages/AgentDashboardPage';
import AgentConfigPage from './pages/AgentConfigPage';
import UsersPage from './pages/UsersPage';
import AuditLogsPage from './pages/AuditLogsPage';
import CallbackPage from './pages/CallbackPage';
import DataSourcesPage from './pages/DataSourcesPage';
import AIRegistryPage from './pages/AIRegistryPage';

import { AuthProvider, useAuth } from './contexts/AuthContext';
import type { UserRole } from './types';
import { roleAtLeast } from './utils/permissions';

// Create a client with disabled retries to prevent infinite API loops
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,           // Disable retries to prevent infinite loops on 404/500
      staleTime: 5 * 60 * 1000, // 5 minutes - reduce unnecessary refetches
    },
    mutations: {
      retry: false,
    },
  },
});

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

// Default redirect component - routes users based on their role
function DefaultRedirect() {
  const { user, isLoading, isAuthenticated } = useAuth();

  // If not authenticated, go to login
  if (!isAuthenticated && !isLoading) {
    return <Navigate to="/login" replace />;
  }

  // Wait for user to load
  if (isLoading) {
    return <div>Loading...</div>;
  }

  // Redirect based on role - super_admin and admin go to agents page
  if (roleAtLeast(user?.role, 'admin')) {
    return <Navigate to="/agents" replace />;
  }

  // Default to chat for all other users
  return <Navigate to="/chat" replace />;
}

// Protected route wrapper
function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { user, isLoading, isAuthenticated } = useAuth();

  // Wait for auth state to load
  if (isLoading) {
    return <div>Loading...</div>;
  }

  // Check if authenticated via OIDC
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check role authorization using hierarchy
  if (allowedRoles && user?.role) {
    const hasAccess = allowedRoles.some(allowedRole =>
      roleAtLeast(user.role, allowedRole)
    );
    if (!hasAccess) {
      return <Navigate to="/chat" replace />;
    }
  }

  return <>{children}</>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SystemSettingsProvider>
          <ToastProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/callback" element={<CallbackPage />} />
                <Route path="/" element={<DefaultRedirect />} />
                <Route
                  path="/chat"
                  element={
                    <ProtectedRoute>
                      <ChatPage />
                    </ProtectedRoute>
                  }
                />

                {/* Agent routes */}
                <Route
                  path="/agents"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <AgentsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/agents/:id"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <AgentDashboardPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/agents/:id/config"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <AgentConfigPage />
                    </ProtectedRoute>
                  }
                />

                {/* Backward compatibility redirect */}
                <Route
                  path="/config"
                  element={<Navigate to="/agents" replace />}
                />

                <Route path="/about" element={<AboutPage />} />

                <Route
                  path="/users"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <UsersPage />
                    </ProtectedRoute>
                  }
                />

                <Route
                  path="/audit"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <AuditLogsPage />
                    </ProtectedRoute>
                  }
                />

                <Route
                  path="/data-sources"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <DataSourcesPage />
                    </ProtectedRoute>
                  }
                />

                <Route
                  path="/ai-registry"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <AIRegistryPage />
                    </ProtectedRoute>
                  }
                />

                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </ToastProvider>
        </SystemSettingsProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;