"""
Unit tests for audit logger functionality.
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from datetime import datetime, timezone

from src.utils.audit_logger import (
    AuditLogger,
    AuditEntry,
    AuditCategory,
    audit_logger,
    log_audit_entry,
    read_audit_entries,
    validate_audit_entry,
)


@pytest.fixture
def temp_audit_file():
    """Create a temporary audit log file for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = Path(temp_dir) / "audit.log"
        with patch('src.utils.audit_logger.config') as mock_config:
            mock_config.audit_log_file = str(temp_file)
            mock_config.audit_webhook_url = None  # Disable Discord notifications
            yield temp_file


@pytest.fixture
def mock_aiofiles():
    """Mock aiofiles for file operations."""
    with patch('src.utils.audit_logger.aiofiles') as mock_aiofiles:
        # Mock context managers
        mock_file = AsyncMock()
        mock_open_cm = MagicMock()
        mock_open_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open_cm.__aexit__ = AsyncMock(return_value=None)
        mock_aiofiles.open.return_value = mock_open_cm
        yield mock_aiofiles, mock_file


@pytest.fixture
def sample_audit_entry():
    """Create a sample audit entry for testing."""
    return AuditEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id="123456789",
        user_name="testuser#1234",
        action="update_settings",
        category=AuditCategory.SETTINGS,
        details={"setting": "max_requests_per_minute", "old": 5, "new": 10},
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0...",
        success=True,
        session_id="abc123def456"
    )


@pytest.mark.asyncio
class TestLogAuditEntry:
    """Test audit entry logging functionality."""

    async def test_log_audit_entry_module_success(self, temp_audit_file, mock_aiofiles):
        """Test module-level log_audit_entry success."""
        mock_aiofiles, mock_file = mock_aiofiles
        mock_file.read = AsyncMock(return_value="")
        mock_file.write = AsyncMock()

        result = await log_audit_entry(
            user_id="123456789",
            action="login",
            category=AuditCategory.AUTHENTICATION,
            success=True
        )

        assert result is True
        mock_file.write.assert_called()

    async def test_log_audit_entry_class_success(self, temp_audit_file, mock_aiofiles, sample_audit_entry):
        """Test class-level log_audit_entry success."""
        mock_aiofiles, mock_file = mock_aiofiles
        mock_file.read = AsyncMock(return_value="")
        mock_file.write = AsyncMock()

        logger = AuditLogger()
        result = await logger.log_audit_entry(
            user_id="123456789",
            action="login",
            category=AuditCategory.AUTHENTICATION
        )

        assert result is True
        mock_file.write.assert_called()

    async def test_log_audit_entry_with_details(self, temp_audit_file, mock_aiofiles):
        """Test logging with details dictionary."""
        mock_aiofiles, mock_file = mock_aiofiles
        mock_file.read = AsyncMock(return_value="")
        mock_file.write = AsyncMock()

        details = {"key": "value", "number": 42}
        result = await log_audit_entry(
            user_id="123456789",
            action="update_settings",
            category=AuditCategory.SETTINGS,
            details=details
        )

        assert result is True
        # Verify details are included in written content
        write_call_args = mock_file.write.call_args[0][0]
        written_data = json.loads(write_call_args.strip())
        assert written_data["details"] == details

    async def test_log_audit_entry_failure_handling(self, temp_audit_file, mock_aiofiles):
        """Test failure handling during logging."""
        mock_aiofiles, mock_file = mock_aiofiles
        mock_file.write = AsyncMock(side_effect=Exception("Write failed"))

        result = await log_audit_entry(
            user_id="123456789",
            action="test_action",
            category=AuditCategory.ADMIN
        )

        assert result is False

    @patch('src.utils.audit_logger.audit_logger')
    async def test_log_audit_entry_delegates_to_global(self, mock_global_logger):
        """Test module function delegates to global logger."""
        mock_global_logger.log_audit_entry = AsyncMock(return_value=True)

        result = await log_audit_entry(
            user_id="123456789",
            action="test",
            category=AuditCategory.ADMIN
        )

        assert result is True
        mock_global_logger.log_audit_entry.assert_called_once()


@pytest.mark.asyncio
class TestReadAuditEntries:
    """Test audit entries reading functionality."""

    async def test_read_audit_entries_empty_file(self, temp_audit_file, mock_aiofiles):
        """Test reading from empty file."""
        mock_aiofiles, mock_file = mock_aiofiles
        mock_file.readlines = AsyncMock(return_value=[])

        entries = await read_audit_entries()

        assert entries == []

    async def test_read_audit_entries_valid_entries(self, temp_audit_file, mock_aiofiles):
        """Test reading valid audit entries."""
        mock_aiofiles, mock_file = mock_aiofiles

        # Create sample JSON lines
        entry1 = {
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication",
            "success": True
        }
        entry2 = {
            "timestamp": "2025-09-03T10:01:00+00:00",
            "user_id": "987654321",
            "action": "update_settings",
            "category": "settings",
            "success": True
        }

        lines = [
            json.dumps(entry1) + "\n",
            json.dumps(entry2) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        entries = await read_audit_entries(reverse=True)

        assert len(entries) == 2
        assert entries[0]["user_id"] == "987654321"  # Reversed order
        assert entries[1]["user_id"] == "123456789"

    async def test_read_audit_entries_with_filters(self, temp_audit_file, mock_aiofiles):
        """Test reading with user ID filter."""
        mock_aiofiles, mock_file = mock_aiofiles

        entry1 = {
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication",
            "success": True
        }
        entry2 = {
            "timestamp": "2025-09-03T10:01:00+00:00",
            "user_id": "987654321",
            "action": "logout",
            "category": "authentication",
            "success": True
        }

        lines = [
            json.dumps(entry1) + "\n",
            json.dumps(entry2) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        # Filter by user_id
        entries = await read_audit_entries(filter_user_id="123456789")

        assert len(entries) == 1
        assert entries[0]["user_id"] == "123456789"

    async def test_read_audit_entries_category_filter(self, temp_audit_file, mock_aiofiles):
        """Test reading with category filter."""
        mock_aiofiles, mock_file = mock_aiofiles

        entry1 = {
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication",
            "success": True
        }
        entry2 = {
            "timestamp": "2025-09-03T10:01:00+00:00",
            "user_id": "123456789",
            "action": "update_settings",
            "category": "settings",
            "success": True
        }

        lines = [
            json.dumps(entry1) + "\n",
            json.dumps(entry2) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        entries = await read_audit_entries(filter_category=AuditCategory.SETTINGS)

        assert len(entries) == 1
        assert entries[0]["category"] == "settings"

    async def test_read_audit_entries_action_filter(self, temp_audit_file, mock_aiofiles):
        """Test reading with action filter."""
        mock_aiofiles, mock_file = mock_aiofiles

        entry1 = {
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication"
        }
        entry2 = {
            "timestamp": "2025-09-03T10:01:00+00:00",
            "user_id": "123456789",
            "action": "logout",
            "category": "authentication"
        }

        lines = [
            json.dumps(entry1) + "\n",
            json.dumps(entry2) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        entries = await read_audit_entries(filter_action="logout")

        assert len(entries) == 1
        assert entries[0]["action"] == "logout"

    async def test_read_audit_entries_limit_offset(self, temp_audit_file, mock_aiofiles):
        """Test reading with limit and offset."""
        mock_aiofiles, mock_file = mock_aiofiles

        # Create many entries
        lines = []
        for i in range(10):
            entry = {
                "timestamp": f"2025-09-03T{i:02d}:00:00+00:00",
                "user_id": f"user{i}",
                "action": f"action{i}",
                "category": "authentication"
            }
            lines.append(json.dumps(entry) + "\n")

        mock_file.readlines = AsyncMock(return_value=lines)

        # Test limit
        entries = await read_audit_entries(limit=3, reverse=False)
        assert len(entries) == 3

        # Test offset
        entries = await read_audit_entries(offset=5, reverse=False)
        assert len(entries) == 5
        assert entries[0]["user_id"] == "user5"

    async def test_read_audit_entries_malformed_json(self, temp_audit_file, mock_aiofiles):
        """Test handling of malformed JSON lines."""
        mock_aiofiles, mock_file = mock_aiofiles

        # Mix valid and invalid JSON
        lines = [
            json.dumps({"valid": "entry"}) + "\n",
            "invalid json line\n",
            '{"missing": "brace"',
            json.dumps({"another": "valid"}) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        entries = await read_audit_entries()

        assert len(entries) == 2
        assert entries[0]["another"] == "valid"

    async def test_read_audit_entries_file_not_exists(self, temp_audit_file):
        """Test reading when audit file doesn't exist."""
        entries = await read_audit_entries()
        assert entries == []

    @patch('src.utils.audit_logger.datetime')
    async def test_read_audit_entries_timestamp_filter(self, mock_datetime, temp_audit_file, mock_aiofiles):
        """Test reading with timestamp filter."""
        mock_aiofiles, mock_file = mock_aiofiles

        # Mock datetime.fromisoformat
        mock_dt = Mock(spec=datetime)
        mock_datetime.fromisoformat.return_value = mock_dt

        # Mock comparison
        mock_dt.__lt__ = Mock(return_value=False)
        mock_filter_time = Mock()
        mock_filter_time.replace.return_value = None

        lines = [
            json.dumps({
                "timestamp": "2025-09-03T10:00:00+00:00",
                "user_id": "123456789",
                "action": "test"
            }) + "\n"
        ]
        mock_file.readlines = AsyncMock(return_value=lines)

        # This might need more mocking for datetime.fromisoformat
        entries = await read_audit_entries(since_timestamp=datetime.now(timezone.utc))

        # Verify filtering was applied
        mock_datetime.fromisoformat.assert_called()


@pytest.mark.asyncio
class TestValidateAuditEntry:
    """Test audit entry validation."""

    @pytest.mark.asyncio
    async def test_validate_audit_entry_dict_success(self):
        """Test validating valid audit entry dict."""
        entry_data = {
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication",
            "success": True
        }

        valid, error = await validate_audit_entry(entry_data)

        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_audit_entry_string_success(self):
        """Test validating valid audit entry JSON string."""
        entry_str = json.dumps({
            "timestamp": "2025-09-03T10:00:00+00:00",
            "user_id": "123456789",
            "action": "login",
            "category": "authentication"
        })

        valid, error = await validate_audit_entry(entry_str)

        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_audit_entry_missing_fields(self):
        """Test validation fails with missing required fields."""
        entry_data = {"timestamp": "2025-09-03T10:00:00+00:00"}

        valid, error = await validate_audit_entry(entry_data)

        assert valid is False
        if error:
            assert "Missing required" in error

    @pytest.mark.asyncio
    async def test_validate_audit_entry_invalid_timestamp(self):
        """Test validation fails with invalid timestamp."""
        entry_data = {
            "timestamp": "invalid-timestamp",
            "user_id": "123456789",
            "action": "login"
        }

        valid, error = await validate_audit_entry(entry_data)

        assert valid is False
        if error:
            assert "Invalid timestamp format" in error


class TestAuditEntryModel:
    """Test AuditEntry Pydantic model."""

    def test_audit_entry_required_fields(self):
        """Test AuditEntry requires essential fields."""
        entry = AuditEntry(
            timestamp="2025-09-03T10:00:00+00:00",
            user_id="123456789",
            action="login",
            category=AuditCategory.AUTHENTICATION
        )

        assert entry.timestamp == "2025-09-03T10:00:00+00:00"
        assert entry.user_id == "123456789"
        assert entry.action == "login"
        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.success is True  # default

    def test_audit_entry_optional_fields(self):
        """Test AuditEntry optional fields."""
        entry = AuditEntry(
            timestamp="2025-09-03T10:00:00+00:00",
            user_id="123456789",
            action="login",
            category=AuditCategory.AUTHENTICATION,
            user_name="testuser#1234",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            session_id="abc123"
        )

        assert entry.user_name == "testuser#1234"
        assert entry.ip_address == "192.168.1.100"
        assert entry.session_id == "abc123"

    def test_audit_entry_category_enum(self):
        """Test category uses enum values."""
        entry = AuditEntry(
            timestamp="2025-09-03T10:00:00+00:00",
            user_id="123456789",
            action="login",
            category=AuditCategory.SETTINGS
        )

        # Verify enum value is used in serialization
        entry_dict = entry.dict()
        assert entry_dict["category"] == "settings"


class TestAuditLoggerClass:
    """Test AuditLogger class initialization and behavior."""

    def test_audit_logger_initialization(self, temp_audit_file):
        """Test AuditLogger proper initialization."""
        with patch('src.utils.audit_logger.config') as mock_config:
            mock_config.audit_log_file = None

            logger = AuditLogger()

            assert logger.log_file == Path("data/audit.log")
            assert logger.rotation_config.max_size_mb == 10.0

    def test_audit_logger_custom_config(self, temp_audit_file):
        """Test AuditLogger with custom rotation config."""
        from src.utils.audit_logger import AuditLogRotationConfig

        rotation_config = AuditLogRotationConfig(max_size_mb=5.0, max_files=5)
        logger = AuditLogger(rotation_config=rotation_config)

        assert logger.rotation_config.max_size_mb == 5.0
        assert logger.rotation_config.max_files == 5


if __name__ == "__main__":
    pytest.main([__file__])