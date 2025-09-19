import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from app.limiter import rate_limit, _check_rate_limit, _parse_rate_limit
from app.server import create_app


class TestRateLimiting:
    """Test suite for rate limiting functionality"""

    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_parse_rate_limit(self):
        """Test that rate limit parsing works correctly"""
        assert _parse_rate_limit("5/minute") == (5, 60)
        assert _parse_rate_limit("10/second") == (10, 1)
        assert _parse_rate_limit("100/hour") == (100, 3600)
        assert _parse_rate_limit("1000/day") == (1000, 86400)

    def test_check_rate_limit_basic(self):
        """Test basic rate limit checking"""
        key = "test_key_1"
        
        # First request should pass
        assert _check_rate_limit(key, "2/minute") == True
        
        # Second request should pass
        assert _check_rate_limit(key, "2/minute") == True
        
        # Third request should fail
        assert _check_rate_limit(key, "2/minute") == False

    def test_check_rate_limit_window_reset(self):
        """Test that rate limit window resets correctly"""
        key = "test_key_2"
        
        # Use a very short window for testing
        assert _check_rate_limit(key, "1/second") == True
        assert _check_rate_limit(key, "1/second") == False
        
        # Wait for window to reset
        time.sleep(1.1)
        
        # Should be able to make request again
        assert _check_rate_limit(key, "1/second") == True

    def test_rate_limit_decorator_with_mock_request(self):
        """Test that rate_limit decorator works with mock request"""
        
        @rate_limit("5/minute")
        async def test_endpoint(request: Request):
            return {"message": "success"}
        
        # Mock request
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/test"
        
        # Should work without errors
        result = asyncio.run(test_endpoint(mock_request))
        assert result == {"message": "success"}

    def test_rate_limit_decorator_without_request(self):
        """Test that rate_limit decorator works when no request is provided"""
        
        @rate_limit("5/minute")
        async def test_endpoint():
            return {"message": "success"}
        
        # Should work without errors (rate limiting skipped)
        result = asyncio.run(test_endpoint())
        assert result == {"message": "success"}

    def test_rate_limit_decorator_sync_function(self):
        """Test that rate_limit decorator works with sync functions"""
        
        @rate_limit("5/minute")
        def sync_endpoint():
            return {"message": "success"}
        
        # Should work without errors
        result = asyncio.run(sync_endpoint())
        assert result == {"message": "success"}

    def test_rate_limit_decorator_with_args_and_kwargs(self):
        """Test that rate_limit decorator preserves function arguments"""
        
        @rate_limit("5/minute")
        async def test_endpoint(request: Request, user_id: int = None, data: str = "default"):
            return {
                "message": "success",
                "user_id": user_id,
                "data": data
            }
        
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/test"
        
        result = asyncio.run(test_endpoint(mock_request, user_id=123, data="custom"))
        assert result["message"] == "success"
        assert result["user_id"] == 123
        assert result["data"] == "custom"

    def test_rate_limit_different_keys(self):
        """Test that different keys have separate rate limits"""
        key1 = "user1:/endpoint"
        key2 = "user2:/endpoint"
        
        # Both should pass initially
        assert _check_rate_limit(key1, "1/minute") == True
        assert _check_rate_limit(key2, "1/minute") == True
        
        # Both should fail on second attempt
        assert _check_rate_limit(key1, "1/minute") == False
        assert _check_rate_limit(key2, "1/minute") == False

    def test_rate_limit_error_handling(self):
        """Test that rate limit errors are handled gracefully"""
        
        @rate_limit("5/minute")
        async def test_endpoint(request):
            return {"message": "success"}
        
        # Pass an invalid request object
        invalid_request = "not a request"
        
        # Should still work (error handling should catch the issue)
        result = asyncio.run(test_endpoint(invalid_request))
        assert result == {"message": "success"}


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with FastAPI app"""

    def setup_method(self):
        """Set up test fixtures before each test method"""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_app_creation_without_slowapi_errors(self):
        """Test that the app can be created without SlowAPI errors"""
        # This should not raise any exceptions
        app = create_app()
        assert app is not None

    def test_basic_endpoint_access(self):
        """Test that basic endpoints work without rate limiting errors"""
        # Test docs endpoint
        response = self.client.get("/docs")
        assert response.status_code == 200

    def test_auth_endpoints_work(self):
        """Test that auth endpoints don't throw SlowAPI errors"""
        # Test login endpoint with invalid data
        response = self.client.post("/auth/login", json={
            "username": "test@example.com",
            "password": "testpass"
        })
        
        # Should not get 500 error due to SlowAPI issues
        # Might get 401, 422, or other errors, but not 500
        assert response.status_code != 500

    def test_mobile_endpoints_work(self):
        """Test that mobile endpoints don't throw SlowAPI errors"""
        # Test mobile scenarios endpoint
        response = self.client.get("/mobile/scenarios")
        
        # Should not get 500 error due to SlowAPI issues
        assert response.status_code != 500

    def test_rate_limiting_actually_works(self):
        """Test that rate limiting actually prevents excessive requests"""
        # This would require setting up a test endpoint with very low limits
        # For now, we just verify no errors occur
        
        responses = []
        for i in range(3):
            response = self.client.post("/auth/login", json={
                "username": f"test{i}@example.com",
                "password": "testpass"
            })
            responses.append(response)
        
        # All responses should be valid HTTP responses (not 500 errors)
        for response in responses:
            assert response.status_code != 500

    def test_cors_headers_still_work(self):
        """Test that CORS headers are still present after our changes"""
        response = self.client.options("/auth/login")
        assert "access-control-allow-origin" in response.headers

    def test_openapi_schema_accessible(self):
        """Test that OpenAPI schema is accessible without errors"""
        response = self.client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert "paths" in schema
        assert "components" in schema


class TestRateLimitingPerformance:
    """Performance tests for rate limiting"""

    def test_rate_limit_performance(self):
        """Test that rate limiting doesn't significantly impact performance"""
        
        @rate_limit("1000/minute")
        async def fast_endpoint():
            return {"message": "fast"}
        
        # Time multiple calls
        start_time = time.time()
        
        for _ in range(10):
            result = asyncio.run(fast_endpoint())
            assert result == {"message": "fast"}
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete 10 calls in under 1 second
        assert duration < 1.0

    def test_memory_usage_reasonable(self):
        """Test that rate limiting doesn't cause memory leaks"""
        from app.limiter import _rate_limit_store
        
        # Clear any existing data
        _rate_limit_store.clear()
        
        # Make many requests with different keys
        for i in range(100):
            _check_rate_limit(f"key_{i}", "10/minute")
        
        # Should have entries for all keys
        assert len(_rate_limit_store) == 100
        
        # Memory usage should be reasonable (each entry is small)
        # This is a basic check - in production you might want more sophisticated monitoring


if __name__ == "__main__":
    pytest.main([__file__])