import functools
import inspect
from typing import Callable, Optional
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional


def get_client_ip(request: Request) -> str:
    # Honor X-Forwarded-For if present (use left-most as client)
    xff: Optional[str] = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)

# Create the limiter instance with proxy-aware IP extraction
limiter = Limiter(key_func=get_client_ip)


def rate_limit(limit_value: str) -> Callable:
    """
    A decorator that adds rate limiting to FastAPI endpoint functions.
    This handles the request parameter requirements automatically.

    Args:
        limit_value: A string like "5/minute" or "100/day" defining the rate limit

    Returns:
        A decorator function that can be applied to FastAPI endpoints
    """
    def decorator(func: Callable) -> Callable:
        # Get the signature of the original function
        sig = inspect.signature(func)
        has_request_param = False

        # Check if it already has a request parameter
        for param_name, param in sig.parameters.items():
            if param_name == "request" and param.annotation == Request:
                has_request_param = True
                break

        # If it already has a request parameter, just apply the limiter
        if has_request_param:
            return limiter.limit(limit_value)(func)

        # Otherwise, create a wrapper function that accepts the request
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            return await func(*args, **kwargs)

        # Apply the limiter to the wrapper
        return limiter.limit(limit_value)(wrapper)

    return decorator
