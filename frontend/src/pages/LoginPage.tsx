import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import { API_ENDPOINTS } from '../config';
import { useAuth } from '../contexts/AuthContext';
import type { LoginResponse } from '../types';

/**
 * Login Page Component
 * 
 * Features:
 * - Username/password authentication
 * - JWT token storage with expiration tracking
 * - Automatic redirect to chat page on success
 * - Error display for failed login attempts
 * - Link to registration page for new users
 */
export default function LoginPage() {
  // Form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');          // Display error messages
  const [isLoading, setIsLoading] = useState(false);  // Disable form during login
  const navigate = useNavigate();
  const { setUser } = useAuth();  // Update global authentication state

  /**
   * Handle login form submission
   * Authenticates user and stores JWT token with expiration time
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();  // Prevent default form submission
    setError('');        // Clear previous errors
    setIsLoading(true);  // Disable submit button

    try {
      // Send login request to backend
      const response = await apiClient.post<LoginResponse>(API_ENDPOINTS.AUTH.LOGIN, {
        username,
        password,
      });

      // Calculate absolute expiration time (Unix timestamp)
      // expires_in is in seconds, Date.now() is in milliseconds
      const expiresAt = Math.floor(Date.now() / 1000) + response.data.expires_in;

      // Store JWT token and expiration in localStorage
      // This persists across page refreshes but not browser restarts (for security)
      localStorage.setItem('auth_token', response.data.access_token);
      localStorage.setItem('expiresAt', expiresAt.toString());

      // Update global auth state with complete user object
      // This includes username, email, full_name, and role from backend
      // Use optional chaining for optional fields (email, full_name, role)
      setUser({
        username: response.data.user.username,
        email: response.data.user?.email,
        full_name: response.data.user?.full_name,
        role: response.data.user?.role
      });

      // Redirect to chat page (protected route)
      navigate('/chat');
    } catch (err) {
      // Display error message to user
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);  // Re-enable submit button
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg">
        <div>
          <h2 className="text-center text-3xl font-bold text-gray-900">
            FHIR RAG Assistant
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign in to access the medical data assistant
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Enter your username"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Enter your password"
              />
            </div>
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Signing in...' : 'Sign in'}
            </button>
          </div>

          <div className="text-center">
            <p className="text-sm text-gray-600">
              Don't have an account?{' '}
              <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-500">
                Sign up
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
