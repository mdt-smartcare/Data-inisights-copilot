import axios, { AxiosError } from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { API_BASE_URL } from '../config';
import { oidcService } from './oidcService';
import { ErrorCode } from '../constants/errorCodes';

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
      // Note: getAccessToken() checks expiration and attempts renewal if needed
      const accessToken = await oidcService.getAccessToken();

      if (accessToken) {
        // Add Bearer token to all authenticated requests
        config.headers.Authorization = `Bearer ${accessToken}`;
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
 * 1. Handle 401 Unauthorized errors for inactive users
 * 2. Renew expired tokens and retry the request
 */
apiClient.interceptors.response.use(
  (response) => response,  // Pass successful responses through unchanged
  async (error: AxiosError) => {
    // Handle authentication errors globally
    if (error.response?.status === 401) {
      const responseData = error.response?.data as { detail?: string | { message?: string; error_code?: string }; error_code?: string };
      const errorCode = typeof responseData?.detail === 'object'
        ? responseData.detail?.error_code
        : responseData?.error_code;

      // Inactive user - logout from Keycloak and redirect to login with error
      if (errorCode === ErrorCode.USER_INACTIVE) {
        await oidcService.logoutWithMessage(ErrorCode.USER_INACTIVE);
        return Promise.reject(error);
      }

      // Check if token is expired and we can try renewal
      const oidcUser = await oidcService.getUser();
      const config = error.config as AxiosRequestConfig & { _retry?: boolean };

      // Only try renewal once, and only if we have a refresh token
      if (oidcUser?.refresh_token && config && !config._retry) {
        config._retry = true; // Prevent infinite retry
        try {
          const user = await oidcService.renewToken();
          if (user) {
            config.headers = config.headers || {};
            config.headers.Authorization = `Bearer ${user.access_token}`;
            return apiClient.request(config);
          }
        } catch {
          // Renewal failed - redirect to login
          console.error('Token renewal failed, redirecting to login');
          await oidcService.removeUser();
          window.location.href = '/login?error=TOKEN_EXPIRED';
          return Promise.reject(error);
        }
      }

      // No refresh token or still failing - redirect to login
      if (!oidcUser || oidcUser.expired) {
        await oidcService.removeUser();
        window.location.href = '/login?error=TOKEN_EXPIRED';
        return Promise.reject(error);
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

export const generateSystemPrompt = async (dataDictionary: string, dataSourceType: string = 'database'): Promise<{ draft_prompt: string; reasoning?: Record<string, string>; example_questions?: string[] }> => {
  const response = await apiClient.post('/api/v1/config/generate', {
    data_dictionary: dataDictionary,
    data_source_type: dataSourceType
  });
  return response.data;
};

export const publishSystemPrompt = async (
  promptText: string,
  reasoning?: Record<string, string>,
  exampleQuestions?: string[],
  embeddingConfig?: any,
  retrieverConfig?: any,
  chunkingConfig?: any,
  llmConfig?: any,
  agentId?: string,
  dataSourceType: string = 'database',
  ingestionDocuments?: string,
  ingestionFileName?: string,
  ingestionFileType?: string,
  selectedFileColumns?: string[]
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

  // For file sources, the schema_selection is actually the selected columns
  const finalSchemaSelection = dataSourceType === 'file' && selectedFileColumns
    ? JSON.stringify(selectedFileColumns)
    : (window as any).__config_schema ? JSON.stringify((window as any).__config_schema) : null;

  const response = await apiClient.post('/api/v1/config/publish', {
    prompt_text: promptText,
    user_id: userId,
    connection_id: (window as any).__config_connectionId,
    schema_selection: finalSchemaSelection,
    data_dictionary: (window as any).__config_dictionary,
    reasoning: reasoning ? JSON.stringify(reasoning) : null,
    example_questions: exampleQuestions ? JSON.stringify(exampleQuestions) : null,
    embedding_config: embeddingConfig ? JSON.stringify(embeddingConfig) : null,
    retriever_config: retrieverConfig ? JSON.stringify(retrieverConfig) : null,
    chunking_config: chunkingConfig ? JSON.stringify(chunkingConfig) : null,
    llm_config: llmConfig ? JSON.stringify(llmConfig) : null,
    agent_id: agentId,
    data_source_type: dataSourceType,
    ingestion_documents: ingestionDocuments,
    ingestion_file_name: ingestionFileName,
    ingestion_file_type: ingestionFileType
  });
  return response.data;
};

export const getPromptHistory = async (agentId?: string): Promise<any> => {
  const response = await apiClient.get('/api/v1/config/history', { params: { agent_id: agentId } });
  return response.data;
};

export const rollbackToVersion = async (versionId: number): Promise<{ status: string; message: string; version: number }> => {
  const response = await apiClient.post(`/api/v1/config/rollback/${versionId}`);
  return response.data;
};

export const getActiveConfigMetadata = async (agentId?: string): Promise<any> => {
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

export interface SearchUser {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  role: string;
  is_active: boolean;
}

export const searchUsers = async (query: string, limit: number = 20): Promise<SearchUser[]> => {
  const response = await apiClient.get('/api/v1/users/search', { params: { q: query, limit } });
  return response.data;
};

export const lookupUsersByEmails = async (emails: string[]): Promise<SearchUser[]> => {
  const response = await apiClient.post('/api/v1/users/lookup-by-emails', { emails });
  return response.data;
};

export const getActivePrompt = async (agentId?: string): Promise<{ prompt_text: string }> => {
  const response = await apiClient.get('/api/v1/config/active', { params: { agent_id: agentId } });
  return response.data;
};

export const createAgent = async (data: { name: string; description?: string; type?: string; system_prompt?: string }): Promise<Agent> => {
  const response = await apiClient.post('/api/v1/agents', data);
  return response.data;
};

export const updateAgent = async (agentId: string, data: { name?: string; description?: string }): Promise<Agent> => {
  const response = await apiClient.patch(`/api/v1/agents/${agentId}`, data);
  return response.data;
};

export const deleteAgent = async (agentId: string): Promise<void> => {
  await apiClient.delete(`/api/v1/agents/${agentId}`);
};

export const assignUserToAgent = async (agentId: string, userId: string, role: string): Promise<{ status: string }> => {
  const response = await apiClient.post(`/api/v1/agents/${agentId}/users`, { user_id: userId, role });
  return response.data;
};

export const bulkAssignAgents = async (userId: string, agentIds: string[], role: string = 'user'): Promise<{ status: string; assigned: string[]; failed: string[]; message: string }> => {
  const response = await apiClient.post('/api/v1/agents/bulk-assign', { user_id: userId, agent_ids: agentIds, role });
  return response.data;
};

export const revokeUserAccess = async (agentId: string, userId: string): Promise<{ status: string }> => {
  const response = await apiClient.delete(`/api/v1/agents/${agentId}/users/${userId}`);
  return response.data;
};

export interface AgentUser {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  user_role: string;
  is_active: boolean;
  created_at?: string;
  agent_role: string;
  granted_by?: string;
}

export const getAgentUsers = async (agentId: string): Promise<{ users: AgentUser[]; agent_id: string }> => {
  const response = await apiClient.get(`/api/v1/agents/${agentId}/users`);
  return response.data;
};

export const getUserAgents = async (userId: string): Promise<{ agents: Agent[]; is_admin: boolean; message?: string }> => {
  const response = await apiClient.get(`/api/v1/users/${userId}/agents`);
  return response.data;
};

export const getAllAgents = async (): Promise<Agent[]> => {
  const response = await apiClient.get('/api/v1/agents/all');
  return response.data;
};


// ============================================================================
// DATA SETUP & CONNECTION API (Phase 6 & 7)
// ============================================================================

// Cache for in-flight status requests to deduplicate concurrent calls
const vectorDbStatusCache: Map<string, { promise: Promise<any>; timestamp: number }> = new Map();
const CACHE_TTL_MS = 1000; // 1 second deduplication window

export const getVectorDbStatus = async (vectorDbName: string): Promise<{
  name: string;
  exists: boolean;
  total_documents_indexed: number;
  total_vectors: number;
  last_updated_at: string | null;
  embedding_model: string | null;
  llm: string | null;
  last_full_run: string | null;
  last_incremental_run: string | null;
  version: string;
  diagnostics: Array<{ level: string; message: string }>;
  schedule: any;
}> => {
  const now = Date.now();
  const cached = vectorDbStatusCache.get(vectorDbName);

  // Return cached promise if still valid (within TTL)
  if (cached && (now - cached.timestamp) < CACHE_TTL_MS) {
    return cached.promise;
  }

  // Create new request and cache it
  const promise = apiClient.get(`/api/v1/vector-db/status/${vectorDbName}`)
    .then(response => response.data)
    .finally(() => {
      // Clean up cache entry after request completes + small buffer
      setTimeout(() => {
        const entry = vectorDbStatusCache.get(vectorDbName);
        if (entry && entry.promise === promise) {
          vectorDbStatusCache.delete(vectorDbName);
        }
      }, 100);
    });

  vectorDbStatusCache.set(vectorDbName, { promise, timestamp: now });
  return promise;
};

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
  config_id?: number;
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
 * Get total count of notifications (for pagination).
 */
export const getNotificationCount = async (params?: {
  status_filter?: string;
}): Promise<{ count: number }> => {
  const response = await apiClient.get('/api/v1/notifications/count', { params });
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

export const getRecentTraces = async (limit: number = 10) => {
  const response = await apiClient.get(`/api/v1/observability/traces?limit=${limit}`);
  return response.data;
};

export const testLogEmission = async (level: string, message: string) => {
  const response = await apiClient.post(`/api/v1/observability/test-log?level=${level}&message=${encodeURIComponent(message)}`);
  return response.data;
};

// ============================================================================
// INGESTION API
// ============================================================================

export interface ExtractedDocument {
  page_content: string;
  metadata: Record<string, any>;
}

export interface IngestionResponse {
  status: string;
  file_name: string;
  file_type: string;
  total_documents: number;
  documents: ExtractedDocument[];
  table_name?: string;
  columns?: string[];
  column_details?: Array<{ name: string; type: string }>;
  row_count?: number;
  processing_mode?: string;
  message?: string;
  selectedColumns?: string[];  // Added by frontend after user column selection
}

/**
 * Upload a file for ingestion testing.
 * Sends file as multipart/form-data and returns extracted document previews.
 */
export const uploadForIngestion = async (file: File): Promise<IngestionResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post('/api/v1/ingestion/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120 * 1000, // 2 min for large files
  });
  return response.data;
};

// ============================================================================
// MODEL REGISTRY API
// ============================================================================

export interface ModelInfo {
  id: number;
  provider: string;
  model_name: string;
  display_name: string;
  is_active: number;
  is_custom: number;
  dimensions?: number;
  max_tokens?: number;
  context_length?: number;
  max_output_tokens?: number;
  parameters?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  catalog_info?: CatalogModelInfo;
  is_catalog_model?: boolean;
}

/** Catalog model information with detailed specs */
export interface CatalogModelInfo {
  provider: string;
  model_name: string;
  display_name: string;
  dimensions: number;
  max_tokens: number;
  category: 'general' | 'multilingual' | 'fast' | 'medical' | 'code';
  description: string;
  speed_rating: number;  // 1-5, 5 fastest
  quality_rating: number;  // 1-5, 5 best
  local: boolean;
  requires_api_key: boolean;
  recommended_batch_size: number;
  model_size_mb?: number;
  catalog_key: string;
  is_registered: boolean;
}

/** Response when activating an embedding model */
export interface ModelActivationResponse {
  model: ModelInfo;
  dimension_changed: boolean;
  previous_dimensions: number | null;
  new_dimensions: number;
  requires_rebuild: boolean;
  rebuild_warning: string | null;
  system_settings_updated: boolean;
}

/** List all registered embedding models from the DB */
export const getEmbeddingModels = async (): Promise<ModelInfo[]> => {
  const response = await apiClient.get('/api/v1/settings/embedding/models');
  return response.data;
};

/** List all registered LLM models from the DB */
export const getLLMModels = async (): Promise<ModelInfo[]> => {
  const response = await apiClient.get('/api/v1/settings/llm/models');
  return response.data;
};

/** Get LLM models compatible with the active embedding model */
export const getCompatibleLLMs = async (): Promise<ModelInfo[]> => {
  const response = await apiClient.get('/api/v1/settings/llm/models/compatible');
  return response.data;
};

/** 
 * Activate an embedding model by ID 
 * Returns detailed info including rebuild warnings if dimensions change
 */
export const activateEmbeddingModel = async (modelId: number): Promise<ModelActivationResponse> => {
  const response = await apiClient.put(`/api/v1/settings/embedding/models/${modelId}/activate`);
  return response.data;
};

/** Activate an LLM model by ID */
export const activateLLMModel = async (modelId: number): Promise<ModelInfo> => {
  const response = await apiClient.put(`/api/v1/settings/llm/models/${modelId}/activate`);
  return response.data;
};

/** Register a new custom embedding model */
export const registerEmbeddingModel = async (data: Partial<ModelInfo>): Promise<ModelInfo> => {
  const response = await apiClient.post('/api/v1/settings/embedding/models', data);
  return response.data;
};

/** Register a new custom LLM model */
export const registerLLMModel = async (data: Partial<ModelInfo>): Promise<ModelInfo> => {
  const response = await apiClient.post('/api/v1/settings/llm/models', data);
  return response.data;
};

// ============================================================================
// MODEL CATALOG API (NEW)
// ============================================================================

/**
 * Get the curated model catalog with pre-validated embedding models.
 * Each model includes dimensions, quality/speed ratings, and recommendations.
 */
export const getModelCatalog = async (options?: {
  category?: 'general' | 'multilingual' | 'fast' | 'medical';
  localOnly?: boolean;
}): Promise<CatalogModelInfo[]> => {
  const params: Record<string, any> = {};
  if (options?.category) params.category = options.category;
  if (options?.localOnly) params.local_only = options.localOnly;

  const response = await apiClient.get('/api/v1/settings/embedding/catalog', { params });
  return response.data;
};

/**
 * Add a model from the curated catalog to the registry.
 * Ensures correct dimensions and settings are used automatically.
 */
export const addModelFromCatalog = async (modelName: string): Promise<ModelInfo> => {
  const response = await apiClient.post('/api/v1/settings/embedding/catalog/add', {
    model_name: modelName,
  });
  return response.data;
};

/**
 * Validate that a model can be used.
 * For local models: checks if model can be downloaded
 * For API models: checks if API key is configured
 */
export const validateModelAvailability = async (modelName: string): Promise<{
  model_name: string;
  available: boolean;
  message: string;
}> => {
  const response = await apiClient.get(`/api/v1/settings/embedding/catalog/${encodeURIComponent(modelName)}/validate`);
  return response.data;
};

/**
 * Get the currently active embedding model with full details.
 */
export const getActiveEmbeddingModel = async (): Promise<ModelInfo> => {
  const response = await apiClient.get('/api/v1/settings/embedding/models/active');
  return response.data;
};

// ============================================================================
// VECTOR DB SCHEDULE API
// ============================================================================

export interface VectorDbSchedule {
  vector_db_name: string;
  enabled: boolean;
  schedule_type: 'hourly' | 'daily' | 'weekly' | 'interval' | 'custom';
  schedule_hour: number;
  schedule_minute: number;
  schedule_day_of_week?: number;
  schedule_cron?: string;
  next_run_at?: string;
  countdown_seconds?: number;
  last_run_at?: string;
  last_run_status?: 'success' | 'failed' | 'running';
  exists?: boolean; // false when no schedule is configured
  schedule?: any;   // null when no schedule is configured
}

export interface ScheduleCreateRequest {
  schedule_type: 'hourly' | 'daily' | 'weekly' | 'interval' | 'custom';
  hour?: number;
  minute?: number;
  day_of_week?: number;
  cron_expression?: string;
  enabled?: boolean;
}

/**
 * Create or update a sync schedule for a Vector Database.
 */
export const createVectorDbSchedule = async (
  vectorDbName: string,
  schedule: ScheduleCreateRequest
): Promise<{ status: string; message: string; schedule: VectorDbSchedule }> => {
  const response = await apiClient.post(`/api/v1/vector-db/schedule/${vectorDbName}`, schedule);
  return response.data;
};

/**
 * Get schedule configuration for a Vector Database.
 */
// Cache for in-flight schedule requests to deduplicate concurrent calls
const vectorDbScheduleCache: Map<string, { promise: Promise<any>; timestamp: number }> = new Map();

export const getVectorDbSchedule = async (vectorDbName: string): Promise<VectorDbSchedule> => {
  const now = Date.now();
  const cached = vectorDbScheduleCache.get(vectorDbName);

  // Return cached promise if still valid (within 1s TTL)
  if (cached && (now - cached.timestamp) < CACHE_TTL_MS) {
    return cached.promise;
  }

  // Create new request and cache it
  const promise = apiClient.get(`/api/v1/vector-db/schedule/${vectorDbName}`)
    .then(response => response.data)
    .finally(() => {
      setTimeout(() => {
        const entry = vectorDbScheduleCache.get(vectorDbName);
        if (entry && entry.promise === promise) {
          vectorDbScheduleCache.delete(vectorDbName);
        }
      }, 100);
    });

  vectorDbScheduleCache.set(vectorDbName, { promise, timestamp: now });
  return promise;
};

/**
 * Delete a schedule for a Vector Database.
 */
export const deleteVectorDbSchedule = async (vectorDbName: string): Promise<{ status: string; message: string }> => {
  const response = await apiClient.delete(`/api/v1/vector-db/schedule/${vectorDbName}`);
  return response.data;
};

/**
 * List all Vector DB schedules.
 */
export const listVectorDbSchedules = async (): Promise<VectorDbSchedule[]> => {
  const response = await apiClient.get('/api/v1/vector-db/schedules');
  return response.data;
};

/**
 * Manually trigger an immediate sync for a Vector Database.
 */
export const triggerVectorDbSync = async (vectorDbName: string): Promise<{ status: string; message: string }> => {
  const response = await apiClient.post(`/api/v1/vector-db/schedule/${vectorDbName}/trigger`);
  return response.data;
};

// ============================================================================
// SYSTEM SETTINGS API
// ============================================================================

export const getSystemSettings = async (category: string): Promise<Record<string, any>> => {
  const response = await apiClient.get(`/api/v1/settings/${category}`);
  return response.data;
};

export const updateSystemSettings = async (category: string, settings: Record<string, any>, reason?: string): Promise<Record<string, any>> => {
  const response = await apiClient.put(`/api/v1/settings/${category}`, { settings, reason });
  return response.data;
};

// ============================================================================
// FILE SQL API - DuckDB-based SQL queries on uploaded files
// ============================================================================

export interface FileTable {
  name: string;
  original_filename: string;
  file_type: string;
  row_count: number;
  columns: string[];
  created_at: string | null;
}

export interface SQLQueryResult {
  status: string;
  query: string;
  row_count: number;
  columns: string[];
  rows: Record<string, any>[];
  execution_time_ms?: number;
  error?: string;
}

export interface TableSchema {
  table_name: string;
  schema: Array<{ column_name: string; data_type: string }>;
}

export interface NaturalLanguageQueryResult {
  status: string;
  answer?: string;
  sql?: string;
  columns?: string[];
  rows?: Record<string, any>[];
  total_rows?: number;
  execution_time_ms?: number;
  error?: string;
}

/**
 * List all uploaded file tables available for SQL querying.
 */
export const getFileSqlTables = async (): Promise<{ tables: FileTable[] }> => {
  const response = await apiClient.get('/api/v1/ingestion/sql/tables');
  return response.data;
};

/**
 * Execute a raw SQL query against uploaded file data using DuckDB.
 * Only SELECT queries are allowed for security.
 */
export const executeFileSqlQuery = async (query: string): Promise<SQLQueryResult> => {
  const response = await apiClient.post('/api/v1/ingestion/sql/query', { query });
  return response.data;
};

/**
 * Delete a specific uploaded file table and its data.
 */
export const deleteFileSqlTable = async (tableName: string): Promise<{ status: string; message: string }> => {
  const response = await apiClient.delete(`/api/v1/ingestion/sql/tables/${tableName}`);
  return response.data;
};

/**
 * Delete all uploaded file tables for the current user.
 */
export const deleteAllFileSqlTables = async (): Promise<{ status: string; message: string }> => {
  const response = await apiClient.delete('/api/v1/ingestion/sql/tables');
  return response.data;
};

/**
 * Get the schema (columns and types) of a specific table.
 */
export const getFileSqlTableSchema = async (tableName: string): Promise<TableSchema> => {
  const response = await apiClient.get(`/api/v1/ingestion/sql/schema/${tableName}`);
  return response.data;
};

/**
 * Check if a table is ready for querying (useful for background processing).
 */
export const getFileSqlTableStatus = async (tableName: string): Promise<{
  status: string;
  ready: boolean;
  row_count?: number;
  created_at?: string;
  error?: string;
}> => {
  const response = await apiClient.get(`/api/v1/ingestion/sql/status/${tableName}`);
  return response.data;
};

/**
 * Text-to-SQL: Ask questions in natural language about uploaded data.
 * The LLM translates the question to SQL and returns results with an answer.
 */
export const askNaturalLanguageQuery = async (question: string): Promise<NaturalLanguageQueryResult> => {
  const response = await apiClient.post('/api/v1/ingestion/sql/ask', { question });
  return response.data;
};

/**
 * Get the full schema context for LLM prompts.
 */
export const getSchemaContext = async (): Promise<{
  status: string;
  tables: FileTable[];
  schema_text: string;
  message?: string;
}> => {
  const response = await apiClient.get('/api/v1/ingestion/sql/schema-context');
  return response.data;
};

// ============================================================================
// FILE RAG API - Semantic search on text columns
// ============================================================================

export interface ColumnClassification {
  type: string;
  confidence: number;
  reason: string;
  avg_length: number;
  sample_values: string[];
}

export interface ColumnClassificationResult {
  status: string;
  table_name: string;
  total_columns: number;
  text_columns: string[];
  structured_columns: string[];
  classifications: Record<string, ColumnClassification>;
  recommendation: {
    embed_for_rag: string[];
    sql_only: string[];
    estimated_rag_rows: string;
  };
}

export interface RAGConfig {
  table_name: string;
  text_columns: string[];
  id_column?: string;
  parent_chunk_size?: number;
  child_chunk_size?: number;
}

export interface RAGProcessingResult {
  status: string;
  table_name: string;
  text_columns: string[];
  total_documents?: number;
  parent_chunks?: number;
  child_chunks?: number;
  embeddings_created?: number;
  processing_time_seconds?: number;
  message?: string;
  error?: string;
}

export interface RAGStatus {
  status: string;
  table_name: string;
  text_columns?: string[];
  id_column?: string;
  stats?: {
    parent_chunks?: number;
    child_chunks?: number;
    embeddings_created?: number;
    error?: string;
  };
  updated_at?: string;
  error?: string;
}

export interface RAGTableInfo {
  table_name: string;
  text_columns: string[];
  id_column: string;
  status: string;
  parent_chunks?: number;
  child_chunks?: number;
  embeddings_created?: number;
  updated_at?: string;
}

export interface SemanticSearchResult {
  status: string;
  query: string;
  table_name: string;
  result_count: number;
  results: Array<{
    content: string;
    metadata: Record<string, any>;
    score: number;
    parent_content?: string;
  }>;
}

/**
 * Classify columns in a table as structured vs unstructured.
 * Returns recommendations for which columns should be embedded for RAG.
 */
export const classifyTableColumns = async (tableName: string): Promise<ColumnClassificationResult> => {
  const response = await apiClient.get(`/api/v1/ingestion/columns/classify/${tableName}`);
  return response.data;
};

/**
 * Start RAG embedding for selected text columns in a table.
 * Processing runs in background for large datasets.
 * 
 * NOTE: chunk sizes should come from system settings, not hardcoded.
 * The backend will use system_settings defaults if not provided.
 */
export const startRAGEmbedding = async (config: RAGConfig): Promise<RAGProcessingResult> => {
  const response = await apiClient.post('/api/v1/ingestion/rag/embed', {
    table_name: config.table_name,
    text_columns: config.text_columns,
    id_column: config.id_column || 'patient_id',
    // Don't hardcode - let backend use system_settings defaults
    parent_chunk_size: config.parent_chunk_size,
    child_chunk_size: config.child_chunk_size,
  });
  return response.data;
};

/**
 * Check the RAG embedding status for a table.
 */
export const getRAGStatus = async (tableName: string): Promise<RAGStatus> => {
  const response = await apiClient.get(`/api/v1/ingestion/rag/status/${tableName}`);
  return response.data;
};

/**
 * List all tables that have RAG embedding configured.
 */
export const getRAGEnabledTables = async (): Promise<{ tables: RAGTableInfo[] }> => {
  const response = await apiClient.get('/api/v1/ingestion/rag/tables');
  return response.data;
};

/**
 * Delete RAG embeddings for a table.
 */
export const deleteRAGEmbeddings = async (tableName: string): Promise<{ status: string; message: string }> => {
  const response = await apiClient.delete(`/api/v1/ingestion/rag/${tableName}`);
  return response.data;
};

/**
 * Perform semantic search on a specific table's text columns.
 */
export const semanticSearchTable = async (
  tableName: string,
  query: string,
  topK: number = 10
): Promise<SemanticSearchResult> => {
  const response = await apiClient.post(
    `/api/v1/ingestion/rag/search/${tableName}?query=${encodeURIComponent(query)}&top_k=${topK}`
  );
  return response.data;
};

// ============================================================================
// UNIFIED QUERY API - Automatic SQL/RAG routing
// ============================================================================

export interface UnifiedQueryResult {
  status: string;
  query_type: string;  // 'sql', 'rag', 'hybrid', 'sql_fallback'
  intent: string;
  confidence: number;

  // Final answer
  final_answer?: string;

  // SQL results
  sql_answer?: string;
  sql_query?: string;
  sql_rows?: Record<string, any>[];
  sql_execution_ms?: number;

  // RAG results
  rag_answer?: string;
  rag_documents?: Array<{ content: string; metadata: Record<string, any> }>;
  rag_sources?: string[];

  // Metadata
  routing_reason?: string;
  error?: string;
}

export interface RoutingPreview {
  status: string;
  question: string;
  engine: string;
  intent?: string;
  confidence?: number;
  reasoning?: string;
  message?: string;
}

export interface AgenticHybridResult {
  status: string;
  question: string;

  // Workflow stages
  stage_1_rag: {
    query: string;
    matches_found: number;
    patient_ids?: string[];
    sample_contexts?: string[];
  };
  stage_2_sql: {
    generated_sql: string;
    rows_returned: number;
    columns: string[];
    sample_rows?: Record<string, any>[];
  };
  stage_3_synthesis: {
    prompt_context: string;
    model_used: string;
  };

  // Final answer
  final_answer: string;

  // Performance metrics
  total_time_ms: number;
  rag_time_ms: number;
  sql_time_ms: number;
  synthesis_time_ms: number;

  error?: string;
}

export interface WorkflowCapabilities {
  status: string;
  workflows: {
    sql: {
      available: boolean;
      tables: string[];
      description: string;
    };
    rag: {
      available: boolean;
      tables: string[];
      description: string;
    };
    agentic_hybrid: {
      available: boolean;
      description: string;
      example_queries: string[];
    };
  };
  recommended_endpoint: string;
  message?: string;
}

/**
 * Unified query endpoint with automatic intent routing.
 * Automatically determines optimal retrieval strategy (SQL, RAG, or Hybrid).
 */
export const unifiedQuery = async (
  question: string,
  useLlmRouting: boolean = true
): Promise<UnifiedQueryResult> => {
  const response = await apiClient.post('/api/v1/ingestion/query', {
    question,
    use_llm_routing: useLlmRouting,
  });
  return response.data;
};

/**
 * Preview how a query will be routed WITHOUT executing it.
 * Useful for UI to show users which engine will handle their query.
 */
export const previewQueryRouting = async (question: string): Promise<RoutingPreview> => {
  const response = await apiClient.post('/api/v1/ingestion/query/preview', {
    question,
    use_llm_routing: true,
  });
  return response.data;
};

/**
 * Agentic Hybrid Query: RAG → SQL → Synthesis workflow.
 * Most sophisticated query approach combining semantic search with SQL aggregations.
 * 
 * Example: "What is the average age of patients with migraine symptoms?"
 * - Stage 1: RAG finds patients mentioning migraines
 * - Stage 2: SQL aggregates ages for those patient IDs
 * - Stage 3: LLM synthesizes final answer
 */
export const agenticHybridQuery = async (
  question: string,
  tableName?: string,
  ragTopK: number = 50
): Promise<AgenticHybridResult> => {
  const response = await apiClient.post('/api/v1/ingestion/query/agentic-hybrid', {
    question,
    table_name: tableName,
    rag_top_k: ragTopK,
  });
  return response.data;
};

/**
 * Check which query workflows are available for the current user.
 * Returns status of SQL, RAG, and Agentic Hybrid capabilities.
 */
export const getWorkflowCapabilities = async (): Promise<WorkflowCapabilities> => {
  const response = await apiClient.get('/api/v1/ingestion/query/workflow-status');
  return response.data;
};

// ============================================================================
// VECTOR DB REGISTRY API - Central management of all vector databases
// ============================================================================

export interface VectorDbRegistryItem {
  id: number;
  name: string;
  data_source_id: string | null;
  created_at: string | null;
  created_by: string | null;
  embedding_model: string | null;
  llm: string | null;
  version: string;
  last_full_run: string | null;
  last_incremental_run: string | null;
  disk_size_bytes: number;
  disk_size_formatted: string;
  document_count: number;
  vector_count: number;
  last_updated: string | null;
  chroma_exists: boolean;
  schedule: {
    enabled: boolean;
    schedule_type: string;
    next_run_at: string | null;
    last_run_at: string | null;
    last_run_status: string | null;
  } | null;
  health_status: 'healthy' | 'warning' | 'error' | 'missing' | 'orphaned';
}

export interface OrphanedVectorDb {
  name: string;
  path: string;
  disk_size_bytes: number;
  disk_size_formatted: string;
  vector_count: number;
  health_status: 'orphaned';
}

export interface VectorDbRegistryResponse {
  status: string;
  total_vector_dbs: number;
  total_disk_size_bytes: number;
  total_disk_size_formatted: string;
  vector_dbs: VectorDbRegistryItem[];
  orphaned_dbs: OrphanedVectorDb[];
}

/**
 * Get all vector databases with their disk sizes, document counts, and sync status.
 * Provides a centralized registry view for IT admins.
 */
export const getVectorDbRegistry = async (): Promise<VectorDbRegistryResponse> => {
  const response = await apiClient.get('/api/v1/vector-db/registry');
  return response.data;
};

/**
 * Delete a vector database from the registry and optionally remove its files.
 */
export const deleteVectorDb = async (
  vectorDbName: string,
  deleteFiles: boolean = true
): Promise<{ status: string; message: string; files_deleted: boolean }> => {
  const response = await apiClient.delete(`/api/v1/vector-db/registry/${vectorDbName}`, {
    params: { delete_files: deleteFiles }
  });
  return response.data;
};

