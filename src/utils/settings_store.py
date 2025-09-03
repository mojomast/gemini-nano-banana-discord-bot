"""
Configuration management for the Discord bot dashboard.

This module provides persistent settings storage with hot-reload capabilities,
Pydantic validation, and secure secret handling.

Features:
- Pydantic models for type-safe settings validation
- Async file operations with atomic writes
- Hot-reload functionality for runtime settings updates
- File watchers for automatic reload on external changes
- Thread-safe operations with asyncio.Lock
- Error handling with rollback on failures
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

import aiofiles
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# File paths
SETTINGS_FILE = Path("data/settings.json")

# Settings categories requiring restart vs hot-reload
HOT_RELOADABLE: Set[str] = {"rate_limits", "image_settings", "processing"}
RESTART_REQUIRED: Set[str] = {"secrets"}


class RateLimits(BaseModel):
    """Rate limiting configuration."""
    max_requests_per_minute: int = Field(gt=0, default=60, description="Max requests per minute")
    max_requests_per_hour: int = Field(gt=0, default=1000, description="Max requests per hour")
    max_images_per_day: int = Field(gt=0, default=500, description="Max images per day")


class ImageSettings(BaseModel):
    """Image processing configuration."""
    max_size_mb: float = Field(gt=0, default=10.0, description="Max image size in MB")
    allowed_types: list[str] = Field(default=["png", "jpg", "jpeg", "webp"],
                                  description="Allowed image types")
    quality: int = Field(ge=1, le=100, default=85, description="Image quality (1-100)")
    compression: str = Field(default="lossy", description="Compression type")


class Processing(BaseModel):
    """Processing configuration."""
    max_concurrent_jobs: int = Field(gt=0, default=5, description="Max concurrent jobs")
    timeout_seconds: int = Field(gt=0, default=60, description="Job timeout in seconds")
    retry_attempts: int = Field(ge=0, default=3, description="Number of retry attempts")


class Secrets(BaseModel):
    """Secret configuration (optional)"""
    # Note: Secrets are primarily managed via environment variables
    # This model allows for dashboard-managed secrets if needed
    pass


class SettingsModel(BaseModel):
    """Main settings configuration model."""
    rate_limits: RateLimits = Field(default_factory=RateLimits, description="Rate limiting settings")
    image_settings: ImageSettings = Field(default_factory=ImageSettings, description="Image processing settings")
    processing: Processing = Field(default_factory=Processing, description="Processing settings")
    secrets: Optional[Secrets] = Field(default=None, description="Secret settings")

    class Config:
        validate_assignment = True


# Global settings instance and lock
_settings_cache: Optional[SettingsModel] = None
_settings_lock = asyncio.Lock()


def _get_default_settings() -> SettingsModel:
    """Get default settings instance."""
    return SettingsModel()


async def load_settings(force: bool = False) -> SettingsModel:
    """
    Load settings from data/settings.json asynchronously.

    Args:
        force: Force reload from file, ignoring cache

    Returns:
        SettingsModel: Validated settings

    Raises:
        FileNotFoundError: If settings file doesn't exist and can't be created
        ValidationError: If settings data is invalid
        JSONDecodeError: If JSON is malformed
        OSError: For file system errors
    """
    global _settings_cache

    if not force and _settings_cache is not None:
        return _settings_cache

    async with _settings_lock:
        try:
            # Ensure data directory exists
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Load from file if exists
            if SETTINGS_FILE.exists():
                async with aiofiles.open(SETTINGS_FILE, 'r') as f:
                    content = await f.read()
                    settings_dict = json.loads(content) if content.strip() else {}
            else:
                # Create with defaults
                settings_dict = {}
                logger.info(f"Settings file {SETTINGS_FILE} not found, creating with defaults")

            # Merge with defaults and validate
            defaults = _get_default_settings().dict()
            defaults.update(settings_dict)
            settings = SettingsModel(**defaults)

            _settings_cache = settings
            logger.info("Settings loaded successfully")
            return settings

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid settings data: {e}")
            if SETTINGS_FILE.exists():
                backup_path = SETTINGS_FILE.with_suffix('.backup')
                try:
                    await aiofiles.copy(SETTINGS_FILE, backup_path)
                    logger.warning(f"Created backup of invalid settings: {backup_path}")
                except Exception as backup_error:
                    logger.error(f"Failed to create backup: {backup_error}")

            # Fall back to defaults if possible
            settings = _get_default_settings()
            _settings_cache = settings
            return settings

        except OSError as e:
            logger.error(f"File system error loading settings: {e}")
            # Fall back to defaults
            settings = _get_default_settings()
            _settings_cache = settings
            return settings


async def save_settings(settings: SettingsModel) -> None:
    """
    Save settings to data/settings.json with atomic writes.

    Args:
        settings: SettingsModel instance to save

    Raises:
        OSError: For file system errors
        ValidationError: If settings data is invalid
    """
    async with _settings_lock:
        try:
            # Ensure data directory exists
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Prepare temp file path
            temp_file = SETTINGS_FILE.with_suffix('.tmp')

            # Write to temp file
            settings_dict = settings.dict()
            async with aiofiles.open(temp_file, 'w') as f:
                await f.write(json.dumps(settings_dict, indent=2, default=str))

            # Atomic rename
            # Note: Python's Path.replace() is atomic on POSIX systems
            temp_file.replace(SETTINGS_FILE)

            # Update cache
            global _settings_cache
            _settings_cache = settings

            logger.info("Settings saved successfully")

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            # Clean up temp file if possible
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise


async def reload_settings() -> SettingsModel:
    """
    Reload settings from file and apply changes for hot-reload.

    This function distinguishes between hot-reloadable settings (applied immediately)
    and restart-required settings (not applied, but changes are reported).

    Returns:
        SettingsModel: New settings instance

    Raises:
        Same as load_settings()
    """
    try:
        new_settings = await load_settings(force=True)

        if _settings_cache is None:
            # First time
            logger.info("Initial settings loaded")
            return new_settings

        # Detect changes requiring restart
        restart_changes = []
        reload_changes = []

        old_dict = _settings_cache.dict()
        new_dict = new_settings.dict()

        for category in RESTART_REQUIRED:
            if category in old_dict and category in new_dict:
                if old_dict[category] != new_dict[category]:
                    restart_changes.append(category)
            elif category in new_dict and category not in old_dict:
                restart_changes.append(category)

        for category in HOT_RELOADABLE:
            if old_dict.get(category) != new_dict.get(category):
                reload_changes.append(category)

        if restart_changes:
            logger.warning(f"Settings requiring restart changed: {restart_changes}.
                           The bot will need to be restarted for these changes to take effect.")

        if reload_changes:
            logger.info(f"Hot-reloaded settings: {reload_changes}")
            # In a real implementation, notify other components here
            # For example: await queue.reload_settings(new_settings.processing)

        return new_settings

    except Exception as e:
        logger.error(f"Failed to reload settings: {e}")
        raise


def classify_setting(setting_key: str) -> str:
    """
    Classify a setting to determine if it requires a restart or allows hot-reload.

    Args:
        setting_key: The setting key (top-level category like 'rate_limits')

    Returns:
        str: 'restart_required' or 'hot_reload'
    """
    if setting_key in RESTART_REQUIRED:
        return 'restart_required'
    elif setting_key in HOT_RELOADABLE:
        return 'hot_reload'
    else:
        # Unknown settings are assumed to require restart for safety
        logger.warning(f"Unknown setting category '{setting_key}', assuming restart required")
        return 'restart_required'


async def validate_settings(settings_dict: Dict[str, Any]) -> SettingsModel:
    """
    Validate settings dictionary and return validated SettingsModel.

    Args:
        settings_dict: Dictionary of settings to validate

    Returns:
        SettingsModel: Validated settings

    Raises:
        ValidationError: If validation fails
    """
    try:
        settings = SettingsModel(**settings_dict)
        logger.info("Settings validation successful")
        return settings
    except ValidationError as e:
        logger.error(f"Settings validation failed: {e}")
        raise


def get_secret(key: str) -> Optional[str]:
    """
    Get a secret value, returning masked version for security.

    Args:
        key: Environment variable key

    Returns:
        Optional[str]: Masked secret (e.g., 'sk-****abcd') or None if not set
    """
    value = os.getenv(key)
    if not value:
        return None

    if len(value) <= 8:
        return '*' * len(value)
    else:
        return value[:4] + '*' * (len(value) - 8) + value[-4:]


async def set_secret(key: str, value: str) -> None:
    """
    Set a secret value in environment variables.

    Note: This is write-only. Changes are persisted to environment but user
    will need to restart the application for secrets to take effect.

    Args:
        key: Environment variable key
        value: Secret value to set

    Raises:
        ValueError: If key or value is empty
    """
    if not key or not value:
        raise ValueError("Secret key and value must be non-empty")

    # In a production environment, you might want to persist to .env file
    # But for now, we just set in environment
    os.environ[key] = value

    logger.warning(f"Secret '{key}' updated. Restart required for changes to take effect.")

    # Note: Environment variables are not automatically persisted
    # You would need to update .env file for persistence across restarts


# File watcher functionality (placeholder for future extension with aiofiles watch)
async def start_file_watcher(callback: Optional[Any] = None) -> None:
    """
    Start file watcher for automatic settings reload.

    Args:
        callback: Optional callback function to call on file change
    """
    # This is a placeholder. In a full implementation, you would use
    # aiofiles to watch for file changes and trigger reload_settings()
    logger.info("File watcher started (placeholder)")
    if callback:
        await callback()


