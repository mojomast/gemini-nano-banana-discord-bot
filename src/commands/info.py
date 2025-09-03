from typing import Any
import discord
from discord import app_commands

# Ensure discord is in globals for type annotation resolution
globals()['discord'] = discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.rate_limiter import rate_limiter, rate_limited

logger = setup_logger(__name__)

# Bot version - extracted from CHANGELOG.md
VERSION = "v0.1.0"

# Model used
MODEL = "google/gemini-2.5-flash-image-preview"

async def info(interaction) -> None:
    """Handle the /info command to display bot information with embed."""
    logger.debug(f"Received /info command from {interaction.user}")

    embed = discord.Embed(
        title="🔍 Bot Information",
        description="Details about this gemini-nano-banana-discord-bot instance:",
        color=0x2ecc71
    )

    embed.add_field(
        name="🤖 Model",
        value=f"`{MODEL}`\nPowered by OpenRouter for AI image generation.",
        inline=True
    )

    embed.add_field(
        name="📦 Version",
        value=VERSION,
        inline=True
    )

    embed.add_field(
        name="⚡ Performance Notes",
        value="Response times may vary based on server load and image complexity. Always wait for the bot to finish processing before issuing another command.",
        inline=False
    )

    embed.add_field(
        name="🔒 Rate Limits",
        value="Rate limits are enforced by OpenRouter. If you exceed limits, you may need to wait before making another request. Check your tier limits in OpenRouter settings.",
        inline=False
    )

    embed.add_field(
        name="🛡️ Privacy Note",
        value="Images and prompts are sent to OpenRouter's API for processing. Your data is handled according to their privacy policy. No personal data is stored by this bot beyond what's required for operation.",
        inline=False
    )

    embed.set_footer(text=f"gemini-nano-banana-discord-bot {VERSION} | Built with discord.py")

    await interaction.response.send_message(embed=embed, ephemeral=True)