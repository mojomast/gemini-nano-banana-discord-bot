from typing import Optional, Any
import discord
from discord import app_commands

# Ensure discord is in globals for type annotation resolution
globals()['discord'] = discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.error_handler import handle_error, ErrorCategory
from src.commands.utils.validators import validate_prompt, validate_prompt_content, validate_count_parameter, ValidationError
from src.commands.utils.styles import Style
from src.commands.utils.rate_limiter import rate_limiter, rate_limited
from src.commands.utils.queue import initialize_queue

logger = setup_logger(__name__)

# Set custom rate limit for imagine command: 5 per 5 minutes
rate_limiter.set_command_limit("imagine", 5, 300)

# Global queue, initialize once
image_queue = None

async def imagine(
    interaction,
    prompt: str,
    style: Optional[str] = None,
    count: int = 1,
    seed: Optional[int] = None,
    format: str = "png",
    size: str = "640x640"
) -> None:
    """Handle the /imagine command to generate images from prompts."""
    logger.debug(f"Received /imagine command from {interaction.user}: prompt='{prompt}', style={style}, count={count}, seed={seed}, format={format}")
    
    # Log interaction details for debugging
    logger.debug(f"Interaction data keys: {interaction.data.keys() if hasattr(interaction, 'data') and interaction.data else 'No data'}")
    logger.debug(f"Interaction message: {interaction.message}")
    if hasattr(interaction, 'message') and interaction.message:
        logger.debug(f"Message attachments: {len(interaction.message.attachments) if interaction.message.attachments else 0}")

    # Check for image attachments and provide helpful error
    if hasattr(interaction, 'message') and interaction.message and interaction.message.attachments:
        await interaction.response.send_message(
            "❌ **The `/imagine` command is for text-to-image generation only.**\n\n"
            "📷 I see you've attached an image. If you want to:\n"
            "• **Edit an existing image** → Use `/edit` instead\n"
            "• **Generate from text only** → Remove the attachment and try again\n\n"
            "💡 **Example:** `/edit prompt:add a rainbow to this image source1:[your image]`",
            ephemeral=True
        )
        return

    # Defer the response
    await interaction.response.defer()

    global image_queue
    if image_queue is None:
        image_queue = initialize_queue()

    try:
        # Validate inputs
        await validate_prompt(interaction, prompt)
        await validate_prompt_content(prompt)
        await validate_count_parameter(interaction, count, 1, 4)

        # Enqueue for asynchronous processing
        await image_queue.enqueue_imagine(interaction, prompt, style, count, seed, format, size)

    except ValidationError as e:
        await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
        return
    except Exception as e:
        logger.error(f"Error in /imagine command: {e}", exc_info=True)
        await handle_error(interaction, "Unexpected error occurred.", category=ErrorCategory.INTERNAL)
