# Configuration Guide

This comprehensive guide explains all configuration options for Slop Bot, including environment variables and runtime settings.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Bot Configuration](#bot-configuration)
- [Rate Limiting](#rate-limiting)
- [Image Processing Settings](#image-processing-settings)
- [Cache Configuration](#cache-configuration)
- [Security Settings](#security-settings)
- [Logging Configuration](#logging-configuration)
- [Advanced Options](#advanced-options)

## Environment Variables

Slop Bot is configured primarily through environment variables. Copy `.env.example` to `.env` and modify as needed.

### Required Variables

#### `DISCORD_TOKEN` *(Required)*
Your Discord Bot Token from the Developer Portal.

**Format**: String (64+ characters)
**Default**: None
**Required**: Yes

```bash
DISCORD_TOKEN=NjQwXXXXXXXXXXXXXX.bot_token_string_using_numbers_and_letters
```

**Where to get it**:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Navigate to "Bot" section
4. Click "Reset Token" if needed
5. Copy the token

#### `OPENROUTER_API_KEY` *(Required)*
Your OpenRouter API Key for AI model access.

**Format**: String (64+ characters starting with `sk-or-`)
**Default**: None
**Required**: Yes

```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxx
```

**Where to get it**:
1. Sign up at [OpenRouter.ai](https://openrouter.ai/keys)
2. Click "Create API Key"
3. Copy the generated key

### API Configuration

#### `OPENROUTER_BASE_URL`
Base URL for OpenRouter API endpoints.

**Format**: URL
**Default**: `https://openrouter.ai/api/v1`
**Required**: No (use default)

```bash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Only change this if OpenRouter provides alternative endpoints.

#### `MODEL_ID`
Default AI model for image generation.

**Format**: String (provider/model-name)
**Default**: `google/gemini-2.5-flash-image-preview`
**Options**:
- `google/gemini-2.5-flash-image-preview` (recommended)
- `openai/gpt-4o` (high quality)
- `anthropic/claude-3-haiku` (fast)
- `meta/llama-vision-free` (experimental)

```bash
MODEL_ID=google/gemini-2.5-flash-image-preview
```

### Bot Configuration

#### `LOG_LEVEL`
Determines how much information is logged.

**Format**: String
**Default**: `INFO`
**Options**:
- `DEBUG`: Everything including raw API responses (for development)
- `INFO`: General operational information
- `WARNING`: Only warnings and errors
- `ERROR`: Only errors and critical issues

```bash
LOG_LEVEL=INFO
```

Log levels are hierarchical - setting INFO shows INFO, WARNING, and ERROR messages.

### Resource Configuration

#### `CONCURRENCY`
Maximum number of concurrent operations the bot can handle.

**Format**: Integer
**Default**: `2`
**Range**: 1-10

```bash
CONCURRENCY=2
```

Higher values increase throughput but consume more memory. Start low and increase based on your hardware.

#### `MAX_IMAGE_MB`
Maximum file size for uploaded images in megabytes.

**Format**: Float
**Default**: `10.0`
**Range**: 1.0-50.0

```bash
MAX_IMAGE_MB=10.0
```

This limit applies to all image inputs (uploads and URLs). Discord limits file attachments to 8MB, so total cannot exceed that.

#### `ALLOWED_IMAGE_TYPES`
Comma-separated list of permitted image file extensions.

**Format**: String (comma-separated extensions)
**Default**: `png,jpg,jpeg,webp`
**Options**: `png,jpg,jpeg,webp,gif,bmp,tiff`

```bash
ALLOWED_IMAGE_TYPES=png,jpg,jpeg,webp,gif
```

Only files with these extensions will be processed. Extensions are case-insensitive.

## Rate Limiting

### User Rate Limits

Control how many commands users can execute:

#### `USER_RATE_LIMIT_PER_MINUTE`
Commands per minute per user.

**Format**: Integer
**Default**: `5`
**Range**: 1-60

```bash
USER_RATE_LIMIT_PER_MINUTE=5
```

#### `USER_RATE_LIMIT_PER_HOUR`
Commands per hour per user.

**Format**: Integer
**Default**: `50`
**Range**: 1-500

```bash
USER_RATE_LIMIT_PER_HOUR=50
```

### Server Rate Limits

Per-server limits to prevent abuse:

#### `SERVER_RATE_LIMIT_PER_MINUTE`
Commands per minute per Discord server.

**Format**: Integer
**Default**: `30`
**Range**: 5-200

```bash
SERVER_RATE_LIMIT_PER_MINUTE=30
```

### Burst Handling

#### `BURST_LIMIT`
Number of commands allowed in a short burst period.

**Format**: Integer
**Default**: `10`
**Range**: 2-50

```bash
BURST_LIMIT=10
```

#### `BURST_WINDOW_SECONDS`
Time window for burst calculations in seconds.

**Format**: Integer
**Default**: `60`
**Range**: 30-300

```bash
BURST_WINDOW_SECONDS=60
```

## Image Processing Settings

### Resolution Limits

#### `MAX_IMAGE_WIDTH`
Maximum image width in pixels.

**Format**: Integer
**Default**: `2048`
**Range**: 512-4096

```bash
MAX_IMAGE_WIDTH=2048
```

#### `MAX_IMAGE_HEIGHT`
Maximum image height in pixels.

**Format**: Integer
**Default**: `2048`
**Range**: 512-4096

```bash
MAX_IMAGE_HEIGHT=2048
```

Images larger than these limits will be scaled down automatically.

### Quality Settings

#### `DEFAULT_QUALITY`
Default image processing quality setting.

**Format**: Integer
**Default**: `8`
**Range**: 1-10

```bash
DEFAULT_QUALITY=8
```

Higher values produce better quality but take longer to process.

### Feature Flags

#### `ENABLE_UPSCALE`
Allow image upscaling beyond original resolution.

**Format**: Boolean (true/false)
**Default**: `true`

```bash
ENABLE_UPSCALE=true
```

#### `ENABLE_DOWNSCALE`
Allow automatic downscaling of oversized images.

**Format**: Boolean (true/false)
**Default**: `true`

```bash
ENABLE_DOWNSCALE=true
```

## Cache Configuration

### Disk Cache

Slop Bot caches generated images and API responses to improve performance.

#### `CACHE_DIR`
Directory where cache files are stored.

**Format**: String (path)
**Default**: `.cache`
**Format requirement**: Relative to project root

```bash
CACHE_DIR=.cache
```

#### `CACHE_MAX_SIZE_MB`
Maximum cache size in megabytes.

**Format**: Integer
**Default**: `500`
**Range**: 100-5000

```bash
CACHE_MAX_SIZE_MB=500
```

When cache exceeds this size, oldest files are automatically removed.

#### `CACHE_TTL_HOURS`
How long cached files are considered valid (time-to-live).

**Format**: Integer
**Default**: `24`
**Range**: 1-168 (7 days max)

```bash
CACHE_TTL_HOURS=24
```

Cached files older than this are automatically deleted.

### Cache Behavior

#### `CACHE_ENABLED`
Enable/disable all caching.

**Format**: Boolean (true/false)
**Default**: `true`

```bash
CACHE_ENABLED=true
```

When disabled, no files are cached but generation may be slower.

#### `CACHE_SAVE_GENERATED`
Save all generated images to cache directory.

**Format**: Boolean (true/false)
**Default**: `true`

```bash
CACHE_SAVE_GENERATED=true
```

Useful for reviewing what images were generated recently.

## Security Settings

### Access Control

#### `WHITELISTED_SERVERS`
Comma-separated list of Discord server IDs that can use the bot.

**Format**: String (comma-separated integers)
**Default**: Empty (all servers allowed)
**Example**: `123456789012345678,987654321098765432`

```bash
WHITELISTED_SERVERS=123456789012345678
```

If set, only these servers can use bot commands. Leave empty to allow all servers.

#### `BLACKLISTED_USERS`
Users banned from using the bot.

**Format**: String (comma-separated Discord user IDs)
**Default**: Empty (no users banned)

```bash
BLACKLISTED_USERS=123456789012345678,987654321098765432
```

### Content Moderation

#### `ENABLE_CONTENT_FILTER`
Enable automatic content filtering for harmful content.

**Format**: Boolean (true/false)
**Default**: `true`

```bash
ENABLE_CONTENT_FILTER=true
```

When enabled, prompts and generated content are checked against moderation models.

#### `CONTENT_FILTER_SEVERITY`
Sensitivity level for content filtering.

**Format**: String
**Default**: `medium`
**Options**: `low`, `medium`, `high`, `strict`

```bash
CONTENT_FILTER_SEVERITY=medium
```

Higher settings filter more content but may block creative prompts.

## Logging Configuration

### Log Output

#### `LOG_FORMAT`
Format for log messages.

**Format**: String
**Default**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

```bash
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

#### `LOG_DATE_FORMAT`
Date/time format in log messages.

**Format**: String
**Default**: `%Y-%m-%d %H:%M:%S`

```bash
LOG_DATE_FORMAT=%Y-%m-%d %H:%M:%S
```

### Log File Settings

#### `LOG_FILE`
Path to log file (relative to project root).

**Format**: String
**Default**: `bot.log`

```bash
LOG_FILE=bot.log
```

#### `LOG_MAX_SIZE_MB`
Maximum log file size before rotation.

**Format**: Integer
**Default**: `10`
**Range**: 1-100

```bash
LOG_MAX_SIZE_MB=10
```

#### `LOG_BACKUP_COUNT`
Number of backup log files to keep.

**Format**: Integer
**Default**: `5`
**Range**: 1-50

```bash
LOG_BACKUP_COUNT=5
```

## Advanced Options

### Performance Tuning

#### `WORKER_THREADS`
Number of background worker threads.

**Format**: Integer
**Default**: `2`
**Range**: 1-8

```bash
WORKER_THREADS=2
```

Higher values may improve concurrency but increase memory usage.

#### `API_TIMEOUT_SECONDS`
Timeout for API requests in seconds.

**Format**: Integer
**Default**: `30`
**Range**: 10-120

```bash
API_TIMEOUT_SECONDS=30
```

Requests taking longer than this are cancelled.

### Experimental Features

#### `ENABLE_BETA_FEATURES`
Enable experimental/beta bot features.

**Format**: Boolean (true/false)
**Default**: `false`

```bash
ENABLE_BETA_FEATURES=false
```

Beta features may be unstable and change without notice.

#### `CUSTOM_MODEL_ENDPOINT`
Override the model endpoint URL.

**Format**: String (full URL)
**Default**: Empty (use default)
**Advanced**: Only change if you know what you're doing

```bash
CUSTOM_MODEL_ENDPOINT=https://custom-endpoint.com/v1/models
```

## Configuration Examples

### Development Setup
```bash
DISCORD_TOKEN=your_dev_token
OPENROUTER_API_KEY=your_test_key
LOG_LEVEL=DEBUG
CONCURRENCY=1
CACHE_ENABLED=true
```

### Production Setup
```bash
DISCORD_TOKEN=your_prod_token
OPENROUTER_API_KEY=your_prod_key
LOG_LEVEL=INFO
CONCURRENCY=5
CACHE_MAX_SIZE_MB=1000
LOG_MAX_SIZE_MB=50
```

### High-Traffic Setup
```bash
CONCURRENCY=10
USER_RATE_LIMIT_PER_MINUTE=3
SERVER_RATE_LIMIT_PER_MINUTE=100
BURST_LIMIT=20
CACHE_MAX_SIZE_MB=2000
WORKER_THREADS=8
```

## Environment File Structure

Your `.env` file should look like this:

```bash
# API Keys (Required)
DISCORD_TOKEN=NjQwXXXXXXXXXXXXXX...
OPENROUTER_API_KEY=sk-or-v1-xxxxx...

# API Settings
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MODEL_ID=google/gemini-2.5-flash-image-preview

# Logging
LOG_LEVEL=INFO

# Caching
CACHE_DIR=.cache
CACHE_MAX_SIZE_MB=500
CACHE_TTL_HOURS=24

# Image Constraints
ALLOWED_IMAGE_TYPES=png,jpg,jpeg,webp
MAX_IMAGE_MB=10
CONCURRENCY=3

# Rate Limits
USER_RATE_LIMIT_PER_MINUTE=5
SERVER_RATE_LIMIT_PER_MINUTE=30
```

## Validation

Slop Bot validates configuration on startup. If any required variables are missing or invalid, the bot will refuse to start and log detailed error messages.

**Validation rules**:
- All required variables must be present and non-empty
- `DISCORD_TOKEN` must be 64+ characters
- `OPENROUTER_API_KEY` must start with `sk-or-`
- Numeric values must be within specified ranges
- Paths in `CACHE_DIR` must be writable

## Troubleshooting Configuration

### Bot Won't Start
1. Check for missing required environment variables
2. Verify `DISCORD_TOKEN` is correct
3. Ensure `OPENROUTER_API_KEY` is valid

### Rate Limits Too Restrictive
Increase `USER_RATE_LIMIT_PER_MINUTE` or `SERVER_RATE_LIMIT_PER_MINUTE`

### Images Not Processing
Check `ALLOWED_IMAGE_TYPES` includes your file types
Check `MAX_IMAGE_MB` is large enough

### Out of Disk Space
Reduce `CACHE_MAX_SIZE_MB`
Enable log rotation in `LOG_MAX_SIZE_MB`

---

See also: [ENVIRONMENT.md](ENVIRONMENT.md) for development-specific configuration.

[⬆ Back to top](#configuration-guide)