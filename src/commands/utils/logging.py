import json
import logging
import re
from typing import Any

from ...utils.config import config


class StructuredJSONFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            'timestamp': self.formatTime(record, datefmt='%Y-%m-%dT%H:%M:%S.%fZ'),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.name if hasattr(record, 'name') else '[UNKNOWN]'
        }
        return json.dumps(log_entry)


def redact_sensitive(text: str) -> str:
    """Redacts sensitive information from text using regex patterns.

    This function scans for common patterns of API keys, tokens, secrets, and passwords,
    replacing them with '[REDACTED]' to prevent accidental logging of sensitive data.
    Note: This does not log prompts or images as per security guidelines.

    Args:
        text: The input text to redact.

    Returns:
        The text with sensitive parts redacted.
    """
    patterns = [
        r'(--?)?(?:api[_-]?key|token|secret|password):?\s*\S+',  # Basic patterns
        r'sk-[a-zA-Z0-9]+',  # OpenAI/Bot style keys
        r'pk_[a-zA-Z0-9]+',  # Other public keys that may be sensitive
        r'bearer\s+[a-zA-Z0-9_-]+',
        r'authorization:\s*bearer\s+[a-zA-Z0-9_-]+',
        r'https?://[^\s]*[?&](?:api_key|token|key)=([a-zA-Z0-9_-]+)',  # URLs with keys
    ]
    for pattern in patterns:
        text = re.sub(pattern, '[REDACTED]', text, flags=re.IGNORECASE)
    return text


def setup_logger(name: str) -> logging.Logger:
    """Sets up and returns a configured logger with JSON formatting.

    Loads LOG_LEVEL from environment variables (.env), defaults to INFO.
    Configures console handler with JSON output. Avoids logging user data.

    Args:
        name: The name of the logger (typically module name).

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        logger.handlers.clear()  # Prevent duplicate handlers

    level = getattr(logging, config.log_level, logging.INFO)
    logger.setLevel(level)

    formatter = StructuredJSONFormatter()
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.propagate = False  # Prevent bubbling to root logger
    return logger