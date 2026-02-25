/**
 * Standardized error codes for API responses.
 * Single source of truth: shared/constants.json
 */
import constants from '../../../shared/constants.json';

export const ErrorCode = {
  ...constants.errorCodes
} as const;

export type ErrorCodeType = typeof ErrorCode[keyof typeof ErrorCode];
