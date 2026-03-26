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
  canViewConfig,
  isReadOnly,
  ROLE_DISPLAY_NAMES,
  getRoleDisplayName,
  isSuperAdmin,
  isAtLeastAdmin,
} from '../../utils/permissions';
import type { User } from '../../types';

describe('Permissions', () => {
  const createUser = (role: 'super_admin' | 'admin' | 'user'): User => ({
    id: '11111111-1111-1111-1111-111111111111',
    username: 'testuser',
    email: 'test@example.com',
    role: role,
  });

  const superAdmin = createUser('super_admin');
  const admin = createUser('admin');
  const user = createUser('user');

  describe('ROLE_HIERARCHY', () => {
    it('should define roles in correct order', () => {
      expect(ROLE_HIERARCHY).toEqual(['super_admin', 'admin', 'user']);
    });
  });

  describe('roleAtLeast', () => {
    it.each([
      ['super_admin', 'user', true],
      ['super_admin', 'admin', true],
      ['super_admin', 'super_admin', true],
      ['admin', 'user', true],
      ['admin', 'admin', true],
      ['admin', 'super_admin', false],
      ['user', 'user', true],
      ['user', 'admin', false],
      ['user', 'super_admin', false],
    ])('roleAtLeast(%s, %s) should return %s', (userRole, requiredRole, expected) => {
      expect(roleAtLeast(userRole, requiredRole as 'super_admin' | 'admin' | 'user')).toBe(expected);
    });

    it('should return false for undefined or invalid roles', () => {
      expect(roleAtLeast(undefined, 'user')).toBe(false);
      expect(roleAtLeast('invalid', 'user')).toBe(false);
    });
  });

  describe('isSuperAdmin', () => {
    it('should return true only for super_admin', () => {
      expect(isSuperAdmin(superAdmin)).toBe(true);
      expect(isSuperAdmin(admin)).toBe(false);
      expect(isSuperAdmin(user)).toBe(false);
      expect(isSuperAdmin(null)).toBe(false);
    });
  });

  describe('isAtLeastAdmin', () => {
    it('should return true for super_admin and admin', () => {
      expect(isAtLeastAdmin(superAdmin)).toBe(true);
      expect(isAtLeastAdmin(admin)).toBe(true);
      expect(isAtLeastAdmin(user)).toBe(false);
      expect(isAtLeastAdmin(null)).toBe(false);
    });
  });

  describe('Admin Level Permissions', () => {
    it.each([
      [canManageUsers, 'canManageUsers'],
      [canViewAllAuditLogs, 'canViewAllAuditLogs'],
      [canManageConnections, 'canManageConnections'],
      [canEditConfig, 'canEditConfig'],
      [canEditPrompt, 'canEditPrompt'],
      [canViewConfig, 'canViewConfig'],
      [canPublishPrompt, 'canPublishPrompt'],
      [canRollback, 'canRollback'],
    ])('%s should allow super_admin and admin', (fn) => {
      expect(fn(superAdmin)).toBe(true);
      expect(fn(admin)).toBe(true);
      expect(fn(user)).toBe(false);
      expect(fn(null)).toBe(false);
    });
  });

  describe('All Users Permissions', () => {
    it('canExecuteQuery should allow all authenticated users', () => {
      expect(canExecuteQuery(superAdmin)).toBe(true);
      expect(canExecuteQuery(admin)).toBe(true);
      expect(canExecuteQuery(user)).toBe(true);
      expect(canExecuteQuery(null)).toBe(false);
    });
  });

  describe('isReadOnly', () => {
    it('should return true only for regular users and null', () => {
      expect(isReadOnly(superAdmin)).toBe(false);
      expect(isReadOnly(admin)).toBe(false);
      expect(isReadOnly(user)).toBe(true);
      expect(isReadOnly(null)).toBe(true);
    });
  });

  describe('Role Display Names', () => {
    it('should have correct display names', () => {
      expect(ROLE_DISPLAY_NAMES).toEqual({
        super_admin: 'Super Admin',
        admin: 'Admin',
        user: 'User',
      });
    });

    it('getRoleDisplayName should return correct names', () => {
      expect(getRoleDisplayName('super_admin')).toBe('Super Admin');
      expect(getRoleDisplayName('admin')).toBe('Admin');
      expect(getRoleDisplayName('user')).toBe('User');
      expect(getRoleDisplayName('unknown_role')).toBe('unknown_role');
      expect(getRoleDisplayName(undefined)).toBe('Unknown');
    });
  });
});
