from __future__ import annotations
from typing import Any, Optional
import discord
from discord import app_commands

# Ensure discord is in globals for type annotation resolution
globals()['discord'] = discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.error_handler import handle_error, ErrorCategory
from src.commands.utils.validators import validate_prompt, validate_prompt_content, ValidationError
from src.commands.utils.rate_limiter import rate_limiter, rate_limited
from src.commands.utils.queue import initialize_queue

logger = setup_logger(__name__)

# Global queue, initialize once
image_queue = None

async def edit(
    interaction,
    prompt: str,
    source1,
    source2=None,
    source3=None,
    source4=None,
    mask=None,
    format: str = "png"
) -> None:
    """Handle the /edit command to edit images based on prompts."""
    logger.debug(f"Received /edit command from {interaction.user}: prompt='{prompt}', sources attached, format={format}.")

    # Defer the response
    await interaction.response.defer()

    global image_queue
    if image_queue is None:
        image_queue = initialize_queue()

    try:
        # Validate inputs
        await validate_prompt(interaction, prompt)
        await validate_prompt_content(prompt)

        # Collect sources
        sources = [src for src in [source1, source2, source3, source4] if src is not None]
        if len(sources) < 1 or len(sources) > 4:
            raise ValidationError(f"Requires 1-4 source images, you provided {len(sources)}.", category="validation")

        # Progress message for multi-source
        if len(sources) > 1:
            await interaction.followup.send("Processing your images... This may take a moment.", ephemeral=True)

        # Enqueue for asynchronous processing
        await image_queue.enqueue_edit(interaction, prompt, sources, mask, format)

    except ValidationError as e:
        await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
        return
    except Exception as e:
        logger.error(f"Error in /edit command for user {interaction.user}: {e}", exc_info=True)
        await handle_error(interaction, f"An unexpected error occurred: {e}", category=ErrorCategory.INTERNAL)

