import pytest
import asyncio
import json
import base64
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from io import BytesIO
import tempfile
import os
import discord
from discord import app_commands
from src.commands.utils.openrouter import OpenRouterClient
from src.commands.utils.images import ImageValidationError


@pytest.fixture
def mock_openrouter_client():
    """Mock OpenRouter client for testing."""
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
        client = OpenRouterClient()
        # Mock the session
        mock_session = AsyncMock()
        client.session = mock_session
        return client


@pytest.fixture
def sample_generated_image():
    """Sample GeneratedImage with base64 data."""
    from src.commands.utils.openrouter import GeneratedImage
    # Create a simple 1x1 white PNG base64
    img_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkWKpFDwAChGG8e3MmAAAAAElFTkSuQmCC"
    return GeneratedImage(base64=img_data)


@pytest.fixture
def mock_discord_attachment():
    """Mock Discord Attachment."""
    # Create a real small PNG image for testing
    from PIL import Image
    img = Image.new('RGB', (10, 10), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    image_data = buffer.getvalue()

    attachment = Mock(spec=discord.Attachment)
    attachment.filename = "test_image.png"
    attachment.content_type = "image/png"
    attachment.size = len(image_data)
    attachment.url = "https://example.com/test.png"

    # Mock async reading
    async def mock_read():
        return image_data
    attachment.read = AsyncMock(return_value=image_data)

    return attachment


@pytest.fixture
def mock_discord_interaction():
    """Mock Discord Interaction."""
    interaction = Mock(spec=discord.Interaction)
    interaction.user = Mock()
    interaction.user.display_name = "TestUser"
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


@pytest.fixture
def temp_image_path():
    """Create a temporary image file for testing."""
    img = Image.new('RGB', (100, 100), color='blue')
    fd, path = tempfile.mkstemp(suffix='.png')
    try:
        img.save(path, format='PNG')
        yield path
    finally:
        try:
            os.close(fd)
            os.unlink(path)
        except OSError:
            pass


@pytest.fixture
def golden_payloads():
    """Golden test payloads for validation."""
    return {
        "generate_basic": {
            "model": "google/gemini-2.5-flash-image-preview",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "test prompt"}]}
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        },
        "generate_with_style": {
            "model": "google/gemini-2.5-flash-image-preview",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "test prompt in anime style"}]}
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        },
        "generate_with_seed": {
            "model": "google/gemini-2.5-flash-image-preview",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "test prompt"}]}
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
            "seed": 42
        }
    }


@pytest.fixture
def mock_httpx_response_success():
    """Mock successful httpx response."""
    response = Mock()
    response.status_code = 200
    response.raise_for_status = Mock()
    response.json = Mock(return_value={
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "image", "base64": base64.b64encode(b"fake_image_data").decode()}
                    ]
                }
            }
        ]
    })
    return response


@pytest.fixture
def mock_httpx_response_error():
    """Mock error httpx response."""
    response = Mock()
    response.status_code = 500
    response.raise_for_status = Mock(side_effect=Exception("Server Error"))
    return response


@pytest.fixture(autouse=True)
def mock_env():
    """Mock environment variables for testing."""
    env_vars = {
        "OPENROUTER_API_KEY": "test_key",
        "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "MODEL_ID": "test-model",
        "LOG_LEVEL": "DEBUG",
        "MAX_RETRIES": "2",
        "TIMEOUT": "10"
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()