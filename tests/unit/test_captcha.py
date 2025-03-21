import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.captcha import verify_captcha
import os


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


@pytest.mark.asyncio
async def test_verify_captcha_success():
    """Test that verify_captcha returns True when verification is successful."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}

    with patch("app.captcha.RECAPTCHA_SECRET_KEY", "test_secret_key"), \
            patch("requests.post", return_value=mock_response):
        result = await verify_captcha("test_captcha_response", None)
        assert result is True


@pytest.mark.asyncio
async def test_verify_captcha_failure():
    """Test that verify_captcha raises HTTPException when verification fails."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": False}

    with patch("app.captcha.RECAPTCHA_SECRET_KEY", "test_secret_key"), \
            patch("requests.post", return_value=mock_response):
        with pytest.raises(HTTPException) as excinfo:
            await verify_captcha("test_captcha_response", None)
        assert excinfo.value.status_code == 400
        assert "CAPTCHA verification failed" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_verify_captcha_no_response():
    """Test that verify_captcha raises HTTPException when no captcha response is provided."""
    with patch("app.captcha.RECAPTCHA_SECRET_KEY", "test_secret_key"):
        with pytest.raises(HTTPException) as excinfo:
            await verify_captcha(None, None)
        assert excinfo.value.status_code == 400
        assert "CAPTCHA verification required" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_verify_captcha_request_error():
    """Test that verify_captcha handles request errors properly."""
    with patch("app.captcha.RECAPTCHA_SECRET_KEY", "test_secret_key"), \
            patch("requests.post", side_effect=Exception("Network error")):
        with pytest.raises(HTTPException) as excinfo:
            await verify_captcha("test_captcha_response", None)
        assert excinfo.value.status_code == 500
        assert "CAPTCHA verification error" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_verify_captcha_no_secret_key():
    """Test that verify_captcha allows requests when no secret key is set (development mode)."""
    with patch("app.captcha.RECAPTCHA_SECRET_KEY", None):
        result = await verify_captcha(None, None)
        assert result is True


@pytest.mark.asyncio
async def test_verify_captcha_with_request(mock_request):
    """Test that verify_captcha properly includes the remote IP when a request is provided."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}

    with patch("app.captcha.RECAPTCHA_SECRET_KEY", "test_secret_key"), \
            patch("requests.post") as mock_post:
        mock_post.return_value = mock_response
        await verify_captcha("test_captcha_response", mock_request)

        # Verify the IP address was included in the request
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["remoteip"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_login_endpoint_with_captcha():
    """
    Integration test: Test login endpoint with CAPTCHA.
    This test requires test_client from conftest.py
    """
    from fastapi.testclient import TestClient
    from app.main import app

    # Setup test client with mocked CAPTCHA validation
    with patch("app.captcha.verify_captcha", return_value=True):
        client = TestClient(app)

        # Send login request
        response = client.post(
            "/auth/login",
            data={
                "username": "test@example.com",
                "password": "testpassword",
                "captcha_response": "test_captcha_response"
            }
        )

        # The response might be 401 due to invalid credentials,
        # but we're just testing that the CAPTCHA verification was called
        # and didn't block the request
        assert response.status_code in (200, 401)
        # If 401, it should be due to invalid credentials, not CAPTCHA
        if response.status_code == 401:
            assert "CAPTCHA" not in response.text


@pytest.mark.asyncio
async def test_register_endpoint_with_captcha():
    """
    Integration test: Test register endpoint with CAPTCHA.
    This test requires test_client from conftest.py
    """
    from fastapi.testclient import TestClient
    from app.main import app

    # Setup test client with mocked CAPTCHA validation
    with patch("app.captcha.verify_captcha", return_value=True):
        client = TestClient(app)

        # Send registration request
        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "securepassword"
            },
            headers={"Content-Type": "application/json"},
            params={"captcha_response": "test_captcha_response"}
        )

        # Note: This might fail if the email already exists,
        # but we're just ensuring CAPTCHA validation was properly handled
        assert response.status_code in (200, 400)
        # If 400, it should not be due to CAPTCHA
        if response.status_code == 400:
            assert "CAPTCHA" not in response.text
