"""
Health Check Module for SlopBot

This module provides a FastAPI application for health monitoring and metrics.
It exposes endpoints for health checks and metrics on port 8000.
"""

import asyncio
import logging
import time
from typing import Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils.config import config
from .commands.utils.openrouter import OpenRouterClient
from .commands.utils.storage import get_cache_dir
from .commands.utils.logging import setup_logger

# Configure logging
logger = setup_logger(__name__)

# Global variables for metrics
app_start_time = time.time()
request_counter = 0

# Health Status Model
class HealthStatus(BaseModel):
    status: str  # "ok", "degraded", "unhealthy"
    details: Dict[str, Any]

# Metrics Model
class Metrics(BaseModel):
    uptime_seconds: float
    requests_processed: int
    health_checks: Dict[str, str]

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_start_time
    app_start_time = time.time()
    logger.info("Health check server starting up")
    yield
    logger.info("Health check server shutting down")

# Create FastAPI app
app = FastAPI(
    title="SlopBot Health Check API",
    description="Health monitoring and metrics for SlopBot",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware to count requests
@app.middleware("http")
async def count_requests(request, call_next):
    global request_counter
    request_counter += 1
    logger.debug(f"Request count: {request_counter}")
    return await call_next(request)

# Health Check Functions

async def check_bot_connectivity() -> Dict[str, Any]:
    """Check if the bot is connected to Discord."""
    try:
        # Note: In a real implementation, you'd have access to the bot instance
        # For now, just check if token is set (from config)
        if config.discord_token:
            return {"status": "ok", "message": "Discord token is configured"}
        else:
            return {"status": "unhealthy", "message": "Discord token not configured"}
    except Exception as e:
        logger.error(f"Bot connectivity check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}

async def check_openrouter_api() -> Dict[str, Any]:
    """Check OpenRouter API key validity."""
    try:
        if not config.openrouter_api_key:
            return {"status": "unhealthy", "message": "OpenRouter API key not configured"}

        # Test API key by making a small request
        # We'll make a minimal request to check authentication
        headers = {
            "Authorization": f"Bearer {config.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(f"{config.openrouter_base_url}/models")
            if response.status_code == 200:
                return {"status": "ok", "message": "API key valid"}
            elif response.status_code == 401:
                return {"status": "unhealthy", "message": "Invalid API key"}
            else:
                return {"status": "degraded", "message": f"API returned {response.status_code}"}
    except Exception as e:
        logger.error(f"OpenRouter API check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}

async def check_cache_storage() -> Dict[str, Any]:
    """Check cache storage status."""
    try:
        cache_dir = get_cache_dir()
        if not cache_dir.exists():
            # Try to create it
            cache_dir.mkdir(parents=True, exist_ok=True)

        # Test write access
        test_file = cache_dir / ".health_check_test"
        test_file.write_text("test")
        test_file.unlink()

        return {"status": "ok", "message": "Cache storage accessible"}
    except Exception as e:
        logger.error(f"Cache storage check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}

async def check_database() -> Dict[str, Any]:
    """Check database connectivity if configured."""
    # No database configured in current setup
    return {"status": "ok", "message": "No database configured"}

@app.get("/healthz", response_model=HealthStatus)
async def healthz():
    """Basic health check endpoint."""
    results = await asyncio.gather(
        check_bot_connectivity(),
        check_openrouter_api(),
        check_cache_storage(),
        check_database()
    )

    # Determine overall status
    if any(r["status"] == "unhealthy" for r in results):
        overall_status = "unhealthy"
    elif any(r["status"] == "degraded" for r in results):
        overall_status = "degraded"
    else:
        overall_status = "ok"

    return HealthStatus(
        status=overall_status,
        details={
            "bot_connectivity": results[0],
            "openrouter_api": results[1],
            "cache_storage": results[2],
            "database": results[3]
        }
    )

@app.get("/ready", response_model=HealthStatus)
async def ready():
    """Readiness check endpoint - more thorough than healthz."""
    # For simplicity, use same as healthz but could be more detailed
    return await healthz()

@app.get("/metrics", response_model=Metrics)
async def metrics():
    """Metrics endpoint."""
    uptime = time.time() - app_start_time

    return Metrics(
        uptime_seconds=uptime,
        requests_processed=request_counter,
        health_checks=await get_health_status_summary()
    )

async def get_health_status_summary() -> Dict[str, str]:
    """Get a summary of health check statuses."""
    results = await asyncio.gather(
        check_bot_connectivity(),
        check_openrouter_api(),
        check_cache_storage(),
        check_database()
    )

    return {
        "bot_connectivity": results[0]["status"],
        "openrouter_api": results[1]["status"],
        "cache_storage": results[2]["status"],
        "database": results[3]["status"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)