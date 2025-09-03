import time
import asyncio
from collections import defaultdict, deque
from functools import wraps
from typing import Optional, Callable, Awaitable

# Import for dynamic reloading
from ...utils.settings_store import load_settings, reload_settings


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    pass


class RateLimiter:
    def __init__(self, default_limit=10, default_window=60, settings_reload_callback: Optional[Callable[[], Awaitable[None]]] = None):
        """
        Initialize the rate limiter.

        Args:
            default_limit (int): Default number of requests allowed per window.
            default_window (int): Default time window in seconds.
            settings_reload_callback (Optional[Callable]): Async function to call when settings reload.
        """
        self._cache = defaultdict(dict)  # user_id -> {command -> deque of timestamps}
        self.default_limit = default_limit
        self.default_window = default_window
        self._command_limits = {}  # command -> (limit, window)
        self._settings_reload_callback = settings_reload_callback

    def set_command_limit(self, command, limit, window=None):
        """
        Set custom rate limit for a specific command.

        Args:
            command (str): Command name.
            limit (int): Number of requests allowed.
            window (int, optional): Time window in seconds. If None, uses default_window.
        """
        if window is None:
            window = self.default_window
        self._command_limits[command] = (limit, window)

    def check_rate_limit(self, user_id, command, current_time=None):
        """
        Check if the action is within rate limits.

        Args:
            user_id (str): User identifier.
            command (str): Command name.
            current_time (float, optional): Current timestamp. If None, uses time.time().

        Returns:
            bool: True if within limits, False if exceeded.
        """
        if current_time is None:
            current_time = time.time()

        if command not in self._cache[user_id]:
            self._cache[user_id][command] = deque()

        times = self._cache[user_id][command]
        times.append(current_time)

        limit, window = self._get_limit_window(command)

        # Remove timestamps outside the window
        while times and times[0] < current_time - window:
            times.popleft()

        return len(times) <= limit

    def get_remaining_requests(self, user_id, command, current_time=None):
        """
        Get the number of remaining requests allowed for the user/command.

        Args:
            user_id (str): User identifier.
            command (str): Command name.
            current_time (float, optional): Current timestamp.

        Returns:
            int: Number of remaining requests.
        """
        if current_time is None:
            current_time = time.time()

        times = self._cache.get(user_id, {}).get(command, deque())
        limit, window = self._get_limit_window(command)

        # Clean old timestamps
        cleaned_times = [t for t in times if t >= current_time - window]

        # Update cache
        self._cache[user_id][command] = deque(cleaned_times)

        used = len(cleaned_times)
        return max(0, limit - used)

    def get_reset_time(self, user_id, command, current_time=None):
        """
        Get the time when the rate limit will reset.

        Args:
            user_id (str): User identifier.
            command (str): Command name.
            current_time (float, optional): Current timestamp.

        Returns:
            float: Reset timestamp.
        """
        if current_time is None:
            current_time = time.time()

        times = self._cache.get(user_id, {}).get(command, deque())
        limit, window = self._get_limit_window(command)

        if not times:
            return current_time

        if len(times) < limit:
            return current_time + window

        # Find the earliest timestamp that would still be within limit
        return times[len(times) - limit] + window

    def _get_limit_window(self, command):
        """Get limit and window for a command, using defaults if not set."""
        return self._command_limits.get(command, (self.default_limit, self.default_window))

    def cleanup_inactive_users(self, threshold_hours=24):
        """
        Clean up cache for users who haven't made requests recently.

        Args:
            threshold_hours (int): Remove users inactive longer than this (hours).
        """
        current_time = time.time()
        threshold = current_time - (threshold_hours * 3600)
        to_remove = []

        for user_id, commands in list(self._cache.items()):
            user_active = False
            for cmd, times in list(commands.items()):
                # Keep recent timestamps
                recent_times = [t for t in times if t >= threshold]
                if recent_times:
                    self._cache[user_id][cmd] = deque(recent_times)
                    user_active = True
                else:
                    del self._cache[user_id][cmd]
            if not user_active:
                to_remove.append(user_id)

        for user_id in to_remove:
            del self._cache[user_id]

    async def reload_limits_from_settings(self) -> bool:
        """
        Reload rate limit settings from settings_store.py.

        Returns:
            bool: True if settings were reloaded successfully, False otherwise.
        """
        try:
            # Reload settings from file
            new_settings = await reload_settings()
            rate_limits = new_settings.rate_limits

            # Update default limits if they changed
            if hasattr(rate_limits, 'max_requests_per_minute'):
                old_default = self.default_limit
                self.default_limit = rate_limits.max_requests_per_minute
                if old_default != self.default_limit:
                    print(f"RateLimiter: Updated default limit from {old_default} to {self.default_limit}")

            # Update default window to match current structure (assuming 60 seconds for simplicity)
            # In a full implementation, this could be configurable too

            # Update command-specific limits if any
            # For now, using default mapping - could be extended for per-command limits

            # Call the update callback if provided
            if self._settings_reload_callback:
                try:
                    await self._settings_reload_callback()
                except Exception as e:
                    print(f"RateLimiter: Error in settings reload callback: {e}")

            return True

        except Exception as e:
            print(f"RateLimiter: Error reloading settings: {e}")
            return False

    def set_reload_callback(self, callback: Callable[[], Awaitable[None]]):
        """
        Set an async callback function to be called when settings are reloaded.

        Args:
            callback: Async function that takes no arguments and returns None.
        """
        self._settings_reload_callback = callback


def rate_limited(rate_limiter, user_id_param='user_id', command_name=None):
    """
    Decorator to apply rate limiting to command functions.

    Args:
        rate_limiter (RateLimiter): Rate limiter instance.
        user_id_param (str): Name of the parameter containing user_id.
        command_name (str, optional): Custom command name. If None, uses function.__name__.

    Returns:
        Decorated function.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            wrapper.__globals__.update(func.__globals__)  # Ensure original globals are available
            # Extract user_id from parameters
            user_id = None
            if user_id_param in kwargs:
                user_id = kwargs[user_id_param]
            else:
                # Handle Discord.py slash command interactions
                if args and hasattr(args[0], 'user'):  # Discord.py slash command interaction
                    user_id = str(args[0].user.id)
                elif args and hasattr(args[1], 'author'):  # Discord.py message command style  
                    user_id = str(args[1].author.id)
                else:
                    raise ValueError(f"Could not extract user_id from {user_id_param}")

            if user_id is None:
                # Fallback or error
                raise ValueError("User ID not found")

            cmd_name = command_name or func.__name__

            if not rate_limiter.check_rate_limit(user_id, cmd_name):
                remaining = rate_limiter.get_remaining_requests(user_id, cmd_name)
                reset_time = rate_limiter.get_reset_time(user_id, cmd_name)
                reset_in = int(reset_time - time.time())
                raise RateLimitExceeded(
                    f"Rate limit exceeded. You have {remaining} requests remaining. "
                    f"Try again in {reset_in} seconds."
                )

            # If async, await; else call synchronously
            if hasattr(func, '__call__'):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar logic but for sync functions
            user_id = kwargs.get(user_id_param)
            if user_id is None and args:
                # Assuming first arg or adjust
                user_id = str(args[0])  # Placeholder

            if user_id is None:
                raise ValueError("User ID not found")

            cmd_name = command_name or func.__name__

            if not rate_limiter.check_rate_limit(user_id, cmd_name):
                remaining = rate_limiter.get_remaining_requests(user_id, cmd_name)
                reset_time = rate_limiter.get_reset_time(user_id, cmd_name)
                reset_in = int(reset_time - time.time())
                raise RateLimitExceeded(
                    f"Rate limit exceeded. You have {remaining} requests remaining. "
                    f"Try again in {reset_in} seconds."
                )

            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if hasattr(func, '__call__') and hasattr(func, '__code__'):
            # Check if async by looking at co_flags
            import inspect
            if inspect.iscoroutinefunction(func):
                return wrapper
            else:
                return sync_wrapper
        else:
            return sync_wrapper

    return decorator


# Utility functions for external use
async def reload_rate_limiter_settings():
    """
    Convenient function to reload rate limiter settings from the global instance.
    Can be called from external code when settings change.
    """
    success = await rate_limiter.reload_limits_from_settings()
    return success

async def initialize_rate_limiter():
    """
    Initialize rate limiter with settings and load initial configuration.
    """
    await rate_limiter.reload_limits_from_settings()

def set_rate_limiter_reload_callback(callback: Callable[[], Awaitable[None]]):
    """
    Set the reload callback for the global rate limiter instance.
    """
    rate_limiter.set_reload_callback(callback)

# Singleton instance for easy use
try:
    from ...utils.settings_store import load_settings

    async def _initialize_with_settings():
        global rate_limiter
        try:
            settings = await load_settings()
            # Initialize with settings-based defaults
            default_limit = getattr(settings.rate_limits, 'max_requests_per_minute', 60)
            rate_limiter = RateLimiter(default_limit=default_limit)
            await rate_limiter.reload_limits_from_settings()
        except Exception as e:
            # Fallback to defaults if settings loading fails
            print(f"RateLimiter: Falling back to default settings: {e}")
            rate_limiter = RateLimiter()

    # For now, just create with defaults - async init would be called elsewhere
    rate_limiter = RateLimiter()

except ImportError:
    # Fallback if settings_store is not available
    rate_limiter = RateLimiter()