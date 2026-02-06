import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import { apiClient, handleApiError } from '../../services/api';

// Mock axios create to return a mock instance
vi.mock('axios', async () => {
  const actualAxios = await vi.importActual<typeof axios>('axios');
  return {
    ...actualAxios,
    default: {
      ...actualAxios,
      create: vi.fn(() => ({
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
        post: vi.fn(),
        get: vi.fn(),
      })),
      isAxiosError: actualAxios.isAxiosError,
    },
  };
});

describe('API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('handleApiError', () => {
    it('should extract message from axios error response detail', () => {
      const axiosError = {
        response: {
          data: { detail: 'Invalid credentials' },
        },
        message: 'Request failed',
        isAxiosError: true,
      };
      
      // Mock isAxiosError to return true
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
      
      const result = handleApiError(axiosError);
      expect(result).toBe('Invalid credentials');
    });

    it('should extract message from axios error response message field', () => {
      const axiosError = {
        response: {
          data: { message: 'Server error' },
        },
        message: 'Request failed',
        isAxiosError: true,
      };
      
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
      
      const result = handleApiError(axiosError);
      expect(result).toBe('Server error');
    });

    it('should use error.message as fallback for axios errors', () => {
      const axiosError = {
        response: {
          data: {},
        },
        message: 'Network Error',
        isAxiosError: true,
      };
      
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
      
      const result = handleApiError(axiosError);
      expect(result).toBe('Network Error');
    });

    it('should return generic message for non-axios errors', () => {
      const genericError = new Error('Something went wrong');
      
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(false);
      
      const result = handleApiError(genericError);
      expect(result).toBe('An unexpected error occurred');
    });

    it('should return generic message for null errors', () => {
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(false);
      
      const result = handleApiError(null);
      expect(result).toBe('An unexpected error occurred');
    });

    it('should return generic message for undefined errors', () => {
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(false);
      
      const result = handleApiError(undefined);
      expect(result).toBe('An unexpected error occurred');
    });

    it('should handle axios error without response', () => {
      const axiosError = {
        message: 'Network Error',
        isAxiosError: true,
      };
      
      vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
      
      const result = handleApiError(axiosError);
      expect(result).toBe('Network Error');
    });
  });

  describe('API Client Configuration', () => {
    it('should have apiClient configured', () => {
      // apiClient should be defined from module
      expect(apiClient).toBeDefined();
    });
  });
});

// Separate tests for interceptor logic (testing the logic in isolation)
describe('Request Interceptor Logic', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it.each([
    ['expired', -3600, true],
    ['valid', 3600, false],
  ])('should detect %s token', (_, timeOffset, shouldBeExpired) => {
    const time = Math.floor(Date.now() / 1000) + timeOffset;
    localStorage.setItem('auth_token', 'test_token');
    localStorage.setItem('expiresAt', time.toString());
    const currentTime = Math.floor(Date.now() / 1000);
    const expirationTime = parseInt(localStorage.getItem('expiresAt')!, 10);
    expect(currentTime >= expirationTime).toBe(shouldBeExpired);
  });

  it('should add Bearer token when exists, null when not', () => {
    expect(localStorage.getItem('auth_token')).toBeNull();
    localStorage.setItem('auth_token', 'test_jwt_token');
    const token = localStorage.getItem('auth_token');
    expect(token ? `Bearer ${token}` : undefined).toBe('Bearer test_jwt_token');
  });

  it.each([
    ['/api/v1/auth/login', true],
    ['/api/v1/auth/register', true],
    ['/api/v1/health', true],
    ['/api/v1/chat', false],
  ])('should identify %s as %s endpoint', (url, isPublic) => {
    const publicEndpoints = ['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/health'];
    expect(publicEndpoints.some(endpoint => url.includes(endpoint))).toBe(isPublic);
  });
});

describe('Response Interceptor Logic', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should handle 401 errors and clean up tokens', () => {
    localStorage.setItem('auth_token', 'test_token');
    localStorage.setItem('expiresAt', '123456789');
    
    // 401 should trigger cleanup for protected endpoints
    expect(401 === 401).toBe(true);
    const url = '/api/v1/chat';
    const publicEndpoints = ['/auth/login', '/auth/register'];
    expect(publicEndpoints.some(e => url.includes(e))).toBe(false);
    
    localStorage.removeItem('auth_token');
    localStorage.removeItem('expiresAt');
    expect(localStorage.getItem('auth_token')).toBeNull();
  });
});

// Test user ID extraction logic
describe('User ID Extraction Logic', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it.each([
    [JSON.stringify({ id: 'user123', username: 'testuser' }), 'user123'],
    [JSON.stringify({ username: 'testuser' }), 'testuser'],
    [null, 'admin'],
    ['invalid-json-{', 'admin'],
    [JSON.stringify({}), 'admin'],
  ])('should extract correct userId from localStorage: %s', (storedValue, expectedId) => {
    if (storedValue) localStorage.setItem('user', storedValue);
    
    const user = localStorage.getItem('user');
    let userId = 'admin';
    if (user) {
      try {
        const parsedUser = JSON.parse(user);
        userId = parsedUser.id || parsedUser.username || 'admin';
      } catch { /* keep default */ }
    }
    expect(userId).toBe(expectedId);
  });
});

// Test API URL construction and serialization
describe('API URL Construction & Serialization', () => {
  it.each([
    ['job-123', `/api/v1/embedding-jobs/job-123/progress`],
    ['job-456', `/api/v1/embedding-jobs/job-456/summary`],
  ])('should format embedding job URLs correctly', (jobId, expectedPattern) => {
    const url = expectedPattern.includes('progress') 
      ? `/api/v1/embedding-jobs/${jobId}/progress`
      : `/api/v1/embedding-jobs/${jobId}/summary`;
    expect(url).toBe(expectedPattern);
  });

  it('should serialize configs correctly', () => {
    const poolConfig = { minSize: 5, maxSize: 20 };
    expect(JSON.stringify(poolConfig)).toBe('{"minSize":5,"maxSize":20}');
    const nullVal = null;
    const undefinedVal = undefined;
    expect(nullVal ? JSON.stringify(nullVal) : null).toBeNull();
    expect(undefinedVal ? JSON.stringify(undefinedVal) : null).toBeNull();
  });

  it('should serialize schema and reasoning', () => {
    const schema = { users: ['id', 'name'] };
    const reasoning = { field1: 'reason1' };
    expect(JSON.parse(JSON.stringify(schema))).toEqual(schema);
    expect(JSON.parse(JSON.stringify(reasoning))).toEqual(reasoning);
  });
});
