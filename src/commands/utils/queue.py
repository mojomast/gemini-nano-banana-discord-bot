import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import discord
import os
import uuid
import base64
from io import BytesIO
import requests
from src.commands.utils.logging import setup_logger
from src.commands.utils.openrouter import OpenRouterClient
from src.commands.utils.images import fetch_and_validate_attachments, prepare_image_for_api, process_image_sources, CACHE_DIR
from src.commands.utils.error_handler import handle_error, ErrorCategory
from src.commands.utils.validators import validate_prompt, validate_count_parameter, validate_strength_parameter, ValidationError

logger = setup_logger(__name__)

class ImageIterationView(discord.ui.View):
    """View with buttons for image iteration options."""
    
    def __init__(self, prompt: str, style: Optional[str], seed: Optional[int], format: str, images: Optional[List[Any]] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.prompt = prompt
        self.style = style
        self.seed = seed
        self.format = format
        # size is stored as a string like "640x640"
        self.size = "640x640"
        # Keep a reference to the generated images (GeneratedImage objects)
        # so buttons (like Edit) can operate on them later.
        self.images = images or []
    
    @discord.ui.button(label='🔄 Reroll', style=discord.ButtonStyle.secondary, emoji='🔄')
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate new images with the same prompt but different seed."""
        await interaction.response.defer()
        
        # Get queue and generate new images
        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()
        
        # Generate with random seed (None will generate random)
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 1, None, self.format, self.size)
    
    @discord.ui.button(label='🎯 Variations', style=discord.ButtonStyle.secondary, emoji='🎯')
    async def variations(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate variations of the image."""
        await interaction.response.defer()
        
        # Get queue and generate variations (4 images)
        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 4, None, self.format, self.size)
    
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
        
        await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 1, self.seed, self.format, self.size)

    @discord.ui.button(label='🔍 Regenerate 1280', style=discord.ButtonStyle.secondary, emoji='🔍')
    async def regenerate_1280(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Regenerate the image at 1280x1280 while preserving prompt/style/seed."""
        await interaction.response.defer()

        global image_processing_queue
        if image_processing_queue is None:
            image_processing_queue = AsyncImageQueue()

        # If we have generated images available, use the first one as the source
        # and call the edit/upscale path so we preserve the original image content.
        if not self.images:
            # Fallback: request a single image at higher resolution (best-effort)
            await image_processing_queue.enqueue_imagine(interaction, self.prompt, self.style, 1, self.seed, self.format, "1280x1280")
            return

        # Use the first generated image as the source for upscaling
        source_image = self.images[0]
        # Enqueue an edit which will call the edit/upscale API with the provided source
        await image_processing_queue.enqueue_edit(interaction, self.prompt, [source_image], None, self.format, size="1280x1280")

    @discord.ui.button(label='✏️ Edit', style=discord.ButtonStyle.primary, emoji='✏️')
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Prompt the user for an edit prompt and enqueue an edit using the generated image(s)."""
        # If no generated images are present, inform the user
        if not self.images:
            await interaction.response.send_message("No generated images available to edit.", ephemeral=True)
            return

        # Define a modal to collect the edit prompt and optional image index
        class EditModal(discord.ui.Modal):
            prompt = discord.ui.TextInput(label="Edit prompt", style=discord.TextStyle.long, placeholder="Describe the edits to make...", required=True, max_length=1000)
            index = discord.ui.TextInput(label="Image index (1 for first)", style=discord.TextStyle.short, placeholder="1", required=False, max_length=2)

            def __init__(self, parent_view: ImageIterationView):
                super().__init__(title="Edit generated image")
                self.parent_view = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                prompt_value = self.prompt.value.strip()
                idx = 0
                if self.index.value and self.index.value.strip():
                    try:
                        idx = int(self.index.value.strip()) - 1
                    except Exception:
                        await modal_interaction.response.send_message("Invalid image index. Use a number like 1.", ephemeral=True)
                        return

                if idx < 0 or idx >= len(self.parent_view.images):
                    await modal_interaction.response.send_message(f"Image index out of range. Choose 1-{len(self.parent_view.images)}.", ephemeral=True)
                    return

                selected_image = self.parent_view.images[idx]

                # If the view holds a local file path (string), pass that path directly as source
                if isinstance(selected_image, str):
                    source_to_use = selected_image
                else:
                    source_to_use = selected_image

                # Acknowledge and enqueue edit using the selected generated image
                await modal_interaction.response.defer()
                global image_processing_queue
                if image_processing_queue is None:
                    image_processing_queue = AsyncImageQueue()

                # Enqueue edit with the appropriate source (GeneratedImage or local path string)
                await image_processing_queue.enqueue_edit(modal_interaction, prompt_value, [source_to_use], None, self.parent_view.format)

                await modal_interaction.followup.send(f"Enqueued edit for image {idx+1}.", ephemeral=True)

        # Show the modal to the user
        await interaction.response.send_modal(EditModal(self))

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

    async def enqueue_imagine(self, interaction: discord.Interaction[Any], prompt: str, style: Optional[str] = None, count: int = 1, seed: Optional[int] = None, format: str = "png", size: str = "640x640"):
        await self.queue.put(QueueItem(interaction, 'imagine', {'prompt': prompt, 'style': style, 'count': count, 'seed': seed, 'format': format, 'size': size}))
        logger.debug(f"Enqueued imagine request for user {interaction.user}")

    async def enqueue_edit(self, interaction: discord.Interaction[Any], prompt: str, sources: list, mask: Optional[discord.Attachment] = None, format: str = "png", size: Optional[str] = None):
        await self.queue.put(QueueItem(interaction, 'edit', {'prompt': prompt, 'sources': sources, 'mask': mask, 'format': format, 'size': size}))
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
        size = params.get('size', '640x640')

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

            images = await self.client.generate_image(prompt=prompt, style=style, count=count, seed=seed, format=format, size=size)

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

            # Complete progress — include the full prompt in the embed so it's visible
            embed.description = (
                f"✅ Queued → ✅ Processing → ✅ Generating → ✅ Finalizing\n\n"
                f"**Complete!** Generated {len(files)} image{'s' if len(files) > 1 else ''}\n\n"
                f"**Prompt:** {prompt}\n**Size:** {size}"
            )
            embed.color = 0x00ff00

            # Add iteration buttons and include generated images so buttons can reference them
            view = ImageIterationView(prompt, style, seed, format, images=images[:count])
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
        mask = params.get('mask')
        format = params.get('format', 'png')
        size = params.get('size', None)

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

            # If sources are GeneratedImage objects (from our own generation) or discord.File objects,
            # write them to temp files in CACHE_DIR so the existing pipeline can process them.
            validated_paths = []
            try:
                # Quick heuristic: if the first source has attributes like 'base64' or 'url', treat as GeneratedImage
                first_src = sources[0] if sources else None
            except Exception:
                first_src = None

            from pathlib import Path as _Path
            if first_src is not None and (isinstance(first_src, (str, _Path)) or hasattr(first_src, 'base64') or hasattr(first_src, 'url') or isinstance(first_src, discord.File)):
                # Convert in-memory/generated images to temp files
                for i, src in enumerate(sources):
                    temp_path = os.path.join(CACHE_DIR, f"gen_{uuid.uuid4()}_{i}.{format}")
                    try:
                        # If already a local file path, just reuse it
                        if isinstance(src, (str, _Path)):
                            # validate file exists
                            if os.path.exists(str(src)):
                                validated_paths.append(str(src))
                                continue
                            else:
                                raise Exception(f"Local source path not found: {src}")

                        if isinstance(src, discord.File):
                            # discord.File.fp is a file-like object
                            try:
                                src.fp.seek(0)
                            except Exception:
                                pass
                            data = src.fp.read()
                            with open(temp_path, 'wb') as f:
                                f.write(data)
                            validated_paths.append(temp_path)
                        else:
                            # GeneratedImage-like handling
                            if getattr(src, 'base64', None):
                                b64 = src.base64
                                if b64.startswith('data:'):
                                    _, b64 = b64.split(',', 1)
                                b64 = b64.strip()
                                missing_padding = len(b64) % 4
                                if missing_padding:
                                    b64 += '=' * (4 - missing_padding)
                                data = base64.b64decode(b64)
                                with open(temp_path, 'wb') as f:
                                    f.write(data)
                                validated_paths.append(temp_path)
                            elif getattr(src, 'url', None):
                                if src.url.startswith('data:'):
                                    _, encoded = src.url.split(',', 1)
                                    encoded = encoded.strip()
                                    missing_padding = len(encoded) % 4
                                    if missing_padding:
                                        encoded += '=' * (4 - missing_padding)
                                    data = base64.b64decode(encoded)
                                else:
                                    resp = requests.get(src.url, stream=True, timeout=10)
                                    resp.raise_for_status()
                                    data = resp.content
                                with open(temp_path, 'wb') as f:
                                    f.write(data)
                                validated_paths.append(temp_path)
                            else:
                                # Unknown type; skip
                                logger.warning(f"Unknown generated source type: {type(src)}")
                    except Exception as e:
                        logger.error(f"Failed to convert generated source to temp file: {e}")
                        # Clean up any partial file
                        try:
                            if os.path.exists(temp_path):
                                os.unlink(temp_path)
                        except Exception:
                            pass

                if not validated_paths or len(validated_paths) < len(sources):
                    raise ValidationError("Some generated sources could not be processed for editing.", category="validation")
            else:
                # Fallback: treat sources as regular message attachments and validate/download them
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
                format=format,
                size=size
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
                # Complete progress — include the full prompt in the embed so it's visible
                embed.description = (
                    f"✅ Queued → ✅ Processing → ✅ Editing → ✅ Finalizing\n\n"
                    f"**Complete!** Edited {len(files)} image{'s' if len(files) > 1 else ''}\n\n"
                    f"**Prompt:** {prompt}"
                )
                embed.color = 0x00ff00

                # Save the discord.File objects to local temp files so iteration/edit can reuse them reliably
                saved_paths = []
                for i, df in enumerate(files):
                    try:
                        # df.fp should be a file-like object (BytesIO)
                        try:
                            df.fp.seek(0)
                        except Exception:
                            pass
                        data = df.fp.read()
                        temp_path = os.path.join(CACHE_DIR, f"edited_{uuid.uuid4()}_{i}.{format}")
                        with open(temp_path, 'wb') as tf:
                            tf.write(data)
                        saved_paths.append(temp_path)
                    except Exception as e:
                        logger.warning(f"Failed to write edited image to temp file: {e}")

                # Add saved_paths to validated_paths so they are cleaned up at the end
                if saved_paths:
                    validated_paths.extend(saved_paths)

                # Attach the same iteration view used for imagine, passing the saved local file paths
                try:
                    view = ImageIterationView(prompt, None, None, format, images=saved_paths if saved_paths else edited_images)
                    await progress_msg.edit(embed=embed, view=view)
                except Exception:
                    await progress_msg.edit(embed=embed)

                # Build new discord.File objects from saved temp paths (avoid sending consumed file-like objects)
                send_file_objs = []
                open_files = []
                try:
                    if saved_paths:
                        for p in saved_paths:
                            fobj = open(p, 'rb')
                            open_files.append(fobj)
                            send_file_objs.append(discord.File(fp=fobj, filename=os.path.basename(p)))
                        await interaction.followup.send(files=send_file_objs)
                    else:
                        # Fallback: send original file objects
                        await interaction.followup.send(files=files)
                finally:
                    for f in open_files:
                        try:
                            f.close()
                        except Exception:
                            pass
            else:
                await handle_error(interaction, "Failed to prepare edited image files.", category=ErrorCategory.PROCESSING)

            # Cleanup
            for path in validated_paths:
                try:
                    os.unlink(path)
                except OSError as e:
                    logger.warning(f"Failed to delete temp file {path}: {e}")

        except ValidationError as e:
            # Cleanup temp files on validation error
            if 'validated_paths' in locals() and validated_paths:
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