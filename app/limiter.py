# app/limiter.py
from functools import wraps
import inspect
import time
from typing import Callable, Dict, Any
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

# Create ONE global limiter instance for the whole app
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)

# Simple in-memory rate limiting store
_rate_limit_store: Dict[str, Dict[str, Any]] = {}

def _parse_rate_limit(limit_value: str) -> tuple[int, int]:
    """Parse rate limit string like '5/minute' into (count, seconds)"""
    parts = limit_value.split('/')
    if len(parts) != 2:
        return 60, 60  # Default: 60 requests per minute
    
    count = int(parts[0])
    period = parts[1].lower()
    
    if period.startswith('sec'):
        seconds = 1
    elif period.startswith('min'):
        seconds = 60
    elif period.startswith('hour'):
        seconds = 3600
    elif period.startswith('day'):
        seconds = 86400
    else:
        seconds = 60  # Default to minute
    
    return count, seconds

def _check_rate_limit(key: str, limit_value: str) -> bool:
    """Check if request is within rate limit"""
    max_requests, window_seconds = _parse_rate_limit(limit_value)
    current_time = time.time()
    
    if key not in _rate_limit_store:
        _rate_limit_store[key] = {
            'requests': [],
            'window_start': current_time
        }
    
    store = _rate_limit_store[key]
    
    # Clean old requests outside the window
    cutoff_time = current_time - window_seconds
    store['requests'] = [req_time for req_time in store['requests'] if req_time > cutoff_time]
    
    # Check if we're over the limit
    if len(store['requests']) >= max_requests:
        return False
    
    # Add current request
    store['requests'].append(current_time)
    return True

def rate_limit(limit_value: str):
    """
    Decorator to apply rate limits safely without SlowAPI response issues.

    Usage:
        @router.post("/auth/login")
        @rate_limit("5/minute")
        async def login(...): ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args or kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                request = kwargs.get('request')
            
            if request:
                try:
                    # Get client IP for rate limiting
                    client_ip = get_remote_address(request)
                    rate_limit_key = f"{client_ip}:{request.url.path}"
                    
                    # Check rate limit
                    if not _check_rate_limit(rate_limit_key, limit_value):
                        raise HTTPException(
                            status_code=429,
                            detail="Rate limit exceeded. Please try again later."
                        )
                except Exception as e:
                    # If rate limiting fails for any reason, log and continue
                    # This ensures the app doesn't break due to rate limiting issues
                    print(f"Rate limiting error: {e}")
                    pass
            
            # Call the original function
            result = func(*args, **kwargs)
            
            # Handle async vs sync
            if inspect.isawaitable(result):
                return await result
            return result

        return wrapper
    return decorator