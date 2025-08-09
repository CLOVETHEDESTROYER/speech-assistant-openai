import logging
import os
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException, TwilioException
from app.utils.twilio_helpers import TwilioAuthError, TwilioApiError
from app.db import SessionLocal
from app.models import ProviderCredentials
from app.utils.crypto import decrypt_string

logger = logging.getLogger(__name__)


class TwilioClientService:
    """
    Singleton service for Twilio client management.
    Ensures only one client instance is created and properly initialized.
    """
    _instance: Optional['TwilioClientService'] = None
    _client: Optional[Client] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TwilioClientService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Only initialize once
        if self._initialized:
            return

        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.phone_number = os.getenv('TWILIO_PHONE_NUMBER')

        if not self.account_sid or not self.auth_token:
            logger.warning(
                "Twilio credentials not properly configured. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables.")

        if not self.phone_number:
            logger.warning(
                "Twilio phone number not configured. Check TWILIO_PHONE_NUMBER environment variable.")

        self._client = None
        self._initialized = True

        # Initialize the client
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the Twilio client with proper error handling"""
        if not self.account_sid or not self.auth_token:
            logger.error(
                "Cannot initialize Twilio client: Missing credentials")
            return

        try:
            self._client = Client(self.account_sid, self.auth_token)
            # Validate credentials with a simple API call
            self._client.api.accounts(self.account_sid).fetch()
            logger.info("Twilio client initialized successfully")
        except TwilioRestException as e:
            if e.status == 401:
                logger.error(f"Twilio authentication failed: {e}")
                raise TwilioAuthError(f"Twilio authentication failed: {e}",
                                      status_code=e.status,
                                      twilio_code=e.code)
            else:
                logger.error(f"Error initializing Twilio client: {e}")
                raise TwilioApiError(f"Error initializing Twilio client: {e}",
                                     status_code=e.status,
                                     twilio_code=e.code)
        except Exception as e:
            logger.error(f"Unexpected error initializing Twilio client: {e}")
            raise TwilioApiError(
                f"Unexpected error initializing Twilio client: {e}")

    @property
    def client(self) -> Client:
        """
        Get the Twilio client instance.

        Returns:
            Initialized Twilio client

        Raises:
            TwilioApiError: If client initialization failed
        """
        if self._client is None:
            self._init_client()

        if self._client is None:
            raise TwilioApiError("Twilio client is not initialized")

        return self._client

    def refresh_client(self) -> None:
        """
        Force refresh the Twilio client.
        Useful after credential updates or when experiencing authentication issues.
        """
        self._client = None
        self._init_client()

    def set_user_context(self, user_id: int) -> None:
        """Optionally set client credentials from a user's stored provider credentials."""
        try:
            db = SessionLocal()
            creds = db.query(ProviderCredentials).filter(ProviderCredentials.user_id == user_id).first()
            if not creds:
                return
            # Decrypt values if present; fall back to existing env values when missing
            self.account_sid = decrypt_string(creds.twilio_account_sid) if creds.twilio_account_sid else self.account_sid
            self.auth_token = decrypt_string(creds.twilio_auth_token) if creds.twilio_auth_token else self.auth_token
            self.phone_number = decrypt_string(creds.twilio_phone_number) if creds.twilio_phone_number else self.phone_number
            self.refresh_client()
        except Exception as e:
            logger.warning(f"Failed to load user provider credentials: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def validate_connection(self) -> bool:
        """
        Validate the Twilio client connection.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            if self._client is None:
                return False

            # Make a simple API call to validate the connection
            self._client.api.accounts(self.account_sid).fetch()
            return True
        except Exception as e:
            logger.warning(f"Twilio connection validation failed: {e}")
            return False

    @property
    def phone_number(self) -> str:
        """Get the Twilio phone number."""
        return self._phone_number

    @phone_number.setter
    def phone_number(self, value: str):
        """Set the Twilio phone number."""
        self._phone_number = value


# Create a singleton instance
twilio_client_service = TwilioClientService()


def get_twilio_client() -> Client:
    """
    Get the Twilio client instance.

    Returns:
        Initialized Twilio client

    Raises:
        TwilioApiError: If client initialization failed
    """
    return twilio_client_service.client
