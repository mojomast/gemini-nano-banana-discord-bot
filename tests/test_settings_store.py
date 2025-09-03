"""
Unit tests for settings store functionality.
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock, MagicMock

from src.utils.settings_store import (
    load_settings,
    save_settings,
    reload_settings,
    SettingsModel,
    RateLimits,
    ImageSettings,
    Processing,
    get_secret,
    set_secret,
    classify_setting,
    validate_settings,
    _settings_cache,
    SETTINGS_FILE,
    _settings_lock,
)


@pytest.fixture
def clear_cache():
    """Clear settings cache before each test."""
    global _settings_cache
    yield
    _settings_cache = None


@pytest.fixture
def temp_settings_file():
    """Create a temporary settings file for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = Path(temp_dir) / "settings.json"
        with patch('src.utils.settings_store.SETTINGS_FILE', temp_file):
            yield temp_file


@pytest.fixture
def mock_aiofiles():
    """Mock aiofiles for file operations."""
    with patch('src.utils.settings_store.aiofiles') as mock_aiofiles:
        # Mock context managers for async file operations
        mock_file = AsyncMock()
        mock_open_cm = MagicMock()
        mock_open_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open_cm.__aexit__ = AsyncMock(return_value=None)
        mock_aiofiles.open.return_value = mock_open_cm
        yield mock_aiofiles


class TestLoadSettings:
    """Test settings loading functionality."""

    @pytest.mark.asyncio
    async def test_load_settings_from_file(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test loading settings from existing file."""
        test_data = {
            "rate_limits": {"max_requests_per_minute": 30},
            "image_settings": {"max_size_mb": 5.0}
        }
        mock_aiofiles.open.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=json.dumps(test_data)
        )

        settings = await load_settings()

        assert isinstance(settings, SettingsModel)
        assert settings.rate_limits.max_requests_per_minute == 30
        assert settings.image_settings.max_size_mb == 5.0
        assert _settings_cache is not None

    @pytest.mark.asyncio
    async def test_load_settings_cache(self, clear_cache, mock_aiofiles):
        """Test that settings are cached on load."""
        settings1 = await load_settings()
        settings2 = await load_settings()

        # Should return the same instance from cache
        assert settings1 is settings2
        assert settings1 is _settings_cache

    @pytest.mark.asyncio
    async def test_load_settings_force_reload(self, clear_cache, mock_aiofiles):
        """Test force reload ignores cache."""
        settings1 = await load_settings()

        # Mark file as non-existent for second call
        with patch.object(Path, 'exists', return_value=False):
            settings2 = await load_settings(force=True)

        # Should be different instances
        assert settings1 is not settings2

    @pytest.mark.asyncio
    async def test_load_settings_empty_file(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test loading settings from empty file creates defaults."""
        mock_aiofiles.open.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=""
        )

        settings = await load_settings()

        assert isinstance(settings, SettingsModel)
        assert settings.rate_limits.max_requests_per_minute == 60  # default

    @pytest.mark.asyncio
    async def test_load_settings_invalid_json(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test loading settings with invalid JSON creates backup and falls back to defaults."""
        mock_aiofiles.open.return_value.__aenter__.return_value.read = AsyncMock(
            return_value="invalid json content"
        )
        mock_aiofiles.copy.return_value = None  # Mock backup creation

        settings = await load_settings()

        assert isinstance(settings, SettingsModel)
        # Should have created backup
        mock_aiofiles.copy.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_settings_creates_directory(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test that data directory is created if it doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            with patch('pathlib.Path.mkdir') as mock_mkdir:
                await load_settings()

                mock_mkdir.assert_called_once()


class TestSaveSettings:
    """Test settings saving functionality."""

    @pytest.mark.asyncio
    async def test_save_settings_atomic_write(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test saving settings uses atomic write operations."""
        settings = SettingsModel()
        settings.rate_limits.max_requests_per_minute = 100

        await save_settings(settings)

        # Should have written to temp file then renamed
        mock_aiofiles.open.assert_called()
        assert temp_settings_file.exists()

    @pytest.mark.asyncio
    async def test_save_settings_updates_cache(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test saving settings updates the cache."""
        settings = SettingsModel()
        settings.processing.timeout_seconds = 120

        await save_settings(settings)

        assert _settings_cache is settings

    @pytest.mark.asyncio
    async def test_save_settings_creates_directory(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test that data directory is created on save."""
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            await save_settings(SettingsModel())

            mock_mkdir.assert_called_once()


class TestReloadSettings:
    """Test settings reload functionality."""

    @pytest.mark.asyncio
    async def test_reload_settings_detects_changes(self, clear_cache, temp_settings_file, mock_aiofiles):
        """Test reload detects what settings changed."""
        # Set initial valid cache
        global _settings_cache
        _settings_cache = SettingsModel()
        _settings_cache.rate_limits.max_requests_per_minute = 50

        # Simulate file with different content
        new_data = {
            "rate_limits": {"max_requests_per_minute": 100},
            "image_settings": {"max_size_mb": 20.0}
        }
        mock_aiofiles.open.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=json.dumps(new_data)
        )

        settings = await reload_settings()

        assert settings.rate_limits.max_requests_per_minute == 100
        assert settings.image_settings.max_size_mb == 20.0


class TestClassifySetting:
    """Test setting classification for hot-reload vs restart."""

    def test_classify_hot_reloadable_settings(self):
        """Test classifying settings that can be hot-reloaded."""
        assert classify_setting("rate_limits") == "hot_reload"
        assert classify_setting("image_settings") == "hot_reload"
        assert classify_setting("processing") == "hot_reload"

    def test_classify_restart_required_settings(self):
        """Test classifying settings that require restart."""
        assert classify_setting("secrets") == "restart_required"
        assert classify_setting("unknown_setting") == "restart_required"


class TestValidateSettings:
    """Test settings validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_settings(self):
        """Test validating valid settings dictionary."""
        test_data = {
            "rate_limits": {"max_requests_per_minute": 50},
            "image_settings": {"max_size_mb": 8.0}
        }

        settings = await validate_settings(test_data)

        assert isinstance(settings, SettingsModel)
        assert settings.rate_limits.max_requests_per_minute == 50

    @pytest.mark.asyncio
    async def test_validate_invalid_settings_raises_error(self):
        """Test validating invalid settings raises ValidationError."""
        invalid_data = {
            "rate_limits": {"max_requests_per_minute": -5}  # Invalid negative value
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            await validate_settings(invalid_data)


class TestGetSecret:
    """Test secret retrieval functionality."""

    def test_get_secret_none_when_not_set(self):
        """Test get_secret returns None when environment variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_secret('NONEXISTENT_KEY') is None

    def test_get_secret_short_value_masked(self):
        """Test masking of short secret values."""
        with patch.dict(os.environ, {'TEST_KEY': 'abc'}):
            masked = get_secret('TEST_KEY')
            assert masked == '***'

    def test_get_secret_long_value_partially_masked(self):
        """Test partial masking of long secret values."""
        with patch.dict(os.environ, {'TEST_KEY': 'sk_abcdefghijklmnopqrs'}):
            masked = get_secret('TEST_KEY')
            assert masked == 'sk_****nopqrs'

    def test_get_secret_exactly_8_chars_masked(self):
        """Test masking of exactly 8 character secrets."""
        with patch.dict(os.environ, {'TEST_KEY': '12345678'}):
            masked = get_secret('TEST_KEY')
            assert masked == '********'


class TestSetSecret:
    """Test secret setting functionality."""

    @pytest.mark.asyncio
    async def test_set_secret_valid_key_value(self):
        """Test setting a valid secret."""
        key = 'MY_SECRET_KEY'
        value = 'my_secret_value'

        await set_secret(key, value)

        assert os.environ[key] == value

    @pytest.mark.asyncio
    async def test_set_secret_empty_key_raises_error(self):
        """Test setting secret with empty key raises error."""
        with pytest.raises(ValueError):
            await set_secret('', 'value')

    @pytest.mark.asyncio
    async def test_set_secret_empty_value_raises_error(self):
        """Test setting secret with empty value raises error."""
        with pytest.raises(ValueError):
            await set_secret('key', '')


class TestSettingsModels:
    """Test the Pydantic models themselves."""

    def test_rate_limits_model_validation(self):
        """Test RateLimits model validation."""
        # Valid
        limits = RateLimits(max_requests_per_minute=30)
        assert limits.max_requests_per_minute == 30

        # Invalid - negative value should raise error
        with pytest.raises(Exception):
            RateLimits(max_requests_per_minute=-5)

    def test_image_settings_model_default(self):
        """Test ImageSettings model defaults."""
        settings = ImageSettings()
        assert settings.max_size_mb == 10.0
        assert 'png' in settings.allowed_types

    def test_processing_model_defaults(self):
        """Test Processing model defaults."""
        proc = Processing()
        assert proc.max_concurrent_jobs == 5
        assert proc.timeout_seconds == 60

    def test_settings_model_composition(self):
        """Test SettingsModel builds correctly from sub-models."""
        settings = SettingsModel()

        assert isinstance(settings.rate_limits, RateLimits)
        assert isinstance(settings.image_settings, ImageSettings)
        assert isinstance(settings.processing, Processing)


if __name__ == "__main__":
    pytest.main([__file__])