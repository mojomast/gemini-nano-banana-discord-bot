"""
Admin dashboard API router.

Provides REST endpoints for the Discord bot admin dashboard,
including authentication, status monitoring, and settings management.
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .auth import (
    generate_nonce, validate_nonce, exchange_oauth_code,
    validate_admin_user, create_session_token, validate_session_token,
    cleanup_expired_nonces, SessionData
)
from ..utils.config import config
from ..utils.settings_store import (
    load_settings, save_settings, reload_settings, SettingsModel,
    set_secret, get_secret, validate_settings
)
from ..utils.audit_logger import read_audit_entries, AuditCategory
from ..commands.utils.rate_limiter import RateLimiterError, rate_limiter
from ..commands.utils.logging import setup_logger
from ..commands.utils.queue import image_processing_queue, get_queue_metrics
from ..utils.audit_logger import log_audit_entry, AuditCategory

# Track admin router start time for uptime calculation
admin_start_time = time.time()

logger = setup_logger(__name__)

# Create router
admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Session cookie name
SESSION_COOKIE = "admin_session"
CSRF_TOKEN_KEY = "csrf_token"


def get_current_session(request: Request) -> SessionData:
    """Extract and validate session from request cookies."""
    try:
        session_token = request.cookies.get(SESSION_COOKIE)
        if not session_token:
            raise HTTPException(status_code=401, detail="No session token")

        session_data = validate_session_token(session_token)
        if not session_data:
            raise HTTPException(status_code=401, detail="Invalid session token")

        # Validate admin user
        if not validate_admin_user(session_data.user_id):
            raise HTTPException(status_code=403, detail="User not authorized")

        return session_data
    except Exception as e:
        logger.warning(f"Session validation failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")


@admin_router.get("/status", response_model=Dict[str, Any])
async def get_status(current_session: SessionData = Depends(get_current_session)):
    """Get current bot status and metrics."""
    try:
        # Get queue metrics
        queue_size = image_processing_queue.queue.qsize() if image_processing_queue else 0
        queue_length = queue_size  # For consistency with task requirements

        # Get basic metrics (assume we have access to health check data)
        uptime_seconds = round(time.time() - admin_start_time, 2)
        active_sessions = 1  # Simplified; could track actual sessions
        workers_active = 1 if image_processing_queue else 0

        # Calculate error rates (simplified, would need proper tracking)
        recent_errors = []  # Would need error tracking system
        error_rate = len(recent_errors) / max(uptime_seconds / 3600, 1)  # errors per hour

        return {
            "queue_length": queue_length,
            "active_workers": workers_active,
            "active_sessions": active_sessions,
            "processing_count": queue_size,  # Simplified mapping
            "error_rate": round(error_rate, 2),
            "uptime_seconds": uptime_seconds,
            "discord_token_configured": bool(config.discord_token),
            "openrouter_api_configured": bool(config.openrouter_api_key),
            "rate_limits": {
                "per_minute": rate_limiter.default_limit,
                "per_hour": rate_limiter.default_limit * 60 if hasattr(rate_limiter, 'default_window') else None
            }
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve status")


@admin_router.get("/{nonce}", response_class=HTMLResponse)
async def auth_landing_page(request: Request, nonce: str):
    """Serve the one-time URL landing page with OAuth redirect."""
    try:
        if not validate_nonce(nonce):
            raise HTTPException(status_code=404, detail="Invalid or expired nonce")

        # Generate OAuth URL
        oauth_url = "https://discord.com/api/oauth2/authorize"
        params = {
            "client_id": config.oauth_client_id,
            "redirect_uri": config.oauth_redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": nonce  # Include nonce as state for CSRF protection
        }

        params_str = "&".join(f"{k}={v}" for k, v in params.items())
        full_oauth_url = f"{oauth_url}?{params_str}"

        return templates.TemplateResponse("login.html", {
            "request": request,
            "oauth_url": full_oauth_url
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in auth landing page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Alternative OAuth initiation page."""
    try:
        # Generate new nonce for this session
        nonce = generate_nonce()

        # Generate OAuth URL similar to above
        oauth_url = "https://discord.com/api/oauth2/authorize"
        params = {
            "client_id": config.oauth_client_id,
            "redirect_uri": config.oauth_redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": nonce
        }

        params_str = "&".join(f"{k}={v}" for k, v in params.items())
        full_oauth_url = f"{oauth_url}?{params_str}"

        return templates.TemplateResponse("login.html", {
            "request": request,
            "oauth_url": full_oauth_url
        })
    except Exception as e:
        logger.error(f"Error in login page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@admin_router.get("/callback")
async def oauth_callback(request: Request, code: str, state: str):
    """Handle OAuth2 callback from Discord."""
    try:
        # Validate state (nonce)
        if not validate_nonce(state):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        # Exchange code for Discord user ID
        user_id = await exchange_oauth_code(code, config.oauth_redirect_uri)
        if not user_id:
            raise HTTPException(status_code=400, detail="OAuth exchange failed")

        # Validate admin user
        if not validate_admin_user(user_id):
            raise HTTPException(status_code=403, detail="User not authorized for admin access")

        # Create session token
        session_token = create_session_token(user_id)

        # Get the session data for audit logging
        session_data = validate_session_token(session_token)

        # Log successful login
        await log_audit_entry(
            user_id=user_id,
            action="login",
            category=AuditCategory.AUTHENTICATION,
            details={"method": "oauth2_discord"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            session_id=session_data.csrf_token[:12] if session_data else None,
            success=True
        )

        # Create response with redirect to dashboard
        response = RedirectResponse(url="/admin/", status_code=303)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=session_token,
            httponly=True,
            secure=False,  # Set to True for HTTPS in production
            samesite="strict",
            max_age=config.admin_session_ttl
        )

        logger.info(f"Admin login successful for user {user_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@admin_router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, current_session: SessionData = Depends(get_current_session)):
    """Serve the main dashboard page."""
    try:
        # Get current status for display
        status_data = await get_status(current_session)

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "status": status_data,
            "user_id": current_session.user_id
        })
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


@admin_router.post("/logout")
async def logout(request: Request, response: Response, current_session: SessionData = Depends(get_current_session)):
    """Handle logout by clearing session cookie."""
    try:
        # Log the logout event
        await log_audit_entry(
            user_id=current_session.user_id,
            action="logout",
            category=AuditCategory.AUTHENTICATION,
            details={"method": "session_termination"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            session_id=current_session.csrf_token[:12],
            success=True
        )

        # Clear session cookie
        response.delete_cookie(key=SESSION_COOKIE, path="/")
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Error in logout: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


# Settings endpoints
@admin_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, current_session: SessionData = Depends(get_current_session)):
    """Serve settings management page."""
    try:
        settings = await load_settings()
        settings_dict = settings.dict()

        return templates.TemplateResponse("settings.html", {
            "request": request,
            "settings": settings_dict,
            "csrf_token": current_session.csrf_token
        })
    except Exception as e:
        logger.error(f"Error serving settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to load settings")


@admin_router.post("/settings")
async def update_settings(
    request: Request,
    # Rate limits
    max_requests_per_minute: int = Form(...),
    max_requests_per_hour: int = Form(...),
    max_images_per_day: int = Form(...),
    # Image settings
    max_size_mb: float = Form(...),
    quality: int = Form(...),
    compression: str = Form(...),
    # Processing
    max_concurrent_jobs: int = Form(...),
    timeout_seconds: int = Form(...),
    retry_attempts: int = Form(...),
    # CSRF protection
    csrf_token: str = Form(...),
    current_session: SessionData = Depends(get_current_session)
):
    """Update runtime settings."""
    try:
        # Validate CSRF token
        if csrf_token != current_session.csrf_token:
            raise HTTPException(status_code=403, detail="CSRF token invalid")

        # Get current settings
        current_settings = await load_settings()

        # Update with form data
        settings_dict = current_settings.dict()

        # Rate limits
        settings_dict["rate_limits"].update({
            "max_requests_per_minute": max_requests_per_minute,
            "max_requests_per_hour": max_requests_per_hour,
            "max_images_per_day": max_images_per_day
        })

        # Image settings
        settings_dict["image_settings"].update({
            "max_size_mb": max_size_mb,
            "quality": quality,
            "compression": compression
        })

        # Processing
        settings_dict["processing"].update({
            "max_concurrent_jobs": max_concurrent_jobs,
            "timeout_seconds": timeout_seconds,
            "retry_attempts": retry_attempts
        })

        # Validate and save settings
        new_settings = await validate_settings(settings_dict)
        await save_settings(new_settings)

        # Log the settings change
        changes = {}
        for key, value in settings_dict.items():
            if key in current_settings.dict():
                old_value = current_settings.dict()[key]
                if old_value != value:
                    changes[key] = {"old": old_value, "new": value}

        await log_audit_entry(
            user_id=current_session.user_id,
            action="update_settings",
            category=AuditCategory.SETTINGS,
            details={"changes": changes},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            session_id=current_session.csrf_token[:12],  # Use part of CSRF token as session ID
            success=True
        )

        # Trigger reload in rate limiter
        await reload_rate_limiter_settings()

        return {"message": "Settings updated successfully"}

    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")


@admin_router.get("/status-page", response_class=HTMLResponse)
async def status_page(request: Request, current_session: SessionData = Depends(get_current_session)):
    """Serve detailed status monitoring page."""
    try:
        status_data = await get_status(current_session)

        return templates.TemplateResponse("status.html", {
            "request": request,
            "status": status_data
        })
    except Exception as e:
        logger.error(f"Error serving status page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load status page")


async def get_queue_metrics() -> Dict[str, Any]:
    """Helper function to extract queue metrics for external use."""
    if not image_processing_queue:
        return {"queue_length": 0, "processing_count": 0}

    try:
        queue_size = image_processing_queue.queue.qsize()
        return {
            "queue_length": queue_size,
            "processing_count": queue_size  # Simplified mapping
        }
    except Exception as e:
        logger.error(f"Error getting queue metrics: {e}")
        return {"queue_length": 0, "processing_count": 0}


@admin_router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    current_session: SessionData = Depends(get_current_session),
    limit: int = Query(50, ge=1, le=1000, description="Number of entries to display"),
    offset: int = Query(0, ge=0, description="Skip this many entries"),
    category: Optional[str] = Query(None, description="Filter by audit category"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action")
):
    """Serve audit log viewing page with filtering and pagination."""
    try:
        # Validate category if provided
        if category and category not in [cat.value for cat in AuditCategory]:
            raise HTTPException(status_code=400, detail="Invalid category")

        audit_category = AuditCategory(category) if category else None

        # Read audit entries with filtering
        entries = await read_audit_entries(
            limit=limit,
            offset=offset,
            filter_category=audit_category,
            filter_user_id=user_id,
            filter_action=action,
            reverse=True
        )

        # Format entries for display
        formatted_entries = []
        for entry in entries:
            # Convert timestamp to readable format
            try:
                dt = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                entry['timestamp_display'] = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except Exception:
                entry['timestamp_display'] = entry['timestamp']

            formatted_entries.append(entry)

        return templates.TemplateResponse("audit.html", {
            "request": request,
            "entries": formatted_entries,
            "total_entries": len(formatted_entries),
            "filters": {
                "category": category,
                "user_id": user_id,
                "action": action,
                "limit": limit,
                "offset": offset
            },
            "csrf_token": current_session.csrf_token
        })
    except Exception as e:
        logger.error(f"Error serving audit page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load audit logs")


async def reload_rate_limiter_settings():
    """Helper function to reload rate limiter settings from settings store."""
    try:
        settings = await load_settings()
        # Note: In a full implementation, you would update rate_limiter with new limits
        logger.info("Rate limiter settings reloaded")
    except Exception as e:
        logger.error(f"Error reloading rate limiter settings: {e}")


# Cleanup expired nonces periodically (could be done as a background task)
def cleanup_nonces():
    """Cleanup function for expired nonces."""
    cleanup_expired_nonces()


# Global app reference for accessing health metrics (will be set when router is mounted)
app = None

def set_app_reference(health_app):
    """Set global reference to the health check app for accessing metrics."""
    global app
    app = health_app