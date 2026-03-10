import { useEffect, useState, useRef } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { oidcService } from '../services/oidcService';
import { useAuth } from '../contexts/AuthContext';
import { roleAtLeast } from '../utils/permissions';

/**
 * Check if the URL contains OIDC error response (e.g., from silent auth failure)
 * This happens when silent authentication with prompt=none fails
 */
function getOidcError(): { error: string; description?: string } | null {
  const params = new URLSearchParams(window.location.search);
  const error = params.get('error');
  if (error) {
    return {
      error,
      description: params.get('error_description') || undefined,
    };
  }
  return null;
}

/**
 * OIDC Callback Page
 * 
 * Handles the redirect from Keycloak after successful authentication.
 * For new tab flow: processes the callback, signals main window, and closes tab.
 * For redirect flow (fallback): shows success message.
 * Also handles error responses from failed silent auth (prompt=none).
 */
export default function CallbackPage() {
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const callbackProcessed = useRef(false);

  useEffect(() => {
    // Skip callback processing if already authenticated
    if (isAuthenticated) {
      return;
    }

    const handleCallback = async () => {
      // Prevent double execution due to React StrictMode
      if (callbackProcessed.current) {
        return;
      }
      callbackProcessed.current = true;
      
      try {
        // Check if this is an error response (e.g., from silent auth failure)
        const oidcError = getOidcError();
        if (oidcError) {
          // Handle expected silent auth errors silently - just redirect to login
          if (oidcError.error === 'login_required' || 
              oidcError.error === 'interaction_required' ||
              oidcError.error === 'consent_required') {
            // This is normal when user isn't logged in and silent auth is attempted
            // Redirect to login without showing an error
            navigate('/login', { replace: true });
            return;
          }
          // For other errors, show them to the user
          setError(oidcError.description || `Authentication error: ${oidcError.error}`);
          return;
        }
        
        // Check if this is a callback (has auth code in URL)
        if (oidcService.isTabCallback()) {
          // Process callback - stores tokens, signals main window, and closes tab
          await oidcService.handleTabCallback();
          // If tab didn't close (manual navigation), show success message
          setSuccess(true);
          return;
        }
        
        // Fallback: If not a callback, redirect to login
        navigate('/login', { replace: true });
      } catch (err) {
        console.error('OIDC callback error:', err);
        setError(err instanceof Error ? err.message : 'Authentication failed');
      }
    };

    handleCallback();
  }, [isAuthenticated, navigate]);

  // If already authenticated (e.g., user pressed back button), redirect immediately
  if (isAuthenticated && user) {
    const redirectPath = roleAtLeast(user.role, 'admin') ? '/agents' : '/chat';
    return <Navigate to={redirectPath} replace />;
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
        <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg text-center">
          <div className="text-red-600">
            <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-900">Authentication Error</h2>
          <p className="text-gray-600">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            Return to Login
          </button>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
        <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg text-center">
          <div className="text-green-600">
            <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-900">Sign In Successful!</h2>
          <p className="text-gray-600">You can close this tab and return to the application.</p>
          <button
            onClick={() => window.close()}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
          >
            Close Tab
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg text-center">
        <div className="animate-spin mx-auto h-12 w-12 border-4 border-indigo-600 border-t-transparent rounded-full"></div>
        <h2 className="text-2xl font-bold text-gray-900">Completing Sign In...</h2>
        <p className="text-gray-600">Please wait while we authenticate you.</p>
      </div>
    </div>
  );
}
