import pytest
from fastapi.testclient import TestClient
from unittest import mock
from app.main import app


def test_security_headers():
    """Test that security headers are properly set in the response"""
    with mock.patch('app.main.realtime_manager', create=True) as mock_realtime_manager:
        # Mock the active_sessions attribute for the realtime manager
        mock_realtime_manager.active_sessions = {}

        # Create a client with the mocked dependencies
        client = TestClient(app)

        # Make a request to a simple endpoint
        response = client.get("/test")

        # Check that security headers are present
        assert "X-XSS-Protection" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "Referrer-Policy" in response.headers

        # Verify header values
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_csp_header():
    """Test that Content-Security-Policy header is properly set"""
    with mock.patch('app.main.realtime_manager', create=True) as mock_realtime_manager:
        # Mock the active_sessions attribute
        mock_realtime_manager.active_sessions = {}

        # Create a client
        client = TestClient(app)

        # Make a request
        response = client.get("/test")

        # Check that CSP header is present
        assert "Content-Security-Policy" in response.headers

        # Verify that the CSP header contains expected directives
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "style-src" in csp
        assert "connect-src" in csp
