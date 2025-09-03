"""
Unit tests for admin authentication functionality.
"""
import pytest
import time
import json
from unittest.mock import patch, Mock
from itsdangerous import URLSafeTimedSerializer

from src.admin.auth import (
    generate_nonce,
    validate_nonce,
    create_session_token,
    validate_session_token,
    SessionData,
    nonce_store,
    validate_admin_user,
    exchange_oauth_code,
)


# Mock config values
@pytest.fixture
def mock_config():
    """Mock configuration values."""
    with patch('src.admin.auth.config') as mock_conf:
        mock_conf.admin_nonce_ttl = 300  # 5 minutes
        mock_conf.admin_session_ttl = 1200  # 20 minutes
        mock_conf.dashboard_secret_key = 'test_secret_key_12345678901234567890'
        mock_conf.oauth_client_id = 'test_client_id'
        mock_conf.oauth_client_secret = 'test_client_secret'
        mock_conf.admin_user_ids = ['123456789', '987654321']
        yield mock_conf


class TestGenerateNonce:
    """Test nonce generation functionality."""

    def setup_method(self):
        """Clear nonce store before each test."""
        nonce_store.clear()

    def test_generate_nonce_creates_random_string(self, mock_config):
        """Test that generate_nonce creates a unique random string."""
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()

        assert nonce1 != nonce2
        assert len(nonce1) >= 32  # token_urlsafe with 32 bytes creates longer string
        assert nonce1.isalnum() or '-' in nonce1 or '_' in nonce1  # urlsafe chars

    def test_generate_nonce_stores_data(self, mock_config):
        """Test that nonce data is properly stored."""
        nonce = generate_nonce()

        assert nonce in nonce_store
        data = nonce_store[nonce]

        assert 'created_at' in data
        assert 'expires_at' in data
        assert 'used' in data
        assert data['used'] is False
        assert data['expires_at'] == data['created_at'] + mock_config.admin_nonce_ttl

    def test_generate_nonce_custom_ttl(self):
        """Test custom TTL for generated nonce."""
        custom_ttl = 600
        nonce = generate_nonce(ttl_seconds=custom_ttl)

        data = nonce_store[nonce]
        assert data['expires_at'] - data['created_at'] == custom_ttl


class TestValidateNonce:
    """Test nonce validation functionality."""

    def setup_method(self):
        """Clear nonce store before each test."""
        nonce_store.clear()

    @patch('src.admin.auth.time.time')
    def test_validate_nonce_valid_nonce(self, mock_time, mock_config):
        """Test validation of a valid unused nonce."""
        mock_time.return_value = 1000.0
        nonce = generate_nonce()
        mock_time.return_value = 1100.0  # Still within TTL

        assert validate_nonce(nonce) is True

        # Verify nonce is marked as used
        data = nonce_store[nonce]
        assert data['used'] is True

    def test_validate_nonce_nonexistent(self):
        """Test validation of nonexistent nonce."""
        assert validate_nonce('nonexistent_nonce') is False

    @patch('src.admin.auth.time.time')
    def test_validate_nonce_expired(self, mock_time, mock_config):
        """Test validation fails for expired nonce."""
        mock_time.return_value = 1000.0
        nonce = generate_nonce()  # TTL = 300

        mock_time.return_value = 1400.0  # Expired (1000 + 300 + 100)
        assert validate_nonce(nonce) is False

        # Verify expired nonce is removed
        assert nonce not in nonce_store

    @patch('src.admin.auth.time.time')
    def test_validate_nonce_already_used(self, mock_time, mock_config):
        """Test validation fails for already used nonce."""
        mock_time.return_value = 1000.0
        nonce = generate_nonce()

        # First use
        assert validate_nonce(nonce) is True

        # Second use should fail
        mock_time.return_value = 1100.0
        assert validate_nonce(nonce) is False

    @patch('src.admin.auth.time.time')
    def test_expiration_cleanup_valid_nonce(self, mock_time, mock_config):
        """Test expired nonces are cleaned up during validation."""
        mock_time.return_value = 1000.0
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()

        # Expire first nonce
        mock_time.return_value = 1860.0  # Way past expiry
        assert validate_nonce(nonce1) is False

        # Second nonce should still be valid if within time
        mock_time.return_value = 1300.0  # Still valid
        assert nonce2 in nonce_store  # Should not have been cleaned up


class TestCreateSessionToken:
    """Test session token creation and validation."""

    def test_create_session_token_generates_token(self, mock_config):
        """Test token creation generates a valid string."""
        token = create_session_token('123456789')

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_session_token_with_custom_ttl(self, mock_config):
        """Test token creation with custom TTL."""
        mock_config.admin_session_ttl = 500
        token = create_session_token('123456789', ttl_seconds=500)
        # Validation below will handle expiration check

    def test_create_session_token_can_be_validated(self, mock_config):
        """Test that created token can be validated."""
        token = create_session_token('123456789')

        session_data = validate_session_token(token)

        assert session_data is not None
        assert session_data.user_id == '123456789'
        assert session_data.csrf_token != ''
        assert session_data.created_at > 0

    @patch('src.admin.auth.time.time')
    def test_create_session_token_expiration(self, mock_time, mock_config):
        """Test token can be validated after creation."""
        mock_time.return_value = 1000.0
        token = create_session_token('123456789')

        # Move time forward but within TTL
        mock_time.return_value = 1100.0
        session_data = validate_session_token(token)
        assert session_data is not None

    @patch('src.admin.auth.time.time')
    def test_validate_session_token_expired(self, mock_time, mock_config):
        """Test expired session token validation fails."""
        mock_time.return_value = 1000.0
        token = create_session_token('123456789', ttl_seconds=300)

        # Move time past expiration
        mock_time.return_value = 1400.0
        session_data = validate_session_token(token)
        assert session_data is None

    def test_validate_session_token_invalid_signature(self, mock_config):
        """Test invalid signature validation fails."""
        invalid_token = "invalid.signature.here"
        session_data = validate_session_token(invalid_token)
        assert session_data is None

    def test_validate_session_token_wrong_secret(self, mock_config):
        """Test validation with wrong secret fails."""
        token = create_session_token('123456789')

        # Test with different secret - should fail
        mock_config.dashboard_secret_key = 'different_secret_12345'
        invalid_session = validate_session_token(token)
        assert invalid_session is None


class TestValidateAdminUser:
    """Test admin user validation."""

    def test_validate_admin_user_allowed(self, mock_config):
        """Test validation succeeds for allowed user."""
        assert validate_admin_user('123456789') is True

    def test_validate_admin_user_not_allowed(self, mock_config):
        """Test validation fails for non-allowed user."""
        assert validate_admin_user('999999999') is False


@pytest.mark.asyncio
class TestExchangeOAuthCode:
    """Test OAuth2 code exchange (mocked)."""

    @patch('src.admin.auth.httpx.AsyncClient')
    async def test_exchange_oauth_code_success(self, mock_client, mock_config):
        """Test successful OAuth2 code exchange."""
        # Mock the OAuth client and user API response
        mock_oauth_client = Mock()
        mock_oauth_client.fetch_token.return_value = {"access_token": "test_token"}

        mock_user_response = Mock()
        mock_user_response.json.return_value = {"id": "123456789"}
        mock_oauth_client.get.return_value = mock_user_response

        # Mock context manager
        mock_client.return_value.__aenter__.return_value = Mock()
        mock_client.return_value.__aenter__.return_value.__aenter__.return_value = mock_oauth_client

        result = await exchange_oauth_code("test_code", "http://localhost/callback")

        assert result == "123456789"
        mock_oauth_client.fetch_token.assert_called_once()
        mock_oauth_client.get.assert_called_once_with('https://discord.com/api/users/@me')

    @patch('src.admin.auth.httpx.AsyncClient')
    async def test_exchange_oauth_code_failure(self, mock_client, mock_config):
        """Test OAuth2 code exchange failure handling."""
        # Mock HTTP error
        mock_oauth_client = Mock()
        mock_oauth_client.fetch_token.side_effect = Exception("OAuth2 error")

        mock_client.return_value.__aenter__.return_value = Mock()
        mock_client.return_value.__aenter__.return_value.__aenter__.return_value = mock_oauth_client

        result = await exchange_oauth_code("invalid_code", "http://localhost/callback")

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])