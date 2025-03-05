import logging
import time
import random
import asyncio
from functools import wraps
from typing import Callable, Any, TypeVar, Dict, Optional, List, Union
from twilio.base.exceptions import TwilioRestException, TwilioException
from twilio.http.http_client import TwilioHttpClient
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger(__name__)

# Type variable for generic function return type
T = TypeVar('T')

# Define error categories
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_TWILIO_CODES = {20001, 20002,
                          20003, 30001, 30003, 30005, 30006, 30007}
AUTH_ERROR_CODES = {20003, 20004, 20005, 20006, 20007, 20008}
RESOURCE_ERROR_CODES = {20404, 20400, 20422}


class TwilioApiError(Exception):
    """Base class for Twilio API errors"""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 twilio_code: Optional[int] = None, details: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.twilio_code = twilio_code
        self.details = details or {}
        super().__init__(self.message)


class TwilioRetryableError(TwilioApiError):
    """Error that can be retried"""
    pass


class TwilioAuthError(TwilioApiError):
    """Authentication or authorization error"""
    pass


class TwilioResourceError(TwilioApiError):
    """Resource not found or invalid resource error"""
    pass


class TwilioRateLimitError(TwilioRetryableError):
    """Rate limit exceeded error"""
    pass


class TwilioNetworkError(TwilioRetryableError):
    """Network-related error"""
    pass


def categorize_twilio_exception(exception: Exception) -> TwilioApiError:
    """
    Categorize a Twilio exception into a specific error type

    Args:
        exception: The exception to categorize

    Returns:
        A specific TwilioApiError subclass
    """
    if isinstance(exception, TwilioRestException):
        status = exception.status
        code = exception.code

        # Create a details dictionary with all available information
        details = {
            "status": status,
            "code": code,
            "twilio_error_message": str(exception),
            "more_info": getattr(exception, "more_info", None),
            "details": getattr(exception, "details", None),
        }

        # Rate limit error
        if status == 429 or code in (11200, 11010):
            return TwilioRateLimitError(
                f"Twilio rate limit exceeded: {exception}",
                status_code=status,
                twilio_code=code,
                details=details
            )

        # Authentication errors
        if code in AUTH_ERROR_CODES:
            return TwilioAuthError(
                f"Twilio authentication error: {exception}",
                status_code=status,
                twilio_code=code,
                details=details
            )

        # Resource errors
        if code in RESOURCE_ERROR_CODES or status == 404:
            return TwilioResourceError(
                f"Twilio resource error: {exception}",
                status_code=status,
                twilio_code=code,
                details=details
            )

        # Retryable errors
        if status in RETRYABLE_HTTP_CODES or code in RETRYABLE_TWILIO_CODES:
            return TwilioRetryableError(
                f"Twilio retryable error: {exception}",
                status_code=status,
                twilio_code=code,
                details=details
            )

        # Default case - generic Twilio API error
        return TwilioApiError(
            f"Twilio API error: {exception}",
            status_code=status,
            twilio_code=code,
            details=details
        )

    # Handle network-related exceptions
    elif isinstance(exception, (Timeout, ConnectionError)):
        return TwilioNetworkError(
            f"Twilio network error: {exception}",
            details={"original_exception": str(exception)}
        )

    # Handle other request exceptions
    elif isinstance(exception, RequestException):
        return TwilioNetworkError(
            f"Twilio request error: {exception}",
            details={"original_exception": str(exception)}
        )

    # Handle generic Twilio exceptions
    elif isinstance(exception, TwilioException):
        return TwilioApiError(
            f"Twilio error: {exception}",
            details={"original_exception": str(exception)}
        )

    # Handle all other exceptions
    return TwilioApiError(
        f"Unexpected error in Twilio API call: {exception}",
        details={"original_exception": str(exception)}
    )


def with_twilio_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 8.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for Twilio API calls with exponential backoff retry logic

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for the delay on each retry
        jitter: Whether to add randomness to the delay

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = initial_delay

            # Try the initial call plus retries
            for attempt in range(max_retries + 1):
                try:
                    # Attempt the function call
                    return await func(*args, **kwargs)

                except Exception as e:
                    # Categorize the exception
                    error = categorize_twilio_exception(e)
                    last_exception = error

                    # Don't retry non-retryable errors
                    if not isinstance(error, TwilioRetryableError):
                        logger.warning(
                            f"Non-retryable Twilio error on attempt {attempt+1}/{max_retries+1}: {error}"
                        )
                        raise error

                    # Don't retry if this was the last attempt
                    if attempt >= max_retries:
                        logger.warning(
                            f"Twilio API call failed after {max_retries+1} attempts: {error}"
                        )
                        raise error

                    # Calculate the next delay with exponential backoff
                    if jitter:
                        # Add randomness to prevent thundering herd
                        jitter_amount = random.uniform(0.8, 1.2)
                        current_delay = min(max_delay, delay * jitter_amount)
                    else:
                        current_delay = min(max_delay, delay)

                    logger.info(
                        f"Retryable Twilio error on attempt {attempt+1}/{max_retries+1}. "
                        f"Retrying in {current_delay:.2f}s: {error}"
                    )

                    # Sleep before the next retry
                    await asyncio.sleep(current_delay)

                    # Increase the delay for the next attempt
                    delay = delay * backoff_factor

            # This should never happen due to the raise in the loop
            # but it's here for completeness
            if last_exception:
                raise last_exception
            raise TwilioApiError(
                "Unexpected error: retry loop completed without success or exception")

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = initial_delay

            # Try the initial call plus retries
            for attempt in range(max_retries + 1):
                try:
                    # Attempt the function call
                    return func(*args, **kwargs)

                except Exception as e:
                    # Categorize the exception
                    error = categorize_twilio_exception(e)
                    last_exception = error

                    # Don't retry non-retryable errors
                    if not isinstance(error, TwilioRetryableError):
                        logger.warning(
                            f"Non-retryable Twilio error on attempt {attempt+1}/{max_retries+1}: {error}"
                        )
                        raise error

                    # Don't retry if this was the last attempt
                    if attempt >= max_retries:
                        logger.warning(
                            f"Twilio API call failed after {max_retries+1} attempts: {error}"
                        )
                        raise error

                    # Calculate the next delay with exponential backoff
                    if jitter:
                        # Add randomness to prevent thundering herd
                        jitter_amount = random.uniform(0.8, 1.2)
                        current_delay = min(max_delay, delay * jitter_amount)
                    else:
                        current_delay = min(max_delay, delay)

                    logger.info(
                        f"Retryable Twilio error on attempt {attempt+1}/{max_retries+1}. "
                        f"Retrying in {current_delay:.2f}s: {error}"
                    )

                    # Sleep before the next retry
                    time.sleep(current_delay)

                    # Increase the delay for the next attempt
                    delay = delay * backoff_factor

            # This should never happen due to the raise in the loop
            # but it's here for completeness
            if last_exception:
                raise last_exception
            raise TwilioApiError(
                "Unexpected error: retry loop completed without success or exception")

        # Return the appropriate wrapper based on whether the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def safe_twilio_response(response: Any) -> Dict:
    """
    Safely extract data from a Twilio response object

    Args:
        response: Twilio response object

    Returns:
        Dictionary with response data
    """
    if response is None:
        return {}

    # Handle list responses
    if hasattr(response, '__iter__') and not isinstance(response, (str, dict)):
        return [safe_twilio_response(item) for item in response]

    # Handle dictionary-like responses
    if hasattr(response, 'keys'):
        return {k: safe_twilio_response(v) for k, v in response.items()}

    # Handle objects with __dict__
    if hasattr(response, '__dict__'):
        # Try to convert to dictionary using built-in methods if available
        if hasattr(response, 'to_dict') and callable(getattr(response, 'to_dict')):
            return response.to_dict()

        # Otherwise extract attributes
        result = {}
        for attr in dir(response):
            # Skip private attributes and methods
            if attr.startswith('_') or callable(getattr(response, attr)):
                continue

            try:
                value = getattr(response, attr)
                # Skip complex objects that might cause issues
                if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    continue
                result[attr] = safe_twilio_response(value)
            except Exception:
                # Skip attributes that can't be accessed
                pass
        return result

    # Return primitive types as is
    return response
