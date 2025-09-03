import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional
import discord
from src.commands.utils.logging import setup_logger
from src.commands.utils.openrouter import OpenRouterClient
from src.commands.utils.images import fetch_and_validate_attachments, prepare_image_for_api, process_image_sources
from src.commands.utils.error_handler import handle_error, ErrorCategory
from src.commands.utils.validators import validate_prompt, validate_count_parameter, validate_strength_parameter, ValidationError

logger = setup_logger(__name__)

class ImageIterationView(discord.ui.View):
    """View with buttons for image iteration options."""
    
    def __init__(self, prompt: str, style: Optional[str], seed: Optional[int], format: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.prompt = prompt
        self.style = style
        self.seed = seed
        self.format = format
    
    @discord.ui.button(label='🔄 Reroll', style=discord.ButtonStyle.secondary, emoji='🔄')
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate new images with the same prompt but different seed."""
        await interaction.response.defer()
        
        # Get queue and generate new images
        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()
        
        # Generate with random seed (None will generate random)
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 1, None, self.format)
    
    @discord.ui.button(label='🎯 Variations', style=discord.ButtonStyle.secondary, emoji='🎯')
    async def variations(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate variations of the image."""
        await interaction.response.defer()
        
        # Get queue and generate variations (4 images)
        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()
        
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 4, None, self.format)
    
    @discord.ui.button(label='🔢 Same Seed', style=discord.ButtonStyle.secondary, emoji='🔢')
    async def same_seed(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate with the same seed if available."""
        await interaction.response.defer()
        
        if self.seed is None:
            await interaction.followup.send("No seed available for this image.", ephemeral=True)
            return
            
        # Get queue and generate with same seed
        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()
        
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 1, self.seed, self.format)

# Global queue instance
image_processing_queue = None

@dataclass
class QueueItem:
    interaction: discord.Interaction[Any]
    command: str  # 'imagine', 'edit', 'blend'
    params: Dict[str, Any]

class AsyncImageQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.client = OpenRouterClient()
        self.task = asyncio.create_task(self.worker())
        logger.info("AsyncImageQueue initialized with background worker.")

    async def worker(self):
        while True:
            try:
                item = await self.queue.get()
                logger.debug(f"Processing queue item: {item.command}")
                if item.command == 'imagine':
                    await self.process_imagine(item)
                elif item.command == 'edit':
                    await self.process_edit(item)
                elif item.command == 'blend':
                    await self.process_blend(item)
                else:
                    logger.error(f"Unknown command: {item.command}")
                    await handle_error(item.interaction, "Unknown command in queue.", category=ErrorCategory.INTERNAL)
            except Exception as e:
                logger.error(f"Error processing queue item: {e}", exc_info=True)
                await handle_error(item.interaction, "Queue processing failed.", category=ErrorCategory.INTERNAL)
            finally:
                self.queue.task_done()

    async def enqueue_imagine(self, interaction: discord.Interaction[Any], prompt: str, style: Optional[str] = None, count: int = 1, seed: Optional[int] = None, format: str = "png"):
        await self.queue.put(QueueItem(interaction, 'imagine', {'prompt': prompt, 'style': style, 'count': count, 'seed': seed, 'format': format}))
        logger.debug(f"Enqueued imagine request for user {interaction.user}")

    async def enqueue_edit(self, interaction: discord.Interaction[Any], prompt: str, sources: list, mask: Optional[discord.Attachment] = None, format: str = "png"):
        await self.queue.put(QueueItem(interaction, 'edit', {'prompt': prompt, 'sources': sources, 'mask': mask, 'format': format}))
        logger.debug(f"Enqueued edit request for user {interaction.user}")

    async def enqueue_blend(self, interaction: discord.Interaction[Any], prompt: str, sources: list, strength: float = 0.5, format: str = "png"):
        await self.queue.put(QueueItem(interaction, 'blend', {'prompt': prompt, 'sources': sources, 'strength': strength, 'format': format}))
        logger.debug(f"Enqueued blend request for user {interaction.user}")

    async def process_imagine(self, item: QueueItem):
        params = item.params
        interaction = item.interaction
        prompt = params['prompt']
        style = params['style']
        count = params['count']
        seed = params['seed']
        format = params.get('format', 'png')

        # Single progress message starting with queued
        embed = discord.Embed(
            title="🎨 Image Generation Progress",
            description=f"⏳ Queued → 🔄 Processing → 🎨 Generating → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
            color=0x3498db
        )
        progress_msg = await interaction.followup.send(embed=embed)

        # Copied from original imagine handler (without defer since already deferred)
        try:
            await asyncio.sleep(0.5)

            # Update to processing
            embed.description = f"✅ Queued → 🔄 Processing → 🎨 Generating → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)
            await asyncio.sleep(0.5)

            # Update to generating
            embed.description = f"✅ Queued → ✅ Processing → 🎨 Generating → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            images = await self.client.generate_image(prompt=prompt, style=style, count=count, seed=seed, format=format)

            if not images:
                await handle_error(interaction, "Failed to generate images.", category=ErrorCategory.API)
                return

            # Update to finalizing
            embed.description = f"✅ Queued → ✅ Processing → ✅ Generating → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            raw_files = process_image_sources(images[:count], "generated", count, format)
            files = [f for f in raw_files if f]

            if not files:
                await handle_error(interaction, "Failed to process images.", category=ErrorCategory.PROCESSING)
                return

            # Complete progress
            embed.description = f"✅ Queued → ✅ Processing → ✅ Generating → ✅ Finalizing\n\n**Complete!** Generated {len(files)} image{'s' if len(files) > 1 else ''}"
            embed.color = 0x00ff00
            
            # Add iteration buttons
            view = ImageIterationView(prompt, style, seed, format)
            await progress_msg.edit(embed=embed, view=view)

            # Send just the image files without additional embed
            await interaction.followup.send(files=files)

        except Exception as e:
            logger.error(f"Error in queue process_imagine: {e}", exc_info=True)
            await handle_error(interaction, "Unexpected error occurred.", category=ErrorCategory.INTERNAL)

    async def process_edit(self, item: QueueItem):
        params = item.params
        interaction = item.interaction
        prompt = params['prompt']
        sources = params['sources']
        mask = params['mask']
        format = params.get('format', 'png')

        # Single progress message starting with queued
        embed = discord.Embed(
            title="🖼️ Image Edit Progress",
            description=f"⏳ Queued → 🔄 Processing → 🎨 Editing → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
            color=0x3498db
        )
        progress_msg = await interaction.followup.send(embed=embed)

        try:
            await asyncio.sleep(0.5)

            # Update to processing
            embed.description = f"✅ Queued → 🔄 Processing → 🎨 Editing → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Fetch and validate attachments
            all_attachments = sources[::] if not mask else sources + [mask]
            validated_paths = fetch_and_validate_attachments(all_attachments)
            if not validated_paths or len(validated_paths) < len(sources):
                raise ValidationError("Some attachments could not be validated. Ensure all are valid PNG/JPG/WebP images <10MB.", category="validation")

            # Separate sources and mask
            source_paths = validated_paths[:len(sources)]
            mask_path = validated_paths[-1] if mask and len(validated_paths) > len(sources) else None

            # Prepare for API
            prepared_sources = [prepare_image_for_api(path) for path in source_paths]
            prepared_mask = prepare_image_for_api(mask_path) if mask_path else None

            # Update to editing
            embed.description = f"✅ Queued → ✅ Processing → 🎨 Editing → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Call edit
            edited_images = await self.client.edit_image(
                prompt=prompt,
                sources=[item.get('url', item.get('data')) for item in prepared_sources],
                mask=prepared_mask.get('url', prepared_mask.get('data')) if prepared_mask else None,
                format=format
            )

            if not edited_images:
                await handle_error(interaction, "Image editing failed.", category=ErrorCategory.API)
                return

            # Update to finalizing
            embed.description = f"✅ Queued → ✅ Processing → ✅ Editing → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Process generated images
            logger.debug(f"Processing {len(edited_images)} edited images")
            raw_files = process_image_sources(edited_images, "edited", len(edited_images), format)
            files = [f for f in raw_files if f]
            logger.debug(f"Successfully processed {len(files)} files")

            if files:
                # Complete progress
                embed.description = f"✅ Queued → ✅ Processing → ✅ Editing → ✅ Finalizing\n\n**Complete!** Edited {len(files)} image{'s' if len(files) > 1 else ''}"
                embed.color = 0x00ff00
                await progress_msg.edit(embed=embed)

                # Send the image file with the prompt as content
                await interaction.followup.send(content=f"**Prompt:** {prompt}", files=files)
            else:
                await handle_error(interaction, "Failed to prepare edited image files.", category=ErrorCategory.PROCESSING)

            # Cleanup
            import os
            for path in validated_paths:
                try:
                    os.unlink(path)
                except OSError as e:
                    logger.warning(f"Failed to delete temp file {path}: {e}")

        except ValidationError as e:
            # Cleanup temp files on validation error
            if 'validated_paths' in locals() and validated_paths:
                import os
                for path in validated_paths:
                    try:
                        os.unlink(path)
                    except OSError as cleanup_e:
                        logger.warning(f"Failed to delete temp file {path}: {cleanup_e}")
            await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
        except Exception as e:
            logger.error(f"Error in queue process_edit: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            # Cleanup temp files on unexpected error
            if 'validated_paths' in locals() and validated_paths:
                import os
                for path in validated_paths:
                    try:
                        os.unlink(path)
                    except OSError as cleanup_e:
                        logger.warning(f"Failed to delete temp file {path}: {cleanup_e}")
            await handle_error(interaction, "Unexpected error occurred.", category=ErrorCategory.INTERNAL)

    async def process_blend(self, item: QueueItem):
        params = item.params
        interaction = item.interaction
        prompt = params['prompt']
        sources = params['sources']
        strength = params['strength']
        format = params.get('format', 'png')

        # Single progress message starting with queued
        embed = discord.Embed(
            title="🌀 Image Blend Progress",
            description=f"⏳ Queued → 🔄 Processing → 🎨 Blending → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
            color=0x3498db
        )
        progress_msg = await interaction.followup.send(embed=embed)

        try:
            await asyncio.sleep(0.5)

            # Update to processing
            embed.description = f"✅ Queued → 🔄 Processing → 🎨 Blending → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Fetch and validate all attachments
            validated_paths = fetch_and_validate_attachments(sources)
            if not validated_paths or len(validated_paths) < len(sources):
                raise ValidationError("Some attachments could not be validated. Ensure all are valid PNG/JPG/WebP images <10MB.", category="validation")

            # Prepare for API
            prepared_sources = [prepare_image_for_api(path) for path in validated_paths]

            # Update to blending
            embed.description = f"✅ Queued → ✅ Processing → 🎨 Blending → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Call blend
            blended_images = await self.client.blend_images(
                prompt=prompt,
                sources=[item.get('url', item.get('data')) for item in prepared_sources],
                strength=strength,
                format=format
            )

            if not blended_images:
                await handle_error(interaction, "Blending failed.", category=ErrorCategory.API)
                return

            # Update to finalizing
            embed.description = f"✅ Queued → ✅ Processing → ✅ Blending → 🔧 Finalizing\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            await progress_msg.edit(embed=embed)

            # Process generated images
            raw_files = process_image_sources(blended_images, "blended", len(blended_images), format)
            files = [f for f in raw_files if f]

            if files:
                # Complete progress
                embed.description = f"✅ Queued → ✅ Processing → ✅ Blending → ✅ Finalizing\n\n**Complete!** Blended {len(files)} image{'s' if len(files) > 1 else ''}"
                embed.color = 0x00ff00
                await progress_msg.edit(embed=embed)

                # Send just the image files without additional embed
                await interaction.followup.send(files=files)
            else:
                await handle_error(interaction, "Failed to prepare blended image files.", category=ErrorCategory.PROCESSING)

            # Cleanup
            import os
            for path in validated_paths:
                try:
                    os.unlink(path)
                except OSError as e:
                    logger.warning(f"Failed to delete temp file {path}: {e}")

        except ValidationError as e:
            # Cleanup temp files on validation error
            if 'validated_paths' in locals() and validated_paths:
                import os
                for path in validated_paths:
                    try:
                        os.unlink(path)
                    except OSError as cleanup_e:
                        logger.warning(f"Failed to delete temp file {path}: {cleanup_e}")
            await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
        except Exception as e:
            logger.error(f"Error in queue process_blend: {e}", exc_info=True)
            # Cleanup temp files on unexpected error
            if 'validated_paths' in locals() and validated_paths:
                import os
                for path in validated_paths:
                    try:
                        os.unlink(path)
                    except OSError as cleanup_e:
                        logger.warning(f"Failed to delete temp file {path}: {cleanup_e}")
            await handle_error(interaction, "Unexpected error occurred.", category=ErrorCategory.INTERNAL)

# Initialize global queue
def initialize_queue():
    global image_processing_queue
    if image_processing_queue is None:
        image_processing_queue = AsyncImageQueue()
    return image_processing_queue