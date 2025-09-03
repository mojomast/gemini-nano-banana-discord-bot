"""
Middleware for admin authentication, authorization, and CSRF protection.
"""

import secrets

from fastapi import HTTPException, Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import FormData
from itsdangerous import URLSafeTimedSerializer, BadSignature
from typing import Optional

from src.utils.config import config
from .auth import validate_session_token
from src.utils.audit_logger import log_audit_entry, AuditCategory

class AdminAuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for admin authentication and authorization.

    Handles session validation, admin allowlist checks, and CSRF protection
    for admin dashboard endpoints.
    """

    def __init__(self, app, unprotected_paths: Optional[list[str]] = None):
        super().__init__(app)
        self.unprotected_paths = unprotected_paths or ["/admin/auth/", "/admin/login", "/admin/callback"]

    async def dispatch(self, request: Request, call_next):
        """
        Process incoming requests to admin endpoints.

        Args:
            request: FastAPI request object.
            call_next: Next callable in middleware chain.

        Returns:
            Response object.

        Raises:
            HTTPException: For authentication/authorization failures.
        """
        # Skip non-admin paths
        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        # Skip unprotected admin paths
        if any(request.url.path.startswith(path) for path in self.unprotected_paths):
            return await call_next(request)

        # Validate session
        session_data = await self._validate_session(request)
        if not session_data:
            # Log failed authentication attempt
            await log_audit_entry(
                user_id="unknown",
                action="access_denied",
                category=AuditCategory.AUTHENTICATION,
                details={
                    "reason": "invalid_session",
                    "endpoint": request.url.path,
                    "method": request.method
                },
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                success=False
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required"
            )

        # Validate admin status
        try:
            await self._validate_admin(session_data.user_id)
        except HTTPException:
            # Log admin validation failure
            await log_audit_entry(
                user_id=session_data.user_id,
                action="access_denied",
                category=AuditCategory.AUTHENTICATION,
                details={
                    "reason": "insufficient_permissions",
                    "endpoint": request.url.path,
                    "method": request.method
                },
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                session_id=session_data.csrf_token[:12],
                success=False
            )
            raise

        # Check CSRF for state-changing methods
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                await self._validate_csrf(request, session_data.csrf_token)
            except HTTPException:
                # Log CSRF validation failure
                await log_audit_entry(
                    user_id=session_data.user_id,
                    action="csrf_violation",
                    category=AuditCategory.AUTHENTICATION,
                    details={
                        "endpoint": request.url.path,
                        "method": request.method
                    },
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    session_id=session_data.csrf_token[:12],
                    success=False
                )
                raise

        # Log successful admin access
        await log_audit_entry(
            user_id=session_data.user_id,
            action="access_granted",
            category=AuditCategory.AUTHENTICATION,
            details={
                "endpoint": request.url.path,
                "method": request.method
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            session_id=session_data.csrf_token[:12],
            success=True
        )

        # Set user info in request state for downstream use
        request.state.user_id = session_data.user_id
        request.state.csrf_token = session_data.csrf_token

        response = await call_next(request)

        # Set secure session cookie
        response.set_cookie(
            key="session_token",
            value=session_data.token,  # Assuming we have token
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="strict",
            max_age=config.admin_session_ttl
        )

        return response

    async def _validate_session(self, request: Request):
        """
        Validate session token from cookies.

        Args:
            request: FastAPI request object.

        Returns:
            SessionData object if valid, None otherwise.
        """
        token = request.cookies.get("session_token")
        if not token:
            return None

        return validate_session_token(token)

    async def _validate_admin(self, user_id: str):
        """
        Validate that user is in admin allowlist.

        Args:
            user_id: Discord user ID.

        Raises:
            HTTPException: If user is not admin.
        """
        from .auth import validate_admin_user  # Import here to avoid circular imports

        if not validate_admin_user(user_id):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions"
            )

    async def _validate_csrf(self, request: Request, expected_csrf_token: str):
        """
        Validate CSRF token from request.

        Checks X-CSRF-Token header or form field.

        Args:
            request: FastAPI request object.
            expected_csrf_token: Expected CSRF token from session.

        Raises:
            HTTPException: If CSRF validation fails.
        """
        # Check header first (JSON requests)
        csrf_token = request.headers.get("X-CSRF-Token")

        if not csrf_token:
            # Check form data (form requests)
            try:
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token")
            except Exception:
                pass

        if not csrf_token:
            raise HTTPException(
                status_code=403,
                detail="CSRF token missing"
            )

        # Validate token
        if not self._verify_csrf_token(csrf_token, expected_csrf_token):
            raise HTTPException(
                status_code=403,
                detail="CSRF token invalid"
            )

    def _verify_csrf_token(self, token: str, expected_token: str) -> bool:
        """
        Verify CSRF token against expected value.

        Args:
            token: Token from request.
            expected_token: Expected token from session.

        Returns:
            True if valid, False otherwise.
        """
        try:
            serializer = URLSafeTimedSerializer(config.dashboard_secret_key)
            data = serializer.loads(token, salt="csrf", max_age=3600)  # 1 hour
            return data.get("token") == expected_token
        except (BadSignature, Exception):
            return False

# Utility functions for generating CSRF tokens
def generate_csrf_token() -> str:
    """
    Generate a new CSRF token signed with the secret key.

    Returns:
        Signed CSRF token.
    """
    token = secrets.token_urlsafe(32)
    serializer = URLSafeTimedSerializer(config.dashboard_secret_key)
    return serializer.dumps(
        {"token": token},
        salt="csrf"
    )

def verify_csrf_token(token: str, expected_token: str) -> bool:
    """
    Verify a CSRF token.

    Args:
        token: Signed token.
        expected_token: Expected plaintext token.

    Returns:
        True if valid.
    """
    try:
        serializer = URLSafeTimedSerializer(config.dashboard_secret_key)
        data = serializer.loads(token, salt="csrf", max_age=3600)
        return data.get("token") == expected_token
    except (BadSignature, Exception):
        return False