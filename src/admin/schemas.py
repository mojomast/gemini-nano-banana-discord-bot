"""
Pydantic models for admin authentication and authorization.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime

class OAuth2Token(BaseModel):
    """OAuth2 access token response model."""
    access_token: str
    token_type: str
    expires_in: int
    scope: str = "identify"
    refresh_token: Optional[str] = None

class DiscordUser(BaseModel):
    """Discord user information from API."""
    id: str
    username: str
    discriminator: str
    avatar: Optional[str] = None
    verified: bool = False
    email: Optional[str] = None
    flags: int = 0
    premium_type: int = 0
    public_flags: int = 0

class OAuth2Error(BaseModel):
    """OAuth2 error response model."""
    error: str
    error_description: Optional[str] = None
    error_uri: Optional[str] = None

class SessionData(BaseModel):
    """Session data model for API responses."""
    user_id: str
    csrf_token: str
    created_at: float
    token: str

class AuthErrorResponse(BaseModel):
    """Authentication/authorization error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

class HTTPAuthErrorResponse(BaseModel):
    """HTTP error response for auth failures."""
    detail: str = Field(..., description="Error detail message")

class NonceValidationRequest(BaseModel):
    """Request model for nonce validation."""
    nonce: str

class NonceValidationResponse(BaseModel):
    """Response model for nonce validation."""
    valid: bool
    remaining_ttl: Optional[int] = None

class AdminStatusResponse(BaseModel):
    """Response model for admin status."""
    is_admin: bool
    user_id: str
    valid_session: bool

class OAuth2CallbackResponse(BaseModel):
    """Response model for OAuth2 callback."""
    success: bool
    user_id: str
    session_token: str
    csrf_token: str