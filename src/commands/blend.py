from typing import Any, Optional, List
import discord
from discord import app_commands

# Ensure discord is in globals for type annotation resolution
globals()['discord'] = discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.error_handler import handle_error, ErrorCategory
from src.commands.utils.validators import validate_prompt, validate_prompt_content, validate_strength_parameter, ValidationError
from src.commands.utils.rate_limiter import rate_limiter, rate_limited
from src.commands.utils.queue import initialize_queue

logger = setup_logger(__name__)

# Set custom rate limit for blend command: 15 per minute
rate_limiter.set_command_limit("blend", 15, 60)

# Global queue, initialize once
image_queue = None

async def blend(
    interaction,
    prompt: str,
    source1,
    source2,
    source3=None,
    source4=None,
    source5=None,
    source6=None,
    strength: float = 0.5,
    format: str = "png"
) -> None:
    """Handle the /blend command to blend multiple images based on prompt."""
    logger.debug(f"Received /blend command from {interaction.user}: prompt='{prompt}', strength={strength}, sources attached, format={format}.")

    # Defer the response
    await interaction.response.defer()

    global image_queue
    if image_queue is None:
        image_queue = initialize_queue()

    try:
        # Validate inputs
        await validate_prompt(interaction, prompt)
        await validate_prompt_content(prompt)
        await validate_strength_parameter(interaction, strength, 0.0, 1.0)

        # Collect sources
        sources = [src for src in [source1, source2, source3, source4, source5, source6] if src is not None]
        if len(sources) < 2 or len(sources) > 6:
            raise ValidationError(f"Requires 2-6 source images, you provided {len(sources)}.", category="validation")

        # Progress message for multi-source
        if len(sources) > 2:
            await interaction.followup.send("Processing your images... This may take a moment.", ephemeral=True)

        # Enqueue for asynchronous processing
        await image_queue.enqueue_blend(interaction, prompt, sources, strength, format)

    except ValidationError as e:
        await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
        return
    except Exception as e:
        logger.error(f"Error in /blend command: {e}", exc_info=True)
        await handle_error(interaction, "Unexpected error occurred.", category=ErrorCategory.INTERNAL)

