"""
Integration tests for admin router endpoints.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI
from httpx import AsyncClient

from src.admin.router import admin_router
from src.admin.auth import SessionData


@pytest.fixture
def mock_config():
    """Mock configuration values."""
    with patch('src.admin.router.config') as mock_conf:
        mock_conf.admin_nonce_ttl = 300
        mock_conf.admin_session_ttl = 1200
        mock_conf.discord_token = "mock_discord_token"
        mock_conf.openrouter_api_key = "mock_openrouter_key"
        mock_conf.oauth_client_id = "mock_client_id"
        mock_conf.oauth_redirect_uri = "http://testserver/admin/callback"
        mock_conf.rate_limits = Mock()
        mock_conf.rate_limits.per_minute = 60
        mock_conf.rate_limits.per_hour = 1000
        yield mock_conf


@pytest.fixture
def mock_auth_functions():
    """Mock all auth-related functions."""
    with patch('src.admin.router.generate_nonce') as mock_generate_nonce, \
         patch('src.admin.router.validate_nonce') as mock_validate_nonce, \
         patch('src.admin.router.exchange_oauth_code') as mock_exchange_oauth, \
         patch('src.admin.router.validate_admin_user') as mock_validate_admin, \
         patch('src.admin.router.create_session_token') as mock_create_session, \
         patch('src.admin.router.validate_session_token') as mock_validate_session:

        # Setup default returns
        mock_generate_nonce.return_value = "test_nonce"
        mock_validate_nonce.return_value = True
        mock_exchange_oauth.return_value = Mock()
        mock_exchange_oauth.return_value = "123456789"  # Return user ID
        mock_validate_admin.return_value = True
        mock_create_session.return_value = "mock_session_token"

        # Mock session validation
        mock_session = SessionData(
            user_id="123456789",
            csrf_token="mock_csrf_token",
            created_at=1234567890.0
        )
        mock_validate_session.return_value = mock_session

        yield {
            'generate_nonce': mock_generate_nonce,
            'validate_nonce': mock_validate_nonce,
            'exchange_oauth': mock_exchange_oauth,
            'validate_admin': mock_validate_admin,
            'create_session': mock_create_session,
            'validate_session': mock_validate_session,
        }


@pytest.fixture
def mock_settings_store():
    """Mock settings store functions."""
    with patch('src.admin.router.load_settings') as mock_load, \
         patch('src.admin.router.save_settings') as mock_save, \
         patch('src.admin.router.reload_settings') as mock_reload, \
         patch('src.admin.router.validate_settings') as mock_validate, \
         patch('src.admin.router.set_secret') as mock_set_secret:

        # Mock settings object
        mock_settings = Mock()
        mock_settings.dict.return_value = {
            "rate_limits": {"max_requests_per_minute": 60},
            "image_settings": {"max_size_mb": 10.0},
            "processing": {"max_concurrent_jobs": 5}
        }
        mock_load.return_value = mock_settings
        mock_validate.return_value = mock_settings

        yield {
            'load': mock_load,
            'save': mock_save,
            'reload': mock_reload,
            'validate': mock_validate,
            'set_secret': mock_set_secret
        }


@pytest.fixture
def mock_audit_logger():
    """Mock audit logging functions."""
    with patch('src.admin.router.log_audit_entry') as mock_log:
        mock_log.return_value = True
        yield mock_log


@pytest.fixture
def mock_queue():
    """Mock image processing queue."""
    with patch('src.admin.router.image_processing_queue') as mock_queue, \
         patch('src.admin.router.get_queue_metrics') as mock_get_metrics:

        mock_queue_instance = Mock()
        mock_queue_instance.queue.qsize.return_value = 5
        mock_queue.return_value = mock_queue_instance

        mock_get_metrics.return_value = {"queue_length": 5, "processing_count": 5}

        yield {'queue': mock_queue, 'metrics': mock_get_metrics}


@pytest.fixture
def mock_templates():
    """Mock Jinja2 templates."""
    with patch('src.admin.router.templates') as mock_templates:
        mock_response = Mock()
        mock_response.body = b"<html>Mock template</html>"
        mock_templates.TemplateResponse.return_value = mock_response
        yield mock_templates


@pytest.fixture
def test_app(mock_config, mock_auth_functions, mock_settings_store,
             mock_audit_logger, mock_queue, mock_templates):
    """Create FastAPI test app with mocked dependencies."""
    app = FastAPI()
    app.include_router(admin_router)

    # Mock time.time for uptime calculation
    with patch('src.admin.router.time.time', return_value=1234567900.0):
        yield app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def valid_session_token():
    """Create a valid session token for testing."""
    return "valid_session_token"


@pytest.fixture
def valid_session_cookie(valid_session_token):
    """Create valid session cookie."""
    return {"admin_session": valid_session_token}


class TestAdminRouterIntegration:
    """Integration tests for admin router functionality."""

    def test_status_endpoint_authenticated(self, client, valid_session_cookie, mock_queue):
        """Test /status endpoint with valid authentication."""
        response = client.get("/admin/status", cookies=valid_session_cookie)

        assert response.status_code == 200
        data = response.json()
        assert "queue_length" in data
        assert "active_sessions" in data
        assert "uptime_seconds" in data

    def test_status_endpoint_unauthenticated(self, client):
        """Test /status endpoint without authentication."""
        response = client.get("/admin/status")

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_auth_landing_page_valid_nonce(self, client, mock_auth_functions, mock_templates):
        """Test nonce-based auth landing page."""
        response = client.get("/admin/test_nonce")

        assert response.status_code == 200
        assert b"Mock template" in response.content

    def test_auth_landing_page_invalid_nonce(self, client, mock_auth_functions):
        """Test nonce-based auth landing page with invalid nonce."""
        mock_auth_functions['validate_nonce'].return_value = False

        response = client.get("/admin/invalid_nonce")

        assert response.status_code == 404
        assert "Invalid or expired nonce" in response.json()["detail"]

    def test_login_page(self, client, mock_auth_functions, mock_templates):
        """Test OAuth login page."""
        response = client.get("/admin/login")

        assert response.status_code == 200
        assert b"Mock template" in response.content

    @pytest.mark.asyncio
    async def test_oauth_callback_success(self, mock_auth_functions, mock_audit_logger):
        """Test successful OAuth callback."""
        # Create a test client for async operations
        from httpx import ASGITransport, AsyncClient
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(admin_router)
        async_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")

        # Configure mocks for success
        mock_auth_functions['validate_nonce'].return_value = True
        mock_auth_functions['exchange_oauth'].return_value = "123456789"
        mock_auth_functions['validate_admin'].return_value = True

        response = await async_client.get("/admin/callback?code=test_code&state=test_nonce")

        assert response.status_code == 303  # Redirect
        assert response.headers["location"] == "/admin/"
        # Check if session cookie was set (would need additional setup to verify)

        await async_client.aclose()

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_nonce(self, mock_auth_functions):
        """Test OAuth callback with invalid state."""
        from httpx import ASGITransport, AsyncClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(admin_router)
        async_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")

        mock_auth_functions['validate_nonce'].return_value = False

        response = await async_client.get("/admin/callback?code=test_code&state=invalid_nonce")

        assert response.status_code == 400
        assert "Invalid state parameter" in response.json()["detail"]

        await async_client.aclose()

    def test_dashboard_home_authenticated(self, client, valid_session_cookie, mock_templates, mock_settings_store):
        """Test dashboard home page with authentication."""
        response = client.get("/admin/", cookies=valid_session_cookie)

        assert response.status_code == 200
        assert b"Mock template" in response.content

    def test_dashboard_home_unauthenticated(self, client):
        """Test dashboard home page without authentication."""
        response = client.get("/admin/")

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_logout_authenticated(self, client, valid_session_cookie, mock_audit_logger):
        """Test logout with valid session."""
        response = client.post("/admin/logout", cookies=valid_session_cookie)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

    def test_settings_page_authenticated(self, client, valid_session_cookie, mock_templates, mock_settings_store):
        """Test settings page with authentication."""
        response = client.get("/admin/settings", cookies=valid_session_cookie)

        assert response.status_code == 200
        assert b"Mock template" in response.content

    def test_update_settings_valid_csrf(self, client, valid_session_cookie, mock_settings_store, mock_audit_logger):
        """Test settings update with valid CSRF token."""
        form_data = {
            "max_requests_per_minute": 100,
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 15.0,
            "quality": 80,
            "compression": "lossy",
            "max_concurrent_jobs": 8,
            "timeout_seconds": 120,
            "retry_attempts": 5,
            "csrf_token": "mock_csrf_token"  # Matches mock session
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Settings updated successfully"

    def test_update_settings_invalid_csrf(self, client, valid_session_cookie):
        """Test settings update with invalid CSRF token."""
        form_data = {
            "max_requests_per_minute": 100,
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 15.0,
            "quality": 80,
            "compression": "lossy",
            "max_concurrent_jobs": 8,
            "timeout_seconds": 120,
            "retry_attempts": 5,
            "csrf_token": "invalid_csrf_token"
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        assert response.status_code == 403
        assert "CSRF token invalid" in response.json()["detail"]

    def test_update_settings_validation_error(self, client, valid_session_cookie, mock_settings_store):
        """Test settings update with validation error."""
        mock_settings_store['validate'].side_effect = Exception("Validation failed")

        form_data = {
            "max_requests_per_minute": 100,
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 15.0,
            "quality": 80,
            "compression": "lossy",
            "max_concurrent_jobs": 8,
            "timeout_seconds": 120,
            "retry_attempts": 5,
            "csrf_token": "mock_csrf_token"
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        assert response.status_code == 500
        assert "Failed to update settings" in response.json()["detail"]

    def test_status_page_authenticated(self, client, valid_session_cookie, mock_templates):
        """Test detailed status page with authentication."""
        response = client.get("/admin/status-page", cookies=valid_session_cookie)

        assert response.status_code == 200
        assert b"Mock template" in response.content

    def test_audit_page_authenticated(self, client, valid_session_cookie, mock_templates):
        """Test audit page with authentication."""
        with patch('src.admin.router.read_audit_entries', return_value=[]):
            response = client.get("/admin/audit", cookies=valid_session_cookie)

            assert response.status_code == 200
            assert b"Mock template" in response.content

    def test_audit_page_with_filters(self, client, valid_session_cookie, mock_templates):
        """Test audit page with query parameters."""
        mock_entries = [
            {"user_id": "123456789", "action": "login", "category": "authentication"}
        ]

        with patch('src.admin.router.read_audit_entries', return_value=mock_entries):
            response = client.get("/admin/audit?user_id=123456789&limit=10", cookies=valid_session_cookie)

            assert response.status_code == 200
            assert b"Mock template" in response.content

    def test_audit_page_invalid_category(self, client, valid_session_cookie):
        """Test audit page with invalid category filter."""
        response = client.get("/admin/audit?category=invalid", cookies=valid_session_cookie)

        assert response.status_code == 400
        assert "Invalid category" in response.json()["detail"]


class TestCSRFProtection:
    """Test CSRF token validation."""

    def test_csrf_protection_on_settings_endpoint(self, client, valid_session_cookie):
        """Test that settings endpoint requires valid CSRF token."""
        form_data = {
            "max_requests_per_minute": 100,
            "csrf_token": "wrong_token"
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        assert response.status_code == 403


class TestFormValidation:
    """Test form input validation."""

    def test_settings_update_missing_required_field(self, client, valid_session_cookie):
        """Test settings update with missing required form field."""
        # Missing max_requests_per_minute
        form_data = {
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "csrf_token": "mock_csrf_token"
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        # This should fail due to missing form field
        assert response.status_code == 400

    def test_settings_update_invalid_numeric_input(self, client, valid_session_cookie):
        """Test settings update with invalid numeric input."""
        form_data = {
            "max_requests_per_minute": "not_a_number",
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 15.0,
            "quality": 80,
            "compression": "lossy",
            "max_concurrent_jobs": 8,
            "timeout_seconds": 120,
            "retry_attempts": 5,
            "csrf_token": "mock_csrf_token"
        }

        response = client.post("/admin/settings", data=form_data, cookies=valid_session_cookie)

        # Should fail due to invalid type conversion
        assert response.status_code == 400


class TestErrorHandling:
    """Test error handling in endpoints."""

    def test_endpoint_server_error(self, client, valid_session_cookie, mock_settings_store):
        """Test handling of unexpected server errors."""
        # Simulate database/network error
        mock_settings_store['load'].side_effect = Exception("Database connection failed")

        # This will test how endpoints handle unexpected errors
        response = client.get("/admin/settings", cookies=valid_session_cookie)

        assert response.status_code == 500


if __name__ == "__main__":
    pytest.main([__file__])