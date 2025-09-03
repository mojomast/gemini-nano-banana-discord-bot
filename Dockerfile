# Use slim Python 3.11 Alpine base for production
FROM python:3.11-alpine

# Metadata labels for production
LABEL maintainer="your.name@example.com"
LABEL version="0.1.0"
LABEL description="Discord bot for gemini-nano-banana-discord-bot"

# Set working directory
WORKDIR /app

# Copy pyproject.toml for dependency installation
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir .

# Create data directory for persistent storage
RUN mkdir -p /app/data && chmod 755 /app/data

# Copy source code
COPY . .

# Note: .env file is mounted via docker-compose volume, not copied during build for security

# Expose port for health check
EXPOSE 8000

# Run the bot
CMD ["python", "-m", "src.bot"]