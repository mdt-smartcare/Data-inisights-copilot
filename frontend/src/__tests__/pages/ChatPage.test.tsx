import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ChatPage from '../../pages/ChatPage';
import type { UserRole } from '../../types';

// Mock the auth context
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: { id: 1, username: 'testuser', role: 'user' as UserRole, email: 'test@test.com' },
    isAuthenticated: true,
    isLoading: false,
    logout: vi.fn(),
    setUser: vi.fn(),
  })),
}));

// Mock chat service
vi.mock('../../services/chatService', () => ({
  chatService: {
    sendMessage: vi.fn(),
  },
}));

// Mock API
vi.mock('../../services/api', () => ({
  getActiveConfigMetadata: vi.fn(() => Promise.resolve(null)),
  getNotifications: vi.fn(() => Promise.resolve([])),
  markNotificationRead: vi.fn(() => Promise.resolve()),
  markAllNotificationsRead: vi.fn(() => Promise.resolve()),
}));

// Mock config
vi.mock('../../config', () => ({
  APP_CONFIG: {
    APP_NAME: 'FHIR RAG',
  },
}));

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const renderChatPage = () => {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the chat header with app name', () => {
      renderChatPage();
      expect(screen.getByText('FHIR RAG')).toBeInTheDocument();
    });

    it('should render the chat input', () => {
      renderChatPage();
      expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument();
    });

    it('should render the empty state when no messages', () => {
      renderChatPage();
      expect(screen.getByText(/ask me anything about fhir/i)).toBeInTheDocument();
    });

    it('should not show clear chat button when no messages', () => {
      renderChatPage();
      expect(screen.queryByText(/clear chat/i)).not.toBeInTheDocument();
    });
  });

  describe('Empty State Suggestions', () => {
    it('should display default suggestions', () => {
      renderChatPage();
      expect(screen.getByText(/male patients/i)).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should allow typing in the chat input', async () => {
      const user = userEvent.setup();
      renderChatPage();
      
      const input = screen.getByPlaceholderText(/type your message/i);
      await user.type(input, 'Hello');
      
      expect(input).toHaveValue('Hello');
    });

    it('should clear input after sending message', async () => {
      const { chatService } = await import('../../services/chatService');
      vi.mocked(chatService.sendMessage).mockResolvedValue({
        answer: 'Test response',
        timestamp: new Date().toISOString(),
        sources: [],
        conversation_id: 'conv-123',
      });

      const user = userEvent.setup();
      renderChatPage();
      
      const input = screen.getByPlaceholderText(/type your message/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));
      
      await waitFor(() => {
        expect(input).toHaveValue('');
      });
    });
  });
});
