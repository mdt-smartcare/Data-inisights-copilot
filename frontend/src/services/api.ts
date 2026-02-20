import axios, { AxiosError } from 'axios';
import { API_BASE_URL } from '../config';
import { oidcService } from './oidcService';

/**
 * Configured Axios instance for all API requests
 * 
 * Features:
 * - Automatic OIDC token injection in request headers
 * - Token validation before each request
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

// Import User type
import type { User } from '../types';

/**
 * Request Interceptor
 * Runs before every API request to:
 * 1. Check if OIDC token is valid
 * 2. Automatically inject Authorization header with access token
 * 3. Handle token expiration
 */
apiClient.interceptors.request.use(
  async (config) => {
    // Skip authentication for public endpoints (health check)
    const publicEndpoints = ['/api/v1/health'];
    const isPublicEndpoint = publicEndpoints.some(endpoint => config.url?.includes(endpoint));

    if (isPublicEndpoint) {
      // Don't add auth headers for public endpoints
      return config;
    }

    try {
      // Get current access token from OIDC service
      const accessToken = await oidcService.getAccessToken();
      
      if (accessToken) {
        // Add Bearer token to all authenticated requests
        config.headers.Authorization = `Bearer ${accessToken}`;
      } else {
        // No token available, try silent renewal
        const user = await oidcService.renewToken();
        if (user?.access_token) {
          config.headers.Authorization = `Bearer ${user.access_token}`;
        }
      }
    } catch (error) {
      console.error('Error getting access token:', error);
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
 * 2. Trigger re-authentication via OIDC
 */
apiClient.interceptors.response.use(
  (response) => response,  // Pass successful responses through unchanged
  async (error: AxiosError) => {
    // Handle authentication errors globally
    if (error.response?.status === 401) {
      // Try to renew the token
      try {
        const user = await oidcService.renewToken();
        if (user && error.config) {
          // Retry the failed request with new token
          error.config.headers.Authorization = `Bearer ${user.access_token}`;
          return apiClient.request(error.config);
        }
      } catch (renewError) {
        console.error('Token renewal failed:', renewError);
      }
      
      // If renewal failed, redirect to login
      await oidcService.removeUser();
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
    // Extract error message from API response
    // FastAPI sends errors in 'detail' field, some APIs use 'message'
    return error.response?.data?.detail || error.response?.data?.message || error.message || 'An error occurred';
  }
  return 'An unexpected error occurred';
};

// ============================================================================
// SYSTEM PROMPT CONFIGURATION API
// ============================================================================

export const generateSystemPrompt = async (dataDictionary: string): Promise<{ draft_prompt: string; reasoning?: Record<string, string>; example_questions?: string[] }> => {
  const response = await apiClient.post('/api/v1/config/generate', { data_dictionary: dataDictionary });
  return response.data;
};

export const publishSystemPrompt = async (
  promptText: string,
  reasoning?: Record<string, string>,
  exampleQuestions?: string[],
  embeddingConfig?: any,
  retrieverConfig?: any,
  agentId?: number
): Promise<{ status: string; version: number }> => {
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
    user_id: userId,
    connection_id: (window as any).__config_connectionId,
    schema_selection: (window as any).__config_schema ? JSON.stringify((window as any).__config_schema) : null,
    data_dictionary: (window as any).__config_dictionary,
    reasoning: reasoning ? JSON.stringify(reasoning) : null,
    example_questions: exampleQuestions ? JSON.stringify(exampleQuestions) : null,
    embedding_config: embeddingConfig ? JSON.stringify(embeddingConfig) : null,
    retriever_config: retrieverConfig ? JSON.stringify(retrieverConfig) : null,
    agent_id: agentId
  });
  return response.data;
};

export const getPromptHistory = async (agentId?: number): Promise<any> => {
  const response = await apiClient.get('/api/v1/config/history', { params: { agent_id: agentId } });
  return response.data;
};

export const getActiveConfigMetadata = async (agentId?: number): Promise<any> => {
  const response = await apiClient.get('/api/v1/config/active-metadata', { params: { agent_id: agentId } });
  return response.data;
};

// ============================================================================
// AGENT API
// ============================================================================

import type { Agent } from '../types';

export const getAgents = async (): Promise<Agent[]> => {
  const response = await apiClient.get('/api/v1/agents');
  return response.data;
};

export const getUsers = async (): Promise<User[]> => {
  const response = await apiClient.get('/api/v1/users');
  return response.data;
};

export const getActivePrompt = async (agentId?: number): Promise<{ prompt_text: string }> => {
  const response = await apiClient.get('/api/v1/config/active', { params: { agent_id: agentId } });
  return response.data;
};

export const createAgent = async (data: { name: string; description?: string; type: string; system_prompt?: string }): Promise<Agent> => {
  const response = await apiClient.post('/api/v1/agents', data);
  return response.data;
};

export const assignUserToAgent = async (agentId: number, userId: number, role: string): Promise<{ status: string }> => {
  const response = await apiClient.post(`/api/v1/agents/${agentId}/users`, { user_id: userId, role });
  return response.data;
};

export const revokeUserAccess = async (agentId: number, userId: number): Promise<{ status: string }> => {
  const response = await apiClient.delete(`/api/v1/agents/${agentId}/users/${userId}`);
  return response.data;
};


// ============================================================================
// DATA SETUP & CONNECTION API (Phase 6 & 7)
// ============================================================================

export const getUserProfile = async (): Promise<User> => {
  const response = await apiClient.get('/api/v1/auth/me');
  return response.data;
};

export interface DbConnection {
  id: number;
  name: string;
  uri: string;
  engine_type: string;
  created_at: string;
  pool_config?: string;
}

export const getConnections = async (): Promise<DbConnection[]> => {
  const response = await apiClient.get('/api/v1/data/connections');
  return response.data;
};

export const saveConnection = async (name: string, uri: string, engine_type: string = 'postgresql', pool_config?: any): Promise<{ status: string; id: number }> => {
  // Get user ID similar to publishSystemPrompt
  const user = localStorage.getItem('user');
  let userId = 'admin';
  if (user) {
    try {
      const parsedUser = JSON.parse(user);
      userId = parsedUser.id || parsedUser.username || 'admin';
    } catch (e) {
      console.warn(e);
    }
  }

  const response = await apiClient.post('/api/v1/data/connections', {
    name,
    uri,
    engine_type,
    created_by: userId,
    pool_config: pool_config ? JSON.stringify(pool_config) : null
  });
  return response.data;
};

export const deleteConnection = async (id: number): Promise<{ status: string }> => {
  const response = await apiClient.delete(`/api/v1/data/connections/${id}`);
  return response.data;
};

export const getConnectionSchema = async (id: number): Promise<{ status: string; connection: string; schema: { tables: string[]; details: any } }> => {
  const response = await apiClient.get(`/api/v1/data/connections/${id}/schema`);
  return response.data;
};

// ============================================================================
// EMBEDDING JOBS API
// ============================================================================

import type {
  EmbeddingJobProgress,
  EmbeddingJobSummary,
  EmbeddingJobCreate,
  Notification,
  NotificationPreferences,
  NotificationPreferencesUpdate
} from '../types/rag';

/**
 * Start a new embedding generation job.
 * Requires SuperAdmin role.
 */
export const startEmbeddingJob = async (params: EmbeddingJobCreate): Promise<{ status: string; job_id: string; message: string }> => {
  const response = await apiClient.post('/api/v1/embedding-jobs', params);
  return response.data;
};

/**
 * Get progress of an embedding job.
 */
export const getEmbeddingProgress = async (jobId: string): Promise<EmbeddingJobProgress> => {
  const response = await apiClient.get(`/api/v1/embedding-jobs/${jobId}/progress`);
  return response.data;
};

/**
 * Get summary of a completed embedding job.
 */
export const getEmbeddingSummary = async (jobId: string): Promise<EmbeddingJobSummary> => {
  const response = await apiClient.get(`/api/v1/embedding-jobs/${jobId}/summary`);
  return response.data;
};

/**
 * Cancel a running embedding job.
 */
export const cancelEmbeddingJob = async (jobId: string): Promise<{ status: string; job_id: string; message: string }> => {
  const response = await apiClient.post(`/api/v1/embedding-jobs/${jobId}/cancel`);
  return response.data;
};

/**
 * List embedding jobs with optional filtering.
 */
export const listEmbeddingJobs = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<EmbeddingJobProgress[]> => {
  const response = await apiClient.get('/api/v1/embedding-jobs', { params });
  return response.data;
};

// ============================================================================
// NOTIFICATIONS API
// ============================================================================

/**
 * Get notifications for the current user.
 */
export const getNotifications = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<Notification[]> => {
  const response = await apiClient.get('/api/v1/notifications', { params });
  return response.data;
};

/**
 * Get count of unread notifications.
 */
export const getUnreadNotificationCount = async (): Promise<{ count: number }> => {
  const response = await apiClient.get('/api/v1/notifications/unread-count');
  return response.data;
};

/**
 * Get a specific notification.
 */
export const getNotification = async (notificationId: number): Promise<Notification> => {
  const response = await apiClient.get(`/api/v1/notifications/${notificationId}`);
  return response.data;
};

/**
 * Mark a notification as read.
 */
export const markNotificationAsRead = async (notificationId: number): Promise<{ success: boolean }> => {
  const response = await apiClient.post(`/api/v1/notifications/${notificationId}/read`);
  return response.data;
};

/**
 * Mark all notifications as read.
 */
export const markAllNotificationsAsRead = async (): Promise<{ success: boolean; marked_count: number }> => {
  const response = await apiClient.post('/api/v1/notifications/read-all');
  return response.data;
};

/**
 * Dismiss a notification.
 */
export const dismissNotification = async (notificationId: number): Promise<{ success: boolean }> => {
  const response = await apiClient.post(`/api/v1/notifications/${notificationId}/dismiss`);
  return response.data;
};

/**
 * Get notification preferences for the current user.
 */
export const getNotificationPreferences = async (): Promise<NotificationPreferences> => {
  const response = await apiClient.get('/api/v1/notifications/preferences');
  return response.data;
};

/**
 * Update notification preferences.
 */
export const updateNotificationPreferences = async (preferences: NotificationPreferencesUpdate): Promise<{ success: boolean }> => {
  const response = await apiClient.put('/api/v1/notifications/preferences', preferences);
  return response.data;
};

// ============================================================================
// OBSERVABILITY API
// ============================================================================

export const getObservabilityConfig = async () => {
  const response = await apiClient.get('/api/v1/observability/config');
  return response.data;
};

export const updateObservabilityConfig = async (config: any) => {
  const response = await apiClient.put('/api/v1/observability/config', config);
  return response.data;
};

export const getUsageStats = async (period: string = '24h') => {
  const response = await apiClient.get(`/api/v1/observability/usage?period=${period}`);
  return response.data;
};

export const testLogEmission = async (level: string, message: string) => {
  const response = await apiClient.post(`/api/v1/observability/test-log?level=${level}&message=${encodeURIComponent(message)}`);
  return response.data;
};
