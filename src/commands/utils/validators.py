import discord
from typing import List, Any, Optional, Union
from src.commands.utils.logging import setup_logger

logger = setup_logger(__name__)

class ValidationError(Exception):
    """Custom exception for validation failures."""
    def __init__(self, message: str, category: str = "validation"):
        self.message = message
        self.category = category
        super().__init__(message)

async def validate_prompt(
    interaction: "discord.Interaction[Any]",
    prompt: str,
    min_length: int = 1,
    max_length: int = 1000,
    field_name: str = "prompt"
) -> None:
    """
    Validate a prompt string.

    Args:
        interaction: Discord interaction
        prompt: The prompt string to validate
        min_length: Minimum length required
        max_length: Maximum length allowed
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(prompt, str):
        raise ValidationError("Prompt must be a string", category="validation")

    prompt = prompt.strip()
    if len(prompt) < min_length:
        raise ValidationError(f"{field_name} must be at least {min_length} character(s) long", category="validation")

    if len(prompt) > max_length:
        raise ValidationError(f"{field_name} must be no more than {max_length} characters long", category="validation")

    # Add basic profanity/content checks if needed
    forbidden_words = ["banned_word_example"]  # Can be extended
    lower_prompt = prompt.lower()
    for word in forbidden_words:
        if word in lower_prompt:
            raise ValidationError(f"{field_name} contains inappropriate content", category="validation")

async def validate_attachments(
    interaction: "discord.Interaction[Any]",
    attachments: List["discord.Attachment"],
    min_count: int = 1,
    max_count: Optional[int] = None,
    allowed_types: Optional[List[str]] = None,
    max_size_mb: float = 10.0
) -> None:
    """
    Validate a list of attachments.

    Args:
        interaction: Discord interaction
        attachments: List of attachments to validate
        min_count: Minimum number of attachments required
        max_count: Maximum number of attachments allowed
        allowed_types: List of allowed content types (e.g., ['image/png', 'image/jpeg'])
        max_size_mb: Maximum file size in MB

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(attachments, list):
        raise ValidationError("Attachments must be provided as a list", category="validation")

    count = len(attachments)
    if count < min_count:
        raise ValidationError(f"At least {min_count} attachment(s) required, got {count}", category="validation")

    if max_count is not None and count > max_count:
        raise ValidationError(f"No more than {max_count} attachment(s) allowed, got {count}", category="validation")

    if allowed_types is None:
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']

    max_size_bytes = max_size_mb * 1024 * 1024

    for i, attachment in enumerate(attachments):
        if not isinstance(attachment, discord.Attachment):
            raise ValidationError(f"Item {i+1} is not a valid Discord attachment", category="validation")

        if attachment.content_type and attachment.content_type.lower() not in [t.lower() for t in allowed_types]:
            raise ValidationError(f"Attachment {i+1}: Invalid file type '{attachment.content_type}'. Allowed types: {', '.join(allowed_types)}", category="validation")

        if attachment.size > max_size_bytes:
            raise ValidationError(f"Attachment {i+1}: File too large ({attachment.size / (1024*1024):.1f} MB). Maximum: {max_size_mb} MB", category="validation")

async def validate_numeric_parameter(
    interaction: "discord.Interaction[Any]",
    value: Union[int, float],
    min_value: Union[int, float],
    max_value: Union[int, float],
    field_name: str = "parameter"
) -> None:
    """
    Validate a numeric parameter within a range.

    Args:
        interaction: Discord interaction
        value: The numeric value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        field_name: Name of the parameter for error messages

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be a number", category="validation")

    if value < min_value:
        raise ValidationError(f"{field_name} must be at least {min_value}, got {value}", category="validation")

    if value > max_value:
        raise ValidationError(f"{field_name} must be no more than {max_value}, got {value}", category="validation")

async def validate_count_parameter(
    interaction: "discord.Interaction[Any]",
    count: int,
    min_count: int = 1,
    max_count: int = 10,
    field_name: str = "count"
) -> None:
    """
    Validate a count parameter (convenience wrapper).

    Args:
        interaction: Discord interaction
        count: The count value to validate
        min_count: Minimum allowed count
        max_count: Maximum allowed count
        field_name: Name of the parameter for error messages

    Raises:
        ValidationError: If validation fails
    """
    await validate_numeric_parameter(
        interaction,
        count,
        min_count,
        max_count,
        field_name
    )

async def validate_strength_parameter(
    interaction: "discord.Interaction[Any]",
    strength: float,
    min_strength: float = 0.0,
    max_strength: float = 1.0,
    field_name: str = "strength"
) -> None:
    """
    Validate a strength parameter (convenience wrapper for 0.0-1.0 range).

    Args:
        interaction: Discord interaction
        strength: The strength value to validate
        min_strength: Minimum allowed strength
        max_strength: Maximum allowed strength
        field_name: Name of the parameter for error messages

    Raises:
        ValidationError: If validation fails
    """
    await validate_numeric_parameter(
        interaction,
        strength,
        min_strength,
        max_strength,
        field_name
    )

# Utility function to validate multiple attachments at once
async def validate_attachment_list(
    interaction: "discord.Interaction[Any]",
    attachments: List[Optional[Any]],
    expected_count: int,
    required: bool = True
) -> List["discord.Attachment"]:
    """
    Validate a list of potentially None attachments.

    Args:
        interaction: Discord interaction
        attachments: List that might contain None values
        expected_count: Expected number of non-None attachments
        required: Whether this validation is required

    Returns:
        List of valid attachments

    Raises:
        ValidationError: If validation fails
    """
    valid_attachments = [att for att in attachments if att is not None]

    if required and len(valid_attachments) < expected_count:
        raise ValidationError(f"At least {expected_count} valid attachment(s) required, got {len(valid_attachments)}", category="validation")

    await validate_attachments(interaction, valid_attachments)

    return valid_attachments

# List of prohibited terms for content filtering
PROHIBITED_TERMS = [
    "nigger", "chink", "kike", "spic", "wetback", "coon", "faggot", "dyke",
    "fuck", "shit", "bitch", "bastard", "damn", "asshole", "crap",
    "porn", "sex", "naked", "rape", "incest", "pedophile", "murder",
    "suicide", "drugs", "vomit", "terrorist", "bomb", "gun", "kill"
]

def is_balanced(text: str) -> bool:
    """
    Check if parentheses and quotes are balanced in the text.

    Args:
        text: The string to check

    Returns:
        True if balanced, False otherwise
    """
    stack = []
    pairs = {')': '(', ']': '[', '}': '{', '"': '"', "'": "'", '`': '`'}

    for char in text:
        if char in '({[["\'`':
            stack.append(char)
        elif char in ')}]"\'`':
            if not stack:
                return False
            if stack[-1] != pairs.get(char):
                return False
            stack.pop()

    return not stack

async def validate_prompt_content(
    prompt: str,
    max_length: int = 500
) -> None:
    """
    Validate prompt content with comprehensive checks.

    Args:
        prompt: The prompt string to validate
        max_length: Maximum allowed length in characters

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(prompt, str):
        raise ValidationError("Prompt must be a string", category="validation")

    # Check for empty prompt (after stripping whitespace)
    stripped_prompt = prompt.strip()
    if not stripped_prompt:
        raise ValidationError("Prompt cannot be empty", category="validation")

    # Check length
    if len(stripped_prompt) > max_length:
        raise ValidationError(f"Prompt must be no more than {max_length} characters long, got {len(stripped_prompt)}", category="validation")

    # Check for prohibited terms
    lower_prompt = stripped_prompt.lower()
    for term in PROHIBITED_TERMS:
        if term in lower_prompt:
            raise ValidationError(f"Prompt contains prohibited content: '{term}'", category="validation")

    # Check for balanced parentheses and quotes
    if not is_balanced(stripped_prompt):
        raise ValidationError("Prompt contains unbalanced parentheses or quotes", category="validation")

# Decorators for automatic validation in commands

from functools import wraps
import inspect

def validate_command_prompt(min_length: int = 1, max_length: int = 1000, field_name: str = "prompt"):
    """
    Decorator to validate prompt parameter in app_commands.

    Assumes the command has an interaction and prompt parameter in that order.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get interaction and prompt from args
            if len(args) < 2:
                raise ValidationError("Invalid command signature: missing interaction or prompt", category="validation")
            interaction = args[0]
            prompt = args[1]

            try:
                await validate_prompt(interaction, prompt, min_length, max_length, field_name)
            except ValidationError as e:
                from src.commands.utils.error_handler import handle_error, ErrorCategory
                await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
                return  # Don't execute command

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def validate_command_attachments(min_count: int = 1, max_count: Optional[int] = None, allowed_types: Optional[List[str]] = None, max_size_mb: float = 10.0):
    """
    Decorator to validate attachments in app_commands.

    Assumes the command has interaction as first arg, and attachments as a kwarg or positional.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            interaction = args[0] if args else None
            if not interaction:
                raise ValidationError("Missing interaction", category="validation")

            # Find attachments in kwargs or args
            attachments = kwargs.get('attachments') or [a for a in args[1:] if hasattr(a, 'content_type')] or []
            if isinstance(attachments, list) and attachments:
                try:
                    await validate_attachments(interaction, attachments, min_count, max_count, allowed_types, max_size_mb)
                except ValidationError as e:
                    from src.commands.utils.error_handler import handle_error, ErrorCategory
                    await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
                    return

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def validate_command_count(min_count: int = 1, max_count: int = 10, field_name: str = "count", param_index: int = 3):
    """
    Decorator to validate count parameter.

    Assumes interaction is args[0], and count is args[param_index] or in kwargs.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            interaction = args[0] if args else None
            if not interaction:
                raise ValidationError("Missing interaction", category="validation")

            count = kwargs.get('count', args[param_index] if len(args) > param_index else None)
            if count is not None:
                try:
                    await validate_count_parameter(interaction, count, min_count, max_count, field_name)
                except ValidationError as e:
                    from src.commands.utils.error_handler import handle_error, ErrorCategory
                    await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
                    return

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def validate_command_strength(min_strength: float = 0.0, max_strength: float = 1.0, field_name: str = "strength"):
    """
    Decorator to validate strength parameter.

    Assumes interaction is args[0], and strength is in kwargs or later args.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            interaction = args[0] if args else None
            if not interaction:
                raise ValidationError("Missing interaction", category="validation")

            strength = kwargs.get('strength', None)
            if strength is not None:
                try:
                    await validate_strength_parameter(interaction, strength, min_strength, max_strength, field_name)
                except ValidationError as e:
                    from src.commands.utils.error_handler import handle_error, ErrorCategory
                    await handle_error(interaction, str(e), category=e.category, include_suggestion=True)
                    return

            return await func(*args, **kwargs)
        return wrapper
    return decorator