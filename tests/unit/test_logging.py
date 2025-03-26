import pytest
from app.utils.log_helpers import sanitize_dict, sanitize_text, sanitize_json, safe_log_request_data


def test_sanitize_dict():
    """Test sanitizing dictionary with sensitive data"""
    test_data = {
        "username": "testuser",
        "password": "secret123",
        "api_key": "sk-1234567890abcdef",
        "auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "address": {
            "street": "123 Main St",
            "credit_card": "4111-1111-1111-1111"
        },
        "phone": "555-123-4567"
    }

    sanitized = sanitize_dict(test_data)

    # Check sensitive keys are redacted
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"

    # Check nested sensitive keys are redacted
    assert sanitized["address"]["credit_card"] == "[REDACTED]"

    # Check non-sensitive data is preserved
    assert sanitized["username"] == "testuser"
    assert sanitized["address"]["street"] == "123 Main St"
    assert sanitized["phone"] == "555-123-4567"


def test_sanitize_text():
    """Test sanitizing text with sensitive patterns"""
    test_text = (
        "My credit card is 4111-1111-1111-1111, my SSN is 123-45-6789, "
        "my API key is sdkfjhsdkjfhskdjhfksdjhfk2837482374, "
        "and my email is user@example.com"
    )

    sanitized = sanitize_text(test_text)

    # Check sensitive data is redacted
    assert "[CREDIT_CARD_REDACTED]" in sanitized
    assert "[SSN_REDACTED]" in sanitized
    assert "[API_KEY_REDACTED]" in sanitized
    assert "[EMAIL_REDACTED]" in sanitized

    # Check original sensitive data is not present
    assert "4111-1111-1111-1111" not in sanitized
    assert "123-45-6789" not in sanitized
    assert "user@example.com" not in sanitized


def test_sanitize_json():
    """Test sanitizing JSON string with sensitive data"""
    test_json = '{"username": "testuser", "password": "secret123", "api_key": "sk-1234567890abcdef"}'

    sanitized = sanitize_json(test_json)

    # Parse the sanitized JSON
    import json
    sanitized_dict = json.loads(sanitized)

    # Check sensitive keys are redacted
    assert sanitized_dict["password"] == "[REDACTED]"
    assert sanitized_dict["api_key"] == "[REDACTED]"

    # Check non-sensitive data is preserved
    assert sanitized_dict["username"] == "testuser"


def test_safe_log_request_data_dict():
    """Test safe_log_request_data with dictionary input"""
    test_data = {"username": "testuser", "password": "secret123"}

    sanitized = safe_log_request_data(test_data)

    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["username"] == "testuser"


def test_safe_log_request_data_json():
    """Test safe_log_request_data with JSON string input"""
    test_json = '{"username": "testuser", "password": "secret123"}'

    sanitized = safe_log_request_data(test_json)

    # Verify it's a valid JSON string
    import json
    sanitized_dict = json.loads(sanitized)

    assert sanitized_dict["password"] == "[REDACTED]"
    assert sanitized_dict["username"] == "testuser"


def test_safe_log_request_data_text():
    """Test safe_log_request_data with plain text input"""
    test_text = "My credit card is 4111-1111-1111-1111"

    sanitized = safe_log_request_data(test_text)

    assert "[CREDIT_CARD_REDACTED]" in sanitized
    assert "4111-1111-1111-1111" not in sanitized
