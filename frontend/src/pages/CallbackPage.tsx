import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { oidcService } from '../services/oidcService';
import { apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { User } from '../types';

/**
 * OIDC Callback Page
 * 
 * Handles the redirect from Keycloak after successful authentication.
 * Processes the authorization code and exchanges it for tokens.
 */
export default function CallbackPage() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const callbackProcessed = useRef(false);

  useEffect(() => {
    const handleCallback = async () => {
      // Prevent double execution due to React StrictMode
      if (callbackProcessed.current) {
        return;
      }
      callbackProcessed.current = true;
      try {
        // Process the OIDC callback and exchange code for tokens
        const oidcUser = await oidcService.handleCallback();

        if (oidcUser && oidcUser.access_token) {
          // Fetch user profile from backend API
          const response = await apiClient.get<User>('/api/v1/auth/me');
          const userProfile = response.data;
          
          console.log('User profile from API:', userProfile);

          // Update auth context
          setUser(userProfile);

          // Redirect based on role
          if (userProfile.role === 'admin') {
            navigate('/insights', { replace: true });
          } else {
            navigate('/chat', { replace: true });
          }
        } else {
          setError('Authentication failed: No user returned');
        }
      } catch (err) {
        console.error('OIDC callback error:', err);
        setError(err instanceof Error ? err.message : 'Authentication failed');
      }
    };

    handleCallback();
  }, [navigate, setUser]);

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
