import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LoginPage from '../../pages/LoginPage';
import { AuthProvider } from '../../contexts/AuthContext';
import * as api from '../../services/api';

import type { User } from '../../types';

vi.mock('../../services/api', async () => {
  const actual = await vi.importActual('../../services/api');
  return { ...actual, apiClient: { post: vi.fn() }, getUserProfile: vi.fn(), handleApiError: vi.fn((err) => err.message || 'An error occurred') };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../assets/logo.svg', () => ({ default: 'mock-logo.svg' }));

const renderLoginPage = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuthProvider><BrowserRouter><LoginPage /></BrowserRouter></AuthProvider></QueryClientProvider>);
};

describe('LoginPage', () => {
  const mockApiClient = api.apiClient as unknown as { post: Mock };
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); vi.mocked(api.getUserProfile).mockResolvedValue(undefined as unknown as User); });

  it('renders login form with title, fields, logo, and register link', () => {
    renderLoginPage();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Data Insights AI-Copilot');
    expect(screen.getByLabelText(/username/i)).toBeRequired();
    expect(screen.getByLabelText(/password/i)).toBeRequired();
    expect(screen.getByAltText('Logo')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign up/i })).toHaveAttribute('href', '/register');
  });

  it('allows typing and submits credentials to API', async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValueOnce({
      data: { access_token: 'test_token', token_type: 'bearer', expires_in: 3600, user: { username: 'testuser', role: 'user' } },
    });
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    expect(screen.getByLabelText(/username/i)).toHaveValue('testuser');
    
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(mockApiClient.post).toHaveBeenCalledWith(expect.stringContaining('auth/login'), { username: 'testuser', password: 'password123' }));
  });

  it('stores token and navigates based on role on success', async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValueOnce({
      data: { access_token: 'jwt_token_12345', token_type: 'bearer', expires_in: 7200, user: { username: 'testuser', role: 'user' } },
    });
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(localStorage.getItem('auth_token')).toBe('jwt_token_12345');
      expect(mockNavigate).toHaveBeenCalledWith('/chat');
    });
  });

  it.each([
    ['admin', '/config'],
    ['user', '/chat'],
  ])('navigates to %s destination for %s role', async (role, destination) => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValueOnce({
      data: { access_token: 'token', token_type: 'bearer', expires_in: 3600, user: { username: 'test', role } },
    });
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'test');
    await user.type(screen.getByLabelText(/password/i), 'pass');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith(destination));
  });

  it('shows loading state during submission', async () => {
    const user = userEvent.setup();
    let resolvePromise: (value: unknown) => void;
    mockApiClient.post.mockReturnValueOnce(new Promise((resolve) => { resolvePromise = resolve; }) as any);
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    const button = screen.getByRole('button');
    expect(button).toHaveTextContent(/signing in/i);
    expect(button).toBeDisabled();

    resolvePromise!({ data: { access_token: 'token', token_type: 'bearer', expires_in: 3600, user: { username: 'test', role: 'user' } } });
  });

  it.each([
    ['Invalid credentials', { response: { status: 401, data: { detail: 'Invalid credentials' } }, message: 'Invalid credentials' }],
    ['Network Error', new Error('Network Error')],
  ])('displays error message: %s', async (errorMsg, error) => {
    const user = userEvent.setup();
    vi.mocked(api.handleApiError).mockReturnValueOnce(errorMsg);
    mockApiClient.post.mockRejectedValueOnce(error);
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'test');
    await user.type(screen.getByLabelText(/password/i), 'test');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(errorMsg));
    expect(screen.getByRole('button', { name: /sign in/i })).not.toBeDisabled();
  });

  it('clears previous error on new submission', async () => {
    const user = userEvent.setup();
    vi.mocked(api.handleApiError).mockReturnValueOnce('First error');
    mockApiClient.post.mockRejectedValueOnce(new Error('First error'));
    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), 'test');
    await user.type(screen.getByLabelText(/password/i), 'test');
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('First error'));

    mockApiClient.post.mockResolvedValueOnce({ data: { access_token: 'token', token_type: 'bearer', expires_in: 3600, user: { username: 'test', role: 'user' } } });
    await user.clear(screen.getByLabelText(/username/i));
    await user.type(screen.getByLabelText(/username/i), 'validuser');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.queryByText('First error')).not.toBeInTheDocument());
  });
});
