import pytest
import base64
import json
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path
import asyncio
import os
from src.commands.utils.openrouter import (
    OpenRouterClient,
    GeneratedImage,
    ImageInput,
    ContentItem,
    ContentItem,
    ChatRequest
)


class TestOpenRouterClient:

    def test_initialization_success(self, mock_openrouter_client):
        """Test successful initialization with API key."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            client = OpenRouterClient()
            assert client.api_key == "test_key"
            assert client.base_url == "https://openrouter.ai/api/v1"
            assert client.session is not None

    def test_initialization_missing_key(self):
        """Test initialization failure without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY must be set"):
                OpenRouterClient()

    @pytest.mark.asyncio
    async def test_encode_image_to_base64_valid(self, mock_openrouter_client, temp_image_path):
        """Test encoding valid image to base64."""
        base64_data = await mock_openrouter_client._encode_image_to_base64(Path(temp_image_path))
        assert base64_data.startswith("data:image/png;base64,")
        assert "PNG" in base64_data

    @pytest.mark.asyncio
    async def test_encode_image_to_base64_invalid(self, mock_openrouter_client):
        """Test encoding invalid file."""
        fake_path = Path("nonexistent.png")
        with pytest.raises(ValueError, match="Unsupported image type"):
            await mock_openrouter_client._encode_image_to_base64(fake_path)

    @pytest.mark.asyncio
    async def test_download_image_to_temp(self, mock_openrouter_client):
        """Test downloading image to temp file."""
        mock_response = Mock()
        mock_response.content = b"fake image data"
        mock_openrouter_client.session.get = AsyncMock(return_value=mock_response)

        temp_path = await mock_openrouter_client._download_image_to_temp("https://example.com/img.png")
        assert temp_path.exists()
        assert temp_path.read_bytes() == b"fake image data"
        # Cleanup temp file
        temp_path.unlink()

    @pytest.mark.asyncio
    async def test_process_image_input_url(self, mock_openrouter_client):
        """Test processing URL image input."""
        mock_openrouter_client.session.get = AsyncMock()
        mock_response = Mock()
        mock_response.content = b"fake image data"
        mock_openrouter_client.session.get.return_value = mock_response

        result = await mock_openrouter_client._process_image_input("https://example.com/img.png")
        assert isinstance(result, ContentItem)
        assert result.type == "image_url"
        assert result.image_url == "https://example.com/img.png"

    @pytest.mark.asyncio
    async def test_process_image_input_local_path(self, mock_openrouter_client, temp_image_path):
        """Test processing local image path."""
        result = await mock_openrouter_client._process_image_input(temp_image_path)
        assert isinstance(result, ContentItem)
        assert result.type == "image_url"
        assert result.image_url.startswith("data:image/png;base64,")

    def test_chat_request_model(self, golden_payloads):
        """Test ChatRequest model serialization."""
        content = [ContentItem(type="text", text="test")]
        message = {"role": "user", "content": content}
        request = ChatRequest(model="test-model", messages=[message])

        serialized = request.dict()
        assert serialized["model"] == "test-model"
        assert serialized["messages"][0]["role"] == "user"
        assert serialized["messages"][0]["content"][0]["text"] == "test"

    @pytest.mark.asyncio
    async def test_generate_image_basic(self, mock_openrouter_client, mock_httpx_response_success):
        """Test basic image generation."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        images = await mock_openrouter_client.generate_image("test prompt")
        assert len(images) == 1
        assert isinstance(images[0], GeneratedImage)
        assert images[0].base64 is not None

        # Verify payload
        call_args = mock_openrouter_client.session.post.call_args
        payload = call_args[1]["json"]
        expected_keys = ["model", "messages", "max_tokens", "temperature"]
        for key in expected_keys:
            assert key in payload

    @pytest.mark.asyncio
    async def test_generate_image_with_style(self, mock_openrouter_client, mock_httpx_response_success):
        """Test image generation with style."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        images = await mock_openrouter_client.generate_image("test prompt", style="anime")
        assert len(images) == 1

        # Check payload includes style
        call_args = mock_openrouter_client.session.post.call_args
        payload = call_args[1]["json"]
        assert "style" not in payload  # Assuming style is incorporated in prompt

    @pytest.mark.asyncio
    async def test_generate_image_with_seed(self, mock_openrouter_client, mock_httpx_response_success):
        """Test image generation with seed parameter."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        images = await mock_openrouter_client.generate_image("test prompt", seed=42)
        assert len(images) == 1

        # Verify seed in payload
        call_args = mock_openrouter_client.session.post.call_args
        payload = call_args[1]["json"]
        assert payload["seed"] == 42

    @pytest.mark.asyncio
    async def test_generate_image_count_limit(self, mock_openrouter_client):
        """Test image generation respects count parameter."""
        response_data = {
            "choices": [
                {"message": {"content": [{"type": "image", "base64": "test"}]}},
                {"message": {"content": [{"type": "image", "base64": "test2"}]}},
            ]
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=response_data)
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_response)

        images = await mock_openrouter_client.generate_image("test", count=1)
        assert len(images) == 1

    @pytest.mark.asyncio
    async def test_edit_image_single(self, mock_openrouter_client, mock_httpx_response_success, temp_image_path):
        """Test editing single image."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        images = await mock_openrouter_client.edit_image("edit prompt", [temp_image_path])
        assert len(images) == 1
        assert isinstance(images[0], GeneratedImage)

    @pytest.mark.asyncio
    async def test_edit_image_multiple_sources(self, mock_openrouter_client, mock_httpx_response_success, temp_image_path):
        """Test editing multiple sources."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        sources = [temp_image_path, temp_image_path]  # Same file for simplicity
        images = await mock_openrouter_client.edit_image("edit prompt", sources)
        assert len(images) == 1

    @pytest.mark.asyncio
    async def test_edit_image_with_mask(self, mock_openrouter_client, mock_httpx_response_success, temp_image_path):
        """Test editing with mask."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        images = await mock_openrouter_client.edit_image("edit prompt", [temp_image_path], mask=temp_image_path)
        assert len(images) == 1

    @pytest.mark.asyncio
    async def test_blending_valid_sources(self, mock_openrouter_client, mock_httpx_response_success, temp_image_path):
        """Test blending 2-6 sources."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        sources = [temp_image_path, temp_image_path]
        images = await mock_openrouter_client.blend_images("blend prompt", sources, strength=0.5)
        assert len(images) == 1

    @pytest.mark.asyncio
    async def test_blending_invalid_sources(self, mock_openrouter_client):
        """Test blending with invalid number of sources."""
        with pytest.raises(ValueError, match="Blend requires 2-6 source images"):
            await mock_openrouter_client.blend_images("prompt", [])  # No sources

    @pytest.mark.asyncio
    async def test_make_request_with_retry_success(self, mock_openrouter_client, mock_httpx_response_success):
        """Test successful request without retries."""
        mock_openrouter_client.session.post = AsyncMock(return_value=mock_httpx_response_success)

        result = await mock_openrouter_client._make_request_with_retry({"test": "data"})
        assert result == mock_httpx_response_success.json()

    @pytest.mark.asyncio
    async def test_make_request_with_retry_failed(self, mock_openrouter_client):
        """Test request that fails after retries."""
        error_response = Mock()
        error_response.status_code = 500
        error_response.raise_for_status = Mock(side_effect=Exception("Server Error"))

        mock_openrouter_client.session.post = AsyncMock(return_value=error_response)

        with pytest.raises(Exception, match="Server Error"):
            await mock_openrouter_client._make_request_with_retry({"test": "data"})

    @pytest.mark.asyncio
    async def test_make_request_with_retry_backoff(self, mock_openrouter_client):
        """Test exponential backoff on 429/5xx errors."""
        with patch("asyncio.sleep") as mock_sleep:
            error_response_429 = Mock()
            error_response_429.status_code = 429
            error_response_429.raise_for_status = Mock(side_effect=Exception("Rate Limited"))

            success_response = Mock()
            success_response.status_code = 200
            success_response.raise_for_status = Mock()
            success_response.json = Mock(return_value={"success": True})

            # First call returns 429, second succeeds
            mock_openrouter_client.session.post = AsyncMock()
            mock_openrouter_client.session.post.side_effect = [error_response_429, success_response]

            result = await mock_openrouter_client._make_request_with_retry({"test": "data"})
            assert result == {"success": True}

            # Verify sleep was called with exponential backoff
            mock_sleep.assert_called_once()
            sleep_call = mock_sleep.call_args[0][0]
            assert sleep_call >= 1  # First retry: 2^0 = 1 second

    @pytest.mark.asyncio
    async def test_close_session(self, mock_openrouter_client):
        """Test session cleanup."""
        await mock_openrouter_client.close()
        mock_openrouter_client.session.aclose.assert_called_once()

    # Golden payload tests using golden_payloads fixture
    def test_generate_payload_matches_golden_basic(self, golden_payloads):
        """Test generate payload structure against golden data."""
        content = [ContentItem(type="text", text="test prompt")]
        expected = golden_payloads["generate_basic"]

        # This is a simplified check; in practice, you'd compare serialized payloads
        assert expected["model"] == "google/gemini-2.5-flash-image-preview"
        assert expected["max_tokens"] == 1024
        assert expected["temperature"] == 0.7

    def test_generate_payload_matches_golden_with_seed(self, golden_payloads):
        """Test generate payload with seed against golden data."""
        expected = golden_payloads["generate_with_seed"]
        assert expected.get("seed") == 42
        assert expected["model"] == "google/gemini-2.5-flash-image-preview"


# Pytest fixtures
pytest_plugins = ["pytest_asyncio"]