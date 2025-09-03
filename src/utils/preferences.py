"""
User preferences management for SlopBot.

This module handles user-specific settings like default styles, settings, etc.
Preferences are stored in JSON format for persistence.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from .config import config

class UserPreferences:
    """Manages user preferences with defaults."""

    def __init__(self):
        self.prefs_file = Path(config.cache_dir) / "user_preferences.json"
        self.ensure_prefs_file()
        self._prefs: Dict[str, Dict[str, Any]] = self.load_prefs()

    def ensure_prefs_file(self):
        """Ensure the preferences file exists."""
        self.prefs_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.prefs_file.exists():
            self.prefs_file.write_text("{}")

    def load_prefs(self) -> Dict[str, Dict[str, Any]]:
        """Load preferences from file."""
        try:
            with open(self.prefs_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def save_prefs(self):
        """Save preferences to file."""
        with open(self.prefs_file, 'w') as f:
            json.dump(self._prefs, f, indent=2)

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a preference value for a user."""
        user_prefs = self._prefs.get(user_id, {})
        return user_prefs.get(key, default)

    def set(self, user_id: str, key: str, value: Any):
        """Set a preference value for a user."""
        if user_id not in self._prefs:
            self._prefs[user_id] = {}
        self._prefs[user_id][key] = value
        self.save_prefs()

    def get_all(self, user_id: str) -> Dict[str, Any]:
        """Get all preferences for a user."""
        return self._prefs.get(user_id, {}).copy()

# Global preferences instance
prefs = UserPreferences()