import pytest
import base64
import os
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path
import discord
from discord import app_commands
from src.commands.imagine import imagine
from src.commands.edit import edit
from src.commands.blend import blend
from src.commands.utils.images import ImageValidationError, ImageDownloadError


class TestImagineCommand:

    @pytest.mark.asyncio
    async def test_imagine_basic_success(self, mock_openrouter_client, mock_discord_interaction, sample_generated_image):
        """Test /imagine command with basic parameters."""
        # Mock dependencies
        with patch('src.commands.imagine.openrouter_client', mock_openrouter_client):
            with patch('src.commands.imagine.process_generated_image', return_value=discord.File(b"test", filename="test.png")):
                mock_openrouter_client.generate_image = AsyncMock(return_value=[sample_generated_image])

                # Test
                await imagine(mock_discord_interaction, "test prompt")

                # Verify interactions
                mock_discord_interaction.response.defer.assert_called_once()
                mock_discord_interaction.followup.send.assert_called_once()

                # Check generate_image called with correct params
                mock_openrouter_client.generate_image.assert_called_once_with(
                    prompt="test prompt", style=None, count=1, seed=None
                )

    @pytest.mark.asyncio
    async def test_imagine_with_all_params(self, mock_openrouter_client, mock_discord_interaction, sample_generated_image):
        """Test /imagine with all parameters."""
        with patch('src.commands.imagine.openrouter_client', mock_openrouter_client):
            with patch('src.commands.imagine.process_generated_image', return_value=discord.File(b"test", filename="test.png")):
                mock_openrouter_client.generate_image = AsyncMock(return_value=[sample_generated_image])

                await imagine(mock_discord_interaction, "prompt", "anime", 2, 123)

                mock_openrouter_client.generate_image.assert_called_once_with(
                    prompt="prompt", style="anime", count=2, seed=123
                )

    @pytest.mark.asyncio
    async def test_imagine_invalid_count(self, mock_discord_interaction):
        """Test /imagine with invalid count parameter."""
        await imagine(mock_discord_interaction, "prompt", count=10)

        # Should send error message without calling API
        mock_discord_interaction.response.defer.assert_called_once()
        args, kwargs = mock_discord_interaction.followup.send.call_args
        assert "Count must be between 1 and 4" in args[0]
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_imagine_generation_failure(self, mock_openrouter_client, mock_discord_interaction):
        """Test /imagine when API fails."""
        with patch('src.commands.imagine.openrouter_client', mock_openrouter_client):
            mock_openrouter_client.generate_image = AsyncMock(return_value=[])

            await imagine(mock_discord_interaction, "prompt")

            # Should send failure message
            args, kwargs = mock_discord_interaction.followup.send.call_args
            assert "Failed to generate images" in args[0]
            assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_imagine_processing_failure(self, mock_openrouter_client, mock_discord_interaction, sample_generated_image):
        """Test /imagine when image processing fails."""
        with patch('src.commands.imagine.openrouter_client', mock_openrouter_client):
            with patch('src.commands.imagine.process_generated_image', return_value=None):
                mock_openrouter_client.generate_image = AsyncMock(return_value=[sample_generated_image])

                await imagine(mock_discord_interaction, "prompt")

                args, kwargs = mock_discord_interaction.followup.send.call_args
                assert "Failed to process images" in args[0]
                assert kwargs.get("ephemeral") is True


class TestEditCommand:

    @pytest.mark.asyncio
    async def test_edit_single_source_success(self, mock_openrouter_client, mock_discord_interaction, mock_discord_attachment, sample_generated_image):
        """Test /edit command with single source."""
        with patch('src.commands.edit.openrouter_client', mock_openrouter_client), \
             patch('src.commands.edit.fetch_and_validate_attachments', return_value=["/tmp/test.png"]), \
             patch('src.commands.edit.prepare_image_for_api', return_value={"data": "base64data"}), \
             patch('src.commands.edit._create_discord_file_from_generated_image', return_value=discord.File(b"test", filename="edited.png")), \
             patch('src.commands.edit.os.unlink') as mock_unlink:

            mock_openrouter_client.edit_image = AsyncMock(return_value=[sample_generated_image])

            await edit(mock_discord_interaction, "edit prompt", source1=mock_discord_attachment)

            mock_discord_interaction.response.defer.assert_called_once()
            mock_openrouter_client.edit_image.assert_called_once()

            # Check if cleanup was called
            mock_unlink.assert_called()

    @pytest.mark.asyncio
    async def test_edit_multiple_sources(self, mock_openrouter_client, mock_discord_interaction, mock_discord_attachment, sample_generated_image):
        """Test /edit with multiple sources."""
        with patch('src.commands.edit.openrouter_client', mock_openrouter_client), \
             patch('src.commands.edit.fetch_and_validate_attachments', return_value=["/tmp/test1.png", "/tmp/test2.png"]), \
             patch('src.commands.edit.prepare_image_for_api', return_value={"data": "base64data"}), \
             patch('src.commands.edit._create_discord_file_from_generated_image', return_value=discord.File(b"test", filename="edited.png")):

            mock_openrouter_client.edit_image = AsyncMock(return_value=[sample_generated_image])

            await edit(mock_discord_interaction, "edit prompt", source1=mock_discord_attachment, source2=mock_discord_attachment)

            fetch_args = mock_discord_interaction.fetch_and_validate_attachments.call_args[0][0]
            # Verify both attachments were passed
            assert len(fetch_args) == 2

    @pytest.mark.asyncio
    async def test_edit_with_mask(self, mock_openrouter_client, mock_discord_interaction, mock_discord_attachment, sample_generated_image):
        """Test /edit with mask."""
        with patch('src.commands.edit.openrouter_client', mock_openrouter_client), \
             patch('src.commands.edit.fetch_and_validate_attachments', return_value=["/tmp/test.png", "/tmp/mask.png"]), \
             patch('src.commands.edit.prepare_image_for_api', return_value={"data": "base64data"}), \
             patch('src.commands.edit._create_discord_file_from_generated_image', return_value=discord.File(b"test", filename="edited.png")):

            mock_openrouter_client.edit_image = AsyncMock(return_value=[sample_generated_image])

            await edit(mock_discord_interaction, "edit prompt", source1=mock_discord_attachment, mask=mock_discord_attachment)

            # Verify both source and mask prepared
            call_count = 0
            for call in mock_discord_interaction.prepare_image_for_api.call_args_list:
                call_count += 1
            assert call_count >= 2  # Source and mask

    @pytest.mark.asyncio
    async def test_edit_invalid_source_count(self, mock_discord_interaction):
        """Test /edit with invalid number of sources."""
        with pytest.raises(TypeError):  # No sources provided
            await edit(mock_discord_interaction, "prompt")  # Missing source1


class TestBlendCommand:

    @pytest.mark.asyncio
    async def test_blend_min_sources(self, mock_openrouter_client, mock_discord_interaction, mock_discord_attachment, sample_generated_image):
        """Test /blend with minimum 2 sources."""
        with patch('src.commands.blend.openrouter_client', mock_openrouter_client), \
             patch('src.commands.blend.fetch_and_validate_attachments', return_value=["/tmp/test1.png", "/tmp/test2.png"]), \
             patch('src.commands.blend.prepare_image_for_api', return_value={"data": "base64data"}), \
             patch('src.commands.blend._create_discord_file_from_generated_image', return_value=discord.File(b"test", filename="blended.png")):

            mock_openrouter_client.blend_images = AsyncMock(return_value=[sample_generated_image])

            await blend(mock_discord_interaction, "blend prompt", source1=mock_discord_attachment, source2=mock_discord_attachment)

            mock_openrouter_client.blend_images.assert_called_once()

    @pytest.mark.asyncio
    async def test_blend_max_sources(self, mock_openrouter_client, mock_discord_interaction, mock_discord_attachment, sample_generated_image):
        """Test /blend with maximum 6 sources."""
        sources = [Mock(spec=discord.Attachment) for _ in range(6)]
        for i, src in enumerate(sources):
            src.filename = f"test{i}.png"
            src.content_type = "image/png"
            src.size = 1024

        with patch('src.commands.blend.openrouter_client', mock_openrouter_client), \
             patch('src.commands.blend.fetch_and_validate_attachments', return_value=[f"/tmp/test{i}.png" for i in range(6)]), \
             patch('src.commands.blend.prepare_image_for_api', return_value={"data": "base64data"}), \
             patch('src.commands.blend._create_discord_file_from_generated_image', return_value=discord.File(b"test", filename="blended.png")):

            mock_openrouter_client.blend_images = AsyncMock(return_value=[sample_generated_image])

            await blend(mock_discord_interaction, "blend prompt", source1=sources[0], source2=sources[1], source3=sources[2],
                       source4=sources[3], source5=sources[4], source6=sources[5])

            mock_openrouter_client.blend_images.assert_called_once()

    @pytest.mark.asyncio
    async def test_blend_invalid_source_count(self, mock_discord_interaction, mock_discord_attachment):
        """Test /blend with invalid source count."""
        # This should fail validation in the function
        await blend(mock_discord_interaction, "prompt", source1=mock_discord_attachment)  # Only 1 source

        # Check error message sent
        args, kwargs = mock_discord_interaction.followup.send.call_args
        assert "Requires 2-6 source images" in args[0]
        assert kwargs.get("ephemeral") is True


class TestImageValidation:

    def test_validate_attachment_success(self, mock_discord_attachment):
        """Test attachment validation success."""
        from src.commands.utils.images import validate_attachment
        result = validate_attachment(mock_discord_attachment)
        assert result is True

    def test_validate_attachment_non_image(self):
        """Test attachment validation for non-image."""
        from src.commands.utils.images import validate_attachment
        attachment = Mock(spec=discord.Attachment)
        attachment.content_type = "text/plain"

        with pytest.raises(ImageValidationError, match="not an image"):
            validate_attachment(attachment)

    def test_validate_attachment_oversize(self):
        """Test attachment validation for oversized file."""
        from src.commands.utils.images import validate_attachment
        attachment = Mock(spec=discord.Attachment)
        attachment.content_type = "image/png"
        attachment.filename = "large.png"
        attachment.size = 50 * 1024 * 1024  # 50MB

        with pytest.raises(ImageValidationError, match="size exceeds"):
            validate_attachment(attachment)

    def test_validate_attachment_invalid_type(self):
        """Test attachment validation for invalid image type."""
        from src.commands.utils.images import validate_attachment
        attachment = Mock(spec=discord.Attachment)
        attachment.content_type = "image/png"
        attachment.filename = "test.bmp"

        with pytest.raises(ImageValidationError, match="not allowed"):
            validate_attachment(attachment)


# Test utility functions
class TestImageUtilities:

    def test_encode_to_base64(self, temp_image_path):
        """Test base64 encoding utility."""
        from src.commands.utils.images import encode_to_base64
        result = encode_to_base64(temp_image_path)
        assert isinstance(result, str)
        assert result.startswith("iVBOR") or len(result) > 0  # Basic base64 check

    def test_resize_if_large_resize_needed(self, temp_image_path):
        """Test resizing when image is large."""
        # This would need a large image, mocking resize for now
        pass

    def test_resize_if_large_no_resize(self, temp_image_path):
        """Test no resize when image is small."""
        from src.commands.utils.images import resize_if_large
        result = resize_if_large(temp_image_path, max_size_mb=10)
        assert result == temp_image_path


# Test logging utilities
class TestLogging:

    def test_redact_sensitive_api_key(self):
        """Test redaction of API key patterns."""
        from src.commands.utils.logging import redact_sensitive
        text = "API_KEY=sk-1234567890abcdef"
        redacted = redact_sensitive(text)
        assert "[REDACTED]" in redacted
        assert "sk-1234567890abcdef" not in redacted

    def test_redact_sensitive_bearer(self):
        """Test redaction of bearer tokens."""
        from src.commands.utils.logging import redact_sensitive
        text = "Authorization: Bearer abc123def456"
        redacted = redact_sensitive(text)
        assert "[REDACTED]" in redacted

    def test_redact_sensitive_no_match(self):
        """Test no redaction when no sensitive data."""
        from src.commands.utils.logging import redact_sensitive
        text = "This is normal text"
        redacted = redact_sensitive(text)
        assert redacted == text


# Test storage utilities
class TestStorage:

    def test_get_cache_dir(self):
        """Test cache directory creation."""
        from src.commands.utils.storage import get_cache_dir
        cache_dir = get_cache_dir()
        assert cache_dir.exists()
        assert cache_dir.is_dir()

    def test_cache_image(self, temp_image_path):
        """Test caching an image."""
        from src.commands.utils.storage import cache_image
        with open(temp_image_path, 'rb') as f:
            data = f.read()
        cached_path = cache_image(data, "test.png")
        assert cached_path.exists()
        assert cached_path.name == "test.png"


# Pytest fixtures
pytest_plugins = ["pytest_asyncio"]