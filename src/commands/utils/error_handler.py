import discord
from typing import TYPE_CHECKING, Any, Optional
from src.commands.utils.logging import setup_logger

if TYPE_CHECKING:
    from discord import Interaction

logger = setup_logger(__name__)

class ErrorCategory:
    VALIDATION = "validation"
    API = "api"
    PROCESSING = "processing"
    INTERNAL = "internal"

async def handle_error(
    interaction: "Interaction[Any]",
    error_message: str,
    category: str = ErrorCategory.INTERNAL,
    embed_title: str = "Error",
    color: int = 0xff0000,
    ephemeral: bool = True,
    include_suggestion: bool = False
) -> None:
    """
    Standardized error handler for Discord interactions.

    Args:
        interaction: The Discord interaction instance
        error_message: Descriptive error message
        category: Error category for consistent messaging
        embed_title: Title for the error embed
        color: Embed color (default red)
        ephemeral: Whether to make the response ephemeral
        include_suggestion: Whether to add a generic suggestion
    """
    logger.error(f"Error in {interaction.command.name} command for user {interaction.user}: {error_message} (category: {category})")

    embed = discord.Embed(
        title=f"❌ {embed_title}",
        description=error_message,
        color=color
    )

    if include_suggestion:
        embed.set_footer(text="Please check your input and try again.")

    # Determine if it's a response or followup
    # Check if the interaction has been responded to
    try:
        if hasattr(interaction.response, 'is_done') and not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        elif not hasattr(interaction.response, 'is_done') and not interaction.response._responded:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    except (discord.InteractionResponded, AttributeError):
        # If interaction was already responded to, use followup
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

def create_error_embed(
    title: str,
    description: str,
    color: int = 0xff0000,
    footer_text: Optional[str] = None
) -> discord.Embed:
    """Helper to create a standardized error embed."""
    embed = discord.Embed(title=title, description=description, color=color)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed

async def send_validation_error(
    interaction: "Interaction[Any]",
    field: str,
    reason: str,
    ephemeral: bool = True
) -> None:
    """Send a validation error for a specific field."""
    error_msg = f"Invalid {field}: {reason}"
    await handle_error(
        interaction,
        error_msg,
        category=ErrorCategory.VALIDATION,
        embed_title="Validation Error",
        ephemeral=ephemeral,
        include_suggestion=True
    )

async def send_api_error(
    interaction: "Interaction[Any]",
    reason: str,
    ephemeral: bool = True
) -> None:
    """Send an API-related error."""
    await handle_error(
        interaction,
        reason,
        category=ErrorCategory.API,
        embed_title="API Error",
        ephemeral=ephemeral
    )