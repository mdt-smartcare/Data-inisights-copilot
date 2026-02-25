import { describe, it, expect } from 'vitest';
import {
  ROLE_HIERARCHY,
  roleAtLeast,
  canManageUsers,
  canViewAllAuditLogs,
  canManageConnections,
  canEditConfig,
  canEditPrompt,
  canPublishPrompt,
  canRollback,
  canExecuteQuery,
  canViewHistory,
  canViewConfig,
  canViewInsights,
  isReadOnly,
  ROLE_DISPLAY_NAMES,
  getRoleDisplayName,
} from '../../utils/permissions';
import type { User } from '../../types';

describe('Permissions', () => {
  const createUser = (role: 'admin' | 'user'): User => ({
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    role: role,
  });

  const admin = createUser('admin');
  const user = createUser('user');

  describe('ROLE_HIERARCHY', () => {
    it('should define roles in correct order', () => {
      expect(ROLE_HIERARCHY).toEqual(['admin', 'user']);
    });
  });

  describe('roleAtLeast', () => {
    it.each([
      ['admin', 'user', true],
      ['admin', 'admin', true],
      ['user', 'user', true],
      ['user', 'admin', false],
    ])('roleAtLeast(%s, %s) should return %s', (userRole, requiredRole, expected) => {
      expect(roleAtLeast(userRole, requiredRole as 'admin' | 'user')).toBe(expected);
    });

    it('should return false for undefined or invalid roles', () => {
      expect(roleAtLeast(undefined, 'user')).toBe(false);
      expect(roleAtLeast('invalid', 'user')).toBe(false);
    });
  });

  describe('Admin Only Permissions', () => {
    it.each([
      [canManageUsers, 'canManageUsers'],
      [canViewAllAuditLogs, 'canViewAllAuditLogs'],
      [canManageConnections, 'canManageConnections'],
      [canPublishPrompt, 'canPublishPrompt'],
      [canRollback, 'canRollback'],
      [canEditConfig, 'canEditConfig'],
      [canEditPrompt, 'canEditPrompt'],
      [canViewHistory, 'canViewHistory'],
      [canViewConfig, 'canViewConfig'],
      [canViewInsights, 'canViewInsights'],
    ])('%s should only allow admin', (fn) => {
      expect(fn(admin)).toBe(true);
      expect(fn(user)).toBe(false);
      expect(fn(null)).toBe(false);
    });
  });

  describe('All Users Permissions', () => {
    it('canExecuteQuery should allow all authenticated users', () => {
      expect(canExecuteQuery(admin)).toBe(true);
      expect(canExecuteQuery(user)).toBe(true);
      expect(canExecuteQuery(null)).toBe(false);
    });
  });

  describe('isReadOnly', () => {
    it('should return true only for regular users and null', () => {
      expect(isReadOnly(admin)).toBe(false);
      expect(isReadOnly(user)).toBe(true);
      expect(isReadOnly(null)).toBe(true);
    });
  });

  describe('Role Display Names', () => {
    it('should have correct display names', () => {
      expect(ROLE_DISPLAY_NAMES).toEqual({
        admin: 'Admin',
        user: 'User',
      });
    });

    it('getRoleDisplayName should return correct names', () => {
      expect(getRoleDisplayName('admin')).toBe('Admin');
      expect(getRoleDisplayName('user')).toBe('User');
      expect(getRoleDisplayName('unknown_role')).toBe('unknown_role');
      expect(getRoleDisplayName(undefined)).toBe('Unknown');
    });
  });
});
