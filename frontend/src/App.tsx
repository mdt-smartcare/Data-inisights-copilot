import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import ChatPage from './pages/ChatPage';
import AboutPage from './pages/AboutPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ConfigPage from './pages/ConfigPage';
import UsersPage from './pages/UsersPage';
import AuditLogsPage from './pages/AuditLogsPage';
import PromptHistoryPage from './pages/PromptHistoryPage';
import InsightsPage from './pages/InsightsPage';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import type { UserRole } from './types';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

// Protected route wrapper
function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { user, logout, isLoading } = useAuth();
  const token = localStorage.getItem('auth_token');
  const expiresAt = localStorage.getItem('expiresAt');

  // Check if token exists
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // Check if token has expired
  if (expiresAt) {
    const currentTime = Math.floor(Date.now() / 1000);
    const expirationTime = parseInt(expiresAt, 10);

    if (currentTime >= expirationTime) {
      // Token has expired, clear auth data
      logout();
      return <Navigate to="/login" replace />;
    }
  }

  if (isLoading) {
    return <div>Loading...</div>; // Or return null/spinner
  }

  if (allowedRoles && user?.role && !allowedRoles.includes(user.role)) {
    // User is not authorized for this route
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <ToastContainer
            position="top-center"
            autoClose={3000}
            hideProgressBar={true}
            newestOnTop={false}
            closeOnClick
            rtl={false}
            pauseOnFocusLoss
            draggable
            pauseOnHover
            theme="light"
            toastStyle={{
              background: '#ffffff',
              color: '#000000',
              fontSize: '15px',
              padding: '16px 48px 16px 16px',
            }}
          />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route
              path="/chat"
              element={
                <ProtectedRoute>
                  <ChatPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/config"
              element={
                <ProtectedRoute allowedRoles={['editor', 'super_admin']}>
                  <ConfigPage />
                </ProtectedRoute>
              }
            />
            <Route path="/about" element={<AboutPage />} />
            <Route
              path="/users"
              element={
                <ProtectedRoute allowedRoles={['super_admin']}>
                  <UsersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/audit"
              element={
                <ProtectedRoute allowedRoles={['super_admin']}>
                  <AuditLogsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/history"
              element={
                <ProtectedRoute allowedRoles={['editor', 'super_admin']}>
                  <PromptHistoryPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/insights"
              element={
                <ProtectedRoute allowedRoles={['editor', 'super_admin']}>
                  <InsightsPage />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;