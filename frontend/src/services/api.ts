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
  timeout: 60 * 1000,                         // 60 seconds - important for AI model responses
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
    // Skip authentication for public endpoints (login, register, health)
    const publicEndpoints = ['/auth/login', '/auth/register', '/health'];
    const isPublicEndpoint = publicEndpoints.some(endpoint => config.url?.includes(endpoint));

    if (isPublicEndpoint) {
      // Don't add auth headers or check token expiration for public endpoints
      return config;
    }

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
      // Don't redirect if this is a login/register attempt (let the page handle the error)
      const publicEndpoints = ['/auth/login', '/auth/register'];
      const isPublicEndpoint = publicEndpoints.some(endpoint => error.config?.url?.includes(endpoint));

      if (!isPublicEndpoint) {
        // 401 = Unauthorized (invalid/expired token)
        // Clean up authentication state
        localStorage.removeItem('auth_token');
        localStorage.removeItem('expiresAt');
        // Redirect to login page
        window.location.href = '/login';
      }
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
    // Extract error message from API response
    // FastAPI sends errors in 'detail' field, some APIs use 'message'
    return error.response?.data?.detail || error.response?.data?.message || error.message || 'An error occurred';
  }
  return 'An unexpected error occurred';
};

// ============================================================================
// SYSTEM PROMPT CONFIGURATION API
// ============================================================================

export const generateSystemPrompt = async (dataDictionary: string): Promise<{ draft_prompt: string }> => {
  const response = await apiClient.post('/api/v1/config/generate', { data_dictionary: dataDictionary });
  return response.data;
};

export const publishSystemPrompt = async (promptText: string): Promise<{ status: string; version: number }> => {
  // We need to fetch the user_id from the token or some auth context.
  // For now, let's decode the token or just send a dummy ID if the backend parses the token.
  // Looking at backend/api/routes/config.py, it expects `user_id` in the body.
  // In a real app, this should come from the user context. 
  // I'll grab it from localStorage if available, or use a placeholder "admin_user".
  const user = localStorage.getItem('user'); // Assuming user info might be stored
  let userId = 'admin';
  if (user) {
    try {
      const parsedUser = JSON.parse(user);
      userId = parsedUser.id || parsedUser.username || 'admin';
    } catch (e) {
      console.warn("Could not parse user from local storage", e);
    }
  }

  const response = await apiClient.post('/api/v1/config/publish', {
    prompt_text: promptText,
    user_id: userId
  });
  return response.data;
};

export const getActivePrompt = async (): Promise<{ prompt_text: string }> => {
  const response = await apiClient.get('/api/v1/config/active');
  return response.data;
};

