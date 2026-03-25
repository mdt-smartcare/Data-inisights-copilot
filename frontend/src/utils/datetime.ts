/**
 * Centralized datetime utilities using dayjs for consistent formatting.
 * 
 * Backend sends timestamps in UTC ISO 8601 format.
 * All functions automatically convert to local timezone for display.
 */

import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import relativeTime from 'dayjs/plugin/relativeTime';
import duration from 'dayjs/plugin/duration';
import localizedFormat from 'dayjs/plugin/localizedFormat';

// Initialize plugins
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(relativeTime);
dayjs.extend(duration);
dayjs.extend(localizedFormat);

/**
 * Get the configured timezone from environment or default to browser's local timezone
 */
export function getConfiguredTimezone(): string {
  return import.meta.env.VITE_TIMEZONE || dayjs.tz.guess();
}

/**
 * Parse a UTC datetime string from backend into a dayjs object
 * Handles null/undefined values gracefully
 */
export function parseUTCDate(dateString: string | null | undefined) {
  if (!dateString) return null;
  
  try {
    const parsed = dayjs.utc(dateString);
    if (!parsed.isValid()) {
      console.warn(`Invalid date string: ${dateString}`);
      return null;
    }
    return parsed.tz(getConfiguredTimezone());
  } catch (error) {
    console.error(`Error parsing date: ${dateString}`, error);
    return null;
  }
}

/**
 * Format a UTC datetime string to local date and time
 * Example: "Mar 24, 2026, 3:30 PM"
 * 
 * @param dateString - UTC datetime string from backend
 * @param format - Optional dayjs format string (default: 'll LT')
 */
export function formatDateTime(
  dateString: string | null | undefined,
  format: string = 'll LT'
): string {
  const date = parseUTCDate(dateString);
  if (!date) return '-';
  
  try {
    return date.format(format);
  } catch (error) {
    console.error('Error formatting date:', error);
    return date.format('YYYY-MM-DD HH:mm');
  }
}

/**
 * Format a UTC datetime string to local date only
 * Example: "Mar 24, 2026"
 */
export function formatDate(dateString: string | null | undefined): string {
  const date = parseUTCDate(dateString);
  if (!date) return '-';
  
  return date.format('ll');
}

/**
 * Format a UTC datetime string to local time only
 * Example: "3:30 PM"
 */
export function formatTime(dateString: string | null | undefined): string {
  const date = parseUTCDate(dateString);
  if (!date) return '-';
  
  return date.format('LT');
}

/**
 * Format a UTC datetime string to relative time
 * Examples: "a few seconds ago", "5 minutes ago", "2 hours ago", "3 days ago"
 * 
 * @param dateString - UTC datetime string from backend
 * @param withoutSuffix - Remove "ago" suffix (default: false)
 */
export function formatRelativeTime(
  dateString: string | null | undefined,
  withoutSuffix: boolean = false
): string {
  const date = parseUTCDate(dateString);
  if (!date) return '-';
  
  const now = dayjs();
  const diffDays = now.diff(date, 'day');
  
  // For dates older than 7 days, show the actual date
  if (Math.abs(diffDays) > 7) {
    return formatDate(dateString);
  }
  
  return date.fromNow(withoutSuffix);
}

/**
 * Format a UTC datetime string to short relative time
 * Examples: "Just now", "5m ago", "2h ago", "3d ago"
 */
export function formatRelativeTimeShort(dateString: string | null | undefined): string {
  const date = parseUTCDate(dateString);
  if (!date) return '-';
  
  const now = dayjs();
  const diffSecs = now.diff(date, 'second');
  const diffMins = now.diff(date, 'minute');
  const diffHours = now.diff(date, 'hour');
  const diffDays = now.diff(date, 'day');

  // Future dates
  if (diffSecs < 0) {
    const absDiffMins = Math.abs(diffMins);
    const absDiffHours = Math.abs(diffHours);
    const absDiffDays = Math.abs(diffDays);
    
    if (absDiffMins < 60) return `in ${absDiffMins}m`;
    if (absDiffHours < 24) return `in ${absDiffHours}h`;
    if (absDiffDays < 7) return `in ${absDiffDays}d`;
    return formatDate(dateString);
  }

  // Past dates
  if (diffSecs < 10) return 'Just now';
  if (diffSecs < 60) return `${diffSecs}s ago`;
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  // For older dates, show the actual date
  return formatDate(dateString);
}

/**
 * Format duration in milliseconds to human-readable format
 * Example: "2.5s", "150ms", "1m 30s"
 */
export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined) return '-';
  
  if (milliseconds < 1000) {
    return `${Math.round(milliseconds)}ms`;
  }
  
  const dur = dayjs.duration(milliseconds);
  const minutes = Math.floor(dur.asMinutes());
  const seconds = dur.seconds();
  
  if (minutes === 0) {
    return `${dur.asSeconds().toFixed(1)}s`;
  }
  
  return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`;
}

/**
 * Format remaining time in seconds to human-readable format
 * Example: "5m 30s", "2h 15m", "< 1m"
 */
export function formatTimeRemaining(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return '-';
  
  if (seconds < 60) {
    return seconds < 10 ? '< 1m' : `${Math.ceil(seconds / 10) * 10}s`;
  }
  
  const dur = dayjs.duration(seconds, 'seconds');
  const hours = Math.floor(dur.asHours());
  const minutes = dur.minutes();
  const remainingSeconds = dur.seconds();
  
  if (hours > 0) {
    return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
  }
  
  if (minutes > 0) {
    return remainingSeconds === 0 ? `${minutes}m` : `${minutes}m ${remainingSeconds}s`;
  }
  
  return `${remainingSeconds}s`;
}

/**
 * Format elapsed time in seconds to human-readable format
 * Same as formatTimeRemaining but different semantic meaning
 */
export function formatElapsedTime(seconds: number | null | undefined): string {
  return formatTimeRemaining(seconds);
}

/**
 * Check if a date string is today
 */
export function isToday(dateString: string | null | undefined): boolean {
  const date = parseUTCDate(dateString);
  if (!date) return false;
  
  const today = dayjs();
  return date.isSame(today, 'day');
}

/**
 * Check if a date string is yesterday
 */
export function isYesterday(dateString: string | null | undefined): boolean {
  const date = parseUTCDate(dateString);
  if (!date) return false;
  
  const yesterday = dayjs().subtract(1, 'day');
  return date.isSame(yesterday, 'day');
}

/**
 * Get a human-friendly date label
 * Examples: "Today", "Yesterday", "Mar 24, 2026"
 */
export function getDateLabel(dateString: string | null | undefined): string {
  if (isToday(dateString)) return 'Today';
  if (isYesterday(dateString)) return 'Yesterday';
  return formatDate(dateString);
}

/**
 * Convert local datetime to UTC ISO string for sending to backend
 */
export function toUTCString(date: Date): string {
  return dayjs(date).utc().toISOString();
}

/**
 * Get current UTC timestamp as ISO string
 */
export function getCurrentUTCTimestamp(): string {
  return dayjs.utc().toISOString();
}

// Re-export dayjs for advanced usage
export { dayjs };
