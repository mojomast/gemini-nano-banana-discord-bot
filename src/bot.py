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
from .admin.auth import generate_nonce
from .commands.utils.queue import image_processing_queue

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

    # Admin commands
    @app_commands.command(name="admin", description="Administrative commands")
    @app_commands.describe(action="Action to perform (dashboard, status, invite)", ttl="TTL for dashboard links (minutes, default 5)")
    @app_commands.choices(action=[
        app_commands.Choice(name="dashboard", value="dashboard"),
        app_commands.Choice(name="status", value="status"),
        app_commands.Choice(name="invite", value="invite")
    ])
    async def admin_command(interaction: discord.Interaction, action: str, ttl: int = 5):
        # Check if user is admin
        if str(interaction.user.id) not in config.admin_user_ids:
            await interaction.response.send_message("❌ Access denied. You are not authorized to use admin commands.", ephemeral=True)
            return

        try:
            if ttl <= 0:
                await interaction.response.send_message("❌ TTL must be a positive number.", ephemeral=True)
                return
            elif ttl > 60:
                await interaction.response.send_message("❌ TTL cannot exceed 60 minutes.", ephemeral=True)
                return

            if action == "dashboard":
                # Generate nonce with custom TTL (convert to seconds)
                nonce_ttl = min(ttl * 60, 3600)  # Max 1 hour
                nonce = generate_nonce(nonce_ttl)

                # Create the dashboard URL
                dashboard_url = f"http://localhost:8000/admin/auth/{nonce}"

                embed = discord.Embed(
                    title="🔧 Admin Dashboard Access",
                    description=f"Click the link below to access the admin dashboard.\n\n⚠️ **This link expires in {ttl} minute(s) and can only be used once.**",
                    color=0x3498db
                )
                embed.add_field(name="Dashboard URL", value=f"[Access Admin Panel]({dashboard_url})", inline=False)
                embed.add_field(name="Valid For", value=f"{ttl} minute(s)", inline=True)
                embed.add_field(name="Security Notes", value="• One-time use\n• Expires automatically\n• Requires Discord OAuth", inline=True)

                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"Admin dashboard link generated for user {interaction.user} (nonce: {nonce[:8]}...)")

            elif action == "status":
                # Get status metrics (synchronously for queue)
                try:
                    queue_length = 0
                    try:
                        # Access queue synchronously if possible, fallback to 0
                        if image_processing_queue and hasattr(image_processing_queue, 'queue'):
                            queue_length = image_processing_queue.queue.qsize()
                    except Exception as qe:
                        logger.debug(f"Could not get queue size: {qe}")
                        queue_length = "Unknown"

                    embed = discord.Embed(
                        title="📊 Bot Status Report",
                        description="Current bot health and metrics",
                        color=0x00ff00 if config.discord_token and config.openrouter_api_key else 0xffaa00
                    )

                    embed.add_field(name="🟢 Bot Connected", value="✅ Yes" if config.discord_token else "❌ Missing token", inline=True)
                    embed.add_field(name="🔑 API Connected", value="✅ Yes" if config.openrouter_api_key else "❌ Missing key", inline=True)
                    embed.add_field(name="📋 Queue Length", value=str(queue_length), inline=True)
                    embed.add_field(name="⚙️ Active Workers", value="1" if isinstance(queue_length, int) and queue_length > 0 else "0", inline=True)
                    embed.add_field(name="👥 Processing Count", value=str(queue_length) if isinstance(queue_length, int) else "Unknown", inline=True)
                    embed.add_field(name="🔧 Dashboard URL", value="http://localhost:8000/admin", inline=False)

                    await interaction.response.send_message(embed=embed, ephemeral=True)

                except Exception as e:
                    logger.error(f"Error getting status metrics: {e}")
                    await interaction.response.send_message("❌ Failed to retrieve status information.", ephemeral=True)

            elif action == "invite":
                embed = discord.Embed(
                    title="🔗 Dashboard Invitation Instructions",
                    description=f"How to grant other users admin access to the dashboard.\n\nThe admin dashboard provides:\n• Real-time bot monitoring\n• Runtime configuration management\n• Rate limit adjustments\n• User permission controls",
                    color=0x3498db
                )

                embed.add_field(
                    name="Prerequisites",
                    value="• Users must be in your Discord server\n• Their Discord user IDs must be added to `ADMIN_USER_IDS` environment variable\n• Dashboard must be accessible at the configured URL",
                    inline=False
                )
                embed.add_field(
                    name="Setup Steps",
                    value="1. **Collect User IDs**: Get Discord user IDs for new admin users\n2. **Update Environment**: Add IDs to `ADMIN_USER_IDS` (comma-separated)\n3. **Restart Application**: Required for environment changes\n4. **Generate Access Links**: Use `/admin dashboard` command",
                    inline=False
                )
                embed.add_field(
                    name="Security Notes",
                    value="• All admin actions are logged\n• One-time URLs prevent unauthorized access\n• OAuth2 flow requires Discord authentication\n• User permissions independent from Discord roles",
                    inline=False
                )

                await interaction.response.send_message(embed=embed, ephemeral=True)

            else:
                await interaction.response.send_message("❌ Invalid action. Use `dashboard`, `status`, or `invite`.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in admin command: {e}")
            await interaction.response.send_message("❌ An error occurred while processing the admin command.", ephemeral=True)

    # Register slash commands
    bot.tree.add_command(imagine_command)
    bot.tree.add_command(edit_command)
    bot.tree.add_command(blend_command)
    bot.tree.add_command(help_command)
    bot.tree.add_command(info_command)
    bot.tree.add_command(admin_command)

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