import pytest
from fastapi.testclient import TestClient
from unittest import mock
from app.main import app
from fastapi import Request, status
import json

# Create a mock for realtime_manager to avoid shutdown errors
with mock.patch('app.main.realtime_manager', create=True) as mock_realtime_manager:
    # Mock the active_sessions attribute
    mock_realtime_manager.active_sessions = {}
    # Create a client with the mocked dependencies
    client = TestClient(app)


def test_global_exception_handler():
    """Test that the global exception handler returns a sanitized error message"""

    # Create a test endpoint that will raise an exception
    @app.get("/test-global-error")
    def test_error():
        raise Exception(
            "This is a sensitive error detail that should not be exposed")

    # Make a request to the endpoint that raises an exception
    response = client.get("/test-global-error")

    # Verify response shows a sanitized error message
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "detail": "An unexpected error occurred. Please try again later."}
    assert "This is a sensitive error detail" not in response.text


def test_validation_error_handler():
    """Test that validation errors provide useful information without exposing internals"""

    # Call an endpoint with invalid data that will trigger validation error
    response = client.post("/token", data={})

    # Verify response
    assert response.status_code == 422
    assert "detail" in response.json()
    assert "errors" in response.json()
    # Ensure each error has a field and message
    for error in response.json()["errors"]:
        assert "field" in error
        assert "message" in error


def test_custom_error_messages():
    """Test that custom error messages are used in endpoints"""

    # Mock a function that uses TestClient to raise an exception
    with mock.patch("app.main.get_twilio_client") as mock_get_client:
        mock_get_client.side_effect = Exception(
            "Internal Twilio error details")

        # Make outgoing call which should catch the exception
        response = client.get("/make-call/1234567890/default")

        # Verify sanitized error message
        assert response.status_code == 500
        assert "An error occurred while processing" in response.json()[
            "detail"]
        assert "Internal Twilio error details" not in response.text
