"""
Local storage and caching utilities module for gemini-nano-banana-discord-bot.

This module provides functions for managing a cache directory to store temporary files,
such as fetched attachments and generated images. All cached data is stored in temp files
only and should be cleaned up regularly using cleanup_cache(). Do not store sensitive data
that requires long-term persistence, as files may be removed after RETENTION_HOURS (default 1 hour).
"""
import os
import logging
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, Union
from threading import RLock

from .logging import setup_logger
from ...utils.config import config

# Configure logging
logger = setup_logger(__name__)

# Constants
DEFAULT_CACHE_DIR = ".cache"
DEFAULT_RETENTION_HOURS = 1.0

# Configuration from centralized config
RETENTION_HOURS = config.retention_hours
CACHE_DIR_ENV = str(config.cache_dir)

# Global lock for thread safety during cache operations
cache_lock = RLock()

# Helper: Ensure directory exists
def ensure_dir(path: Union[Path, str]):
    """Ensure the directory exists, creating it if necessary."""
    Path(path).mkdir(parents=True, exist_ok=True)

# Helper: Get the cache directory
def get_cache_dir() -> Path:
    """Get the cache directory path, ensuring it exists."""
    cache_dir = Path.cwd() / CACHE_DIR_ENV
    ensure_dir(cache_dir)
    return cache_dir

# Helper: Create a temp file in the cache directory
def create_temp_file(suffix: str = '.png') -> Path:
    """Create a unique temp file path in the cache directory."""
    cache_dir = get_cache_dir()
    unique_name = f"{uuid.uuid4()}{suffix}"
    return cache_dir / unique_name

# Helper: Clean up old cache files based on age
def cleanup_cache(age_hours: Optional[float] = None) -> int:
    """Remove cache files older than the specified hours. Returns number removed."""
    if age_hours is None:
        age_hours = RETENTION_HOURS
    cache_dir = get_cache_dir()
    now = time.time()
    removed_count = 0

    with cache_lock:
        for file_path in cache_dir.iterdir():
            if file_path.is_file():
                try:
                    file_mtime = file_path.stat().st_mtime
                    if now - file_mtime > age_hours * 3600:
                        file_path.unlink()
                        removed_count += 1
                        logger.debug(f"Cleaned up old cache file: {file_path}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not remove {file_path}: {e}")
                    continue  # Skip if permission denied

    logger.debug(f"Cleanup completed: {removed_count} files removed")
    return removed_count

# Cache: Store image data to cache
def cache_image(image_data: bytes, filename: str) -> Path:
    """Cache image data in the cache directory with the given filename. Returns cached path."""
    cache_dir = get_cache_dir()
    cached_path = cache_dir / filename

    with cache_lock:
        try:
            with open(cached_path, 'wb') as f:
                f.write(image_data)
            logger.debug(f"Cached image to {cached_path}")
            return cached_path
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to cache image {filename}: {e}")
            raise IOError(f"Could not write to cache: {e}") from e

# Cache: Get cached image path
def get_cached_image(filename: str) -> Optional[Path]:
    """Return the path to the cached image if it exists."""
    cache_dir = get_cache_dir()
    cached_path = cache_dir / filename

    if cached_path.exists() and cached_path.is_file():
        logger.debug(f"Found cached image: {cached_path}")
        return cached_path
    logger.debug(f"No cached image found: {filename}")
    return None

# Cache: Check if cached image is recent
def is_cached_recent(filename: str) -> bool:
    """Check if the cached image is within retention time."""
    cache_dir = get_cache_dir()
    cached_path = cache_dir / filename

    if cached_path.exists() and cached_path.is_file():
        file_mtime = cached_path.stat().st_mtime
        now = time.time()
        if now - file_mtime <= RETENTION_HOURS * 3600:
            logger.debug(f"Cached image {filename} is recent")
            return True

    logger.debug(f"Cached image {filename} is not recent or does not exist")
    return False