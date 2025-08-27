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
            "email": current_user.email,
            "is_admin": getattr(current_user, 'is_admin', False),
            "message": f"🧪 Logged in as user {current_user.id}"
        }

    @router.get("/test-sms-bot")
    async def test_sms_bot(
        message: str,
        phone_number: str = "+1234567890",
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test SMS bot response without Twilio."""
        try:
            from app.services.sms_service import SMSService
            from app.services.sms_ai_service import SMSAIService
            
            sms_service = SMSService()
            ai_service = SMSAIService()
            
            # Get or create test conversation
            conversation = await sms_service.get_or_create_conversation(
                phone_number, os.getenv('TWILIO_PHONE_NUMBER', '+18557480210'), db
            )
            
            # Get conversation context
            context = sms_service._get_conversation_context(conversation.id, db)
            customer_info = sms_service._extract_customer_info(conversation)
            
            # Generate AI response
            ai_result = await ai_service.generate_response(message, context, customer_info)
            
            return {
                "status": "✅ SMS BOT TEST SUCCESS",
                "input_message": message,
                "ai_response": ai_result["response"],
                "intent_detected": ai_result.get("intent"),
                "sentiment_score": ai_result.get("sentiment_score"),
                "entities": ai_result.get("entities", {}),
                "conversation_id": conversation.id,
                "context_messages": len(context),
                "lead_score": conversation.lead_score,
                "message": "🤖 SMS bot test completed successfully"
            }
            
        except Exception as e:
            logger.error(f"🧪 SMS bot test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"SMS bot test failed: {str(e)}")

    @router.get("/test-sms-calendar")
    async def test_sms_calendar(
        message: str,
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test SMS calendar parsing and booking."""
        try:
            from app.services.sms_calendar_service import SMSCalendarService
            
            calendar_service = SMSCalendarService()
            
            # Parse datetime from message
            parsed_datetime = await calendar_service.parse_datetime_from_message(message)
            
            if parsed_datetime:
                # Check availability
                availability = await calendar_service.check_availability(parsed_datetime)
                
                return {
                    "status": "✅ CALENDAR TEST SUCCESS",
                    "input_message": message,
                    "parsed_datetime": parsed_datetime.isoformat() if parsed_datetime else None,
                    "availability": availability,
                    "formatted_response": calendar_service.format_availability_response(
                        availability, 
                        parsed_datetime.strftime('%A at %I:%M %p') if parsed_datetime else message
                    ),
                    "message": "📅 Calendar parsing test completed"
                }
            else:
                return {
                    "status": "⚠️ CALENDAR PARSE FAILED",
                    "input_message": message,
                    "parsed_datetime": None,
                    "message": "Could not parse date/time from message",
                    "suggestion": "Try: 'tomorrow at 2pm', 'Friday morning', 'next Tuesday 3:30'"
                }
            
        except Exception as e:
            logger.error(f"🧪 SMS calendar test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Calendar test failed: {str(e)}")

    @router.get("/test-sms-stats")
    async def test_sms_stats(db: Session = Depends(get_db)):
        """🧪 TESTING ONLY: Get SMS bot statistics."""
        try:
            from app.services.sms_service import SMSService
            
            sms_service = SMSService()
            stats = sms_service.get_conversation_stats(db)
            
            return {
                "status": "✅ SMS STATS SUCCESS",
                "stats": stats,
                "message": "📊 SMS statistics retrieved successfully"
            }
            
        except Exception as e:
            logger.error(f"🧪 SMS stats test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Stats test failed: {str(e)}")

    @router.post("/test-send-sms")
    async def test_send_sms(
        to_number: str,
        message: str,
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Send actual SMS via Twilio."""
        try:
            from app.services.sms_service import SMSService
            
            sms_service = SMSService()
            from_number = os.getenv('TWILIO_PHONE_NUMBER')
            
            if not from_number:
                raise HTTPException(status_code=500, detail="TWILIO_PHONE_NUMBER not configured")
            
            # Send SMS
            success = await sms_service.send_sms_response(from_number, to_number, message)
            
            if success:
                return {
                    "status": "✅ SMS SENT SUCCESS",
                    "to_number": to_number,
                    "from_number": from_number,
                    "message": message,
                    "result": "SMS sent successfully via Twilio"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to send SMS")
                
        except Exception as e:
            logger.error(f"🧪 SMS send test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"SMS send test failed: {str(e)}")

    @router.get("/test-sms-config")
    async def test_sms_config():
        """🧪 TESTING ONLY: Check SMS bot configuration."""
        return {
            "status": "✅ SMS CONFIG CHECK",
            "sms_bot_enabled": os.getenv("SMS_BOT_ENABLED", "true").lower() == "true",
            "twilio_phone": os.getenv('TWILIO_PHONE_NUMBER', 'NOT_SET'),
            "notification_phone": os.getenv("SMS_NOTIFICATION_PHONE", "NOT_SET"),
            "rate_limit": os.getenv("SMS_RATE_LIMIT_PER_HOUR", "30"),
            "conversation_timeout": os.getenv("SMS_CONVERSATION_TIMEOUT_HOURS", "24"),
            "calendar_integration": os.getenv("SMS_CALENDAR_INTEGRATION", "true").lower() == "true",
            "lead_scoring": os.getenv("SMS_LEAD_SCORING_ENABLED", "true").lower() == "true",
            "business_hours_only": os.getenv("SMS_BUSINESS_HOURS_ONLY", "false").lower() == "true",
            "message": "🤖 SMS bot configuration check complete"
        }
    
    @router.post("/test-user-business-config")
    async def test_create_user_business_config(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Create default business config for current user."""
        try:
            from app.services.user_sms_service import UserSMSService
            
            user_sms_service = UserSMSService(current_user.id)
            business_config = await user_sms_service.get_or_create_business_config(db)
            
            return {
                "status": "✅ USER BUSINESS CONFIG TEST SUCCESS",
                "user_id": current_user.id,
                "company_name": business_config.company_name,
                "bot_name": business_config.bot_name,
                "webhook_url": f"http://localhost:5051/sms/{current_user.id}/webhook",
                "sms_enabled": business_config.sms_enabled,
                "plan": business_config.sms_plan.value,
                "monthly_limit": business_config.monthly_conversation_limit,
                "message": "🏢 Business config created/retrieved successfully"
            }
            
        except Exception as e:
            logger.error(f"🧪 User business config test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Business config test failed: {str(e)}")
    
    @router.get("/test-user-sms-bot")
    async def test_user_sms_bot(
        message: str,
        phone_number: str = "+1234567890",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test user-specific SMS bot response."""
        try:
            from app.services.user_sms_service import UserSMSService
            
            user_sms_service = UserSMSService(current_user.id)
            business_config = await user_sms_service.get_or_create_business_config(db)
            
            # Get or create conversation
            conversation = await user_sms_service.get_or_create_conversation(
                phone_number, 
                os.getenv('TWILIO_PHONE_NUMBER', '+18557480210'), 
                db
            )
            
            # Get context and generate response
            context = user_sms_service._get_conversation_context(conversation.id, db)
            ai_response = await user_sms_service._generate_business_response(
                message, context, business_config
            )
            
            return {
                "status": "✅ USER SMS BOT TEST SUCCESS",
                "user_id": current_user.id,
                "company_name": business_config.company_name,
                "bot_name": business_config.bot_name,
                "input_message": message,
                "ai_response": ai_response,
                "conversation_id": conversation.id,
                "context_messages": len(context),
                "webhook_url": f"http://localhost:5051/sms/{current_user.id}/webhook",
                "message": "🤖 User-specific SMS bot test completed successfully"
            }

        except Exception as e:
            logger.error(f"🧪 User SMS bot test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"User SMS bot test failed: {str(e)}")
    
    @router.get("/test-user-usage-stats")
    async def test_user_usage_stats(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Get user SMS usage statistics."""
        try:
            from app.services.user_sms_service import UserSMSService
            
            user_sms_service = UserSMSService(current_user.id)
            usage_stats = user_sms_service.get_usage_stats(db)
            
            return {
                "status": "✅ USER USAGE STATS TEST SUCCESS",
                "usage_stats": usage_stats,
                "message": "📊 User usage statistics retrieved successfully"
            }
            
        except Exception as e:
            logger.error(f"🧪 User usage stats test error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Usage stats test failed: {str(e)}")
    
    @router.post("/test-simulate-user-sms-webhook")
    async def test_simulate_user_sms_webhook(
        user_id: int,
        message: str,
        from_phone: str = "+1234567890",
        to_phone: str = None,
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Simulate SMS webhook for specific user."""
        try:
            from app.services.user_sms_service import UserSMSService
            import uuid
            
            if not to_phone:
                to_phone = os.getenv('TWILIO_PHONE_NUMBER', '+18557480210')
            
            # Simulate SMS processing
            user_sms_service = UserSMSService(user_id)
            fake_message_sid = f"test_{uuid.uuid4().hex[:10]}"
            
            result = await user_sms_service.handle_incoming_sms(
                from_number=from_phone,
                to_number=to_phone,
                body=message,
                message_sid=fake_message_sid,
                db=db
            )
            
            return {
                "status": "✅ USER SMS WEBHOOK SIMULATION SUCCESS",
                "user_id": user_id,
                "simulation_result": result,
                "webhook_url": f"http://localhost:5051/sms/{user_id}/webhook",
                "message": "📱 SMS webhook simulation completed successfully"
            }
            
        except Exception as e:
            logger.error(f"🧪 User SMS webhook simulation error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"SMS webhook simulation failed: {str(e)}")

else:
    # Production - create empty router
    router = APIRouter()
    logger.info("🔒 Testing endpoints disabled in production mode")
