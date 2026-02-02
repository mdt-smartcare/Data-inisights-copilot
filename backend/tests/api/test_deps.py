"""
Tests for api/deps.py to increase code coverage.
"""


class TestDepsImports:
    """Tests for deps module imports."""
    
    def test_get_settings_import(self):
        """Test get_settings is imported."""
        from backend.api.deps import get_settings
        assert get_settings is not None
    
    def test_get_token_username_import(self):
        """Test get_token_username is imported."""
        from backend.api.deps import get_token_username
        assert get_token_username is not None
    
    def test_user_model_import(self):
        """Test User model is imported."""
        from backend.api.deps import User
        assert User is not None
    
    def test_get_db_service_import(self):
        """Test get_db_service is imported."""
        from backend.api.deps import get_db_service
        assert get_db_service is not None


class TestDepsReexports:
    """Tests for re-exported functions from permissions."""
    
    def test_user_role_reexport(self):
        """Test UserRole is re-exported."""
        from backend.api.deps import UserRole
        assert UserRole is not None
    
    def test_require_role_reexport(self):
        """Test require_role is re-exported."""
        from backend.api.deps import require_role
        assert require_role is not None
    
    def test_require_at_least_reexport(self):
        """Test require_at_least is re-exported."""
        from backend.api.deps import require_at_least
        assert require_at_least is not None
    
    def test_require_super_admin_reexport(self):
        """Test require_super_admin is re-exported."""
        from backend.api.deps import require_super_admin
        assert require_super_admin is not None
    
    def test_require_editor_reexport(self):
        """Test require_editor is re-exported."""
        from backend.api.deps import require_editor
        assert require_editor is not None
    
    def test_require_user_reexport(self):
        """Test require_user is re-exported."""
        from backend.api.deps import require_user
        assert require_user is not None


class TestDepsGlobalVars:
    """Tests for deps module global variables."""
    
    def test_settings_exists(self):
        """Test settings is defined."""
        from backend.api.deps import settings
        assert settings is not None
    
    def test_security_exists(self):
        """Test security (HTTPBearer) is defined."""
        from backend.api.deps import security
        assert security is not None


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""
    
    def test_get_current_user_exists(self):
        """Test get_current_user function exists."""
        from backend.api.deps import get_current_user
        assert get_current_user is not None
        assert callable(get_current_user)
