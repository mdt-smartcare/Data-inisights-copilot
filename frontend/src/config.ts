// API Base URL Configuration
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const API_VERSION_PATH = 'api/v1';

// API Endpoints
export const API_ENDPOINTS = {
  CHAT: `${API_VERSION_PATH}/chat`,
  FEEDBACK: `${API_VERSION_PATH}/feedback`,
  HEALTH: `${API_VERSION_PATH}/health`,
  AUTH: {
    LOGIN: `${API_VERSION_PATH}/auth/login`,
    LOGOUT: `${API_VERSION_PATH}/auth/logout`,
    REGISTER: `${API_VERSION_PATH}/auth/register`,
  },
} as const;

// Keycloak OIDC Configuration
export const OIDC_CONFIG = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY || 'https://keycloak.mdtlabs.org/realms/smartcare',
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'smartcare-client',
  redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/callback`,
  post_logout_redirect_uri: import.meta.env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI || `${window.location.origin}/login`,
  scope: import.meta.env.VITE_OIDC_SCOPE || 'openid profile email',
  response_type: 'code',
} as const;

// App Configuration
export const APP_CONFIG = {
  APP_NAME: 'Data Insights AI-Copilot',
  MAX_MESSAGE_LENGTH: 2000,
  CHAT_HISTORY_LIMIT: 50,
} as const;

// Confirmation Messages
export const CONFIRMATION_MESSAGES = {
  DELETE_CONNECTION: 'Are you sure you want to delete this database connection? This action will remove all associated configurations and cannot be undone.',
  DEACTIVATE_USER: 'Are you sure you want to deactivate this user? They will no longer be able to log in or access the system.',
  ROLLBACK_PROMPT: 'Are you sure you want to rollback to this version? This will immediately update the active prompt for all users.',
  CLEAR_DICTIONARY: 'This will clear all data dictionary content. Are you sure you want to proceed?',
} as const;
