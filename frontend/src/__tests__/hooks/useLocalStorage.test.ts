import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLocalStorage } from '../../hooks/useLocalStorage';

describe('useLocalStorage', () => {
  const TEST_KEY = 'test_key';

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Initial Value', () => {
    it('should return initial value when localStorage is empty', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'default'));
      expect(result.current[0]).toBe('default');
    });

    it('should return stored value from localStorage', () => {
      localStorage.setItem(TEST_KEY, JSON.stringify('stored value'));
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'default'));
      expect(result.current[0]).toBe('stored value');
    });

    it('should handle object values', () => {
      const storedObject = { name: 'test', count: 42 };
      localStorage.setItem(TEST_KEY, JSON.stringify(storedObject));
      const { result } = renderHook(() =>
        useLocalStorage(TEST_KEY, { name: '', count: 0 })
      );
      expect(result.current[0]).toEqual(storedObject);
    });

    it('should handle array values', () => {
      const storedArray = [1, 2, 3];
      localStorage.setItem(TEST_KEY, JSON.stringify(storedArray));
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, []));
      expect(result.current[0]).toEqual(storedArray);
    });

    it('should handle boolean values', () => {
      localStorage.setItem(TEST_KEY, JSON.stringify(true));
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, false));
      expect(result.current[0]).toBe(true);
    });

    it('should handle number values', () => {
      localStorage.setItem(TEST_KEY, JSON.stringify(123));
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 0));
      expect(result.current[0]).toBe(123);
    });

    it('should handle null values', () => {
      localStorage.setItem(TEST_KEY, JSON.stringify(null));
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'default'));
      expect(result.current[0]).toBeNull();
    });
  });

  describe('setValue', () => {
    it('should update state and localStorage', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'initial'));

      act(() => {
        result.current[1]('updated');
      });

      expect(result.current[0]).toBe('updated');
      expect(JSON.parse(localStorage.getItem(TEST_KEY)!)).toBe('updated');
    });

    it('should handle function updates', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 5));

      act(() => {
        result.current[1]((prev) => prev + 1);
      });

      expect(result.current[0]).toBe(6);
    });

    it('should update object values', () => {
      const { result } = renderHook(() =>
        useLocalStorage(TEST_KEY, { name: 'initial' })
      );

      act(() => {
        result.current[1]({ name: 'updated' });
      });

      expect(result.current[0]).toEqual({ name: 'updated' });
      expect(JSON.parse(localStorage.getItem(TEST_KEY)!)).toEqual({
        name: 'updated',
      });
    });

    it('should update array values', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, [1, 2]));

      act(() => {
        result.current[1]([1, 2, 3]);
      });

      expect(result.current[0]).toEqual([1, 2, 3]);
    });
  });

  describe('Error Handling', () => {
    it('should return initial value when localStorage has invalid JSON', () => {
      localStorage.setItem(TEST_KEY, 'invalid json');
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'default'));

      expect(result.current[0]).toBe('default');
      expect(consoleSpy).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });

    it('should handle localStorage quota exceeded', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const originalSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = vi.fn(() => {
        throw new Error('QuotaExceededError');
      });

      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'initial'));

      act(() => {
        result.current[1]('new value');
      });

      // State should still update even if localStorage fails
      expect(result.current[0]).toBe('new value');
      expect(consoleSpy).toHaveBeenCalled();

      Storage.prototype.setItem = originalSetItem;
      consoleSpy.mockRestore();
    });
  });

  describe('Key Changes', () => {
    it('should return different values for different keys', () => {
      localStorage.setItem('key1', JSON.stringify('value1'));
      localStorage.setItem('key2', JSON.stringify('value2'));

      const { result: result1 } = renderHook(() =>
        useLocalStorage('key1', 'default')
      );
      const { result: result2 } = renderHook(() =>
        useLocalStorage('key2', 'default')
      );

      expect(result1.current[0]).toBe('value1');
      expect(result2.current[0]).toBe('value2');
    });
  });

  describe('Type Preservation', () => {
    it('should preserve string type', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 'test'));
      expect(typeof result.current[0]).toBe('string');
    });

    it('should preserve number type', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, 42));
      expect(typeof result.current[0]).toBe('number');
    });

    it('should preserve object type', () => {
      const { result } = renderHook(() => useLocalStorage(TEST_KEY, { a: 1 }));
      expect(typeof result.current[0]).toBe('object');
      expect(result.current[0]).toHaveProperty('a');
    });
  });
});
