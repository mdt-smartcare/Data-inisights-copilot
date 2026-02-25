import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { APP_CONFIG } from '../config';
import { useAuth } from '../contexts/AuthContext';
import Alert from '../components/Alert';
import logo from '../assets/logo.svg';
import { ErrorCode } from '../constants/errorCodes';

// Error messages for different error codes (using ErrorCode constants as keys)
const ERROR_MESSAGES: Record<string, string> = {
  [ErrorCode.USER_INACTIVE]: 'Your account has been deactivated. Please contact your administrator.',
  [ErrorCode.TOKEN_EXPIRED]: 'Your session has expired. Please sign in again.',
  [ErrorCode.TOKEN_INVALID]: 'Invalid session. Please sign in again.',
};

/**
 * Login Page Component
 * 
 * Features:
 * - Keycloak OIDC authentication via redirect
 * - Automatic redirect if already authenticated
 * - Error display for failed login attempts
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { login, isAuthenticated, isLoading: authLoading, user } = useAuth();
  
  // Initialize error from URL params (lazy initializer to avoid effect)
  const [error, setError] = useState(() => {
    const errorCode = searchParams.get('error');
    return errorCode && ERROR_MESSAGES[errorCode] ? ERROR_MESSAGES[errorCode] : '';
  });
  const [isLoading, setIsLoading] = useState(false);

  // Clear error from URL after reading (one-time effect)
  useEffect(() => {
    if (searchParams.get('error')) {
      searchParams.delete('error');
      setSearchParams(searchParams, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Redirect if already authenticated
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      // Redirect based on role
      if (user?.role === 'admin') {
        navigate('/config', { replace: true });
      } else {
        navigate('/chat', { replace: true });
      }
    }
  }, [isAuthenticated, authLoading, navigate, user]);

  /**
   * Handle login button click
   * Redirects to Keycloak login page
   */
  const handleLogin = async () => {
    setError('');
    setIsLoading(true);

    try {
      await login();
      // login() redirects to Keycloak, so this line won't be reached
    } catch (err) {
      console.error('Login error:', err);
      setError(err instanceof Error ? err.message : 'Failed to initiate login');
      setIsLoading(false);
    }
  };

  // Show loading while checking auth status
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="animate-spin h-12 w-12 border-4 border-indigo-600 border-t-transparent rounded-full"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg">
        <div>
          <div className="flex justify-center mb-4">
            <img src={logo} alt="Logo" className="h-12" />
          </div>
          <h2 className="text-center text-3xl font-bold text-gray-900">
            {APP_CONFIG.APP_NAME}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign in to access the medical data assistant
          </p>
        </div>

        <div className="mt-8 space-y-6">
          {error && (
            <Alert
              type="error"
              message={error}
              onDismiss={() => setError('')}
            />
          )}

          <div>
            <button
              onClick={handleLogin}
              disabled={isLoading}
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Redirecting to login...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
                  </svg>
                  Sign in with Keycloak
                </>
              )}
            </button>
          </div>

          <div className="text-center">
            <p className="text-xs text-gray-500">
              You will be redirected to the secure login page
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
