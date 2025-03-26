import pytest
from app.models import User, Token
from app.utils import verify_password


def test_register_user(client, db_session):
    """Test user registration."""
    user_data = {
        "email": "newuser@example.com",
        "password": "testpassword123"
    }

    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify user in database
    db_user = db_session.query(User).filter(
        User.email == user_data["email"]
    ).first()
    assert db_user is not None
    assert verify_password(user_data["password"], db_user.hashed_password)

    # Verify token in database
    db_token = db_session.query(Token).filter(
        Token.user_id == db_user.id
    ).first()
    assert db_token is not None
    assert db_token.access_token == data["access_token"]
    assert db_token.refresh_token == data["refresh_token"]
    assert db_token.token_type == "bearer"
    assert db_token.is_valid is True


def test_register_duplicate_email(client, test_user):
    """Test registering with an existing email."""
    user_data = {
        "email": "test@example.com",  # Same as test_user fixture
        "password": "newpassword123"
    }

    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


def test_login_success(client, test_user):
    """Test successful login."""
    login_data = {
        "username": "test@example.com",
        "password": "testpassword123"
    }

    response = client.post("/auth/login", data=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client, test_user):
    """Test login with invalid credentials."""
    login_data = {
        "username": "test@example.com",
        "password": "wrongpassword"
    }

    response = client.post("/auth/login", data=login_data)

    assert response.status_code == 401
    assert "Incorrect" in response.json()["detail"]


def test_protected_route_with_token(client, auth_headers):
    """Test accessing protected route with valid token."""
    response = client.get("/protected", headers=auth_headers)

    assert response.status_code == 200
    assert "message" in response.json()


def test_protected_route_without_token(client):
    """Test accessing protected route without token."""
    response = client.get("/protected")

    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


def test_get_current_user(client, auth_headers, test_user):
    """Test getting current user information."""
    response = client.get("/users/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["is_active"] == test_user.is_active


def test_update_user_name(client, auth_headers):
    """Test updating user name."""
    name_data = {
        "name": "John Doe"
    }

    response = client.post(
        "/update-user-name",
        json=name_data,
        headers=auth_headers
    )

    assert response.status_code == 200
    assert "User name updated" in response.json()["message"]


def test_token_expiration(client, auth_headers, mocker):
    """Test token expiration handling."""
    # Mock time to simulate token expiration
    mocker.patch("app.utils.datetime", autospec=True)
    mocker.patch("app.utils.datetime.utcnow").return_value = mocker.Mock(
        timestamp=lambda: 9999999999  # Far in the future
    )

    response = client.get("/protected", headers=auth_headers)

    assert response.status_code == 401
    assert "Token has expired" in response.json()["detail"]


def test_refresh_token(client, test_user):
    """Test refreshing access token."""
    # First login to get refresh token
    login_data = {
        "username": "test@example.com",
        "password": "testpassword123"
    }
    login_response = client.post("/auth/login", data=login_data)
    refresh_token = login_response.json()["refresh_token"]

    # Use refresh token to get new access token
    refresh_data = {
        "refresh_token": refresh_token
    }
    response = client.post("/auth/refresh", json=refresh_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
