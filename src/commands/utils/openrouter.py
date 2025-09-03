import asyncio
import logging
import base64
import tempfile
import aiofiles
from typing import Any, Optional, Union, List, Dict
from pathlib import Path
import mimetypes
from pydantic import BaseModel
import httpx
from PIL import Image
from io import BytesIO

try:
    from discord import Attachment
    AttachmentType = Attachment
except ImportError:
    AttachmentType = None  # Graceful fallback if discord not available

from ...utils.config import config

# Configure logging
import logging
from .logging import setup_logger
logger = setup_logger(__name__)

class ImageInput(BaseModel):
    type: str  # "image_url" or "base64"
    image_url: Optional[str] = None
    image_base64: Optional[str] = None

class ContentItem(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[str] = None

class Message(BaseModel):
    role: str
    content: List[ContentItem]

class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7

class GeneratedImage(BaseModel):
    url: Optional[str] = None
    base64: Optional[str] = None
    seed: Optional[int] = None
    model: Optional[str] = None
    style: Optional[str] = None
    prompt: Optional[str] = None

class OpenRouterClient:
    def __init__(self):
        if not config.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY must be set in environment variables.")
        self.api_key = config.openrouter_api_key
        self.base_url = config.openrouter_base_url
        self.model = config.model_id
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Referer": config.referer,
            "X-Title": config.title,
        }
        self.session = httpx.AsyncClient(timeout=config.timeout, headers=headers)
        logger.info("OpenRouter client initialized.")

    async def close(self):
        await self.session.aclose()
        logger.info("Session closed.")

    async def _encode_image_to_base64(self, image_path: Path) -> str:
        """Encode a local image file to base64 data URL."""
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type or not mime_type.startswith("image/"):
            raise ValueError(f"Unsupported image type for {image_path}")
        async with aiofiles.open(image_path, "rb") as f:
            data = await f.read()
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    async def _download_image_to_temp(self, url: str) -> Path:
        """Download image from URL to temporary file and return path."""
        response = await self.session.get(url)
        response.raise_for_status()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(url).suffix)
        async with aiofiles.open(temp_file.name, "wb") as f:
            await f.write(response.content)
        logger.debug(f"Downloaded image to {temp_file.name}")
        return Path(temp_file.name)

    async def _process_image_input(self, image: Union[str, Path, Attachment]) -> ContentItem:
        """Process image input (path, URL, or Attachment) into ContentItem."""
        if Attachment and isinstance(image, Attachment):
            # For Discord Attachment, use URL if possible, else download
            if image.content_type and image.content_type.startswith("image/"):
                temp_path = await self._download_image_to_temp(image.url)
                base64_data = await self._encode_image_to_base64(temp_path)
                temp_path.unlink()  # Clean up
                # Return as base64 if preferred, but to match requirement, use image_url with base64 value
                # Actually, for OpenRouter, use base64 directly
                return ContentItem(type="image_url", image_url=f"data:image/png;base64,{base64.split(',')[1]}")
            else:
                raise ValueError("Attachment is not an image")
        elif isinstance(image, (str, Path)):
            image_str = str(image)
            if image_str.startswith(("http://", "https://")):
                # It's a URL
                return ContentItem(type="image_url", image_url=image_str)
            elif image_str.startswith("data:image/"):
                # It's already a base64 data URL
                return ContentItem(type="image_url", image_url=image_str)
            else:
                # It's a local path
                base64_data = await self._encode_image_to_base64(Path(image))
                return ContentItem(type="image_url", image_url=base64_data)
        else:
            raise ValueError(f"Unsupported image input type: {type(image)}")

    async def _make_request_with_retry(self, payload: dict) -> dict:
        """Make request with retry logic for network errors, timeouts, and 429/5xx errors."""
        for attempt in range(config.max_retries + 1):
            try:
                response = await self.session.post(f"{self.base_url}/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < config.max_retries:
                    delay = 2 ** attempt  # Exponential backoff
                    if isinstance(e, httpx.HTTPStatusError):
                        if 500 <= e.response.status_code < 600 or e.response.status_code == 429:
                            logger.warning(f"Request failed with {e.response.status_code}, retrying in {delay}s (attempt {attempt + 1}/{config.max_retries + 1})")
                        else:
                            logger.error(f"Request failed with status {e.response.status_code}: {e}")
                            # Log response content for debugging
                            try:
                                error_content = e.response.text
                                logger.error(f"Error response: {error_content}")
                            except:
                                pass
                            raise
                    else:
                        logger.warning(f"Request error: {e}, retrying in {delay}s (attempt {attempt + 1}/{config.max_retries + 1})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Request failed after {config.max_retries + 1} attempts: {e}")
                    raise

    async def generate_image(self, prompt: str, style: Optional[str] = None, count: int = 1, seed: Optional[int] = None, format: str = "png") -> List[GeneratedImage]:
        """Generate images from text prompt."""
        prompt_to_send = prompt
        if style:
            prompt_to_send += f" in {style} style"
        contents = [ContentItem(type="text", text=prompt_to_send)]
        messages = [Message(role="user", content=contents)]
        request_data = {
            "model": self.model,
            "messages": [m.dict() for m in messages],
            "max_tokens": 1024,
            "temperature": 0.7,
            "format": format,
        }
        if seed:
            request_data["seed"] = seed
        
        logger.debug(f"Sending image generation request with data: {request_data}")
        
        response = await self._make_request_with_retry(request_data)
        # Parse response: assume response["choices"][0]["message"]["content"] contains image data
        # For Gemini, responses might differ; assuming it's a list of base64 images or URLs
        # For simplicity, extract as list of GeneratedImage
        # This may need adjustment based on actual API response format
        images = []
        
        logger.debug(f"API response structure: {response.keys()}")
        logger.debug(f"Full API response: {response}")
        
        for choice in response.get("choices", []):
            content = choice["message"].get("content", "")
            logger.debug(f"Choice content type: {type(content)}, content preview: {str(content)[:100]}")
            
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image":
                        img_url = item.get("url")
                        img_b64 = item.get("base64")
                        if img_b64:
                            # Clean base64 string
                            img_b64 = img_b64.strip()
                            # Don't add extra padding here - let the processing function handle it
                        images.append(GeneratedImage(url=img_url, base64=img_b64, seed=seed, model=self.model, style=style, prompt=prompt))
            elif isinstance(content, str):
                content = content.strip()
                if len(content) > 1000:  # Likely image data
                    # Extract base64 data if it's a data URL
                    if content.startswith("data:image/"):
                        content = content.split(",", 1)[1]
                    images.append(GeneratedImage(base64=content, model=self.model, prompt=prompt))
                else:
                    # Skip text-only responses like "Here you go!"
                    logger.debug(f"Text content received: {content}")
                    continue
        
        # If no images found in content, check if there are image attachments in the response
        if not images:
            logger.debug("No images found in content, checking for attachment data...")
            # Look for image data in various possible locations in the response
            for choice in response.get("choices", []):
                # Check for attachments or tool calls that might contain image data
                if "attachments" in choice.get("message", {}):
                    for attachment in choice["message"]["attachments"]:
                        if "image" in attachment.get("type", ""):
                            img_data = attachment.get("data") or attachment.get("base64")
                            if img_data:
                                images.append(GeneratedImage(base64=img_data, seed=seed, model=self.model, style=style, prompt=prompt))
                
                # Check for tool_calls that might contain image generation results
                if "tool_calls" in choice.get("message", {}):
                    for tool_call in choice["message"]["tool_calls"]:
                        if tool_call.get("type") == "function":
                            function_result = tool_call.get("function", {}).get("arguments", "")
                            try:
                                import json
                                parsed_result = json.loads(function_result) if isinstance(function_result, str) else function_result
                                if isinstance(parsed_result, dict) and "image" in parsed_result:
                                    img_data = parsed_result["image"]
                                    if isinstance(img_data, str) and len(img_data) > 100:  # Reasonable base64 length check
                                        images.append(GeneratedImage(base64=img_data, seed=seed, model=self.model, style=style, prompt=prompt))
                            except:
                                pass
        
        # If still no images, do a deep search through the entire response for base64 strings
        if not images:
            logger.debug("Performing deep search for base64 image data in response...")
            def find_base64_strings(obj, path=""):
                """Recursively search for base64 strings in a nested object"""
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        if isinstance(value, str) and len(value) > 1000 and value.startswith(('iVBORw0KGgo', '/9j/', 'R0lGOD', 'UklGRg')):  # Common image headers
                            logger.debug(f"Found potential base64 image at path: {current_path}, length: {len(value)}")
                            images.append(GeneratedImage(base64=value, seed=seed, model=self.model, style=style, prompt=prompt))
                        else:
                            find_base64_strings(value, current_path)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f"{path}[{i}]" if path else f"[{i}]"
                        find_base64_strings(item, current_path)
            
            find_base64_strings(response)
            
        # If still no images found, try to extract from raw response text
        if not images:
            logger.debug("Attempting to extract base64 from raw response as fallback...")
            response_str = str(response)
            # Look for common base64 patterns within the response string
            import re
            # Pattern to match base64 strings that look like image data (PNG, JPEG, GIF, WEBP)
            patterns = [
                r'iVBORw0KGgo[A-Za-z0-9+/=]+',  # PNG
                r'/9j/[A-Za-z0-9+/=]+',          # JPEG
                r'R0lGOD[A-Za-z0-9+/=]+',        # GIF
                r'UklGRg[A-Za-z0-9+/=]+'         # WEBP
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response_str)
                for match in matches:
                    if len(match) > 1000:  # Reasonable minimum length for an image
                        logger.debug(f"Found base64 pattern via regex: {pattern}, length: {len(match)}")
                        images.append(GeneratedImage(base64=match, seed=seed, model=self.model, style=style, prompt=prompt))
                        break  # Take the first good match
                if images:  # If we found images, stop searching
                    break
        
        logger.debug(f"Parsed {len(images)} images from API response")
        return images[:count] if images else []

    async def edit_image(self, prompt: str, sources: List[Union[str, Path, Attachment]], mask: Optional[Union[str, Path, Attachment]] = None, format: str = "png") -> List[GeneratedImage]:
        """Edit image(s) based on prompt."""
        contents = [ContentItem(type="text", text=prompt)]
        for src in sources:
            contents.append(await self._process_image_input(src))
        if mask:
            # For mask, treat as additional image
            contents.append(await self._process_image_input(mask))
        messages = [Message(role="user", content=contents)]
        request_data = {
            "model": self.model,
            "messages": [m.dict() for m in messages],
            "max_tokens": 1024,
            "temperature": 0.7,
            "format": format,
        }
        response = await self._make_request_with_retry(request_data)
        # Parse similarly to generate_image
        images = []
        logger.debug(f"Edit API response structure: {response.keys()}")

        for choice in response.get("choices", []):
            content = choice["message"].get("content", "")
            logger.debug(f"Edit choice content type: {type(content)}, content preview: {str(content)[:100]}")

            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image":
                        img_url = item.get("url")
                        img_b64 = item.get("base64")
                        if img_b64:
                            img_b64 = img_b64.strip()
                        images.append(GeneratedImage(url=img_url, base64=img_b64, model=self.model, prompt=prompt))
            elif isinstance(content, str):
                content = content.strip()
                if len(content) > 1000:  # Likely image data
                    # Extract base64 data if it's a data URL
                    if content.startswith("data:image/"):
                        content = content.split(",", 1)[1]
                    images.append(GeneratedImage(base64=content, model=self.model, prompt=prompt))
                else:
                    # Skip text-only responses like "Here you go!"
                    logger.debug(f"Text content received: {content}")
                    continue

        # If no images found in content, check if there are image attachments in the response
        if not images:
            logger.debug("No images found in edit content, checking for attachment data...")
            # Look for image data in various possible locations in the response
            for choice in response.get("choices", []):
                # Check for attachments or tool calls that might contain image data
                if "attachments" in choice.get("message", {}):
                    for attachment in choice["message"]["attachments"]:
                        if "image" in attachment.get("type", ""):
                            img_data = attachment.get("data") or attachment.get("base64")
                            if img_data:
                                images.append(GeneratedImage(base64=img_data, model=self.model, prompt=prompt))

                # Check for tool_calls that might contain image generation results
                if "tool_calls" in choice.get("message", {}):
                    for tool_call in choice["message"]["tool_calls"]:
                        if tool_call.get("type") == "function":
                            function_result = tool_call.get("function", {}).get("arguments", "")
                            try:
                                import json
                                parsed_result = json.loads(function_result) if isinstance(function_result, str) else function_result
                                if isinstance(parsed_result, dict) and "image" in parsed_result:
                                    img_data = parsed_result["image"]
                                    if isinstance(img_data, str) and len(img_data) > 100:  # Reasonable base64 length check
                                        images.append(GeneratedImage(base64=img_data, model=self.model, prompt=prompt))
                            except:
                                pass

        # If still no images, do a deep search through the entire response for base64 strings
        if not images:
            logger.debug("Performing deep search for base64 image data in edit response...")
            def find_base64_strings(obj, path=""):
                """Recursively search for base64 strings in a nested object"""
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        if isinstance(value, str) and len(value) > 1000 and (value.startswith(('iVBORw0KGgo', '/9j/', 'R0lGOD', 'UklGRg')) or value.startswith("data:image/")):  # Common image headers or data URLs
                            logger.debug(f"Found potential base64 image at path: {current_path}, length: {len(value)}")
                            base64_data = value
                            if value.startswith("data:image/"):
                                base64_data = value.split(",", 1)[1]  # Extract after comma
                            images.append(GeneratedImage(base64=base64_data, model=self.model, prompt=prompt))
                        else:
                            find_base64_strings(value, current_path)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f"{path}[{i}]" if path else f"[{i}]"
                        find_base64_strings(item, current_path)

            find_base64_strings(response)

        # If still no images found, try to extract from raw response text
        if not images:
            logger.debug("Attempting to extract base64 from raw response as fallback...")
            response_str = str(response)
            # Look for common base64 patterns within the response string
            import re
            # Pattern to match base64 strings that look like image data (PNG, JPEG, GIF, WEBP)
            patterns = [
                r'iVBORw0KGgo[A-Za-z0-9+/=]+',  # PNG
                r'/9j/[A-Za-z0-9+/=]+',          # JPEG
                r'R0lGOD[A-Za-z0-9+/=]+',        # GIF
                r'UklGRg[A-Za-z0-9+/=]+'         # WEBP
            ]

            for pattern in patterns:
                matches = re.findall(pattern, response_str)
                for match in matches:
                    if len(match) > 1000:  # Reasonable minimum length for an image
                        logger.debug(f"Found base64 pattern via regex: {pattern}, length: {len(match)}")
                        images.append(GeneratedImage(base64=match, model=self.model, prompt=prompt))
                        break  # Take the first good match
                if images:  # If we found images, stop searching
                    break

        logger.debug(f"Parsed {len(images)} images from edit API response")
        return images

    async def blend_images(self, prompt: str, sources: List[Union[str, Path, Attachment]], strength: float = 0.5, format: str = "png") -> List[GeneratedImage]:
        """Blend multiple images based on prompt."""
        if not 2 <= len(sources) <= 6:
            raise ValueError("Blend requires 2-6 source images.")
        contents = [ContentItem(type="text", text=f"{prompt} with blend strength {strength}")]
        for src in sources:
            contents.append(await self._process_image_input(src))
        messages = [Message(role="user", content=contents)]
        request_data = {
            "model": self.model,
            "messages": [m.dict() for m in messages],
            "max_tokens": 1024,
            "temperature": 0.7,
            "format": format,
        }
        response = await self._make_request_with_retry(request_data)
        # Parse similarly to generate_image
        images = []
        logger.debug(f"Blend API response structure: {response.keys()}")

        for choice in response.get("choices", []):
            content = choice["message"].get("content", "")
            logger.debug(f"Blend choice content type: {type(content)}, content preview: {str(content)[:100]}")

            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image":
                        img_url = item.get("url")
                        img_b64 = item.get("base64")
                        if img_b64:
                            img_b64 = img_b64.strip()
                        images.append(GeneratedImage(url=img_url, base64=img_b64, model=self.model, prompt=prompt))
            elif isinstance(content, str):
                # Skip text-only responses like "Here you go!" - look for image data in the full response
                logger.debug(f"Text content received: {content}")
                continue

        # If no images found in content, check if there are image attachments in the response
        if not images:
            logger.debug("No images found in blend content, checking for attachment data...")
            # Look for image data in various possible locations in the response
            for choice in response.get("choices", []):
                # Check for attachments or tool calls that might contain image data
                if "attachments" in choice.get("message", {}):
                    for attachment in choice["message"]["attachments"]:
                        if "image" in attachment.get("type", ""):
                            img_data = attachment.get("data") or attachment.get("base64")
                            if img_data:
                                images.append(GeneratedImage(base64=img_data, model=self.model, prompt=prompt))

                # Check for tool_calls that might contain image generation results
                if "tool_calls" in choice.get("message", {}):
                    for tool_call in choice["message"]["tool_calls"]:
                        if tool_call.get("type") == "function":
                            function_result = tool_call.get("function", {}).get("arguments", "")
                            try:
                                import json
                                parsed_result = json.loads(function_result) if isinstance(function_result, str) else function_result
                                if isinstance(parsed_result, dict) and "image" in parsed_result:
                                    img_data = parsed_result["image"]
                                    if isinstance(img_data, str) and len(img_data) > 100:  # Reasonable base64 length check
                                        images.append(GeneratedImage(base64=img_data, model=self.model, prompt=prompt))
                            except:
                                pass

        # If still no images, do a deep search through the entire response for base64 strings
        if not images:
            logger.debug("Performing deep search for base64 image data in blend response...")
            def find_base64_strings(obj, path=""):
                """Recursively search for base64 strings in a nested object"""
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        if isinstance(value, str) and len(value) > 1000 and (value.startswith(('iVBORw0KGgo', '/9j/', 'R0lGOD', 'UklGRg')) or value.startswith("data:image/")):  # Common image headers or data URLs
                            logger.debug(f"Found potential base64 image at path: {current_path}, length: {len(value)}")
                            base64_data = value
                            if value.startswith("data:image/"):
                                base64_data = value.split(",", 1)[1]  # Extract after comma
                            images.append(GeneratedImage(base64=base64_data, model=self.model, prompt=prompt))
                        else:
                            find_base64_strings(value, current_path)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f"{path}[{i}]" if path else f"[{i}]"
                        find_base64_strings(item, current_path)

            find_base64_strings(response)

        # If still no images found, try to extract from raw response text
        if not images:
            logger.debug("Attempting to extract base64 from raw response as fallback...")
            response_str = str(response)
            # Look for common base64 patterns within the response string
            import re
            # Pattern to match base64 strings that look like image data (PNG, JPEG, GIF, WEBP)
            patterns = [
                r'iVBORw0KGgo[A-Za-z0-9+/=]+',  # PNG
                r'/9j/[A-Za-z0-9+/=]+',          # JPEG
                r'R0lGOD[A-Za-z0-9+/=]+',        # GIF
                r'UklGRg[A-Za-z0-9+/=]+'         # WEBP
            ]

            for pattern in patterns:
                matches = re.findall(pattern, response_str)
                for match in matches:
                    if len(match) > 1000:  # Reasonable minimum length for an image
                        logger.debug(f"Found base64 pattern via regex: {pattern}, length: {len(match)}")
                        images.append(GeneratedImage(base64=match, model=self.model, prompt=prompt))
                        break  # Take the first good match
                if images:  # If we found images, stop searching
                    break

        logger.debug(f"Parsed {len(images)} images from blend API response")
        return images
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()