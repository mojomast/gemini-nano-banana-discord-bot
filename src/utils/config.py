"""
Centralized configuration management for gemini-nano-banana-discord-bot.

This module loads environment variables into a structured configuration object.
All application settings are defined here with defaults.
"""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Configuration dataclass
class Config:
    # Discord settings
    discord_token: str

    # OpenRouter settings
    openrouter_api_key: str
    openrouter_base_url: str
    model_id: str
    referer: str
    title: str
    log_level: str
    max_retries: int
    timeout: int

    # Storage settings
    retention_hours: float
    cache_dir: Path

    # Image settings
    allowed_image_types: List[str]
    max_image_mb: float

    # Dashboard settings
    admin_user_ids: List[str]
    oauth_client_id: str
    oauth_client_secret: str
    oauth_redirect_uri: str
    dashboard_secret_key: str
    admin_session_ttl: int
    admin_nonce_ttl: int

    # Audit settings
    audit_webhook_url: Optional[str]

    def __init__(self):
        # Discord
        self.discord_token = self._get_required_env('DISCORD_TOKEN')

        # OpenRouter
        self.openrouter_api_key = self._get_required_env('OPENROUTER_API_KEY')
        self.openrouter_base_url = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
        self.model_id = os.getenv('MODEL_ID', 'google/gemini-2.5-flash-image-preview')
        self.referer = "https://github.com/mojomast/gemini-nano-banana-discord-bot"
        self.title = "gemini-nano-banana-discord-bot"
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.timeout = int(os.getenv('TIMEOUT', '60'))

        # Storage
        self.retention_hours = float(os.getenv('RETENTION_HOURS', '1.0'))
        self.cache_dir = Path(os.getenv('CACHE_DIR', '.cache'))

        # Images
        self.allowed_image_types = os.getenv('ALLOWED_IMAGE_TYPES', 'png,jpg,jpeg,webp').split(',')
        self.max_image_mb = float(os.getenv('MAX_IMAGE_MB', '10.0'))

        # Strip whitespace from types
        self.allowed_image_types = [t.strip() for t in self.allowed_image_types]

        # Dashboard
        self.admin_user_ids = [uid.strip() for uid in os.getenv('ADMIN_USER_IDS', '').split(',') if uid.strip()]
        self.oauth_client_id = self._get_required_env('OAUTH_CLIENT_ID')
        self.oauth_client_secret = self._get_required_env('OAUTH_CLIENT_SECRET')
        self.oauth_redirect_uri = self._get_required_env('OAUTH_REDIRECT_URI')
        self.dashboard_secret_key = self._get_required_env('DASHBOARD_SECRET_KEY')
        self.admin_session_ttl = int(os.getenv('ADMIN_SESSION_TTL_SECONDS', '1200'))
        self.admin_nonce_ttl = int(os.getenv('ADMIN_NONCE_TTL_SECONDS', '300'))

        # Audit settings
        self.audit_webhook_url = os.getenv('AUDIT_WEBHOOK_URL')

    @staticmethod
    def _get_required_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set.")
        return value

# Global config instance
config = Config()