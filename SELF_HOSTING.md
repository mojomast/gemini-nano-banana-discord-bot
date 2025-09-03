# Self Hosting Guide

This guide walks you through setting up Slop Bot for local development and self-hosting. Whether you're contributing code or running your own instance, follow these steps to get started.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Discord Application Setup](#discord-application-setup)
- [Local Development Setup](#local-development-setup)
- [Running the Bot](#running-the-bot)
- [Docker Setup](#docker-setup)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before starting, ensure you have:

### System Requirements

- **Python 3.8 or higher** (3.9+ recommended)
- **4GB RAM minimum** (8GB recommended for image processing)
- **2GB free disk space** for model caches and dependencies
- **Stable internet connection** for API calls

### Accounts Required

- Discord account with developer access
- OpenRouter account (https://openrouter.ai/keys)

### Development Tools

```bash
# Package manager
pip (comes with Python)

# Virtual environment tool
venv (comes with Python)
```

## Discord Application Setup

### 1. Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" in the top right
3. Enter your bot name (e.g., "My Slop Bot")
4. Click "Create"

![](/assets/discord_app_create.png)
*Figure 1: Creating a new Discord application*

### 2. Bot Configuration

1. In the application, click "Bot" in the left sidebar
2. Click "Add Bot" -> Confirm
3. Under "Bot" section:
   - Set a username (this is public display name)
   - Upload an avatar if desired
   - Enable "Message Content Intent" (required for commands)
   - Enable "Server Members Intent" (for user management)
   - Enable "Presence Intent" (for bot status)

![](/assets/bot_intents.png)
*Figure 2: Enabling required bot intents*

### 3. Get Bot Token

1. In the "Bot" section, under "Token":
2. Click "Reset Token" -> Copy the new token
3. **IMPORTANT**: Store this token securely - never share it publicly!

### 4. Generate Bot Invite Link

1. Go to "OAuth2" -> "URL Generator" section
2. Select scopes:
   - `bot`
   - `applications.commands`
3. Select bot permissions:
   - Send Messages
   - Attach Files
   - Use Slash Commands
   - Read Message History
   - Add Reactions
4. Copy the generated URL at the bottom

![](/assets/bot_permissions.png)
*Figure 3: Selecting bot permissions for invite*

### 5. Invite Bot to Server

1. Paste the generated URL into your browser
2. Select your Discord server from the dropdown
3. Click "Authorize"
4. Complete the CAPTCHA if prompted

## Local Development Setup

Choose your platform setup below:

### Windows Setup

#### Install Python
```powershell
# Download from python.org
# Or use Chocolatey:
choco install python

# Verify installation
python --version
pip --version
```

#### Clone and Setup Project
```powershell
# Clone repository
git clone https://github.com/your-username/slopbot.git
cd slopbot

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### macOS Setup

#### Install Python
```bash
# Install via Homebrew
brew install python@3.9

# Verify installation
python3 --version
pip3 --version
```

#### Setup Project
```bash
# Clone repository
git clone https://github.com/your-username/slopbot.git
cd slopbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Linux Setup

#### Install Python (Ubuntu/Debian)
```bash
# Update package list
sudo apt update

# Install Python
sudo apt install python3 python3-pip python3-venv

# Verify installation
python3 --version
pip3 --version
```

#### Install Python (Red Hat/CentOS/Fedora)
```bash
# Install Python
sudo dnf install python3 python3-pip python3-venv

# Or for Red Hat/CentOS:
sudo yum install python3 python3-pip
```

#### Setup Project
```bash
# Clone repository
git clone https://github.com/your-username/slopbot.git
cd slopbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Optional Setup Steps

#### Install Development Dependencies
```bash
# Install development requirements
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

#### Configure Environment Variables
```bash
# Copy environment template
cp .env.example .env

# Edit with your tokens
# DISCORD_TOKEN=your_bot_token_here
# OPENROUTER_API_KEY=your_openrouter_key_here
```

See [CONFIG.md](CONFIG.md) for detailed environment variable documentation.

## Running the Bot

### 1. Basic Local Run

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Run the bot
python -m src.bot
```

### 2. Development Mode

```bash
# Run with debug logging
PYTHONPATH=src python -m bot --debug
```

### 3. Test Commands

Once running, the bot will appear online in your Discord server. Test with:

```
/help
```

Expected output: Bot responds with available commands.

```
/imagine prompt:test image
```

Expected output: Bot generates and posts an image.

### 4. Monitoring Logs

The bot outputs logs to console. Redirect to file for monitoring:

```bash
python -m src.bot > bot.log 2>&1 &
```

Check logs:
```bash
tail -f bot.log
```

## Docker Setup

### Prerequisites

- [Docker](https://docker.com) installed
- [Docker Compose](https://docs.docker.com/compose/) installed

### Quick Docker Run

```bash
# Clone repository
git clone https://github.com/your-username/slopbot.git
cd slopbot

# Copy example environment file
cp .env.example .env

# Edit .env with your tokens
nano .env  # or your preferred editor

# Build and run
docker-compose up --build
```

### Development with Docker

```bash
# Build development image
docker build -t slopbot:dev -f Dockerfile.dev .

# Run with volume mounting for live reload
docker run -v $(pwd):/app slopbot:dev
```

### Production Docker Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production Docker setups.

## Troubleshooting

### Common Issues

#### Bot Not Starting

**Error**: `ModuleNotFoundError: No module named 'discord'`

**Solution**:
```bash
pip install -r requirements.txt
```

#### Discord API Error

**Error**: `Bot token is invalid`

**Solution**:
1. Check your `.env` file for correct token
2. Reset token in Discord Developer Portal if needed
3. Ensure no extra spaces or quotes in token

#### Command Not Appearing

**Problem**: Slash commands not showing in Discord

**Solution**:
1. Ensure bot has `applications.commands` scope
2. Wait up to 1 hour for Discord to sync commands
3. Re-invite bot or reset application commands

#### Image Generation Failed

**Error**: `OpenRouter API key invalid`

**Solution**:
1. Check OpenRouter API key is correct
2. Verify account has credits/quota
3. Check network connectivity to OpenRouter

### Logging and Debugging

#### Enable Debug Logging

```bash
# Set environment variable
export BOT_LOG_LEVEL=DEBUG
python -m src.bot
```

#### View Logs

```bash
# View recent logs (10 lines)
tail -n 10 bot.log

# Monitor logs in real-time
tail -f bot.log
```

#### Log Levels
- `ERROR`: Only errors and critical issues
- `WARNING`: Warnings and errors
- `INFO`: General information and status
- `DEBUG`: Detailed debugging information

### Performance Issues

#### High Memory Usage
- Reduce concurrent requests in config
- Clear image cache periodically
- Use Docker limits: `docker run --memory=2g slopbot`

#### Slow Response Times
- Check internet speed
- Use faster models (specify in config)
- Add caching layer for repeated requests

### Network Issues

#### Firewall Blocking
- Allow outbound HTTPS (port 443) to Discord API
- Allow outbound HTTPS to OpenRouter API
- Check corporate proxy settings

#### DNS Resolution
```bash
# Test connectivity
ping discord.com
ping openrouter.ai
```

## Next Steps

- Configure advanced features in [CONFIG.md](CONFIG.md)
- Set up production deployment in [DEPLOYMENT.md](DEPLOYMENT.md)
- Review security best practices in [SECURITY.md](SECURITY.md)
- Contribute back with [CONTRIBUTING.md](CONTRIBUTING.md)

## Support

Join our Discord server for setup assistance or create GitHub issues for bugs.

Happy slopping! 🎨🤖

[⬆ Back to top](#self-hosting-guide)