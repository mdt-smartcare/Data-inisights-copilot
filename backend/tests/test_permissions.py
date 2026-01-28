"""
Unit tests for backend/core/permissions.py - RBAC enforcement.
"""
import pytest
from backend.core.permissions import (
    UserRole,
    ROLE_HIERARCHY,
    role_at_least,
    can_manage_users,
    can_view_all_audit_logs,
    can_manage_connections,
    can_edit_config,
    can_publish_prompt,
    can_execute_queries,
    can_view_config,
)


class TestUserRole:
    """Tests for UserRole enum."""
    
    def test_role_values(self):
        """Verify role string values match expected."""
        assert UserRole.SUPER_ADMIN.value == "super_admin"
        assert UserRole.EDITOR.value == "editor"
        assert UserRole.USER.value == "user"
        assert UserRole.VIEWER.value == "viewer"
    
    def test_role_hierarchy_contains_main_roles(self):
        """Hierarchy should contain super_admin, editor, user."""
        assert "super_admin" in ROLE_HIERARCHY
        assert "editor" in ROLE_HIERARCHY
        assert "user" in ROLE_HIERARCHY


class TestRoleAtLeast:
    """Tests for role_at_least hierarchy function."""
    
    def test_super_admin_is_at_least_super_admin(self):
        assert role_at_least("super_admin", "super_admin") is True
    
    def test_super_admin_is_at_least_editor(self):
        assert role_at_least("super_admin", "editor") is True
    
    def test_super_admin_is_at_least_user(self):
        assert role_at_least("super_admin", "user") is True
    
    def test_editor_is_at_least_editor(self):
        assert role_at_least("editor", "editor") is True
    
    def test_editor_is_at_least_user(self):
        assert role_at_least("editor", "user") is True
    
    def test_editor_is_not_at_least_super_admin(self):
        assert role_at_least("editor", "super_admin") is False
    
    def test_user_is_at_least_user(self):
        assert role_at_least("user", "user") is True
    
    def test_user_is_not_at_least_editor(self):
        assert role_at_least("user", "editor") is False
    
    def test_unknown_role_returns_false(self):
        assert role_at_least("unknown_role", "user") is False
        assert role_at_least("user", "unknown_role") is False


class TestPermissionHelpers:
    """Tests for individual permission check functions."""
    
    # can_manage_users
    def test_super_admin_can_manage_users(self):
        assert can_manage_users("super_admin") is True
    
    def test_editor_cannot_manage_users(self):
        assert can_manage_users("editor") is False
    
    def test_user_cannot_manage_users(self):
        assert can_manage_users("user") is False
    
    # can_view_all_audit_logs
    def test_super_admin_can_view_audit_logs(self):
        assert can_view_all_audit_logs("super_admin") is True
    
    def test_editor_cannot_view_audit_logs(self):
        assert can_view_all_audit_logs("editor") is False
    
    # can_manage_connections
    def test_super_admin_can_manage_connections(self):
        assert can_manage_connections("super_admin") is True
    
    def test_editor_cannot_manage_connections(self):
        assert can_manage_connections("editor") is False
    
    # can_edit_config
    def test_super_admin_can_edit_config(self):
        assert can_edit_config("super_admin") is True
    
    def test_editor_can_edit_config(self):
        assert can_edit_config("editor") is True
    
    def test_user_cannot_edit_config(self):
        assert can_edit_config("user") is False
    
    # can_publish_prompt
    def test_super_admin_can_publish_prompt(self):
        assert can_publish_prompt("super_admin") is True
    
    def test_editor_cannot_publish_prompt(self):
        assert can_publish_prompt("editor") is False
    
    # can_execute_queries
    def test_super_admin_can_execute_queries(self):
        assert can_execute_queries("super_admin") is True
    
    def test_editor_can_execute_queries(self):
        assert can_execute_queries("editor") is True
    
    def test_user_can_execute_queries(self):
        assert can_execute_queries("user") is True
    
    # can_view_config
    def test_all_hierarchy_roles_can_view_config(self):
        for role in ROLE_HIERARCHY:
            assert can_view_config(role) is True
    
    def test_viewer_cannot_view_config_via_hierarchy(self):
        # Viewer is NOT in ROLE_HIERARCHY, so can_view_config returns False
        assert can_view_config("viewer") is False
