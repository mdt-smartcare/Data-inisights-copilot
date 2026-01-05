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

// App Configuration
export const APP_CONFIG = {
  APP_NAME: 'FHIR RAG Assistant',
  MAX_MESSAGE_LENGTH: 2000,
  CHAT_HISTORY_LIMIT: 50,
} as const;
