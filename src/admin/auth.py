"""
Authentication module for admin dashboard.

Handles OAuth2 authentication with Discord, one-time nonces,
session management, and admin validation.
"""

import time
import secrets
import json
from typing import Dict, Optional, Any
from dataclasses import dataclass

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from src.utils.config import config

# In-memory nonce store (should be Redis in production)
nonce_store: Dict[str, Dict[str, Any]] = {}

# OAuth2 URLs for Discord
DISCORD_OAUTH_BASE_URL = "https://discord.com/api"
DISCORD_AUTHORIZE_URL = f"{DISCORD_OAUTH_BASE_URL}/oauth2/authorize"
DISCORD_TOKEN_URL = f"{DISCORD_OAUTH_BASE_URL}/oauth2/token"
DISCORD_USER_API_URL = f"{DISCORD_OAUTH_BASE_URL}/users/@me"

@dataclass
class SessionData:
    """Data stored in signed session token."""
    user_id: str
    csrf_token: str
    created_at: float
    token: str = ""  # The signed token itself, set after creation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "csrf_token": self.csrf_token,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], token: str = "") -> "SessionData":
        return cls(
            user_id=data["user_id"],
            csrf_token=data["csrf_token"],
            created_at=data["created_at"],
            token=token
        )

def generate_nonce(ttl_seconds: int = config.admin_nonce_ttl) -> str:
    """
    Generate a cryptographically random one-time nonce.

    Args:
        ttl_seconds: Time-to-live for the nonce in seconds (default 5 minutes).

    Returns:
        The generated nonce string.
    """
    nonce = secrets.token_urlsafe(32)
    expires_at = time.time() + ttl_seconds

    nonce_store[nonce] = {
        "created_at": time.time(),
        "expires_at": expires_at,
        "used": False
    }

    return nonce

def validate_nonce(nonce: str) -> bool:
    """
    Validate a one-time nonce.

    Checks if nonce exists, hasn't expired, and hasn't been used.
    Marks as used if valid.

    Args:
        nonce: The nonce to validate.

    Returns:
        True if nonce is valid, False otherwise.
    """
    if nonce not in nonce_store:
        return False

    nonce_data = nonce_store[nonce]
    current_time = time.time()

    if current_time > nonce_data["expires_at"]:
        del nonce_store[nonce]
        return False

    if nonce_data["used"]:
        return False

    # Mark as used
    nonce_data["used"] = True
    return True

async def exchange_oauth_code(code: str, redirect_uri: str) -> Optional[str]:
    """
    Exchange OAuth2 authorization code for Discord user ID.

    Args:
        code: The authorization code from Discord.
        redirect_uri: The redirect URI configured for OAuth2.

    Returns:
        Discord user ID if successful, None if failed.

    Raises:
        httpx.HTTPError: If OAuth2 request fails.
    """
    try:
        async with httpx.AsyncClient() as client:
            async with AsyncOAuth2Client(
                client_id=config.oauth_client_id,
                client_secret=config.oauth_client_secret,
                token_endpoint=DISCORD_TOKEN_URL,
                client=client
            ) as oauth_client:
                # Exchange code for token
                token_data = await oauth_client.fetch_token(
                    DISCORD_TOKEN_URL,
                    code=code,
                    redirect_uri=redirect_uri
                )

                # Get user info
                user_response = await oauth_client.get(DISCORD_USER_API_URL)
                user_response.raise_for_status()
                user_data = user_response.json()

                return user_data.get("id")

    except httpx.HTTPError as e:
        print(f"OAuth2 exchange failed: {e}")
        return None

def validate_admin_user(user_id: str) -> bool:
    """
    Validate if user is in admin allowlist.

    Args:
        user_id: Discord user ID to validate.

    Returns:
        True if user is admin, False otherwise.
    """
    return user_id in config.admin_user_ids

def create_session_token(user_id: str, ttl_seconds: int = config.admin_session_ttl) -> str:
    """
    Create a secure signed session token.

    Args:
        user_id: Discord user ID for session.
        ttl_seconds: Session TTL in seconds.

    Returns:
        Signed session token.
    """
    csrf_token = secrets.token_urlsafe(32)
    session_data = SessionData(
        user_id=user_id,
        csrf_token=csrf_token,
        created_at=time.time()
    )

    serializer = URLSafeTimedSerializer(config.dashboard_secret_key)
    token = serializer.dumps(
        session_data.to_dict(),
        salt="session",
        max_age=ttl_seconds
    )
    session_data.token = token
    return token

def validate_session_token(token: str) -> Optional[SessionData]:
    """
    Validate and decode a session token.

    Args:
        token: The signed session token.

    Returns:
        SessionData if valid and not expired, None otherwise.
    """
    try:
        serializer = URLSafeTimedSerializer(config.dashboard_secret_key)
        data = serializer.loads(token, salt="session", max_age=config.admin_session_ttl)
        return SessionData.from_dict(data, token)
    except (BadSignature, SignatureExpired, json.JSONDecodeError):
        return None

# Clean up expired nonces periodically (could be run as background task)
def cleanup_expired_nonces():
    """Remove expired nonces from store."""
    current_time = time.time()
    expired = [nonce for nonce, data in nonce_store.items() if current_time > data["expires_at"]]
    for nonce in expired:
        del nonce_store[nonce]