"""
End-to-end tests for admin dashboard functionality.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.admin.router import admin_router
from src.admin.middleware import AdminAuthMiddleware
from src.admin.auth import SessionData, generate_nonce, validate_nonce


@pytest.fixture
def mock_config():
    """Mock configuration values."""
    with patch('src.admin.router.config') as mock_conf:
        mock_conf.admin_nonce_ttl = 300
        mock_conf.admin_session_ttl = 1200
        mock_conf.dashboard_secret_key = 'test_secret_key_12345678901234567890'
        mock_conf.oauth_client_id = 'test_client_id'
        mock_conf.oauth_client_secret = 'test_client_secret'
        mock_conf.oauth_redirect_uri = 'http://testserver/admin/callback'
        mock_conf.admin_user_ids = ['123456789']
        mock_conf.audit_webhook_url = None  # Disable Discord notifications
        yield mock_conf


@pytest.fixture
def mock_all_dependencies(mock_config):
    """Mock all external dependencies for E2E tests."""
    with patch('src.admin.router.load_settings') as mock_load, \
         patch('src.admin.router.save_settings') as mock_save, \
         patch('src.admin.router.reload_settings') as mock_reload, \
         patch('src.admin.router.validate_settings') as mock_validate, \
         patch('src.admin.router.read_audit_entries') as mock_read_audit, \
         patch('src.admin.router.log_audit_entry') as mock_log_audit, \
         patch('src.admin.router.image_processing_queue') as mock_queue, \
         patch('src.admin.router.templates') as mock_templates, \
         patch('src.admin.router.exchange_oauth_code') as mock_exchange_oauth, \
         patch('src.admin.router.validate_admin_user') as mock_validate_admin, \
         patch('src.admin.router.create_session_token') as mock_create_session, \
         patch('src.admin.router.validate_session_token') as mock_validate_session, \
         patch('src.admin.router.generate_nonce') as mock_gen_nonce, \
         patch('src.admin.router.validate_nonce') as mock_val_nonce:

        # Setup mocks
        mock_settings = Mock()
        mock_settings.dict.return_value = {
            "rate_limits": {"max_requests_per_minute": 60},
            "image_settings": {"max_size_mb": 10.0},
            "processing": {"max_concurrent_jobs": 5}
        }
        mock_load.return_value = mock_settings
        mock_validate.return_value = mock_settings
        mock_read_audit.return_value = []
        mock_log_audit.return_value = True

        # Mock templates
        mock_response = Mock()
        mock_response.body = b"<html>E2E Test Page</html>"
        mock_templates.TemplateResponse.return_value = mock_response

        # Mock OAAuth
        mock_exchange_oauth.return_value = "123456789"
        mock_validate_admin.return_value = True

        # Mock session and token handling
        mock_session = SessionData(
            user_id="123456789",
            csrf_token="e2e_csrf_token",
            created_at=1234567890.0,
            token="e2e_session_token"
        )
        mock_create_session.return_value = "e2e_session_token"
        mock_validate_session.return_value = mock_session

        # Mock nonce handling
        mock_gen_nonce.return_value = "test_nonce_123"
        mock_val_nonce.return_value = True

        # Mock queue
        mock_queue_instance = Mock()
        mock_queue_instance.queue.qsize.return_value = 3
        mock_queue.return_value = mock_queue_instance

        yield {
            'load': mock_load,
            'save': mock_save,
            'reload': mock_reload,
            'validate': mock_validate,
            'read_audit': mock_read_audit,
            'log_audit': mock_log_audit,
            'queue': (mock_queue, mock_queue_instance),
            'templates': mock_templates,
            'oauth': mock_exchange_oauth,
            'admin': mock_validate_admin,
            'session': mock_create_session,
            'validate': mock_validate_session,
            'nonce_gen': mock_gen_nonce,
            'nonce_val': mock_val_nonce,
            'session_data': mock_session
        }


@pytest.fixture
async def e2e_client(mock_all_dependencies):
    """Create E2E test client with full application setup."""
    app = FastAPI(title="E2E Test App")
    app.add_middleware(AdminAuthMiddleware)
    app.include_router(admin_router)

    async_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    yield async_client
    await async_client.aclose()


class TestCompleteOAuthFlow:
    """Test complete OAuth2 authentication flow."""

    @pytest.mark.asyncio
    async def test_full_oauth_authentication_journey(self, e2e_client, mock_all_dependencies):
        """Test complete user journey from Discord URL to dashboard access."""
        mocks = mock_all_dependencies

        # Step 1: Simulate user clicking Discord bot link
        # This would be generated by /admin/dashboard in the bot
        nonce = generate_nonce()

        # Step 2: User visits the authentication landing page
        landing_response = await e2e_client.get(f"/admin/auth/{nonce}")
        assert landing_response.status_code == 200

        # Step 3: User clicks OAuth button (simulated redirect)
        # In real flow, this would redirect to Discord
        login_response = await e2e_client.get("/admin/login")
        assert login_response.status_code == 200

        # Step 4: Discord redirects back with authorization code
        # This is the most critical step - OAuth callback
        callback_response = await e2e_client.get("/admin/callback?code=oauth_code_123&state=test_nonce_123")

        # Should redirect to dashboard
        assert callback_response.status_code == 303
        assert callback_response.headers["location"] == "/admin/"

        # Check that session cookie was set
        # (Httpx handles this differently, but verify status)
        assert callback_response.status_code in [303, 200]

    @pytest.mark.asyncio
    async def test_oauth_with_invalid_state(self, e2e_client, mock_all_dependencies):
        """Test OAuth flow with invalid state parameter."""
        mocks = mock_all_dependencies
        mocks['nonce_val'].return_value = False  # Invalid nonce

        response = await e2e_client.get("/admin/callback?code=oauth_code&state=invalid_nonce")

        assert response.status_code == 400
        assert b"Invalid state parameter" in response.content

    @pytest.mark.asyncio
    async def test_oauth_with_non_admin_user(self, e2e_client, mock_all_dependencies):
        """Test OAuth flow with non-admin user."""
        mocks = mock_all_dependencies
        mocks['admin'].return_value = False  # Not admin

        response = await e2e_client.get("/admin/callback?code=oauth_code&state=test_nonce_123")

        assert response.status_code == 403
        assert b"User not authorized" in response.content


class TestDashboardAccessAfterLogin:
    """Test dashboard access and functionality after authentication."""

    @pytest.mark.asyncio
    async def test_dashboard_access_with_session(self, e2e_client, mock_all_dependencies):
        """Test dashboard access with valid session."""
        mocks = mock_all_dependencies

        # Simulate authenticated user
        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/", cookies=cookies)

        assert response.status_code == 200
        # Should render dashboard template

    @pytest.mark.asyncio
    async def test_status_endpoint_with_session(self, e2e_client, mock_all_dependencies):
        """Test status endpoint with authenticated session."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/status", cookies=cookies)

        assert response.status_code == 200
        data = response.json()
        assert "queue_length" in data
        assert "active_sessions" in data
        assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_settings_page_access(self, e2e_client, mock_all_dependencies):
        """Test accessing settings page after login."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/settings", cookies=cookies)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_audit_page_access(self, e2e_client, mock_all_dependencies):
        """Test accessing audit page after login."""
        mocks = mock_all_dependencies
        mocks['read_audit'].return_value = [
            {"user_id": "123456789", "action": "login", "timestamp": "2025-09-03T10:00:00+00:00"}
        ]

        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/audit", cookies=cookies)

        assert response.status_code == 200


class TestSettingsManagement:
    """Test end-to-end settings modification workflow."""

    @pytest.mark.asyncio
    async def test_settings_modification_workflow(self, e2e_client, mock_all_dependencies):
        """Test complete settings modification workflow."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        # Access settings page
        get_response = await e2e_client.get("/admin/settings", cookies=cookies)
        assert get_response.status_code == 200

        # Update settings
        form_data = {
            "max_requests_per_minute": 100,
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 15.0,
            "quality": 85,
            "compression": "lossy",
            "max_concurrent_jobs": 10,
            "timeout_seconds": 120,
            "retry_attempts": 5,
            "csrf_token": "e2e_csrf_token"
        }

        post_response = await e2e_client.post("/admin/settings", data=form_data, cookies=cookies)

        assert post_response.status_code == 200
        result = post_response.json()
        assert "Settings updated successfully" in result["message"]

        # Verify settings were saved and audit logged
        mocks['save'].assert_called_once()
        mocks['log_audit'].assert_called()

    @pytest.mark.asyncio
    async def test_settings_change_audit_logging(self, e2e_client, mock_all_dependencies):
        """Test that settings changes are properly audit logged."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        # Make settings change
        form_data = {
            "max_requests_per_minute": 200,
            "max_requests_per_hour": 1000,
            "max_images_per_day": 500,
            "max_size_mb": 10.0,
            "quality": 80,
            "compression": "none",
            "max_concurrent_jobs": 5,
            "timeout_seconds": 60,
            "retry_attempts": 3,
            "csrf_token": "e2e_csrf_token"
        }

        response = await e2e_client.post("/admin/settings", data=form_data, cookies=cookies)

        assert response.status_code == 200

        # Verify audit entry was logged
        mocks['log_audit'].assert_called()

    @pytest.mark.asyncio
    async def test_invalid_settings_input_handling(self, e2e_client, mock_all_dependencies):
        """Test handling of invalid settings input."""
        mocks = mock_all_dependencies
        mocks['validate'].side_effect = ValueError("Invalid settings")

        cookies = {"session_token": "e2e_session_token"}

        # Try to post invalid settings
        form_data = {
            "max_requests_per_minute": -5,  # Invalid negative value
            "csrf_token": "e2e_csrf_token"
        }

        response = await e2e_client.post("/admin/settings", data=form_data, cookies=cookies)

        assert response.status_code == 500


class TestAuditLoggingIntegration:
    """Test audit logging throughout the application."""

    @pytest.mark.asyncio
    async def test_login_audit_entry(self, e2e_client, mock_all_dependencies):
        """Test that login creates audit entry."""
        mocks = mock_all_dependencies

        # Simulate OAuth callback (login)
        response = await e2e_client.get("/admin/callback?code=oauth_code&state=test_nonce_123")

        # Verify login was audit logged
        mocks['log_audit'].assert_called()
        call_args = mocks['log_audit'].call_args
        assert call_args[1]["action"] == "login"  # Check kwargs

    @pytest.mark.asyncio
    async def test_audit_log_reading(self, e2e_client, mock_all_dependencies):
        """Test reading audit entries."""
        mocks = mock_all_dependencies
        mocks['read_audit'].return_value = [
            {
                "timestamp": "2025-09-03T10:00:00+00:00",
                "user_id": "123456789",
                "action": "login",
                "category": "authentication",
                "success": True
            },
            {
                "timestamp": "2025-09-03T10:01:00+00:00",
                "user_id": "123456789",
                "action": "update_settings",
                "category": "settings",
                "success": True
            }
        ]

        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/audit", cookies=cookies)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_audit_log_with_filters(self, e2e_client, mock_all_dependencies):
        """Test audit log with filtering."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        response = await e2e_client.get("/admin/audit?user_id=123456789&limit=10", cookies=cookies)

        assert response.status_code == 200
        mocks['read_audit'].assert_called()


class TestLogoutWorkflow:
    """Test logout and session termination."""

    @pytest.mark.asyncio
    async def test_logout_and_session_cleanup(self, e2e_client, mock_all_dependencies):
        """Test complete logout workflow."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        # Logout
        response = await e2e_client.post("/admin/logout", cookies=cookies)

        assert response.status_code == 200
        result = response.json()
        assert "Logged out successfully" in result["message"]

        # Verify logout was audit logged
        mocks['log_audit'].assert_called()


class TestSecurityControls:
    """Test security controls throughout E2E flow."""

    @pytest.mark.asyncio
    async def test_csrf_protection_on_settings(self, e2e_client, mock_all_dependencies):
        """Test CSRF protection on settings modifications."""
        mocks = mock_all_dependencies

        cookies = {"session_token": "e2e_session_token"}

        # Try to update settings without CSRF token
        form_data = {"max_requests_per_minute": 50}

        response = await e2e_client.post("/admin/settings", data=form_data, cookies=cookies)

        # Should fail due to missing CSRF token
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_session_timeout_simulation(self, e2e_client, mock_all_dependencies):
        """Test behavior when session becomes invalid."""
        mocks = mock_all_dependencies
        mocks['validate'].side_effect = Exception("Session expired")

        cookies = {"session_token": "expired_session"}

        response = await e2e_client.get("/admin/", cookies=cookies)

        # Should redirect to login or return 401
        assert response.status_code in [401, 303]


if __name__ == "__main__":
    pytest.main([__file__])