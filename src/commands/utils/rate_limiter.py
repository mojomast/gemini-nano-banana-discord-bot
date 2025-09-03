import time
from collections import defaultdict, deque
from functools import wraps


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    pass


class RateLimiter:
    def __init__(self, default_limit=10, default_window=60):
        """
        Initialize the rate limiter.

        Args:
            default_limit (int): Default number of requests allowed per window.
            default_window (int): Default time window in seconds.
        """
        self._cache = defaultdict(dict)  # user_id -> {command -> deque of timestamps}
        self.default_limit = default_limit
        self.default_window = default_window
        self._command_limits = {}  # command -> (limit, window)

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


# Singleton instance for easy use
rate_limiter = RateLimiter()