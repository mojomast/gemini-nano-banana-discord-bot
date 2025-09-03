import os
import logging
import tempfile
import base64
import mimetypes
import shutil
import uuid
from typing import List, Union, Optional, Dict, Any
from io import BytesIO
import uuid
import requests
from PIL import Image, UnidentifiedImageError
import discord

from .logging import setup_logger
from ...utils.config import config

# Set up logging
logger = setup_logger(__name__)

# Custom exceptions
class ImageValidationError(Exception):
    pass

class ImageDownloadError(Exception):
    pass

class ImageProcessingError(Exception):
    pass

# Helper: Convert image format
def convert_image_format(image_bytes: bytes, target_format: str) -> bytes:
    """
    Convert image bytes to target format using PIL.
    """
    if target_format == "png":
        return image_bytes
    elif target_format in ["jpg", "jpeg", "webp"]:
        img = Image.open(BytesIO(image_bytes))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        format_upper = target_format.upper() if target_format != "jpg" else "JPEG"
        output = BytesIO()
        if target_format == "jpg":
            img.save(output, format_upper, quality=85)
        elif target_format == "webp":
            img.save(output, format_upper)
        else:
            img.save(output, format_upper)
        return output.getvalue()
    else:
        return image_bytes

# Load configuration from centralized config
ALLOWED_IMAGE_TYPES = config.allowed_image_types
MAX_IMAGE_MB = config.max_image_mb
CACHE_DIR = str(config.cache_dir)

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

# Helper: Validate attachment
def validate_attachment(attachment: discord.Attachment) -> bool:
    """
    Validate if the attachment is an allowed image type and within size limits.
    """
    # Check if it's an image content type
    if not attachment.content_type or not attachment.content_type.startswith('image/'):
        logger.warning(f"Attachment {attachment.filename} is not an image.")
        raise ImageValidationError(f"Attachment {attachment.filename} is not an image.")

    # Check allowed types by file extension from filename
    _, ext = os.path.splitext(attachment.filename.lower())
    ext = ext[1:]  # remove dot
    if ext not in ALLOWED_IMAGE_TYPES:
        logger.warning(f"Attachment type {ext} not allowed. Allowed: {ALLOWED_IMAGE_TYPES}")
        raise ImageValidationError(f"Attachment type {ext} not allowed.")

    # MIME sniffing: check content_type against allowed
    mimetype, _ = mimetypes.guess_type(attachment.filename)
    if not mimetype or not mimetype.startswith('image/') or mimetype.split('/')[1].lower() not in ALLOWED_IMAGE_TYPES:
        logger.warning(f"MIME type {mimetype} invalid for {attachment.filename}")
        raise ImageValidationError(f"MIME type {mimetype} invalid for {attachment.filename}")

    # Size check: attachment.size is in bytes, max is MAX_IMAGE_MB
    max_bytes = MAX_IMAGE_MB * 1024 * 1024
    if attachment.size > max_bytes:
        logger.warning(f"Attachment {attachment.filename} size {attachment.size} bytes exceeds {MAX_IMAGE_MB} MB.")
        raise ImageValidationError(f"Attachment size exceeds {MAX_IMAGE_MB} MB.")

    logger.info(f"Attachment {attachment.filename} validated successfully.")
    return True

# Helper: Download attachment to temp file
def download_attachment(attachment: discord.Attachment) -> str:
    """
    Download the attachment and save to a temp file in CACHE_DIR.
    Returns the temp path.
    """
    try:
        response = requests.get(attachment.url, stream=True)
        response.raise_for_status()
        temp_filename = f"{uuid.uuid4()}_{attachment.filename}"
        temp_path = os.path.join(CACHE_DIR, temp_filename)
        try:
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except Exception as write_e:
            # If writing fails, clean partial file
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as unlink_e:
                    logger.warning(f"Failed to clean partial download {temp_path}: {unlink_e}")
            raise write_e
        logger.info(f"Downloaded {attachment.filename} to {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"Failed to download attachment {attachment.filename}: {e}")
        raise ImageDownloadError(f"Failed to download attachment: {e}") from e

# Helper: Encode to base64
def encode_to_base64(image_input: Union[str, Image.Image]) -> str:
    """
    Encode image file path or PIL Image to base64 string.
    """
    if isinstance(image_input, str):
        # File path
        try:
            with open(image_input, 'rb') as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {image_input}: {e}")
            raise ImageProcessingError(f"Failed to read file: {e}") from e
    elif isinstance(image_input, Image.Image):
        # PIL Image
        buffer = BytesIO()
        image_input.save(buffer, format=image_input.format or 'PNG')
        image_bytes = buffer.getvalue()
    else:
        raise ImageProcessingError("Invalid input type for encoding.")

    encoded = base64.b64encode(image_bytes).decode('utf-8')
    logger.info("Image encoded to base64.")
    return encoded

# Helper: Resize if large
def resize_if_large(image_path: str, max_size_mb: float = 8.0) -> str:
    """
    If image file size > max_size_mb, resize to reduce size while preserving aspect ratio.
    Returns the resized path (original if no resize needed).
    """
    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return image_path

    try:
        with Image.open(image_path) as img:
            # Shrink by half each time until below limit
            while file_size_mb > max_size_mb and img.size[0] > 1 and img.size[1] > 1:
                new_size = (img.size[0] // 2, img.size[1] // 2)
                img = img.resize(new_size, Image.LANCZOS)
                temp_path = os.path.join(CACHE_DIR, f"resized_{uuid.uuid4()}_{os.path.basename(image_path)}")
                try:
                    img.save(temp_path, quality=85)  # Save with quality to reduce size
                except Exception as save_e:
                    # If save fails, clean temp file
                    if os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except OSError as unlink_e:
                            logger.warning(f"Failed to clean temp resize {temp_path}: {unlink_e}")
                    raise save_e
                new_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                if new_size_mb < file_size_mb:
                    file_size_mb = new_size_mb
                    image_path = temp_path
                else:
                    # If not smaller, delete temp and stop
                    try:
                        os.unlink(temp_path)
                    except OSError as unlink_e:
                        logger.warning(f"Failed to delete non-useful temp resize {temp_path}: {unlink_e}")
                    break
        logger.info(f"Resized image to {image_path}")
        return image_path
    except UnidentifiedImageError:
        raise ImageProcessingError("Could not process image.")
    except Exception as e:
        logger.error(f"Failed to resize image {image_path}: {e}")
        raise ImageProcessingError(f"Failed to resize image: {e}") from e

# Main: Fetch and validate attachments
def fetch_and_validate_attachments(attachments: List[discord.Attachment]) -> List[str]:
    """
    Fetch and validate a list of attachments, return list of temp paths.
    Validates each, downloads if valid.
    """
    validated_paths = []
    for att in attachments:
        try:
            validate_attachment(att)
            temp_path = download_attachment(att)
            validated_paths.append(temp_path)
        except (ImageValidationError, ImageDownloadError) as e:
            logger.error(f"Skipping attachment {att.filename}: {e}")
            continue  # Skip invalid
    return validated_paths

# Main: Prepare image for API
def prepare_image_for_api(image_path: str) -> Dict[str, Any]:
    """
    Prepare image for OpenRouter API: if size <= 4MB (half of 8MB for safety), return {'url': 'data:image/...'},
    else encode to base64 {'data': b64string}.
    Assuming OpenRouter accepts data URIs or base64.
    """
    # First, ensure size is under 8MB by resizing if needed
    adjusted_path = resize_if_large(image_path, max_size_mb=8.0)
    file_size_mb = os.path.getsize(adjusted_path) / (1024 * 1024)

    if file_size_mb <= 4.0:  # Threshold for URL vs base64
        # Assume we can create a data URI
        with open(adjusted_path, 'rb') as f:
            image_bytes = f.read()
        encoded = base64.b64encode(image_bytes).decode('utf-8')
        mimetype, _ = mimetypes.guess_type(adjusted_path)
        data_uri = f"data:{mimetype or 'image/png'};base64,{encoded}"
        # Clean temp file if different from original
        if adjusted_path != image_path:
            try:
                os.unlink(adjusted_path)
            except OSError as e:
                logger.warning(f"Failed to clean temp file {adjusted_path}: {e}")
        return {'url': data_uri}
    else:
        encoded = encode_to_base64(adjusted_path)
        # Clean temp file if different from original
        if adjusted_path != image_path:
            try:
                os.unlink(adjusted_path)
            except OSError as e:
                logger.warning(f"Failed to clean temp file {adjusted_path}: {e}")
        return {'data': encoded}

# Cleanup utility
def cleanup_temp_files(dir_path: str = CACHE_DIR) -> None:
    """
    Clean up all files in CACHE_DIR (if it's our temp dir).
    """
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Cleaned up temp files in {dir_path}")

from src.commands.utils.openrouter import GeneratedImage

def process_image_sources(sources_list: List[GeneratedImage], prefix: str = "image", total: int = 1, format: str = "png") -> List[Optional[discord.File]]:
    """
    Convert a list of GeneratedImage objects to a list of Discord File objects.
    Handles base64, data URI, and HTTP URL formats.
    """
    files = []
    # format for extension
    for i, img in enumerate(sources_list):
        if total > 1:
            filename = f"{prefix}_{i+1}.{format}"
        else:
            filename = f"{prefix}.{format}"

        try:
            if img.base64:
                # Clean and validate base64 string
                base64_data = img.base64
                if base64_data.startswith("data:"):
                    _, base64_data = base64_data.split(",", 1)
                
                # Remove any whitespace and validate base64 padding
                base64_data = base64_data.strip()
                
                # Add padding if missing (base64 strings should be multiples of 4)
                missing_padding = len(base64_data) % 4
                if missing_padding:
                    base64_data += '=' * (4 - missing_padding)
                
                # Validate that it's actually base64 before decoding
                try:
                    image_data = base64.b64decode(base64_data, validate=True)
                except Exception as decode_error:
                    logger.error(f"Invalid base64 data for image {i+1}: {decode_error}")
                    logger.debug(f"Base64 string length: {len(base64_data)}, content preview: {base64_data[:50]}...")
                    files.append(None)
                    continue
                    
                image_data = convert_image_format(image_data, format)
                files.append(discord.File(fp=BytesIO(image_data), filename=filename))
            elif img.url:
                if img.url.startswith("data:"):
                    _, encoded = img.url.split(",", 1)
                    # Clean and validate base64 string
                    encoded = encoded.strip()
                    missing_padding = len(encoded) % 4
                    if missing_padding:
                        encoded += '=' * (4 - missing_padding)
                    
                    try:
                        image_data = base64.b64decode(encoded, validate=True)
                    except Exception as decode_error:
                        logger.error(f"Invalid base64 data in URL for image {i+1}: {decode_error}")
                        files.append(None)
                        continue
                else:
                    # Download from URL
                    try:
                        response = requests.get(img.url, stream=True, timeout=10)
                        response.raise_for_status()
                        image_data = b''
                        for chunk in response.iter_content(chunk_size=8192):
                            image_data += chunk
                    except Exception as download_error:
                        logger.error(f"Failed to download image from URL {img.url}: {download_error}")
                        files.append(None)
                        continue
                        
                image_data = convert_image_format(image_data, format)
                files.append(discord.File(fp=BytesIO(image_data), filename=filename))
            else:
                logger.error(f"No image data in GeneratedImage {i+1}")
                files.append(None)
        except Exception as e:
            logger.error(f"Failed to process generated image {i+1}: {e}")
            files.append(None)

    return files

# Main: Save image to cache
def save_image_to_cache(prompt: str, image_data: bytes) -> str:
    """
    Save the generated image to cache with a filename based on the prompt.
    """
    prompt_text = prompt.replace(" ", "_")
    # Truncate the filename to avoid "Filename too long" errors
    max_filename_length = 100
    if len(prompt_text) > max_filename_length:
        prompt_text = prompt_text[:max_filename_length]
    filename = f"{uuid.uuid4()}_{prompt_text}.png"
    file_path = os.path.join(CACHE_DIR, filename)

    try:
        with open(file_path, 'wb') as f:
            f.write(image_data)
        logger.info(f"Image saved to cache: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to save image to cache: {e}")
        raise ImageProcessingError(f"Failed to save image to cache: {e}") from e