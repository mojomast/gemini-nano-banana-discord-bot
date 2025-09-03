#!/usr/bin/env python3
"""
Interactive Environment Setup Script for SlopBot

This script helps configure the .env file by prompting for all required
environment variables from .env.example with helpful instructions.
"""

import os
import re
import shutil
import secrets
from typing import Dict, Tuple, Optional, List
from urllib.parse import urlparse

# Configuration
ENV_EXAMPLE_PATH = ".env.example"
ENV_FILE_PATH = ".env"
BACKUP_SUFFIX = ".backup"

# Categories and their variables with info
VARIABLES = {
    "Discord Bot": [
        {
            "var": "DISCORD_TOKEN",
            "required": True,
            "instruction": "Obtain from Discord Developer Portal (https://discord.com/developers/applications)",
            "validate": lambda x: bool(x.strip())
        },
        {
            "var": "DISCORD_ADMIN_LOG_CHANNEL_ID",
            "required": False,
            "instruction": "Optional: Discord channel ID for audit notifications (right-click channel -> Copy ID)",
            "validate": lambda x: not x or (x.isdigit() and len(x) >= 17 and len(x) <= 20)
        }
    ],
    "API": [
        {
            "var": "OPENROUTER_API_KEY",
            "required": True,
            "instruction": "Your OpenRouter API key for AI model access",
            "validate": lambda x: bool(x.strip())
        },
        {
            "var": "OPENROUTER_BASE_URL",
            "required": False,
            "instruction": "Base URL for OpenRouter API",
            "validate": lambda x: not x or is_valid_url(x),
            "default": "https://openrouter.ai/api/v1"
        },
        {
            "var": "MODEL_ID",
            "required": False,
            "instruction": "AI model identifier",
            "validate": lambda x: not x or bool(x.strip()),
            "default": "google/gemini-2.5-flash-image-preview"
        }
    ],
    "General Config": [
        {
            "var": "LOG_LEVEL",
            "required": False,
            "instruction": "Logging level (DEBUG, INFO, WARNING, ERROR)",
            "validate": lambda x: not x or x.upper() in ["DEBUG", "INFO", "WARNING", "ERROR"],
            "default": "INFO"
        },
        {
            "var": "CACHE_DIR",
            "required": False,
            "instruction": "Directory for caching data",
            "validate": lambda x: not x or bool(x.strip()),
            "default": ".cache"
        },
        {
            "var": "CONCURRENCY",
            "required": False,
            "instruction": "Maximum number of concurrent operations",
            "validate": lambda x: not x or x.isdigit(),
            "default": "2"
        },
        {
            "var": "SETTINGS_FILE",
            "required": False,
            "instruction": "Path to settings file",
            "default": "./data/settings.json"
        },
        {
            "var": "AUDIT_LOG_FILE",
            "required": False,
            "instruction": "Path to audit log file",
            "default": "./data/audit.log"
        },
        {
            "var": "DASHBOARD_HOST",
            "required": False,
            "instruction": "Dashboard bind address",
            "default": "0.0.0.0"
        },
        {
            "var": "DASHBOARD_PORT",
            "required": False,
            "instruction": "Dashboard port",
            "validate": lambda x: not x or (x.isdigit() and 1000 <= int(x) <= 65535),
            "default": "8000"
        }
    ],
    "Image Handling": [
        {
            "var": "ALLOWED_IMAGE_TYPES",
            "required": False,
            "instruction": "Allowed image file types (comma-separated)",
            "default": "png,jpg,jpeg,webp"
        },
        {
            "var": "MAX_IMAGE_MB",
            "required": False,
            "instruction": "Maximum image file size in MB",
            "validate": lambda x: not x or (x.isdigit() and int(x) > 0),
            "default": "10"
        }
    ],
    "Admin Dashboard": [
        {
            "var": "ADMIN_USER_IDS",
            "required": False,
            "instruction": "Discord user IDs for admin access (comma-separated, right-click user -> Copy ID)",
            "validate": lambda x: not x or all(id.strip().isdigit() and len(id.strip()) >= 17 and len(id.strip()) <= 20 for id in x.split(','))
        },
        {
            "var": "ADMIN_SESSION_TTL_SECONDS",
            "required": False,
            "instruction": "Admin session timeout in seconds",
            "validate": lambda x: not x or (x.isdigit() and int(x) > 0),
            "default": "1200"
        },
        {
            "var": "ADMIN_NONCE_TTL_SECONDS",
            "required": False,
            "instruction": "One-time URL lifetime in seconds",
            "default": "300"
        },
        {
            "var": "OAUTH_CLIENT_ID",
            "required": True,
            "instruction": "Discord OAuth2 Application ID (create app at https://discord.com/developers/applications)",
            "validate": lambda x: bool(x.strip())
        },
        {
            "var": "OAUTH_CLIENT_SECRET",
            "required": True,
            "instruction": "Discord OAuth2 Application Secret (from same app)",
            "validate": lambda x: bool(x.strip())
        },
        {
            "var": "OAUTH_REDIRECT_URI",
            "required": False,
            "instruction": "OAuth2 redirect URL after Discord authorization",
            "validate": lambda x: not x or is_valid_url(x),
            "default": "https://yourdomain.com/admin/callback"
        },
        {
            "var": "DASHBOARD_SECRET_KEY",
            "required": True,
            "instruction": "Auto-generated secure key for session management",
            "auto_generate": True,
            "validate": lambda x: bool(x.strip())
        }
    ]
}

def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    parsed = urlparse(url)
    scheme = parsed.scheme
    netloc = parsed.netloc
    return scheme in ("http", "https") and bool(netloc.strip())

def load_existing_env() -> Dict[str, str]:
    """Load existing .env values for pre-filling."""
    env_vals = {}
    if os.path.exists(ENV_FILE_PATH):
        try:
            with open(ENV_FILE_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, val = line.split('=', 1)
                            env_vals[key.strip()] = val.strip()
        except Exception as e:
            print(f"Warning: Could not read existing .env file: {e}")
    return env_vals

def prompt_for_variable(var_info: dict, existing_val: Optional[str] = None) -> str:
    """Prompt user for a variable's value with validation."""
    var = var_info['var']
    required = var_info['required']
    instruction = var_info['instruction']
    validator = var_info.get('validate', lambda x: True)
    default = var_info.get('default', '')
    auto_gen = var_info.get('auto_generate', False)

    if auto_gen:
        value = secrets.token_urlsafe(32)
        return value

    prefill = existing_val if existing_val else default
    required_mark = " (Required)" if required else " (Optional)"

    print(f"\n{var}{required_mark}")
    print(f"Instructions: {instruction}")

    if prefill:
        print(f"Default/Prefill: {prefill}")

    while True:
        try:
            user_input = input(f"Enter value for {var} (or press Enter for default): ").strip()
            value = user_input if user_input else prefill

            if required and not value:
                print("This field is required. Please enter a value.")
                continue

            if validator(value):
                return value
            else:
                print("Invalid input. Please try again.")

        except KeyboardInterrupt:
            print("\nSetup cancelled by user.")
            exit(0)
        except Exception as e:
            print(f"Error: {e}. Please try again.")

def backup_existing_env():
    """Backup existing .env file if it exists."""
    if os.path.exists(ENV_FILE_PATH):
        backup_path = f"{ENV_FILE_PATH}{BACKUP_SUFFIX}"
        shutil.copy2(ENV_FILE_PATH, backup_path)
        print(f"Backed up existing .env to {backup_path}")

def write_env_file(results: Dict[str, str]):
    """Write collected values to .env file."""
    with open(ENV_FILE_PATH, 'w') as f:
        f.write("# .env file generated by setup_env.py\n\n")
        for category, vars_list in VARIABLES.items():
            f.write(f"# {category}\n")
            for var_info in vars_list:
                var = var_info['var']
                if var in results:
                    f.write(f"{var}={results[var]}\n")
            f.write("\n")

def main():
    """Main setup flow."""
    print("=== SlopBot Environment Setup ===\n")
    print("This script will help you configure your .env file step-by-step.\n")

    # Check if .env.example exists
    if not os.path.exists(ENV_EXAMPLE_PATH):
        print(f"Error: {ENV_EXAMPLE_PATH} not found. Please ensure the project is set up correctly.")
        exit(1)

    # Load existing values
    existing_vals = load_existing_env()
    if existing_vals:
        print("Found existing .env file. Values will be pre-filled.")

    # Collect all variables
    results = {}
    total_categories = len(VARIABLES)
    for i, (category, vars_list) in enumerate(VARIABLES.items()):
        print(f"\n[Step {i+1}/{total_categories}] {category}")
        for var_info in vars_list:
            var = var_info['var']
            existing = existing_vals.get(var)
            value = prompt_for_variable(var_info, existing)
            results[var] = value

    # Backup and write
    print("\nGenerating .env file...")
    backup_existing_env()
    write_env_file(results)
    print(f"✅ .env file created successfully!")

    # Next steps summary
    print("\n🚀 Setup complete! Next steps:")
    print("1. Review the generated .env file")
    print("2. Run the bot: python -m src.bot")
    print("3. Access admin dashboard at http://localhost:8000")
    print("\nFor help, refer to README.md or CONFIG.md")

    if results.get('DASHBOARD_SECRET_KEY'):
        print("Note: A secure dashboard secret key has been auto-generated.")

if __name__ == "__main__":
    main()