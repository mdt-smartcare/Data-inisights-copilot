import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { chatService } from '../../services/chatService';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({ apiClient: { post: vi.fn() } }));

describe('chatService', () => {
  const mockApiClient = api.apiClient as unknown as { post: Mock };
  beforeEach(() => vi.clearAllMocks());

  it('calls API and returns various response types correctly', async () => {
    const fullResponse = {
      answer: 'Response', conversation_id: 'conv-123', timestamp: '2025-01-30T10:00:00Z',
      session_id: 'sess-456', sql_query: 'SELECT * FROM patients', trace_id: 'trace-789',
      sources: [{ content: 'Source 1', metadata: { table: 'test' } }],
      chart_data: { type: 'bar', title: 'Test', data: [] },
      suggested_questions: ['Q1?', 'Q2?'], processing_time: 1.5,
    };
    mockApiClient.post.mockResolvedValueOnce({ data: fullResponse });

    const result = await chatService.sendMessage({ query: 'Test', session_id: 'sess-456' });

    expect(mockApiClient.post).toHaveBeenCalledWith(expect.stringContaining('chat'), expect.objectContaining({ session_id: 'sess-456' }));
    expect(result).toEqual(fullResponse);
    expect(result.sources).toHaveLength(1);
    expect(result.chart_data?.type).toBe('bar');
    expect(result.suggested_questions).toHaveLength(2);
  });

  it.each([
    ['network', new Error('Network error'), 'Network error'],
    ['401', { response: { status: 401 }, message: 'Unauthorized' }, null],
    ['500', { response: { status: 500, data: { detail: 'Server error' } }, message: 'Request failed' }, null],
  ])('handles %s error correctly', async (_, error, expectedMessage) => {
    mockApiClient.post.mockRejectedValueOnce(error);
    const promise = chatService.sendMessage({ query: 'Test' });
    if (expectedMessage) {
      await expect(promise).rejects.toThrow(expectedMessage);
    } else {
      await expect(promise).rejects.toEqual(error);
    }
  });
});
