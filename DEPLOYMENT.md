# Deployment Guide

This guide covers production deployment strategies for Slop Bot, including Docker, systemd services, and reverse proxy configurations.

## Table of Contents

- [Quick Deployment](#quick-deployment)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Systemd Service](#systemd-service)
- [Reverse Proxy Setup](#reverse-proxy-setup)
- [Persistent Cache Configuration](#persistent-cache-configuration)
- [Updating Deployments](#updating-deployments)
- [Monitoring and Health Checks](#monitoring-and-health-checks)
- [Troubleshooting](#troubleshooting)

## Quick Deployment

For the fastest deployment, use Docker Compose:

```bash
# Clone repository
git clone https://github.com/mojomast/gemini-nano-banana-discord-bot.git
cd gemini-nano-banana-discord-bot

# Create environment file
cp .env.example .env
# Edit .env with your API keys

# Deploy
docker-compose up -d --build

# Monitor logs
docker-compose logs -f gemini-nano-banana-discord-bot
```

## Docker Compose Deployment

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 1.29+
- 4GB free RAM
- 5GB free disk space

### Production Docker Compose Configuration

Create or modify `docker-compose.yml`:

```yaml
version: '3.8'

services:
  gemini-nano-banana-discord-bot:
    build: .
    container_name: slopbot
    restart: unless-stopped
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - LOG_LEVEL=INFO
    volumes:
      - ./cache:/app/cache:rw
      - ./logs:/app/logs:rw
    networks:
      - slopbot-net
    healthcheck:
      test: ["CMD", "python", "-c", "import discord; print('Bot client available')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Optional: Redis cache backend
  redis:
    image: redis:7-alpine
    container_name: slopbot-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - slopbot-net
    command: redis-server --appendonly yes

volumes:
  redis_data:

networks:
  slopbot-net:
    driver: bridge
```

### Environment File Setup

Create `.env` file in the project root:

```bash
# API Credentials
DISCORD_TOKEN=your_bot_token_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Production Settings
LOG_LEVEL=INFO
CACHE_DIR=/app/cache
LOG_FILE=/app/logs/bot.log

# Performance
CONCURRENCY=5
WORKER_THREADS=4

# Rate Limits
USER_RATE_LIMIT_PER_MINUTE=3
SERVER_RATE_LIMIT_PER_MINUTE=20
BURST_LIMIT=15

# Security
CONTENT_FILTER_SEVERITY=medium
ENABLE_CONTENT_FILTER=true
```

### Deployment Steps

1. **Prepare the environment:**
   ```bash
   cp docker-compose.yml docker-compose.prod.yml
   mkdir -p cache logs
   ```

2. **Create environment file:**
   ```bash
   nano .env
   # Add your API keys and configuration
   ```

3. **Build and deploy:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d --build
   ```

4. **Verify deployment:**
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   docker-compose -f docker-compose.prod.yml logs slopbot
   ```

## Systemd Service

For direct Linux system daemon deployment:

### Prerequisites

- Ubuntu/Debian/CentOS/RHEL
- Python 3.8+
- System privileges

### Installation Steps

1. **Clone and setup:**
   ```bash
   cd /opt
  git clone https://github.com/mojomast/gemini-nano-banana-discord-bot.git
  cd gemini-nano-banana-discord-bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Create dedicated user:**
   ```bash
   useradd -r -s /bin/false slopbot
   chown -R slopbot:slopbot /opt/slopbot
   mkdir -p /var/log/slopbot /var/cache/slopbot
   chown slopbot:slopbot /var/log/slopbot /var/cache/slopbot
   ```

3. **Create systemd service file:**
   ```bash
   sudo nano /etc/systemd/system/slopbot.service
   ```

   Add the following content:

   ```ini
   [Unit]
   Description=Slop Bot Discord Service
   After=network.target
   Wants=network.target

   [Service]
   Type=simple
   User=slopbot
   Group=slopbot
   WorkingDirectory=/opt/slopbot
   EnvironmentFile=/opt/slopbot/.env
   ExecStart=/opt/slopbot/venv/bin/python -m src.bot
   ExecReload=/bin/kill -HUP $MAINPID

   # Restart policy
   Restart=always
   RestartSec=10

   # Resource limits
   MemoryLimit=2G
   CPUWeight=50

   # Logging
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

4. **Configure environment:**
   ```bash
   sudo nano /opt/slopbot/.env

   # Add your configuration
   DISCORD_TOKEN=your_token
   OPENROUTER_API_KEY=your_key
   CACHE_DIR=/var/cache/slopbot
   LOG_FILE=/var/log/slopbot/bot.log
   LOG_LEVEL=INFO
   ```

5. **Enable and start service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable slopbot
   sudo systemctl start slopbot
   ```

6. **Monitor service:**
   ```bash
   sudo systemctl status slopbot
   sudo journalctl -u slopbot -f
   ```

### Systemd Management Commands

```bash
# View status
sudo systemctl status slopbot

# View logs
sudo journalctl -u slopbot -n 100

# Restart service
sudo systemctl restart slopbot

# Stop service
sudo systemctl stop slopbot

# Reload configuration (if supported)
sudo systemctl reload slopbot
```

## Reverse Proxy Setup

### Nginx Configuration

For web-facing deployments or load balancing:

#### Prerequisites

- Nginx installed
- SSL certificate (Let's Encrypt recommended)

#### Configuration File

Create `/etc/nginx/sites-available/slopbot`:

```nginx
# Upstream backend servers
upstream slopbot_backend {
    server localhost:8000;  # If bot has web interface
    keepalive 32;
}

# Main server block
server {
    listen 80;
    server_name slopbot.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

# HTTPS server block
server {
    listen 443 ssl http2;
    server_name slopbot.yourdomain.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/slopbot.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/slopbot.yourdomain.com/privkey.pem;

    # SSL security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!SRP:!CAMELLIA;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/javascript application/xml+rss;

    # Cache static files
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Proxy to bot (if web interface)
    location /api/ {
        proxy_pass http://slopbot_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Rate limiting
        limit_req zone=api burst=10 nodelay;
    }

    # Default response
    location / {
        return 200 "Slop Bot is running\n";
        add_header Content-Type text/plain;
    }
}

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=general:10m rate=5r/s;
```

#### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/slopbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Apache Configuration

Alternative Apache reverse proxy setup:

```apache
<VirtualHost *:80>
    ServerName slopbot.yourdomain.com
    Redirect permanent / https://slopbot.yourdomain.com/
</VirtualHost>

<VirtualHost *:443>
    ServerName slopbot.yourdomain.com

    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/slopbot.crt
    SSLCertificateKeyFile /etc/ssl/private/slopbot.key

    ProxyPreserveHost On
    ProxyPass /api/ http://localhost:8000/
    ProxyPassReverse /api/ http://localhost:8000/

    ErrorLog ${APACHE_LOG_DIR}/slopbot_error.log
    CustomLog ${APACHE_LOG_DIR}/slopbot_access.log combined
</VirtualHost>
```

### SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d slopbot.yourdomain.com
```

## Persistent Cache Configuration

### Docker Cache Persistence

For Docker deployments, ensure cache persists across container restarts:

```yaml
# In docker-compose.yml
services:
  slopbot:
    volumes:
      - ./cache:/app/cache:rw
      - ./logs:/app/logs:rw
      # External volume for persistence
      - cache_data:/app/external-cache

volumes:
  cache_data:
    driver: local
    driver_opts:
      type: none
      device: /opt/slopbot/cache
      o: bind
```

### Systemd Cache Management

For systemd deployments:

```bash
# Create cache directory
sudo mkdir -p /var/cache/slopbot
sudo chown slopbot:slopbot /var/cache/slopbot

# Configure in .env
CACHE_DIR=/var/cache/slopbot
CACHE_MAX_SIZE_MB=2048
CACHE_TTL_HOURS=168  # 7 days
```

### Cache Backup Strategy

1. **Automated backup script:**
   ```bash
   #!/bin/bash
   # /opt/slopbot/backup-cache.sh

   DATE=$(date +%Y%m%d_%H%M%S)
   tar -czf /opt/slopbot/backups/cache_$DATE.tar.gz -C /var/cache/slopbot .
   ```

2. **Cron job for daily backups:**
   ```bash
   sudo crontab -e
   # Add: 0 2 * * * /opt/slopbot/backup-cache.sh
   ```

3. **Cleanup old backups:**
   ```bash
   find /opt/slopbot/backups -name "cache_*.tar.gz" -mtime +30 -delete
   ```

## Updating Deployments

### Docker Compose Updates

```bash
# Pull latest changes
git pull origin main

# Stop current instance
docker-compose down

# Build new image
docker-compose build --no-cache

# Start updated instance
docker-compose up -d

# Verify update
docker-compose logs | tail -n 20
```

### Systemd Updates

```bash
# Stop service
sudo systemctl stop slopbot

# Backup current installation
sudo cp -r /opt/slopbot /opt/slopbot.backup.$(date +%s)

# Update code
cd /opt/slopbot
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Start service
sudo systemctl start slopbot
```

### Zero-Downtime Updates

1. **Blue-green deployment pattern:**
   ```bash
   # Create new compose file
   cp docker-compose.yml docker-compose.green.yml

   # Update configuration
   docker-compose -f docker-compose.green.yml up -d

   # Wait for health check
   sleep 30

   # Switch traffic (if using load balancer)
   # Update reverse proxy to point to new container

   # Stop old instance
   docker-compose down
   ```

### Rollback Strategy

```bash
# Quick rollback for Docker
docker-compose down
git reset --hard HEAD~1
docker-compose up -d --build

# Rollback for systemd
sudo systemctl stop slopbot
cd /opt/slopbot
git reset --hard HEAD~1
sudo systemctl start slopbot
```

## Monitoring and Health Checks

### Docker Health Checks

```yaml
# In docker-compose.yml
services:
  slopbot:
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import discord; discord.Client().login(\"test\")' > /dev/null 2>&1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Systemd Monitoring

```bash
# Monitor service status
sudo systemctl status slopbot

# Monitor resource usage
sudo systemd-cgtop

# View process information
ps aux | grep slopbot
```

### Log Aggregation

```bash
# Docker logs
docker-compose logs -f --tail=100

# Systemd logs
sudo journalctl -u slopbot -f

# System monitoring
tail -f /var/log/slopbot/bot.log
```

## Troubleshooting

### Common Deployment Issues

#### Docker Container Won't Start

**Error:** `Container exits immediately`

**Solution:**
```bash
# Check container logs
docker-compose logs slopbot

# Check environment variables
docker-compose exec slopbot env

# Verify file permissions
docker-compose exec slopbot ls -la /app
```

#### Systemd Service Fails

**Error:** `Service enters failed state`

**Solution:**
```bash
# View service status
sudo systemctl status slopbot

# View detailed logs
sudo journalctl -u slopbot -n 50

# Check service file syntax
sudo systemd-analyze verify slopbot.service

# Test manual execution
sudo -u slopbot /opt/slopbot/venv/bin/python -m src.bot
```

#### Permission Denied

**Error:** `Permission denied when writing cache`

**Solution:**
```bash
# Check directory permissions
ls -la /var/cache/slopbot

# Fix ownership
sudo chown -R slopbot:slopbot /var/cache/slopbot

# Check SELinux/AppArmor (if applicable)
sudo ausearch -m avc -ts recent | grep slopbot
```

#### High Resource Usage

**Symptoms:** High CPU/Memory usage

**Solution:**
```bash
# Monitor resource usage
docker stats  # For Docker
sudo htop     # For systemd

# Reduce concurrency in config
CONCURRENCY=2
WORKER_THREADS=2

# Enable resource limits
memory_limit: 2G
cpu_quota: 50000
```

#### Network Connectivity Issues

**Error:** `Connection timeout to Discord/OpenRouter`

**Solution:**
```bash
# Check network connectivity
curl -I https://discord.com/api/v10
curl -I https://openrouter.ai/api/v1

# Test DNS resolution
nslookup discord.com
nslookup openrouter.ai

# Check firewall rules
sudo ufw status
sudo iptables -L
```

### Performance Tuning

#### Optimize Docker Settings

```yaml
# Advanced docker-compose.yml
services:
  slopbot:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:noexec,nodev,nosuid,size=100m
      - /var/run:noexec,nodev,nosuid,size=10m
```

#### Systemd Resource Control

```ini
# Enhanced systemd service
[Service]
MemoryLimit=2G
MemoryHigh=1.5G
CPUQuota=50%
TasksMax=100
```

### Backup and Recovery

```bash
# Complete backup script
#!/bin/bash
# /opt/slopbot/full-backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/slopbot/backups/$DATE"

mkdir -p "$BACKUP_DIR"

# Backup source code
cp -r /opt/slopbot "$BACKUP_DIR/src"

# Backup configuration
cp /opt/slopbot/.env "$BACKUP_DIR/"

# Backup cache (if needed)
cp -r /var/cache/slopbot "$BACKUP_DIR/cache"

# Backup logs
cp -r /var/log/slopbot "$BACKUP_DIR/logs"

# Create archive
tar -czf "/opt/slopbot/backups/full_$DATE.tar.gz" -C "$BACKUP_DIR" .

# Cleanup
rm -rf "$BACKUP_DIR"
```

---

For local development setup, see [SELF_HOSTING.md](SELF_HOSTING.md).

[⬆ Back to top](#deployment-guide)