# Security

This document outlines security best practices for Slop Bot, including secrets handling, access controls, content policies, and privacy considerations.

## Table of Contents

- [Secret Handling](#secret-handling)
- [Principle of Least Privilege](#principle-of-least-privilege)
- [Safe Prompting and Input Validation](#safe-prompting-and-input-validation)
- [Content Policy and Moderation](#content-policy-and-moderation)
- [Privacy Protections](#privacy-protections)
- [Image Security](#image-security)
- [Network Security](#network-security)
- [Security Audits](#security-audits)
- [Incident Response](#incident-response)
- [Vulnerability Disclosure](#vulnerability-disclosure)

## Secret Handling

### Environment Variables Management

#### Secure Storage Practices

1. **Never commit secrets to version control:**
   ```bash
   # Bad practice - DO NOT DO THIS
   echo "DISCORD_TOKEN=your_token" >> .env

   # Good practice
   echo "DISCORD_TOKEN=" >> .env
   echo "# Add your Discord token above" >> .env
   ```

2. **Use secure environment file permissions:**
   ```bash
   # Set restrictive permissions
   chmod 600 .env

   # Make sure owner is the bot user
   chown slopbot:slopbot .env
   ```

3. **Environment file location:**
   - Development: Project root (`.env`)
   - Production: System-protected location (`/etc/slopbot/.env`)
   - Docker: Passed as environment variables or external secrets

#### Secret Rotation

1. **Regular token rotation:**
   ```bash
   # Rotate Discord token
   # 1. Generate new token in Developer Portal
   # 2. Update .env file
   # 3. Restart bot service
   # 4. Delete old token from Developer Portal

   # Rotate OpenRouter key
   # Similar process for OpenRouter API keys
   ```

2. **Automated rotation (recommended):**
   ```bash
   # Use secret management tools like:
   # - HashiCorp Vault
   # - AWS Secrets Manager
   # - Azure Key Vault
   # - Doppler
   # - GitHub Secrets (for CI/CD)
   ```

### Docker Security

```yaml
# Secure docker-compose.yml
version: '3.8'

services:
  slopbot:
    environment:
      # Don't pass secrets directly in compose file
      - DISCORD_TOKEN
      - OPENROUTER_API_KEY
    env_file:
      - .env
    # Use external secrets file for production
    secrets:
      - discord_token
      - openrouter_key

secrets:
  discord_token:
    file: /run/secrets/discord_token
  openrouter_key:
    file: /run/secrets/openrouter_key
```

## Principle of Least Privilege

### Discord Bot Permissions

#### Minimal Required Permissions

The bot should have the absolute minimum permissions needed:

```json
{
  "permissions": "68608", // 68608 = 0x10C00 = bot + applications.commands + message.content
  "oauth2_scopes": ["bot", "applications.commands"],
  "bot_permissions": {
    "send_messages": true,
    "attach_files": true,
    "use_slash_commands": true,
    "read_message_history": true,
    "add_reactions": true,
    // NO: administrator, manage_server, kick_members, etc.
  }
}
```

#### Server-Specific Permissions

1. **Channel permissions:**
   - Only grant access to channels where bot is needed
   - Use channel-specific permission overrides
   - Deny access to sensitive channels (admin, logs, etc.)

2. **Role hierarchy:**
   - Bot role should be below admin roles but above regular users
   - Bot should not have permission to manage roles or permissions

### File System Permissions

#### Linux/macOS Permissions

```bash
# Create dedicated bot user
sudo useradd -r -s /bin/false slopbot-user

# Set ownership of bot files
sudo chown -R slopbot-user:slopbot-user /opt/slopbot

# Set restrictive permissions
chmod 750 /opt/slopbot
chmod 600 /opt/slopbot/.env
chmod 755 /opt/slopbot/src
```

#### Windows Permissions

```powershell
# Create dedicated service account
New-LocalUser -Name "slopbot-user" -Description "Slop Bot Service Account" -NoPassword

# Configure NTFS permissions
icacls "C:\Program Files\slopbot" /grant "slopbot-user:(OI)(CI)F" /T
icacls "C:\Program Files\slopbot\.env" /grant "slopbot-user:F"
icacls "C:\Program Files\slopbot\.env" /remove "BUILTIN\Users"
```

### Network Access

#### Firewall Configuration

```bash
# Allow only necessary outbound connections
sudo ufw default deny outgoing
sudo ufw default deny incoming
sudo ufw allow out to discord.com port 443
sudo ufw allow out to openrouter.ai port 443
sudo ufw allow in to any port 80 proto tcp  # If web interface needed
```

#### Docker Network Security

```yaml
# Restrict container networking
services:
  slopbot:
    networks:
      - slopbot-net
    dns:
      - 8.8.8.8
      - 1.1.1.1
    # Disable inter-container communication
    links: []  # Deprecated, but ensure no links
    depends_on: []  # If using other services

networks:
  slopbot-net:
    driver: bridge
    internal: true  # Isolate from other containers
```

## Safe Prompting and Input Validation

### Input Sanitization

#### Text Input Validation

```python
# Example: Safe prompt processing
import re

def sanitize_prompt(prompt: str) -> str:
    """Sanitize user prompts to prevent injection or harmful content."""

    # Remove potentially dangerous characters/patterns
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',  # XSS prevention
        r'\\x[0-9a-fA-F]{2}',         # Hex escapes
        r'\\u[0-9a-fA-F]{4}',         # Unicode escapes
    ]

    for pattern in dangerous_patterns:
        prompt = re.sub(pattern, '', prompt, flags=re.IGNORECASE)

    # Limit prompt length
    max_prompt_length = 1000
    if len(prompt) > max_prompt_length:
        prompt = prompt[:max_prompt_length] + "..."

    return prompt.strip()
```

#### File Upload Validation

```python
def validate_image_file(file_path: str) -> bool:
    """Validate uploaded image files."""

    import os
    import magic

    # Check file extension
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    _, ext = os.path.splitext(file_path.lower())
    if ext not in allowed_extensions:
        return False

    # Check file size
    max_size = 10 * 1024 * 1024  # 10MB
    if os.path.getsize(file_path) > max_size:
        return False

    # Check MIME type
    mime = magic.Magic(mime=True)
    actual_mime = mime.from_file(file_path)
    allowed_mimes = {
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/gif'
    }

    if actual_mime not in allowed_mimes:
        return False

    # Additional security checks can be added here
    # - Virus scanning
    # - Image metadata stripping
    # - Content moderation

    return True
```

### Rate Limiting and Abuse Prevention

#### Command Rate Limiting

```python
# Implement per-user and per-server rate limiting
from collections import defaultdict, deque
import time

class RateLimiter:
    def __init__(self):
        self.user_limits = defaultdict(lambda: deque(maxlen=10))
        self.server_limits = defaultdict(lambda: deque(maxlen=50))

    def check_rate_limit(self, user_id: str, server_id: str, command: str) -> bool:
        """Check if user/server is within rate limits."""

        current_time = time.time()

        # User rate limit: 5 commands per minute
        user_times = self.user_limits[user_id]
        user_times.append(current_time)

        # Remove old entries (older than 60 seconds)
        while user_times and user_times[0] < current_time - 60:
            user_times.popleft()

        if len(user_times) > 5:
            return False  # Rate limit exceeded

        # Server rate limit: 30 commands per minute
        server_times = self.server_limits[server_id]
        server_times.append(current_time)

        while server_times and server_times[0] < current_time - 60:
            server_times.popleft()

        if len(server_times) > 30:
            return False  # Server rate limit exceeded

        return True
```

## Content Policy and Moderation

### Content Filtering Levels

#### Prompt Moderation

1. **Pre-flight checks:** Scan prompts before sending to AI
2. **Post-generation filtering:** Review AI responses
3. **Real-time monitoring:** Watch for abuse patterns

#### Content Categories

**Blocked Content:**
- Violence and gore
- Hate speech
- Adult/Sexual content (in non-private contexts)
- Illegal activities
- Self-harm encouragement
- Spam/malicious intent

**Allowed with Warning:**
- Artistic nudity
- Mild violence (in fiction)
- Political content
- Professional use cases

### Moderation Implementation

```python
class ContentModerator:
    def __init__(self):
        self.blocked_keywords = {
            # Violence
            'kill', 'murder', 'torture', 'rape', 'suicide',

            # Hate speech
            'racist', 'nazi', 'terrorist', 'hate',

            # Illegal
            'drug', 'explosive', 'weapon', 'hack',

            # Adult content (basic filter)
            'nsfw', 'porn', 'sexual'
        }

    def moderate_content(self, text: str, context: str = 'general') -> dict:
        """Moderate text content based on context."""

        result = {
            'approved': True,
            'reasons': [],
            'severity': 'low',
            'modified_text': text
        }

        # Check for blocked keywords
        for keyword in self.blocked_keywords:
            if keyword in text.lower():
                result['approved'] = False
                result['reasons'].append(f'Contains blocked keyword: {keyword}')
                result['severity'] = 'high'

        # Context-specific rules
        if context == 'private':
            # More lenient in private channels
            result['severity'] = 'low'
        elif context == 'public':
            # Stricter in public channels
            if len(result['reasons']) > 0:
                result['severity'] = 'high'

        return result
```

### User Consent and Warnings

```python
# Age verification and consent for adult content
def check_user_consent(user_id: str, content_type: str) -> bool:
    """Verify user consent for specific content types."""

    # Check user preferences/settings
    # Return cached consent status
    # Prompt for consent if not set

    # For adult content, require explicit consent
    if content_type == 'adult':
        return user_has_adult_consent(user_id)

    # For political content, allow with disclaimer
    if content_type == 'political':
        return send_disclaimer(user_id)
```

## Privacy Protections

### Personally Identifiable Information (PII)

#### Data Collection Policy

**What we collect:**
- Discord User IDs (for rate limiting and preferences)
- Discord Server IDs (for server-specific settings)
- Command usage logs (for debugging and analytics)
- Generated images (cached temporarily)

**What we do NOT collect:**
- Real names, emails, or personal contact info
- Private message content (except bot commands)
- Voice channel data
- Location information
- Financial information

#### Data Retention

```python
class DataRetention:
    def __init__(self):
        self.cache_ttl = 86400 * 7  # 7 days cache
        self.log_ttl = 86400 * 30   # 30 days logs
        self.session_ttl = 3600     # 1 hour sessions

    def cleanup_old_data(self):
        """Remove expired data from storage."""

        # Clean up generated images
        cleanup_old_files(self.cache_dir, self.cache_ttl)

        # Clean up logs
        cleanup_old_files(self.logs_dir, self.log_ttl)

        # Clean up temporary files
        cleanup_temp_files()
```

### Privacy by Design

#### Minimum Data Principle

- Only store data necessary for bot operation
- Use anonymized data where possible
- Implement automatic data deletion schedules

#### Encryption at Rest

```bash
# Encrypt sensitive data files
openssl enc -aes-256-cbc -salt -in .env -out .env.enc

# Decrypt for use
openssl enc -aes-256-cbc -d -in .env.enc -out .env
```

#### Access Logging

Monitor who accesses what data:

```python
def log_data_access(user_id: str, resource: str, action: str):
    """Log all data access for audit purposes."""

    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,  # Obfuscated
        'resource': resource,
        'action': action,
        'ip_address': anonymize_ip(get_ip_address())
    }

    # Store in tamper-evident log
    write_to_secure_log(log_entry)
```

### User Data Rights

#### GDPR/Privacy Compliance

Users have the right to:

1. **Access:** Request what data is stored about them
2. **Rectification:** Correct inaccurate data
3. **Erasure:** Delete their data ("right to be forgotten")
4. **Portability:** Export their data in portable format
5. **Restriction:** Limit processing of their data

#### Implementation

```python
class PrivacyManager:
    def export_user_data(self, user_id: str) -> dict:
        """Export all user data for GDPR compliance."""

        return {
            'user_id': user_id,
            'command_history': get_command_history(user_id),
            'generated_images': list_user_images(user_id),
            'preferences': get_user_preferences(user_id),
            'export_date': datetime.now().isoformat()
        }

    def delete_user_data(self, user_id: str):
        """Completely delete user data."""

        # Remove from all databases
        delete_command_history(user_id)
        delete_user_images(user_id)
        delete_user_preferences(user_id)

        # Remove from cache
        clear_user_cache(user_id)

        # Log deletion for audit
        log_privacy_action(user_id, 'data_deletion', 'gdpr_compliance')
```

### Temporary Files and SynthID

#### SynthID Watermarking

All generated images include SynthID watermarks:

```python
def add_synthid_watermark(image_path: str) -> str:
    """Add SynthID watermark to generated images."""

    # Apply invisible watermark
    synthid_watermark = load_synthid_watermark()

    with Image.open(image_path) as img:
        # Apply watermark (invisible to human eye but detectable)
        watermarked_img = apply_watermark(img, synthid_watermark)

        # Save with SynthID metadata
        output_path = generate_watermarked_path(image_path)
        watermarked_img.save(output_path,
                           embed_synthid=True,
                           synthid_version='1.0')

        return output_path
```

#### Temporary File Management

```bash
# Secure temporary directory setup
export TMPDIR=/dev/shm/slopbot  # Memory-backed temp files

# Create secure temp directory
mkdir -p /dev/shm/slopbot
chmod 700 /dev/shm/slopbot
chown slopbot:slopbot /dev/shm/slopbot

# Cleanup script
find /dev/shm/slopbot -type f -mtime +1 -delete
```

## Image Security

### Upload Validation

#### File Type Verification

Multiple layers of validation:

1. **Extension check**
2. **MIME type verification**
3. **File header analysis**
4. **Content inspection** (optional - heavier)

#### Storage Security

```python
def secure_image_upload(uploaded_file, user_id: str) -> str:
    """Securely handle image uploads."""

    # Validate file
    if not is_safe_image(uploaded_file):
        raise SecurityError("Unsafe image upload")

    # Generate secure filename
    safe_filename = generate_secure_filename(user_id, uploaded_file)

    # Store in user-specific directory
    user_dir = ensure_user_directory(user_id)
    storage_path = os.path.join(user_dir, safe_filename)

    # Save with restricted permissions
    save_with_restrictions(uploaded_file, storage_path)

    # Log upload for audit
    log_image_upload(user_id, uploaded_file, storage_path)

    return storage_path
```

### Generated Content Security

#### Output Filtering

- All generated images are watermarked with SynthID
- Content moderation scans all outputs
- Automatic removal of flagged content
- User reporting system for inappropriate content

### Cache Security

#### Secure Cache Directory

```bash
# Create secure cache directory
sudo mkdir -p /var/cache/slopbot
sudo chown slopbot:slopbot /var/cache/slopbot
sudo chmod 700 /var/cache/slopbot

# Set disk quotas
sudo setquota -u slopbot 100M 0 0 0 /var/cache
```

## Network Security

### HTTPS Configuration

#### SSL/TLS Setup

```nginx
# Nginx SSL configuration
server {
    listen 443 ssl http2;
    server_name slopbot.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/slopbot.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/slopbot.yourdomain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/slopbot.yourdomain.com/chain.pem;
}
```

### API Security

#### OpenRouter Security

- Use API keys with read-only scopes when available
- Implement retry logic for rate limits
- Monitor API usage for anomalies

#### Discord API Security

- Use webhook URLs instead of tokens when possible
- Implement proper error handling for API failures
- Follow Discord's API rate limiting guidelines

## Security Audits

### Regular Security Reviews

1. **Dependency Scanning:**
   ```bash
   # Use safety and pip-audit
   pip install safety pip-audit
   safety check
   pip-audit
   ```

2. **Code Security Review:**
   ```bash
   # Use bandit for Python security
   pip install bandit
   bandit -r src/
   ```

3. **Container Security:**
   ```bash
   # Scan Docker images
   docker scan slopbot:latest

   # Use Clair for detailed vulnerability scanning
   clair-scanner slopbot:latest
   ```

### Security Checklist

**Before Deployment:**
- [ ] All secrets are in environment variables or secure vaults
- [ ] File permissions are restrictive
- [ ] Network access is minimized
- [ ] Dependencies are regularly updated
- [ ] Code has been reviewed for security issues
- [ ] HTTPS is enabled and configured properly
- [ ] Rate limiting is implemented
- [ ] Content moderation is active

**Monthly Checks:**
- [ ] Review access logs for anomalies
- [ ] Update all dependencies
- [ ] Rotate cryptographic keys if necessary
- [ ] Verify backup integrity
- [ ] Check for security advisories

## Incident Response

### Security Incident Process

1. **Detection and Assessment**
   - Monitor for unusual activity
   - Alert system administrators
   - Assess scope of incident

2. **Containment**
   - Isolate affected systems
   - Disable compromised accounts
   - Change all credentials

3. **Recovery**
   - Restore from clean backups
   - Update security measures
   - Test system functionality

4. **Lessons Learned**
   - Document incident details
   - Update security procedures
   - Implement preventive measures

### Emergency Contacts

- **Security Lead:** security@yourdomain.com
- **System Administrator:** admin@yourdomain.com
- **Legal Counsel:** legal@yourdomain.com

### Reporting Template

When reporting security incidents:

```markdown
**Incident Report Template**

- **Date/Time:** [timestamp]
- **Reporter:** [name/contact]
- **Severity:** [critical/high/medium/low]
- **Systems Affected:** [services/hosts]
- **Description:** [detailed description]
- **Indicators:** [logs, screenshots, etc.]
- **Impact:** [current and potential impact]
- **Mitigation:** [immediate actions taken]
```

## Vulnerability Disclosure

### Responsible Disclosure Policy

We encourage security research and responsible disclosure:

1. **Please email vulnerabilities to:** security@yourdomain.com
2. **Include detailed technical information**
3. **Avoid harming other users**
4. **Give us reasonable time to fix issues before public disclosure**
5. **We will acknowledge receipt within 48 hours**
6. **We will update you on our progress regularly**

### Disclosure Guidelines

- **Good:** Detailed description with proof-of-concept
- **Bad:** Public disclosure without prior contact
- **Bad:** Attempted system compromise
- **Bad:** Data exfiltration

### Security Hall of Fame

Contributors who help improve our security will be:

- Acknowledged publicly (with permission)
- Added to our security credits
- Eligible for bounty programs (when available)

---

**Last Updated:** January 2024

For questions about this security policy, contact security@yourdomain.com

[⬆ Back to top](#security)