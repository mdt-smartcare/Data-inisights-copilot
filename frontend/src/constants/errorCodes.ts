/**
 * Standardized error codes for API responses.
 * Auto-generated from shared/constants.json - DO NOT EDIT MANUALLY
 */
import constants from '../../../shared/constants.json';

export const ErrorCode = {
  ...constants.errorCodes
} as const;

export type ErrorCodeType = typeof ErrorCode[keyof typeof ErrorCode];
