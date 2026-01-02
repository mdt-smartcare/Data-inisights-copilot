// API Base URL Configuration
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// API Endpoints
export const API_ENDPOINTS = {
  CHAT: '/api/chat',
  FEEDBACK: '/api/feedback',
  HEALTH: '/api/health',
  AUTH: {
    LOGIN: '/api/auth/login',
    LOGOUT: '/api/auth/logout',
    REGISTER: '/api/auth/register',
  },
} as const;

// App Configuration
export const APP_CONFIG = {
  APP_NAME: 'FHIR RAG Assistant',
  MAX_MESSAGE_LENGTH: 2000,
  CHAT_HISTORY_LIMIT: 50,
} as const;
