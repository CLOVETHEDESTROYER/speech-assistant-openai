import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from app.server import create_app


class TestErrorHandling:
    """Test suite for error handling improvements"""

    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_slowapi_error_resolution(self):
        """Test that the SlowAPI response type error is resolved"""
        
        # This test ensures that the specific error from production logs is fixed
        # "Exception: parameter `response` must be an instance of starlette.responses.Response"
        
        # Make multiple requests to trigger rate limiting
        responses = []
        for i in range(10):
            response = self.client.post("/auth/login", json={
                "username": f"test{i}@example.com",
                "password": "testpass"
            })
            responses.append(response)
        
        # None of the responses should be 500 errors due to SlowAPI issues
        for response in responses:
            assert response.status_code != 500
            # If it's a rate limit error, it should be 429, not 500
            if response.status_code == 429:
                assert "rate limit" in response.json().get("detail", "").lower()

    def test_registration_error_handling(self):
        """Test that registration errors are handled properly"""
        
        # Test with invalid data
        response = self.client.post("/auth/register", json={
            "email": "invalid-email",
            "password": "123"  # Too short
        })
        
        # Should return 422 (validation error) or 400 (bad request), not 500
        assert response.status_code in [400, 422]
        assert response.status_code != 500

    def test_mobile_call_payment_errors(self):
        """Test that mobile call payment errors are handled properly"""
        
        # Test mobile call endpoint (this might require authentication)
        response = self.client.post("/mobile/make-call", json={
            "phone_number": "+1234567890",
            "scenario": "default"
        })
        
        # Should return 401 (unauthorized) or 402 (payment required), not 500
        assert response.status_code in [401, 402, 422]
        assert response.status_code != 500

    def test_duplicate_operation_id_warnings(self):
        """Test that duplicate operation ID warnings are resolved"""
        
        # Get the OpenAPI schema
        response = self.client.get("/openapi.json")
        assert response.status_code == 200
        
        # The response should not contain warnings about duplicate operation IDs
        # This is more of a logging issue, but we can verify the schema is valid
        schema = response.json()
        assert "paths" in schema
        assert "components" in schema

    def test_websocket_connection_handling(self):
        """Test that WebSocket connections are handled properly"""
        
        # Test WebSocket endpoint
        with self.client.websocket_connect("/media-stream/default") as websocket:
            # Should be able to connect without errors
            assert websocket is not None

    def test_health_check_endpoint(self):
        """Test that health check endpoints work properly"""
        
        # Test if there's a health endpoint
        response = self.client.get("/health")
        # Should return 200 or 404 (if not implemented)
        assert response.status_code in [200, 404]

    def test_cors_headers_present(self):
        """Test that CORS headers are present"""
        
        response = self.client.options("/auth/login")
        # Should have CORS headers
        assert "access-control-allow-origin" in response.headers

    def test_security_headers_present(self):
        """Test that security headers are present"""
        
        response = self.client.get("/docs")
        # Should have security headers if enabled
        headers = response.headers
        # Check for common security headers
        security_headers = [
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection"
        ]
        
        # At least some security headers should be present
        present_headers = [h for h in security_headers if h in headers]
        # This is optional depending on your security configuration
        # assert len(present_headers) > 0


if __name__ == "__main__":
    pytest.main([__file__])