import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RegisterPage from '../../pages/RegisterPage';
import { AuthProvider } from '../../contexts/AuthContext';
import * as api from '../../services/api';

import type { User } from '../../types';

vi.mock('../../services/api', async () => {
  const actual = await vi.importActual('../../services/api');
  return { ...actual, apiClient: { post: vi.fn() }, getUserProfile: vi.fn(), handleApiError: vi.fn((err) => err.message || 'An error occurred') };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => ({ ...(await vi.importActual('react-router-dom')), useNavigate: () => mockNavigate }));
vi.mock('../../assets/logo.svg', () => ({ default: 'mock-logo.svg' }));
vi.mock('react-toastify', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from 'react-toastify';

const renderRegisterPage = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuthProvider><BrowserRouter><RegisterPage /></BrowserRouter></AuthProvider></QueryClientProvider>);
};

describe('RegisterPage', () => {
  const mockApiClient = api.apiClient as unknown as { post: Mock };
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); vi.mocked(api.getUserProfile).mockResolvedValue(undefined as unknown as User); vi.useFakeTimers({ shouldAdvanceTime: true }); });
  afterEach(() => vi.useRealTimers());

  it('renders form with all fields, logo, and login link', () => {
    renderRegisterPage();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Create Account');
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByAltText('Logo')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
  });

  it.each([
    ['username too short', 'ab', 'password123', 'password123', /username must be at least 3 characters/i],
    ['password too short', 'validuser', '12345', '12345', /password must be at least 6 characters/i],
    ['passwords mismatch', 'validuser', 'password123', 'password456', /passwords do not match/i],
  ])('validates: %s', async (_, username, password, confirm, errorPattern) => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderRegisterPage();
    
    await user.type(screen.getByLabelText(/username/i), username);
    await user.type(screen.getByLabelText(/^password/i), password);
    await user.type(screen.getByLabelText(/confirm password/i), confirm);
    await user.click(screen.getByRole('button', { name: /sign up|create account|register/i }));
    
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(errorPattern));
    expect(mockApiClient.post).not.toHaveBeenCalled();
  });

  it('submits required fields only when optional are empty', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockApiClient.post.mockResolvedValueOnce({ data: { id: 1, username: 'newuser', role: 'user', created_at: '2025-01-01T00:00:00Z' } });
    renderRegisterPage();

    await user.type(screen.getByLabelText(/username/i), 'newuser');
    await user.type(screen.getByLabelText(/^password/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign up|create account|register/i }));

    await waitFor(() => expect(mockApiClient.post).toHaveBeenCalledWith(expect.stringContaining('auth/register'), { username: 'newuser', password: 'password123' }));
  });

  it('submits with optional fields and shows success', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockApiClient.post.mockResolvedValueOnce({ data: { id: 1, username: 'newuser', email: 'new@example.com', full_name: 'NewUser', role: 'user', created_at: '' } });
    renderRegisterPage();

    await user.type(screen.getByLabelText(/username/i), 'newuser');
    await user.type(screen.getByLabelText(/full name/i), 'NewUser');
    await user.type(screen.getByLabelText(/email/i), 'new@example.com');
    await user.type(screen.getByLabelText(/^password/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign up|create account|register/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith(expect.stringContaining('auth/register'), expect.objectContaining({ username: 'newuser', password: 'password123', email: 'new@example.com', full_name: 'NewUser' }));
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Account created successfully'), expect.any(Object));
    });
    
    await vi.advanceTimersByTimeAsync(1500);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/login'));
  });

  it('shows loading state during submission', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let resolvePromise: (value: unknown) => void;
    mockApiClient.post.mockReturnValueOnce(new Promise(resolve => { resolvePromise = resolve; }) as any);
    renderRegisterPage();

    await user.type(screen.getByLabelText(/username/i), 'newuser');
    await user.type(screen.getByLabelText(/^password/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign up|create account|register/i }));

    await waitFor(() => expect(screen.getByRole('button', { name: /signing up|creating|loading/i })).toBeDisabled());
    resolvePromise!({ data: { id: 1, username: 'newuser', role: 'user', created_at: '' } });
  });

  it('handles API error and re-enables button', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.mocked(api.handleApiError).mockReturnValueOnce('Username already exists');
    mockApiClient.post.mockRejectedValueOnce({ response: { status: 400, data: { detail: 'Username already exists' } }, message: 'Username already exists' });
    renderRegisterPage();

    await user.type(screen.getByLabelText(/username/i), 'existinguser');
    await user.type(screen.getByLabelText(/^password/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign up|create account|register/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Username already exists');
      expect(screen.getByRole('button', { name: /sign up|create account|register/i })).not.toBeDisabled();
    });
  });

  it('has proper input types for accessibility', () => {
    renderRegisterPage();
    expect(screen.getByLabelText(/username/i)).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText(/email/i)).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText(/^password/i)).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText(/confirm password/i)).toHaveAttribute('type', 'password');
  });
});
