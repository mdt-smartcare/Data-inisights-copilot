import axios, { AxiosError } from 'axios';
import { API_BASE_URL } from '../config';

/**
 * Configured Axios instance for all API requests
 * 
 * Features:
 * - Automatic JWT token injection in request headers
 * - Token expiration checking before each request
 * - Automatic redirect to login on authentication errors
 * - 60 second timeout for requests
 * 
 * Usage:
 *   import { apiClient } from '../services/api';
 *   const response = await apiClient.post('/endpoint', data);
 */
export const apiClient = axios.create({
  baseURL: API_BASE_URL,                    // Base URL from config (e.g., http://localhost:8000/api/v1)
  headers: {
    'Content-Type': 'application/json',     // Default content type for all requests
  },
  timeout: 60*1000,                         // 60 seconds - important for AI model responses
});

/**
 * Request Interceptor
 * Runs before every API request to:
 * 1. Check if JWT token has expired (prevents unnecessary API calls)
 * 2. Automatically inject Authorization header with JWT token
 * 3. Redirect to login if token is expired
 */
apiClient.interceptors.request.use(
  (config) => {
    // Check token expiration before making request
    const expiresAt = localStorage.getItem('expiresAt');
    if (expiresAt) {
      const currentTime = Math.floor(Date.now() / 1000);  // Current time in seconds
      const expirationTime = parseInt(expiresAt, 10);      // Token expiration in seconds
      
      if (currentTime >= expirationTime) {
        // Token has expired - clean up and redirect
        localStorage.removeItem('auth_token');
        localStorage.removeItem('expiresAt');
        window.location.href = '/login';
        return Promise.reject(new Error('Token expired'));
      }
    }
    
    // Automatically add Authorization header if token exists
    const token = localStorage.getItem('auth_token');
    if (token) {
      // Add Bearer token to all authenticated requests
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response Interceptor
 * Runs after every API response to:
 * 1. Handle 401 Unauthorized errors globally
 * 2. Clear expired/invalid tokens
 * 3. Redirect to login on authentication failure
 */
apiClient.interceptors.response.use(
  (response) => response,  // Pass successful responses through unchanged
  (error: AxiosError) => {
    // Handle authentication errors globally
    if (error.response?.status === 401) {
      // 401 = Unauthorized (invalid/expired token)
      // Clean up authentication state
      localStorage.removeItem('auth_token');
      localStorage.removeItem('expiresAt');
      // Redirect to login page
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

/**
 * Centralized error message extractor
 * Converts various error types into user-friendly messages
 * 
 * @param error - Error from API call (any type)
 * @returns User-friendly error message string
 * 
 * Usage:
 *   try {
 *     await apiClient.post('/endpoint', data);
 *   } catch (err) {
 *     const message = handleApiError(err);
 *     setError(message);
 *   }
 */
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    // Extract error message from API response, fallback to generic message
    return error.response?.data?.message || error.message || 'An error occurred';
  }
  return 'An unexpected error occurred';
};
