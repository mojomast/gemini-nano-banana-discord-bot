"""Discord Bot with Slash Commands

This module sets up the core Discord bot with slash commands implemented in separate files.
Also starts a background health check server on port 8000.
"""

import asyncio
import os
from typing import Any, Union, Optional

import discord
from discord import app_commands
import uvicorn

from .utils.config import config
from .health_check import app as health_app

from .commands.utils.logging import setup_logger
from .commands.utils.rate_limiter import rate_limiter, rate_limited
from .commands.utils.styles import Style
from .commands.imagine import imagine
from .commands.edit import edit
from .commands.blend import blend
from .commands.help import help
from .commands.info import info

DISCORD_TOKEN: Union[str, None] = config.discord_token
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env")

logger = setup_logger(__name__)


class Bot(discord.Client):
    """Discord bot client with application commands."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        # Disable privileged intents to avoid PrivilegedIntentsRequired error
        # Re-enable if needed after approving in Discord developer portal
        intents.messages = False
        intents.message_content = False
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self) -> None:
        """Event handler for when the bot is ready."""
        logger.info(f"Bot is ready! Logged in as {self.user}")
        logger.info(f"Bot is in {len(self.guilds)} server(s)")

        # Log guild info
        logger.info(f"Bot user ID: {self.user.id}")
        logger.info(f"Guilds: {len(self.guilds)}")
        for guild in self.guilds:
            logger.info(f"In server: {guild.name} (ID: {guild.id})")

        # Log registered commands
        try:
            registered_commands = [cmd.name for cmd in self.tree.get_commands()]
            logger.info(f"Commands registered: {registered_commands}")
        except Exception as e:
            logger.error(f"Failed to get commands: {e}")

        # Sync slash commands with Discord
        try:
            await self.tree.sync()
            logger.info("Slash commands synced with Discord successfully")
        except Exception as e:
            logger.error(f"Failed to sync commands: {type(e).__name__}: {str(e)}")
            # Log additional context
            logger.error("Sync failed - bot may need proper permissions or re-invite")



async def main() -> None:
    """Main entry point for the bot."""
    bot = Bot()

    # Create decorated slash commands
    @app_commands.command(name="imagine", description="Generate images from text prompts")
    @app_commands.describe(
        prompt="The text prompt to generate an image from (required)",
        style="Optional artistic style (e.g., 'photorealistic', 'anime', 'sketch')",
        count="Number of images to generate (1-4, default 1)",
        seed="Optional seed for reproducible results",
        format="Output image format (png, jpg, webp, default png)"
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name=Style.PHOTOREALISTIC.name, value=Style.PHOTOREALISTIC.value),
            app_commands.Choice(name=Style.ANIME.name, value=Style.ANIME.value),
            app_commands.Choice(name=Style.SKETCH.name, value=Style.SKETCH.value),
            app_commands.Choice(name=Style.CARTOON.name, value=Style.CARTOON.value),
            app_commands.Choice(name=Style.ABSTRACT.name, value=Style.ABSTRACT.value),
        ],
        format=[
            app_commands.Choice(name="PNG", value="png"),
            app_commands.Choice(name="JPG", value="jpg"),
            app_commands.Choice(name="WebP", value="webp"),
        ]
    )
    @rate_limited(rate_limiter)
    async def imagine_command(interaction: discord.Interaction, prompt: str, style: Optional[str] = None, count: int = 1, seed: Optional[int] = None, format: str = "png"):
        logger.info(f"Imagine command called by {interaction.user} with prompt: {prompt}")
        await imagine(interaction, prompt, style, count, seed, format)

    @app_commands.command(name="edit", description="Edit existing images with prompts")
    @app_commands.describe(
        prompt="The editing prompt for the images (required)",
        source1="First source image (required, attach PNG/JPG/WebP <10MB)",
        source2="Second source image (optional)",
        source3="Third source image (optional)",
        source4="Fourth source image (optional)",
        mask="Optional mask image for precise editing (attach PNG/JPG/WebP <10MB)",
        format="Output image format (png, jpg, webp, default png)"
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="PNG", value="png"),
            app_commands.Choice(name="JPG", value="jpg"),
            app_commands.Choice(name="WebP", value="webp"),
        ]
    )
    @rate_limited(rate_limiter)
    async def edit_command(interaction: discord.Interaction, prompt: str, source1: discord.Attachment, source2: Optional[discord.Attachment] = None, source3: Optional[discord.Attachment] = None, source4: Optional[discord.Attachment] = None, mask: Optional[discord.Attachment] = None, format: str = "png"):
        logger.info(f"Edit command called by {interaction.user} with prompt: {prompt}")
        await edit(interaction, prompt, source1, source2, source3, source4, mask, format)

    @app_commands.command(name="blend", description="Blend multiple images with prompt guidance")
    @app_commands.describe(
        prompt="The text prompt for blending images (required)",
        source1="First source image (required, attach PNG/JPG/WebP <10MB)",
        source2="Second source image (required, attach PNG/JPG/WebP <10MB)",
        source3="Third source image (optional)",
        source4="Fourth source image (optional)",
        source5="Fifth source image (optional)",
        source6="Sixth source image (optional)",
        strength="Blending strength (0.0 to 1.0, default 0.5)",
        format="Output image format (png, jpg, webp, default png)"
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="PNG", value="png"),
            app_commands.Choice(name="JPG", value="jpg"),
            app_commands.Choice(name="WebP", value="webp"),
        ]
    )
    @rate_limited(rate_limiter)
    async def blend_command(interaction: discord.Interaction, prompt: str, source1: discord.Attachment, source2: discord.Attachment, source3: Optional[discord.Attachment] = None, source4: Optional[discord.Attachment] = None, source5: Optional[discord.Attachment] = None, source6: Optional[discord.Attachment] = None, strength: float = 0.5, format: str = "png"):
        await blend(interaction, prompt, source1, source2, source3, source4, source5, source6, strength, format)

    @app_commands.command(name="help", description="Show help information and list of available commands")
    @rate_limited(rate_limiter)
    async def help_command(interaction: discord.Interaction):
        logger.info(f"Help command called by {interaction.user}")
        await help(interaction)

    @app_commands.command(name="info", description="Show bot information including model, version, and usage notes")
    @rate_limited(rate_limiter)
    async def info_command(interaction: discord.Interaction):
        await info(interaction)

    # Register slash commands
    bot.tree.add_command(imagine_command)
    bot.tree.add_command(edit_command)
    bot.tree.add_command(blend_command)
    bot.tree.add_command(help_command)
    bot.tree.add_command(info_command)

    # Start health check server in background
    async def run_health_server():
        config = uvicorn.Config(health_app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    health_task = asyncio.create_task(run_health_server())
    logger.info("Health check server task created")

    # Start both the bot and health server
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        health_task
    )


if __name__ == "__main__":
    asyncio.run(main())