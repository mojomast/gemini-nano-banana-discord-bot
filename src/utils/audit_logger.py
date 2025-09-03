"""
Audit logging module for Discord bot admin dashboard.

Implements tamper-evident audit logging with JSON Lines format,
automatic rotation, and optional Discord notifications.
"""

import json
import os
import hashlib
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

import aiofiles
import httpx
from pydantic import BaseModel, Field

from .config import config


class AuditCategory(str, Enum):
    """Enumeration of audit log categories."""
    AUTHENTICATION = "authentication"
    SETTINGS = "settings"
    SECRETS = "secrets"
    RATE_LIMITS = "rate_limits"
    ADMIN = "admin"


class AuditEntry(BaseModel):
    """Pydantic model for audit log entries."""
    timestamp: str = Field(
        description="ISO 8601 timestamp in UTC"
    )
    user_id: str = Field(
        description="Discord user ID performing the action"
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Discord username (optional)"
    )
    action: str = Field(
        description="Action performed (e.g., 'update_settings', 'login')"
    )
    category: AuditCategory = Field(
        description="Category of action (authentication, settings, etc.)"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional details about the action"
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="Client IP address"
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Client user agent string"
    )
    success: bool = Field(
        default=True,
        description="Whether the action was successful"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier"
    )

    class Config:
        use_enum_values = True


@dataclass
class AuditLogRotationConfig:
    """Configuration for audit log rotation."""
    max_size_mb: float = 10.0
    max_files: int = 2
    enabled: bool = True


class AuditLogger:
    """Tamper-evident audit logger with Discord notifications."""

    def __init__(
        self,
        log_file: Optional[str] = None,
        rotation_config: Optional[AuditLogRotationConfig] = None
    ):
        self.log_file = Path(log_file or config.audit_log_file or "data/audit.log")
        self.log_file.parent.mkdir(exist_ok=True, parents=True)
        self.rotation_config = rotation_config or AuditLogRotationConfig()
        self._lock = asyncio.Lock()
        self._checksums: Dict[str, str] = {}

    async def log_audit_entry(
        self,
        user_id: str,
        action: str,
        category: AuditCategory,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        user_name: Optional[str] = None,
        success: bool = True,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Log an audit entry to the JSON Lines file with atomic writes.

        Args:
            user_id: Discord user ID
            action: Action performed
            category: Audit category
            details: Optional details dictionary
            ip_address: Client IP address
            user_agent: Client user agent
            user_name: Discord username
            success: Action success status
            session_id: Session identifier

        Returns:
            True if logging successful, False otherwise
        """
        try:
            # Create audit entry
            entry = AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                user_id=user_id,
                user_name=user_name,
                action=action,
                category=category,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                session_id=session_id
            )

            entry_json = entry.json() + "\n"

            async with self._lock:
                # Check if rotation is needed
                await self._check_rotation()

                # Atomic write to log file
                await self._atomic_append(entry_json)

                # Update checksum for tamper detection
                await self._update_checksum()

            # Send Discord notification if configured
            if config.audit_webhook_url:
                asyncio.create_task(self._notify_discord_audit(entry))

            return True

        except Exception as e:
            # Log error but don't expose internal details
            print(f"Audit logging error: {e}")
            return False

    async def _atomic_append(self, data: str) -> None:
        """Atomically append data to the audit log file."""
        temp_file = self.log_file.with_suffix('.tmp')

        try:
            # Read existing content if file exists
            if self.log_file.exists():
                async with aiofiles.open(self.log_file, 'r') as f:
                    existing_content = await f.read()
            else:
                existing_content = ""

            # Write to temporary file
            async with aiofiles.open(temp_file, 'w') as f:
                await f.write(existing_content + data)

            # Atomic rename
            await asyncio.to_thread(temp_file.replace, self.log_file)

        except Exception:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise

    async def _check_rotation(self) -> None:
        """Check if log rotation is needed based on size."""
        if not self.rotation_config.enabled or not self.log_file.exists():
            return

        try:
            file_size_mb = self.log_file.stat().st_size / (1024 * 1024)

            if file_size_mb >= self.rotation_config.max_size_mb:
                await self.rotate_audit_log()

        except Exception as e:
            print(f"Log rotation check failed: {e}")

    async def rotate_audit_log(self) -> bool:
        """
        Rotate audit log files based on size and retention policy.

        Returns:
            True if rotation successful, False otherwise
        """
        try:
            if not self.log_file.exists():
                return True

            async with self._lock:
                # Create backup files
                for i in range(self.rotation_config.max_files - 1, 0, -1):
                    backup_file = self.log_file.with_suffix(f'.{i}')
                    if backup_file.exists():
                        await asyncio.to_thread(backup_file.replace,
                                              self.log_file.with_suffix(f'.{i+1}'))

                # Move current log to backup
                if self.rotation_config.max_files > 1:
                    await asyncio.to_thread(self.log_file.replace,
                                          self.log_file.with_suffix('.1'))

                # Clear checksums for rotation
                await self._clear_checksums()

            return True

        except Exception as e:
            print(f"Log rotation failed: {e}")
            return False

    async def _update_checksum(self) -> None:
        """Update checksums for tamper detection."""
        if not self.log_file.exists():
            return

        try:
            async with aiofiles.open(self.log_file, 'rb') as f:
                content = await f.read()

            checksum = hashlib.sha256(content).hexdigest()
            self._checksums[str(self.log_file)] = checksum

        except Exception as e:
            print(f"Checksum update failed: {e}")

    async def _clear_checksums(self) -> None:
        """Clear checksums after log rotation."""
        self._checksums.clear()

    async def _notify_discord_audit(self, entry: AuditEntry) -> None:
        """Send audit notification to Discord webhook."""
        if not config.audit_webhook_url:
            return

        try:
            # Create embed for Discord notification
            embed = {
                "title": "🔧 Admin Action Logged",
                "description": f"**{entry.user_name or entry.user_id}** performed `{entry.action}`",
                "color": 0x3498db if entry.success else 0xe74c3c,
                "fields": [
                    {
                        "name": "Category",
                        "value": entry.category.value,
                        "inline": True
                    },
                    {
                        "name": "Success",
                        "value": "✅ Yes" if entry.success else "❌ No",
                        "inline": True
                    },
                    {
                        "name": "Session",
                        "value": entry.session_id[:12] + "..." if entry.session_id and len(entry.session_id) > 12 else entry.session_id or "N/A",
                        "inline": True
                    }
                ],
                "timestamp": entry.timestamp
            }

            # Add details if present
            if entry.details:
                details_str = "\n".join([
                    f"**{k}:** {v}" for k, v in entry.details.items()
                    if k != 'changed' and len(str(v)) < 100
                ])
                if details_str:
                    embed["fields"].append({
                        "name": "Details",
                        "value": details_str[:1000],  # Discord limit
                        "inline": False
                    })

            payload = {"embeds": [embed]}

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(config.audit_webhook_url, json=payload)
                response.raise_for_status()

        except Exception as e:
            print(f"Discord audit notification failed: {e}")

    async def validate_audit_entry(
        self,
        entry_data: Union[Dict[str, Any], str],
        check_integrity: bool = True
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an audit entry for tamper-evident integrity.

        Args:
            entry_data: Dict or JSON string of audit entry
            check_integrity: Whether to verify file integrity

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if isinstance(entry_data, str):
                entry = AuditEntry.parse_raw(entry_data)
            else:
                entry = AuditEntry(**entry_data)

            # Validate required fields
            if not entry.timestamp or not entry.user_id or not entry.action:
                return False, "Missing required audit entry fields"

            # Validate timestamp format
            try:
                datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00'))
            except ValueError:
                return False, "Invalid timestamp format"

            # Check file integrity if enabled
            if check_integrity and self.log_file.exists():
                current_checksum = hashlib.sha256(self.log_file.read_bytes()).hexdigest()
                stored_checksum = self._checksums.get(str(self.log_file))

                if stored_checksum and current_checksum != stored_checksum:
                    return False, "Log file integrity compromised - checksum mismatch"

            return True, None

        except Exception as e:
            return False, f"Validation failed: {e}"

    async def read_audit_entries(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        filter_user_id: Optional[str] = None,
        filter_category: Optional[AuditCategory] = None,
        filter_action: Optional[str] = None,
        since_timestamp: Optional[datetime] = None,
        reverse: bool = True  # Most recent first
    ) -> List[Dict[str, Any]]:
        """
        Read audit entries with optional filtering and pagination.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            filter_user_id: Filter by user ID
            filter_category: Filter by category
            filter_action: Filter by action
            since_timestamp: Only entries after this timestamp
            reverse: Return in reverse chronological order

        Returns:
            List of audit entries as dictionaries
        """
        entries = []

        if not self.log_file.exists():
            return entries

        try:
            async with aiofiles.open(self.log_file, 'r') as f:
                lines = await f.readlines()

            # Process lines (skip empty lines)
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry_dict = json.loads(line)

                    # Apply filters
                    if filter_user_id and entry_dict.get('user_id') != filter_user_id:
                        continue

                    if filter_category and entry_dict.get('category') != filter_category.value:
                        continue

                    if filter_action and entry_dict.get('action') != filter_action:
                        continue

                    if since_timestamp:
                        entry_ts = datetime.fromisoformat(entry_dict['timestamp'].replace('Z', '+00:00'))
                        if entry_ts < since_timestamp:
                            continue

                    entries.append(entry_dict)

                except json.JSONDecodeError:
                    continue  # Skip malformed lines

            # Apply ordering and pagination
            if reverse:
                entries.reverse()

            if offset:
                entries = entries[offset:]

            if limit:
                entries = entries[:limit]

            return entries

        except Exception as e:
            print(f"Error reading audit entries: {e}")
            return []


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for easy access
async def log_audit_entry(
    user_id: str,
    action: str,
    category: AuditCategory,
    **kwargs
) -> bool:
    """Convenience function to log audit entries."""
    return await audit_logger.log_audit_entry(user_id, action, category, **kwargs)


async def rotate_audit_log() -> bool:
    """Convenience function to rotate audit logs."""
    return await audit_logger.rotate_audit_log()


async def notify_discord_audit(entry: AuditEntry) -> None:
    """Convenience function to send Discord notifications."""
    await audit_logger._notify_discord_audit(entry)


async def read_audit_entries(**kwargs) -> List[Dict[str, Any]]:
    """Convenience function to read audit entries."""
    return await audit_logger.read_audit_entries(**kwargs)


async def validate_audit_entry(
    entry_data: Union[Dict[str, Any], str],
    **kwargs
) -> tuple[bool, Optional[str]]:
    """Convenience function to validate audit entries."""
    return await audit_logger.validate_audit_entry(entry_data, **kwargs)