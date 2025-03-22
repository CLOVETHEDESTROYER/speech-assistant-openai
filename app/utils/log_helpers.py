import re
import json
from typing import Dict, Any, List, Union


def sanitize_dict(data: Dict[str, Any], sensitive_keys: List[str] = None) -> Dict[str, Any]:
    """
    Sanitize a dictionary by replacing values of sensitive keys with [REDACTED].

    Args:
        data: Dictionary to sanitize
        sensitive_keys: List of keys to redact. If None, uses default list.

    Returns:
        Sanitized dictionary
    """
    if sensitive_keys is None:
        sensitive_keys = [
            "password", "token", "secret", "key", "auth", "credential",
            "api_key", "apikey", "access_token", "refresh_token",
            "twilio_auth_token", "openai_api_key", "credit_card",
            "ssn", "social_security", "bearer"
        ]

    result = {}

    for key, value in data.items():
        # Check if this key should be redacted (case insensitive partial match)
        should_redact = any(sensitive in key.lower()
                            for sensitive in sensitive_keys)

        if should_redact:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value, sensitive_keys)
        elif isinstance(value, list):
            result[key] = [
                sanitize_dict(item, sensitive_keys) if isinstance(
                    item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


def sanitize_json(json_data: Union[str, bytes], sensitive_keys: List[str] = None) -> str:
    """
    Sanitize a JSON string by replacing values of sensitive keys with [REDACTED].

    Args:
        json_data: JSON string to sanitize
        sensitive_keys: List of keys to redact. If None, uses default list.

    Returns:
        Sanitized JSON string
    """
    try:
        if isinstance(json_data, bytes):
            json_data = json_data.decode('utf-8')

        data = json.loads(json_data)
        sanitized_data = sanitize_dict(data, sensitive_keys)
        return json.dumps(sanitized_data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # If not valid JSON, return as is
        return "[INVALID_JSON]"


def sanitize_text(text: str) -> str:
    """
    Sanitize text by removing potential sensitive data patterns.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text
    """
    # Replace potential credit card numbers
    text = re.sub(r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
                  '[CREDIT_CARD_REDACTED]', text)

    # Replace potential SSNs
    text = re.sub(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b', '[SSN_REDACTED]', text)

    # Replace potential API keys - alphanumeric strings of 20+ chars
    text = re.sub(r'\b[A-Za-z0-9_-]{20,}\b', '[API_KEY_REDACTED]', text)

    # Replace potential email addresses
    text = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', text)

    # Replace potential phone numbers
    text = re.sub(
        r'\b(?:\+\d{1,2}\s?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE_REDACTED]', text)

    return text


def safe_log_request_data(request_data: Union[Dict, str, bytes]) -> Union[Dict, str]:
    """
    Safely sanitize request data for logging purposes.

    Args:
        request_data: Request data to sanitize

    Returns:
        Sanitized request data
    """
    if isinstance(request_data, dict):
        return sanitize_dict(request_data)
    elif isinstance(request_data, (str, bytes)):
        try:
            # Try to parse as JSON first
            return sanitize_json(request_data)
        except:
            # If not JSON, sanitize as text
            if isinstance(request_data, bytes):
                try:
                    request_data = request_data.decode('utf-8')
                except UnicodeDecodeError:
                    return "[BINARY_DATA]"
            return sanitize_text(request_data)
    else:
        return "[UNSUPPORTED_DATA_TYPE]"
