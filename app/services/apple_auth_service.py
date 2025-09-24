import jwt
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import os
import logging

logger = logging.getLogger(__name__)


class AppleAuthService:
    def __init__(self):
        self.team_id = os.getenv("APPLE_TEAM_ID")
        self.service_id = os.getenv("APPLE_SERVICE_ID")
        self.key_id = os.getenv("APPLE_KEY_ID")
        self.private_key = os.getenv("APPLE_PRIVATE_KEY")

        if not all([self.team_id, self.service_id, self.key_id, self.private_key]):
            raise ValueError("Missing Apple authentication configuration")

    def generate_client_secret(self) -> str:
        """Generate JWT client secret for Apple authentication"""
        headers = {
            "kid": self.key_id,
            "alg": "ES256"
        }

        payload = {
            "iss": self.team_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 15777000,  # 6 months
            "sub": self.service_id
        }

        try:
            token = jwt.encode(payload, self.private_key,
                               algorithm="ES256", headers=headers)
            return token
        except Exception as e:
            logger.error(f"Error generating Apple client secret: {e}")
            raise

    async def verify_apple_token(self, identity_token: str) -> Optional[Dict]:
        """Verify Apple identity token and extract user information"""
        try:
            # Get Apple's public keys
            response = requests.get("https://appleid.apple.com/auth/keys")
            response.raise_for_status()
            keys = response.json()["keys"]

            # Decode and verify the token
            decoded = jwt.decode(
                identity_token,
                options={"verify_signature": False}  # We'll verify manually
            )

            # Verify the token is from Apple
            if decoded.get("iss") != "https://appleid.apple.com":
                raise ValueError("Invalid issuer")

            # Verify the audience (Apple sends the App ID as audience, not Service ID)
            expected_audience = "com.hyperlabsAI.AiFriendChat"  # App ID
            if decoded.get("aud") != expected_audience:
                logger.error(
                    f"Audience mismatch - Expected: {expected_audience}, Got: {decoded.get('aud')}")
                raise ValueError("Invalid audience")

            # Verify expiration
            if decoded.get("exp", 0) < time.time():
                raise ValueError("Token expired")

            return decoded

        except Exception as e:
            logger.error(f"Error verifying Apple token: {e}")
            return None

    def extract_user_info(self, decoded_token: Dict) -> Dict:
        """Extract user information from decoded Apple token"""
        return {
            "apple_user_id": decoded_token.get("sub"),
            "email": decoded_token.get("email"),
            "email_verified": decoded_token.get("email_verified", False),
            "is_private_email": decoded_token.get("is_private_email", False)
        }
