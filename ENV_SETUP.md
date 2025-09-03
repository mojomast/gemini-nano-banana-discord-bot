# Environment Setup Guide

This guide provides detailed instructions for configuring the Slop Bot environment variables for Docker deployment.

## Overview

Slop Bot is a Discord bot that provides AI-powered image generation, editing, and blending capabilities using OpenRouter's API. For the bot to function properly, you need to obtain API keys from Discord and OpenRouter.

## Required Environment Variables

### 1. DISCORD_TOKEN

- **Required**: Yes
- **Description**: Authentication token for your Discord bot
- **Example**: `BOT_TOKEN_YOUR_TOKEN_HERE`
- **Setup**: See "Discord Bot Setup Steps" section below

### 2. OPENROUTER_API_KEY

- **Required**: Yes
- **Description**: API key for OpenRouter service to access AI models
- **Example**: `sk-or-v1-your-key-here`
- **Setup**: See "OpenRouter API Setup Steps" section below

## Optional Environment Variables

### OpenRouter Settings
- **OPENROUTER_BASE_URL** (default: https://openrouter.ai/api/v1)
  - API base URL for OpenRouter
- **MODEL_ID** (default: google/gemini-2.5-flash-image-preview)
  - Default AI model to use for image generation
- **LOG_LEVEL** (default: INFO, options: DEBUG, INFO, WARNING, ERROR)
  - Logging verbosity level
- **MAX_RETRIES** (default: 3)
  - Number of retry attempts for API calls
- **TIMEOUT** (default: 60)
  - Timeout in seconds for API requests

### Storage Settings
- **CACHE_DIR** (default: .cache)
  - Directory path for local file caching
- **RETENTION_HOURS** (default: 1.0)
  - Hours to retain cache files

### Image Settings
- **ALLOWED_IMAGE_TYPES** (default: png,jpg,jpeg,webp)
  - Comma-separated list of permitted image file extensions
- **MAX_IMAGE_MB** (default: 10.0)
  - Maximum file size in MB for uploaded images

## Complete .env Template

Copy this complete template to your .env file:

```bash
# =============================================================================
# Slop Bot Environment Configuration
# =============================================================================

# ============================================
# REQUIRED: Discord Bot Token
# ============================================
# Get from: https://discord.com/developers/applications
# Steps: Create app -> Bot -> Add Bot -> Reset Token -> Copy
DISCORD_TOKEN=your_discord_bot_token_here

# ============================================
# REQUIRED: OpenRouter API Key
# ============================================
# Get from: https://openrouter.ai/keys
# Sign up and create an API key
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key_here

# ============================================
# OpenRouter Configuration
# ============================================
# API base URL (default recommended)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Default AI model for image generation
MODEL_ID=google/gemini-2.5-flash-image-preview

# Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# API retry configuration
MAX_RETRIES=3
TIMEOUT=60

# ============================================
# Storage & Cache Configuration
# ============================================
# Directory for caching generated images
CACHE_DIR=.cache

# Cache retention time in hours
RETENTION_HOURS=1.0

# ============================================
# Image Processing Configuration
# ============================================
# Allowed image file types (comma-separated)
ALLOWED_IMAGE_TYPES=png,jpg,jpeg,webp

# Maximum image file size in MB
MAX_IMAGE_MB=10.0
```

## Discord Bot Setup Steps

1. **Create Discord Application**:
   - Visit https://discord.com/developers/applications
   - Click "New Application"
   - Enter a name for your bot
   - Go to "Bot" section and click "Add Bot"

2. **Configure Bot Permissions**:
   - In Bot section, under "Privileged Gateway Intents", enable:
     - Message Content Intent (required for command processing)
     - Server Members Intent (optional, for server management)
     - Presence Intent (optional, for bot status monitoring)

3. **Generate Invite Link**:
   - Go to OAuth2 -> URL Generator
   - Select scopes: `bot` and `applications.commands`
   - Select permissions:
     - Send Messages (required to respond to commands)
     - Attach Files (required to upload generated images)
     - Use Slash Commands (required for actual command usage)
     - Read Message History (required to process command interactions)
     - Add Reactions (recommended for user feedback)
   - Use the generated URL to invite bot to your server

4. **Copy Token**:
   - In Bot section, reset and copy the token
   - Paste into `DISCORD_TOKEN` in .env

**Note**: The bot does NOT require Administrator permissions for normal operation. These standard permissions are sufficient for Slop Bot to function properly in servers.

## OpenRouter API Setup Steps

1. **Sign Up**:
   - Visit [OpenRouter](https://openrouter.ai/)
   - Create an account if you don't have one

2. **Get API Key**:
   - Go to [Keys Page](https://openrouter.ai/keys)
   - Create a new API key
   - Copy the key
   - Paste into `OPENROUTER_API_KEY` in .env

## Docker Deployment

With your .env file configured:

```bash
# Build and start the bot
docker-compose up --build -d

# Check logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

## Local Deployment

For development without Docker:

```bash
# Create virtual environment
python -m venv venv

# Activate venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run the bot
python -m src.bot
```

## Troubleshooting

### Bot Not Starting
- Check DISCORD_TOKEN is correct
- Verify bot permissions in Discord server
- Ensure OpenRouter API key is valid

### Commands Not Appearing
- Bot needs `applications.commands` scope
- May take up to 1 hour to sync in Discord
- Try re-inviting the bot

### API Errors
- Verify OpenRouter API key
- Check account has credits/quota
- Test internet connectivity

For detailed troubleshooting, see DEPLOYMENT.md and SELF_HOSTING.md