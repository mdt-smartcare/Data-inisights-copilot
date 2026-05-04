import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';

/**
 * Custom hook to manage dismissed version alert state per agent.
 * 
 * Uses localStorage to persist dismissed state.
 * Key format: dismissed_config_alert_{agentId}_{versionNumber}
 * 
 * When a new version is created, the dismiss state resets automatically
 * because the key includes the version number.
 */
export function useDismissedVersionAlert(agentId: string, version?: number) {
  // Build the localStorage key dynamically based on agentId and version
  const storageKey = useMemo(() => {
    if (!agentId || version === undefined) {
      return null;
    }
    return `dismissed_config_alert_${agentId}_${version}`;
  }, [agentId, version]);

  // Use a default key that won't match anything when key is null
  const [isDismissed, setIsDismissed] = useLocalStorage<boolean>(
    storageKey || '__temp_dismissed_alert__',
    false
  );

  const dismiss = useCallback(() => {
    if (storageKey) {
      setIsDismissed(true);
    }
  }, [storageKey, setIsDismissed]);

  const reset = useCallback(() => {
    if (storageKey) {
      setIsDismissed(false);
    }
  }, [storageKey, setIsDismissed]);

  // If no valid key, always return false (not dismissed)
  const effectiveDismissed = storageKey ? isDismissed : false;

  return {
    isDismissed: effectiveDismissed,
    dismiss,
    reset,
  };
}

/**
 * Check if a specific version alert was dismissed (without React hook).
 * Useful for non-React contexts.
 */
export function isVersionAlertDismissed(agentId: string, version: number): boolean {
  try {
    const key = `dismissed_config_alert_${agentId}_${version}`;
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) === true : false;
  } catch {
    return false;
  }
}

/**
 * Dismiss a version alert (without React hook).
 * Useful for non-React contexts.
 */
export function dismissVersionAlert(agentId: string, version: number): void {
  try {
    const key = `dismissed_config_alert_${agentId}_${version}`;
    window.localStorage.setItem(key, JSON.stringify(true));
  } catch (error) {
    console.error('Error dismissing version alert:', error);
  }
}
