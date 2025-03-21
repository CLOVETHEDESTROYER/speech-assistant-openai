import pytest
from fastapi import status
from app.limiter import limiter


def test_login_endpoint_rate_limit(client, test_user):
    """Test that the login endpoint enforces rate limits."""
    # Reset limiter for this test
    limiter.reset()

    # Login data
    login_data = {
        "username": "test@example.com",
        "password": "testpassword123"
    }

    # Make successful requests up to the limit (5/minute)
    responses = []
    for _ in range(5):
        response = client.post("/auth/login", data=login_data)
        responses.append(response)

    # All the first 5 requests should succeed
    for response in responses:
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    # The 6th request should be rate limited
    rate_limited_response = client.post("/auth/login", data=login_data)
    assert rate_limited_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in rate_limited_response.text


def test_protected_endpoint_rate_limit(client, auth_headers):
    """Test that a protected endpoint enforces rate limits."""
    # Reset limiter for this test
    limiter.reset()

    # Add rate limiting to the /protected endpoint (done in conftest)
    # Make successful requests up to the limit (5/minute)
    responses = []
    for _ in range(5):
        response = client.get("/protected", headers=auth_headers)
        responses.append(response)

    # All the first 5 requests should succeed
    for response in responses:
        assert response.status_code == status.HTTP_200_OK

    # The 6th request should be rate limited
    rate_limited_response = client.get("/protected", headers=auth_headers)
    assert rate_limited_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in rate_limited_response.text


def test_refresh_token_rate_limit(client, auth_headers):
    """Test that the refresh token endpoint enforces rate limits of 10/minute."""
    # Reset limiter for this test
    limiter.reset()

    # Get a refresh token first
    login_data = {
        "username": "test@example.com",
        "password": "testpassword123"
    }
    login_response = client.post("/auth/login", data=login_data)
    refresh_token = login_response.json()["refresh_token"]

    # Make successful requests up to the limit (10/minute)
    responses = []
    for _ in range(10):
        # We expect these to fail with 401 since we're not properly setting up the refresh token
        # mechanism in tests, but they should still count against rate limit
        response = client.post(
            "/auth/refresh", cookies={"token": refresh_token})
        responses.append(response)

    # The 11th request should be rate limited
    rate_limited_response = client.post(
        "/auth/refresh", cookies={"token": refresh_token})
    assert rate_limited_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in rate_limited_response.text
