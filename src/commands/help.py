from typing import Any
import discord
from discord import app_commands

# Ensure discord is in globals for type annotation resolution
globals()['discord'] = discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.rate_limiter import rate_limiter, rate_limited

logger = setup_logger(__name__)

async def help(interaction) -> None:
    """Handle the /help command to display bot commands with descriptions and usage examples."""
    logger.debug(f"Received /help command from {interaction.user}")

    embed = discord.Embed(
        title="🤖 SlopBot Help",
        description="Here's a list of available commands and how to use them:",
        color=0x3498db
    )

    # Add fields for each command
    embed.add_field(
        name="/imagine <prompt>",
        value='**Description:** Generate images from text prompts.\n**Usage:** `/imagine prompt: "A sunset over mountains"`\n**Options:** `style` (optional), `count` (1-4, default 1), `seed` (optional)\n**Example:** `/imagine prompt: "Anime style dragon" style: anime count: 2`',
        inline=False
    )

    embed.add_field(
        name="/edit <prompt>",
        value='**Description:** Edit existing images with prompts.\n**Usage:** `/edit prompt: "Make it look like a painting" source: [attach image]`\n**Options:** `source` (required image), `strength` (0.0-1.0, default 0.7)\n**Example:** `/edit prompt: "Add sunglasses" source: [image]`',
        inline=False
    )

    embed.add_field(
        name="/blend <prompt>",
        value='**Description:** Blend multiple images with prompt guidance.\n**Usage:** `/blend prompt: "Combine these into a collage" source1: [image] source2: [image]`\n**Options:** `source1-source6` (2-6 images), `strength` (0.0-1.0, default 0.5)\n**Example:** `/blend prompt: "Cyberpunk scene" source1: [city] source2: [character]`',
        inline=False
    )

    embed.add_field(
        name="/info",
        value='**Description:** Show bot information including model, version, and notes.\n**Usage:** `/info`\n**Example:** `/info`',
        inline=False
    )

    embed.add_field(
        name="/help",
        value='**Description:** Show this help information.\n**Usage:** `/help`\n**Example:** `/help`',
        inline=False
    )

    embed.set_footer(text="SlopBot | Powered by OpenRouter and Gemini")

    await interaction.response.send_message(embed=embed, ephemeral=True)