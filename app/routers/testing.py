"""
DEVELOPMENT/TESTING ONLY ENDPOINTS
These endpoints bypass rate limits and security checks for development testing.
DO NOT INCLUDE IN PRODUCTION BUILDS.
"""

import os
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.auth import get_current_user
from app.db import get_db
from app.models import User, Conversation
from app import config
from app.app_config import SCENARIOS
from app.utils.url_helpers import clean_and_validate_url

# Only enable in development mode
IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"

logger = logging.getLogger(__name__)

# Security check - only create endpoints in development
if IS_DEV:
    router = APIRouter()
    
    @router.get("/test-call/{phone_number}")
    async def test_call_no_limits(
        phone_number: str,
        scenario: str = "default",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Make a call without rate limits or usage checks."""
        try:
            logger.info(f"🧪 TEST CALL: User {current_user.id} → {phone_number} [{scenario}]")
            
            # Get system phone number
            from_number = os.getenv('TWILIO_PHONE_NUMBER')
            if not from_number:
                raise HTTPException(
                    status_code=500,
                    detail="TWILIO_PHONE_NUMBER not configured"
                )

            # Validate scenario
            if scenario not in SCENARIOS:
                scenario = "default"

            # Create Twilio client
            client = Client(
                os.getenv('TWILIO_ACCOUNT_SID'),
                os.getenv('TWILIO_AUTH_TOKEN')
            )

            # Build URLs
            base_url = clean_and_validate_url(config.PUBLIC_URL)
            webhook_url = f"{base_url}/outgoing-call/{scenario}"
            status_callback_url = f"{base_url}/call-end-webhook"

            # Make the call
            call = client.calls.create(
                to=phone_number,
                from_=from_number,
                url=webhook_url,
                method='POST',
                status_callback=status_callback_url,
                status_callback_event=['completed']
            )

            # Create conversation record
            conversation = Conversation(
                user_id=current_user.id,
                scenario=scenario,
                phone_number=phone_number,
                direction="outbound",
                status="initiated",
                call_sid=call.sid,
                created_at=datetime.utcnow()
            )
            db.add(conversation)
            db.commit()

            return {
                "status": "✅ TEST CALL SUCCESS",
                "call_sid": call.sid,
                "phone_number": phone_number,
                "scenario": scenario,
                "from_number": from_number,
                "webhook_url": webhook_url,
                "message": f"🧪 Test call initiated to {phone_number} with no rate limits"
            }

        except TwilioRestException as e:
            logger.error(f"🧪 Twilio error: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Twilio error: {str(e)}")
        except Exception as e:
            logger.error(f"🧪 Test call error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Test call failed: {str(e)}")

    @router.post("/test-fast-call")
    async def test_fast_call(
        phone_number: str,
        scenario: str = "default",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Ultra-fast call endpoint for rapid testing."""
        try:
            from_number = os.getenv('TWILIO_PHONE_NUMBER')
            client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
            base_url = clean_and_validate_url(config.PUBLIC_URL)
            
            call = client.calls.create(
                to=phone_number,
                from_=from_number,
                url=f"{base_url}/outgoing-call/{scenario}",
                method='POST'
            )
            
            return {
                "call_sid": call.sid, 
                "status": "🚀 FAST CALL INITIATED",
                "phone_number": phone_number,
                "scenario": scenario,
                "message": "Rapid test call - no rate limits"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fast call failed: {str(e)}")

    @router.get("/test-scenarios")
    async def test_list_scenarios():
        """🧪 TESTING ONLY: List all available scenarios."""
        return {
            "available_scenarios": list(SCENARIOS.keys()),
            "total_scenarios": len(SCENARIOS),
            "scenarios": SCENARIOS,
            "message": "🧪 Available scenarios for testing"
        }

    @router.get("/test-config")
    async def test_config_check():
        """🧪 TESTING ONLY: Check configuration status."""
        return {
            "environment": "🧪 DEVELOPMENT",
            "development_mode": IS_DEV,
            "public_url": config.PUBLIC_URL,
            "twilio_configured": bool(os.getenv('TWILIO_ACCOUNT_SID')),
            "twilio_phone": os.getenv('TWILIO_PHONE_NUMBER', 'NOT_SET'),
            "openai_configured": bool(os.getenv('OPENAI_API_KEY')),
            "database_configured": bool(os.getenv('DATABASE_URL')),
            "encryption_key_set": bool(os.getenv('DATA_ENCRYPTION_KEY')),
            "recaptcha_configured": bool(os.getenv('RECAPTCHA_SECRET_KEY')),
            "message": "🧪 Configuration check complete"
        }

    @router.get("/test-user-info")
    async def test_user_info(current_user: User = Depends(get_current_user)):
        """🧪 TESTING ONLY: Get current user info."""
        return {
            "user_id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "is_admin": getattr(current_user, 'is_admin', False),
            "message": f"🧪 Logged in as {current_user.username}"
        }

else:
    # Production - create empty router
    router = APIRouter()
    logger.info("🔒 Testing endpoints disabled in production mode")
