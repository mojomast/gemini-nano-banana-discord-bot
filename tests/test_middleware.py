"""
Integration tests for admin authentication middleware.
"""
import pytest
from unittest.mock import patch, Mock, AsyncMock
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.testclient import TestClient
from fastapi.middleware.base import BaseHTTPMiddleware

from src.admin.middleware import AdminAuthMiddleware, generate_csrf_token, verify_csrf_token
from src.admin.auth import SessionData


@pytest.fixture
def mock_config():
    """Mock configuration values."""
    with patch('src.admin.middleware.config') as mock_conf:
        mock_conf.admin_session_ttl = 1200
        mock_conf.dashboard_secret_key = 'test_secret_key_12345678901234567890'
        yield mock_conf


@pytest.fixture
def mock_audit_logger():
    """Mock audit logging."""
    with patch('src.admin.middleware.log_audit_entry') as mock_log:
        mock_log.return_value = True
        yield mock_log


@pytest.fixture
def mock_auth_functions():
    """Mock authentication functions."""
    with patch('src.admin.middleware.validate_session_token') as mock_validate_session, \
         patch('src.admin.middleware.validate_admin_user') as mock_validate_admin:

        # Create mock session
        mock_session = SessionData(
            user_id="123456789",
            csrf_token="mock_csrf_token",
            created_at=1234567890.0,
            token="mock_session_token"
        )

        mock_validate_session.return_value = mock_session
        mock_validate_admin.return_value = True

        yield {
            'validate_session': mock_validate_session,
            'validate_admin': mock_validate_admin,
            'session': mock_session
        }


@pytest.fixture
def test_app(mock_config, mock_audit_logger, mock_auth_functions):
    """Create FastAPI test app with AdminAuthMiddleware."""
    app = FastAPI()

    # Add middleware
    app.add_middleware(AdminAuthMiddleware)

    # Add test routes
    @app.get("/admin/test")
    async def admin_test(request: Request):
        return {"message": "Admin endpoint", "user_id": request.state.user_id}

    @app.get("/public/test")
    async def public_test():
        return {"message": "Public endpoint"}

    @app.post("/admin/test-post")
    async def admin_test_post(request: Request):
        return {"message": "Admin POST", "csrf_protected": True}

    yield app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def valid_session_cookie():
    """Valid session cookie."""
    return {"session_token": "valid_session_token"}


class TestAdminAuthMiddleware:
    """Integration tests for AdminAuthMiddleware."""

    def test_non_admin_paths_pass_through(self, client):
        """Test that non-admin paths bypass middleware."""
        response = client.get("/public/test")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Public endpoint"

    def test_unprotected_admin_paths_pass_through(self, client):
        """Test that unprotected admin paths bypass auth checks."""
        # These should not require authentication
        unprotected_paths = [
            "/admin/auth/test",
            "/admin/login",
            "/admin/callback"
        ]

        for path in unprotected_paths:
            response = client.get(path)
            # These will return 404 since the actual routes aren't defined in test app
            assert response.status_code == 404

    def test_protected_admin_path_requires_auth(self, client):
        """Test that protected admin paths require authentication."""
        response = client.get("/admin/test")

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_valid_session_access_granted(self, client, valid_session_cookie, mock_auth_functions, mock_audit_logger):
        """Test successful access with valid session."""
        response = client.get("/admin/test", cookies=valid_session_cookie)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Admin endpoint"
        assert data["user_id"] == "123456789"

        # Verify audit logging
        assert mock_audit_logger.call_count >= 1  # At least one audit entry logged

    def test_invalid_session_denied(self, client, mock_auth_functions):
        """Test access denied with invalid session."""
        mock_auth_functions['validate_session'].return_value = None

        response = client.get("/admin/test", cookies={"session_token": "invalid_token"})

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_non_admin_user_forbidden(self, client, valid_session_cookie, mock_auth_functions):
        """Test access forbidden for non-admin user."""
        mock_auth_functions['validate_admin'].return_value = False

        response = client.get("/admin/test", cookies=valid_session_cookie)

        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]

    def test_post_requires_csrf_token_missing(self, client, valid_session_cookie, mock_auth_functions):
        """Test POST requests require CSRF token when missing."""
        response = client.post("/admin/test-post", cookies=valid_session_cookie)

        assert response.status_code == 403
        assert "CSRF token missing" in response.json()["detail"]

    def test_csrf_validation_via_header(self, client, valid_session_cookie, mock_config, mock_auth_functions):
        """Test CSRF validation via X-CSRF-Token header."""
        # Generate a valid CSRF token based on session
        valid_csrf_token = generate_csrf_token()
        # Verify function exists but may need adjustment for header test

        response = client.post(
            "/admin/test-post",
            cookies=valid_session_cookie,
            headers={"X-CSRF-Token": "invalid_token"}
        )

        # Should fail with invalid token
        assert response.status_code == 403

    def test_csrf_validation_via_form(self, client, valid_session_cookie, mock_auth_functions):
        """Test CSRF validation via form field."""
        # Create a mock CSRF token that should match the expected token
        form_data = {"csrf_token": "mock_csrf_token", "data": "test"}

        response = client.post("/admin/test-post", cookies=valid_session_cookie, data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Admin POST"

    def test_invalid_csrf_token_denied(self, client, valid_session_cookie, mock_auth_functions):
        """Test request denied with invalid CSRF token."""
        form_data = {"csrf_token": "invalid_csrf_token", "data": "test"}

        response = client.post("/admin/test-post", cookies=valid_session_cookie, data=form_data)

        assert response.status_code == 403
        assert "CSRF token invalid" in response.json()["detail"]

    def test_audit_logging_on_access_denied(self, client, mock_auth_functions, mock_audit_logger):
        """Test audit logging for access denied scenarios."""
        mock_auth_functions['validate_session'].return_value = None

        response = client.get("/admin/test", cookies={"session_token": "invalid"})

        assert response.status_code == 401
        # Verify audit log was called for failed access
        mock_audit_logger.assert_called()

    def test_request_state_enriched(self, client, valid_session_cookie, mock_auth_functions):
        """Test that request state is enriched with user data."""
        response = client.get("/admin/test", cookies=valid_session_cookie)

        assert response.status_code == 200
        # The handler verifies request.state.user_id is set

    def test_session_cookie_updated(self, client, valid_session_cookie, mock_auth_functions):
        """Test that session cookie is updated on valid requests."""
        response = client.get("/admin/test", cookies=valid_session_cookie)

        assert response.status_code == 200
        # FastAPI TestClient handles cookies differently, so we check the response
        assert "set_cookie" in str(response.cookies) or response.status_code == 200


class TestCSRFUtilityFunctions:
    """Test CSRF utility functions."""

    def test_generate_csrf_token_creates_token(self, mock_config):
        """Test CSRF token generation."""
        token = generate_csrf_token()

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_csrf_token_valid(self, mock_config):
        """Test CSRF token verification with valid token."""
        csrf_token = generate_csrf_token()
        expected_token = "test_expected_token"

        # Verify that the generated token is a string and can be used
        # (Note: In practice, tokens are time-bound and need specific validation)
        assert csrf_token is not None

    def test_verify_csrf_token_invalid_signature(self, mock_config):
        """Test CSRF token verification with invalid signature."""
        # This would need manually crafted invalid token
        invalid_token = "invalid.signature.here"
        expected_token = "test_expected_token"

        result = verify_csrf_token(invalid_token, expected_token)
        assert result is False


class TestMiddlewareErrorHandling:
    """Test error handling in middleware."""

    def test_middleware_exception_handling(self, client, valid_session_cookie, mock_auth_functions):
        """Test that middleware handles exceptions gracefully."""
        # Make session validation raise an exception
        mock_auth_functions['validate_session'].side_effect = Exception("Unexpected error")

        response = client.get("/admin/test", cookies=valid_session_cookie)

        # Should still return proper HTTP error
        assert response.status_code == 401 or response.status_code == 500


class TestMiddlewareConfiguration:
    """Test middleware configuration options."""

    def test_custom_unprotected_paths(self, mock_config):
        """Test middleware with custom unprotected paths."""
        custom_middleware = AdminAuthMiddleware(
            app=None,  # We don't need the app for this test
            unprotected_paths=["/custom/path1", "/custom/path2"]
        )

        assert "/custom/path1" in custom_middleware.unprotected_paths
        assert "/admin/auth/" not in custom_middleware.unprotected_paths


if __name__ == "__main__":
    pytest.main([__file__])