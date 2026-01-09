import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import { apiClient, handleApiError } from '../services/api';
import { API_ENDPOINTS } from '../config';
import type { RegisterRequest, RegisterResponse } from '../types';

export default function RegisterPage() {
  const [formData, setFormData] = useState<RegisterRequest>({
    username: '',
    password: '',
    email: '',
    full_name: '',
  });
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value?.trim()||"" }));
  };

  const validateForm = (): boolean => {
    if (formData.username.length < 3) {
      setError('Username must be at least 3 characters long');
      return false;
    }

    if (formData.password.length < 6) {
      setError('Password must be at least 6 characters long');
      return false;
    }

    if (formData.password !== confirmPassword) {
      setError('Passwords do not match');
      return false;
    }

    return true;
  };

  /**
   * Handle form submission
   * Validates form, sends registration request to backend, and redirects on success
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();  // Prevent default form submission behavior
    setError('');        // Clear any previous errors

    // Run client-side validation first
    if (!validateForm()) {
      return;  // Stop if validation fails
    }

    setIsLoading(true);  // Disable form during API call

    try {
      // Build payload with only required fields initially
      const payload: RegisterRequest = {
        username: formData.username,
        password: formData.password,
      };

      // Add optional fields only if they have values
      // This prevents sending empty strings to the backend
      if (formData.email?.trim()) {
        payload.email = formData.email;
      }

      if (formData.full_name?.trim()) {
        payload.full_name = formData.full_name;
      }

      // Send registration request to backend
      await apiClient.post<RegisterResponse>(API_ENDPOINTS.AUTH.REGISTER, payload);

      // Registration successful - show toast and redirect
      toast.success('Account created successfully! Redirecting to login...', {
        autoClose: 2000,
      });
      
      // Redirect to login page after 1.5 seconds
      setTimeout(() => {
        navigate('/login');
      }, 1500);
    } catch (err: any) {
      // Handle errors from backend
      // Backend may return validation errors in details array
      if (err.response?.data?.details) {
        setError(err.response.data.details.join(', '));
      } else {
        // Generic error handling
        setError(handleApiError(err));
      }
    } finally {
      setIsLoading(false);  // Re-enable form
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg">
        <div>
          <h2 className="text-center text-3xl font-bold text-gray-900">
            Create Account
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign up to access the FHIR RAG Assistant
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            {/* Username - Required */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                Username <span className="text-red-500">*</span>
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                value={formData.username}
                onChange={handleChange}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Choose a username (min 3 characters)"
                minLength={3}
              />
            </div>

            {/* Full Name - Optional */}
            <div>
              <label htmlFor="full_name" className="block text-sm font-medium text-gray-700">
                Full Name
              </label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                value={formData.full_name}
                onChange={handleChange}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Your full name (optional)"
              />
            </div>

            {/* Email - Optional */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                value={formData.email}
                onChange={handleChange}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="your.email@example.com (optional)"
              />
            </div>

            {/* Password - Required */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password <span className="text-red-500">*</span>
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                value={formData.password}
                onChange={handleChange}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Choose a password (min 6 characters)"
                minLength={6}
              />
            </div>

            {/* Confirm Password */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
                Confirm Password <span className="text-red-500">*</span>
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Confirm your password"
                minLength={6}
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
              {isLoading ? 'Creating account...' : 'Create Account'}
            </button>
          </div>

          <div className="text-center">
            <p className="text-sm text-gray-600">
              Already have an account?{' '}
              <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500">
                Sign in
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
