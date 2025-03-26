import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db import Base, get_db
from app.models import User
from app.utils.password import get_password_hash
from app.realtime_manager import OpenAIRealtimeManager as RealtimeManager
import os

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session(engine):
    """Creates a fresh database session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        yield session
    finally:
        session.close()
        # Clear all tables after each test
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def test_user(db_session):
    """Creates a test user."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def client(db_session):
    """Creates a test client with database session override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client, test_user):
    """Creates authentication headers for test user."""
    # Reset limiter to avoid rate limits during testing
    from app.limiter import limiter
    limiter.reset()

    response = client.post(
        "/auth/login",
        data={
            "username": test_user.email,
            "password": "testpassword123"
        }
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def mock_twilio(mocker):
    """Mocks the Twilio client."""
    mock = mocker.patch("app.services.twilio_client.get_twilio_client")
    mock.return_value.transcripts.create.return_value.sid = "test_transcript_sid"
    mock.return_value.transcripts.get.return_value.data = "Test transcript content"
    return mock


@pytest.fixture(scope="function")
def mock_openai(mocker):
    """Mocks the OpenAI client."""
    mock = mocker.patch("openai.OpenAI")
    mock.return_value.audio.transcriptions.create.return_value.text = "Test transcription"
    return mock


@pytest.fixture(scope="function")
def realtime_manager():
    """Creates a test realtime manager."""
    return RealtimeManager()
