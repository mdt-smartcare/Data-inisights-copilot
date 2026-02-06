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
  const createUser = (role: string): User => ({
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    role: role as User['role'],
  });

  const superAdmin = createUser('super_admin');
  const editor = createUser('editor');
  const user = createUser('user');

  describe('ROLE_HIERARCHY', () => {
    it('should define roles in correct order', () => {
      expect(ROLE_HIERARCHY).toEqual(['super_admin', 'editor', 'user']);
    });
  });

  describe('roleAtLeast', () => {
    it.each([
      ['super_admin', 'editor', true],
      ['super_admin', 'user', true],
      ['editor', 'user', true],
      ['super_admin', 'super_admin', true],
      ['editor', 'editor', true],
      ['user', 'user', true],
      ['user', 'editor', false],
      ['user', 'super_admin', false],
      ['editor', 'super_admin', false],
    ])('roleAtLeast(%s, %s) should return %s', (userRole, requiredRole, expected) => {
      expect(roleAtLeast(userRole, requiredRole)).toBe(expected);
    });

    it('should return false for undefined or invalid roles', () => {
      expect(roleAtLeast(undefined, 'user')).toBe(false);
      expect(roleAtLeast('invalid', 'user')).toBe(false);
    });
  });

  describe('Super Admin Only Permissions', () => {
    it.each([
      [canManageUsers, 'canManageUsers'],
      [canViewAllAuditLogs, 'canViewAllAuditLogs'],
      [canManageConnections, 'canManageConnections'],
      [canPublishPrompt, 'canPublishPrompt'],
      [canRollback, 'canRollback'],
    ])('%s should only allow super_admin', (fn) => {
      expect(fn(superAdmin)).toBe(true);
      expect(fn(editor)).toBe(false);
      expect(fn(user)).toBe(false);
      expect(fn(null)).toBe(false);
    });
  });

  describe('Editor and Above Permissions', () => {
    it.each([
      [canEditConfig, 'canEditConfig'],
      [canEditPrompt, 'canEditPrompt'],
      [canViewHistory, 'canViewHistory'],
      [canViewConfig, 'canViewConfig'],
      [canViewInsights, 'canViewInsights'],
    ])('%s should allow editor and super_admin', (fn) => {
      expect(fn(superAdmin)).toBe(true);
      expect(fn(editor)).toBe(true);
      expect(fn(user)).toBe(false);
      expect(fn(null)).toBe(false);
    });
  });

  describe('All Users Permissions', () => {
    it('canExecuteQuery should allow all authenticated users', () => {
      expect(canExecuteQuery(superAdmin)).toBe(true);
      expect(canExecuteQuery(editor)).toBe(true);
      expect(canExecuteQuery(user)).toBe(true);
      expect(canExecuteQuery(null)).toBe(false);
    });
  });

  describe('isReadOnly', () => {
    it('should return true only for regular users and null', () => {
      expect(isReadOnly(superAdmin)).toBe(false);
      expect(isReadOnly(editor)).toBe(false);
      expect(isReadOnly(user)).toBe(true);
      expect(isReadOnly(null)).toBe(true);
    });
  });

  describe('Role Display Names', () => {
    it('should have correct display names', () => {
      expect(ROLE_DISPLAY_NAMES).toEqual({
        super_admin: 'Super Admin',
        editor: 'Editor',
        user: 'User',
      });
    });

    it('getRoleDisplayName should return correct names', () => {
      expect(getRoleDisplayName('super_admin')).toBe('Super Admin');
      expect(getRoleDisplayName('editor')).toBe('Editor');
      expect(getRoleDisplayName('user')).toBe('User');
      expect(getRoleDisplayName('unknown_role')).toBe('unknown_role');
      expect(getRoleDisplayName(undefined)).toBe('Unknown');
    });
  });
});
