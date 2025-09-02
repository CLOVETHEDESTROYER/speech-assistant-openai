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
from app.models import User, Conversation, GoogleCalendarCredentials
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
            logger.info(
                f"🧪 TEST CALL: User {current_user.id} → {phone_number} [{scenario}]")

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
            raise HTTPException(
                status_code=400, detail=f"Twilio error: {str(e)}")
        except Exception as e:
            logger.error(f"🧪 Test call error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Test call failed: {str(e)}")

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
            client = Client(os.getenv('TWILIO_ACCOUNT_SID'),
                            os.getenv('TWILIO_AUTH_TOKEN'))
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
            raise HTTPException(
                status_code=500, detail=f"Fast call failed: {str(e)}")

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
                phone_number, os.getenv(
                    'TWILIO_PHONE_NUMBER', '+18557480210'), db
            )

            # Get conversation context
            context = sms_service._get_conversation_context(
                conversation.id, db)
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
            raise HTTPException(
                status_code=500, detail=f"SMS bot test failed: {str(e)}")

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
                        parsed_datetime.strftime(
                            '%A at %I:%M %p') if parsed_datetime else message
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
            raise HTTPException(
                status_code=500, detail=f"Calendar test failed: {str(e)}")

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
            raise HTTPException(
                status_code=500, detail=f"Stats test failed: {str(e)}")

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
                raise HTTPException(
                    status_code=500, detail="TWILIO_PHONE_NUMBER not configured")

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
                raise HTTPException(
                    status_code=500, detail="Failed to send SMS")

        except Exception as e:
            logger.error(f"🧪 SMS send test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"SMS send test failed: {str(e)}")

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
            raise HTTPException(
                status_code=500, detail=f"Business config test failed: {str(e)}")

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
            context = user_sms_service._get_conversation_context(
                conversation.id, db)
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
            raise HTTPException(
                status_code=500, detail=f"User SMS bot test failed: {str(e)}")

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
            raise HTTPException(
                status_code=500, detail=f"Usage stats test failed: {str(e)}")

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
            raise HTTPException(
                status_code=500, detail=f"SMS webhook simulation failed: {str(e)}")

    # =================================================================
    # PHASE 1: UNIFIED CALENDAR SERVICE TESTING ENDPOINTS
    # =================================================================

    @router.get("/test-unified-calendar-config")
    async def test_unified_calendar_config():
        """🧪 TESTING ONLY: Check Unified Calendar Service configuration."""
        try:
            return {
                "status": "✅ UNIFIED CALENDAR CONFIG CHECK",
                "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "NOT_SET")[:20] + "..." if os.getenv("GOOGLE_CLIENT_ID") else "NOT_SET",
                "google_client_secret": "SET" if os.getenv("GOOGLE_CLIENT_SECRET") else "NOT_SET",
                "google_redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "NOT_SET"),
                "data_encryption_key": "SET" if os.getenv("DATA_ENCRYPTION_KEY") else "NOT_SET",
                "environment_status": {
                    "all_required_vars": all([
                        os.getenv("GOOGLE_CLIENT_ID"),
                        os.getenv("GOOGLE_CLIENT_SECRET"),
                        os.getenv("GOOGLE_REDIRECT_URI"),
                        os.getenv("DATA_ENCRYPTION_KEY")
                    ])
                },
                "message": "📅 Unified Calendar Service configuration status check"
            }
        except Exception as e:
            logger.error(f"🧪 Unified Calendar config test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar config test failed: {str(e)}")

    @router.get("/test-unified-calendar-credentials")
    async def test_unified_calendar_credentials(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Check if user has Google Calendar credentials for Unified Service."""
        try:
            from app.models import GoogleCalendarCredentials

            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == current_user.id
            ).first()

            if credentials:
                return {
                    "status": "✅ UNIFIED CALENDAR CREDENTIALS FOUND",
                    "user_id": current_user.id,
                    "has_token": bool(credentials.token),
                    "has_refresh_token": bool(credentials.refresh_token),
                    "token_expiry": credentials.token_expiry.isoformat() if credentials.token_expiry else None,
                    "created_at": credentials.created_at.isoformat() if credentials.created_at else None,
                    "updated_at": credentials.updated_at.isoformat() if credentials.updated_at else None,
                    "message": "📅 User has Google Calendar credentials for Unified Service"
                }
            else:
                return {
                    "status": "⚠️ NO UNIFIED CALENDAR CREDENTIALS",
                    "user_id": current_user.id,
                    "message": "📅 User needs to authenticate with Google Calendar",
                    "next_step": "Visit /google-calendar/auth to authenticate"
                }

        except Exception as e:
            logger.error(
                f"🧪 Unified Calendar credentials test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar credentials test failed: {str(e)}")

    @router.get("/test-unified-calendar-read")
    async def test_unified_calendar_read(
        max_results: int = 5,
        days_ahead: int = 7,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test reading calendar events with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService

            calendar_service = UnifiedCalendarService(current_user.id)
            events = await calendar_service.read_upcoming_events(
                db, max_results=max_results, days_ahead=days_ahead
            )

            return {
                "status": "✅ UNIFIED CALENDAR READ SUCCESS",
                "user_id": current_user.id,
                "event_count": len(events),
                "events": events,
                "max_results": max_results,
                "days_ahead": days_ahead,
                "message": f"📅 Retrieved {len(events)} events using Unified Calendar Service"
            }

        except Exception as e:
            logger.error(f"🧪 Unified Calendar read test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar read test failed: {str(e)}")

    @router.post("/test-unified-calendar-create")
    async def test_unified_calendar_create(
        title: str = "Unified Test Event",
        start_time: str = None,  # ISO format or natural language
        duration_minutes: int = 30,
        description: str = "Test event created via Unified Calendar Service",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test creating calendar events with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService
            from dateutil import parser

            calendar_service = UnifiedCalendarService(current_user.id)

            # Parse start time
            if start_time:
                try:
                    parsed_start = parser.parse(start_time)
                except:
                    parsed_start = datetime.now() + timedelta(hours=1)
            else:
                parsed_start = datetime.now() + timedelta(hours=1)

            # Prepare event details
            event_details = {
                "summary": title,
                "description": f"{description} - Created at {datetime.now()}",
                "start_time": parsed_start,
                "end_time": parsed_start + timedelta(minutes=duration_minutes)
            }

            # Create the event
            result = await calendar_service.create_event(db, event_details)

            return {
                "status": "✅ UNIFIED CALENDAR CREATE SUCCESS" if result["success"] else "❌ UNIFIED CALENDAR CREATE FAILED",
                "user_id": current_user.id,
                "event_details": event_details,
                "result": result,
                "message": f"📅 Calendar event creation test completed - {'Success' if result['success'] else 'Failed'}"
            }

        except Exception as e:
            logger.error(f"🧪 Unified Calendar create test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar create test failed: {str(e)}")

    @router.get("/test-unified-calendar-availability")
    async def test_unified_calendar_availability(
        start_time: str = None,  # ISO format or natural language
        duration_minutes: int = 30,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test checking availability with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService
            from dateutil import parser

            calendar_service = UnifiedCalendarService(current_user.id)

            # Parse start time
            if start_time:
                try:
                    parsed_start = parser.parse(start_time)
                except:
                    parsed_start = datetime.now() + timedelta(hours=1)
            else:
                parsed_start = datetime.now() + timedelta(hours=1)

            # Check availability
            availability = await calendar_service.check_availability(
                db, parsed_start, duration_minutes
            )

            return {
                "status": "✅ UNIFIED CALENDAR AVAILABILITY SUCCESS",
                "user_id": current_user.id,
                "requested_time": parsed_start.isoformat(),
                "duration_minutes": duration_minutes,
                "availability": availability,
                "message": f"📅 Availability check completed - {'Available' if availability.get('available') else 'Not Available'}"
            }

        except Exception as e:
            logger.error(
                f"🧪 Unified Calendar availability test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar availability test failed: {str(e)}")

    @router.get("/test-unified-calendar-free-slots")
    async def test_unified_calendar_free_slots(
        days_ahead: int = 7,
        max_results: int = 5,
        min_duration: int = 30,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test finding free slots with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService

            calendar_service = UnifiedCalendarService(current_user.id)

            # Find free slots
            free_slots = await calendar_service.find_free_slots(
                db,
                days_ahead=days_ahead,
                max_results=max_results,
                min_duration_minutes=min_duration
            )

            return {
                "status": "✅ UNIFIED CALENDAR FREE SLOTS SUCCESS",
                "user_id": current_user.id,
                "days_ahead": days_ahead,
                "max_results": max_results,
                "min_duration_minutes": min_duration,
                "free_slots_count": len(free_slots),
                "free_slots": free_slots,
                "message": f"📅 Found {len(free_slots)} free time slots"
            }

        except Exception as e:
            logger.error(f"🧪 Unified Calendar free slots test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar free slots test failed: {str(e)}")

    @router.get("/test-unified-calendar-parse-time")
    async def test_unified_calendar_parse_time(
        message: str,
        current_user: User = Depends(get_current_user)
    ):
        """🧪 TESTING ONLY: Test natural language time parsing with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService

            calendar_service = UnifiedCalendarService(current_user.id)

            # Parse natural language time
            parsed_time = await calendar_service.parse_natural_language_time(message)

            return {
                "status": "✅ UNIFIED CALENDAR TIME PARSE SUCCESS" if parsed_time else "⚠️ UNIFIED CALENDAR TIME PARSE FAILED",
                "user_id": current_user.id,
                "input_message": message,
                "parsed_time": parsed_time.isoformat() if parsed_time else None,
                "formatted_time": parsed_time.strftime('%A, %B %d, %Y at %I:%M %p') if parsed_time else None,
                "message": f"📅 Time parsing test completed - {'Success' if parsed_time else 'Failed'}"
            }

        except Exception as e:
            logger.error(f"🧪 Unified Calendar time parse test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar time parse test failed: {str(e)}")

    @router.get("/test-unified-calendar-ai-context")
    async def test_unified_calendar_ai_context(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test AI context generation with Unified Calendar Service."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService

            calendar_service = UnifiedCalendarService(current_user.id)

            # Get calendar context for AI
            ai_context = await calendar_service.get_calendar_context_for_ai(db)

            return {
                "status": "✅ UNIFIED CALENDAR AI CONTEXT SUCCESS",
                "user_id": current_user.id,
                "ai_context": ai_context,
                "context_length": len(ai_context),
                "message": "📅 AI context generation test completed successfully"
            }

        except Exception as e:
            logger.error(f"🧪 Unified Calendar AI context test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar AI context test failed: {str(e)}")

    @router.get("/test-unified-calendar-comprehensive")
    async def test_unified_calendar_comprehensive(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Comprehensive test of all Unified Calendar Service features."""
        try:
            from app.services.unified_calendar_service import UnifiedCalendarService

            calendar_service = UnifiedCalendarService(current_user.id)
            test_results = {}

            # Test 1: Read events
            try:
                events = await calendar_service.read_upcoming_events(db, max_results=3)
                test_results["read_events"] = {
                    "success": True, "count": len(events), "events": events}
            except Exception as e:
                test_results["read_events"] = {
                    "success": False, "error": str(e)}

            # Test 2: Check availability
            try:
                test_time = datetime.now() + timedelta(hours=2)
                availability = await calendar_service.check_availability(db, test_time, 30)
                test_results["check_availability"] = {
                    "success": True, "availability": availability}
            except Exception as e:
                test_results["check_availability"] = {
                    "success": False, "error": str(e)}

            # Test 3: Find free slots
            try:
                free_slots = await calendar_service.find_free_slots(db, days_ahead=3, max_results=3)
                test_results["find_free_slots"] = {
                    "success": True, "count": len(free_slots), "slots": free_slots}
            except Exception as e:
                test_results["find_free_slots"] = {
                    "success": False, "error": str(e)}

            # Test 4: Parse natural language
            try:
                test_phrases = ["tomorrow at 2pm",
                                "next Friday at 10am", "Monday morning"]
                parse_results = {}
                for phrase in test_phrases:
                    parsed = await calendar_service.parse_natural_language_time(phrase)
                    parse_results[phrase] = parsed.isoformat(
                    ) if parsed else None
                test_results["parse_natural_language"] = {
                    "success": True, "results": parse_results}
            except Exception as e:
                test_results["parse_natural_language"] = {
                    "success": False, "error": str(e)}

            # Test 5: AI context
            try:
                ai_context = await calendar_service.get_calendar_context_for_ai(db)
                test_results["ai_context"] = {
                    "success": True, "context": ai_context}
            except Exception as e:
                test_results["ai_context"] = {
                    "success": False, "error": str(e)}

            # Test 6: Create event (optional - only if user confirms)
            test_results["create_event"] = {
                "success": False, "note": "Skipped - use specific create test to avoid unwanted events"}

            # Summary
            successful_tests = sum(
                1 for test in test_results.values() if test.get("success", False))
            total_tests = len(test_results)

            return {
                "status": f"✅ UNIFIED CALENDAR COMPREHENSIVE TEST {'SUCCESS' if successful_tests == total_tests else 'PARTIAL SUCCESS'}",
                "user_id": current_user.id,
                "summary": {
                    "successful_tests": successful_tests,
                    "total_tests": total_tests,
                    "success_rate": f"{(successful_tests/total_tests)*100:.1f}%"
                },
                "test_results": test_results,
                "message": f"📅 Comprehensive calendar test completed - {successful_tests}/{total_tests} tests passed"
            }

        except Exception as e:
            logger.error(
                f"🧪 Unified Calendar comprehensive test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar comprehensive test failed: {str(e)}")

    # =================================================================
    # PHASE 2 & 3: SMS CALENDAR AND CUSTOM SCENARIO TESTING ENDPOINTS
    # =================================================================

    @router.get("/test-sms-calendar-fixed")
    async def test_sms_calendar_fixed(
        message: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Test FIXED SMS calendar with real calendar integration."""
        try:
            from app.services.sms_calendar_service import SMSCalendarService

            calendar_service = SMSCalendarService()

            # Parse datetime from message
            parsed_datetime = await calendar_service.parse_datetime_from_message(message)

            if parsed_datetime:
                # Test the FIXED schedule_demo method with user context
                result = await calendar_service.schedule_demo(
                    customer_phone="+1234567890",
                    customer_email="test@example.com",
                    requested_datetime=parsed_datetime,
                    customer_name="Test Customer",
                    user_id=current_user.id,
                    db_session=db
                )

                return {
                    "status": "✅ FIXED SMS CALENDAR TEST SUCCESS" if result["success"] else "❌ SMS CALENDAR TEST FAILED",
                    "user_id": current_user.id,
                    "input_message": message,
                    "parsed_datetime": parsed_datetime.isoformat(),
                    "scheduling_result": result,
                    "calendar_created": result.get("calendar_created", False),
                    "message": f"📅 SMS calendar test completed - {'Real calendar event created!' if result.get('calendar_created') else 'Simulated booking (no calendar access)'}"
                }
            else:
                return {
                    "status": "⚠️ CALENDAR PARSE FAILED",
                    "user_id": current_user.id,
                    "input_message": message,
                    "parsed_datetime": None,
                    "message": "Could not parse date/time from message",
                    "suggestion": "Try: 'tomorrow at 2pm', 'Friday morning', 'next Tuesday 3:30'"
                }

        except Exception as e:
            logger.error(f"🧪 Fixed SMS calendar test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"SMS calendar test failed: {str(e)}")

    @router.get("/test-custom-scenario-calendar-check")
    async def test_custom_scenario_calendar_check(
        scenario_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Check if a custom scenario has calendar access."""
        try:
            from app.models import CustomScenario, GoogleCalendarCredentials

            # Find the custom scenario
            custom_scenario = db.query(CustomScenario).filter(
                CustomScenario.scenario_id == scenario_id
            ).first()

            if not custom_scenario:
                return {
                    "status": "❌ SCENARIO NOT FOUND",
                    "scenario_id": scenario_id,
                    "message": "Custom scenario not found"
                }

            # Check if scenario owner has calendar credentials
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == custom_scenario.user_id
            ).first()

            has_calendar = bool(credentials)

            # Determine which endpoint would be used
            endpoint_type = "media-stream-custom-calendar" if has_calendar else "media-stream-custom"

            return {
                "status": "✅ CUSTOM SCENARIO CALENDAR CHECK SUCCESS",
                "scenario_id": scenario_id,
                "scenario_owner_id": custom_scenario.user_id,
                "has_calendar_access": has_calendar,
                "endpoint_type": endpoint_type,
                "calendar_enhanced": has_calendar,
                "webhook_url": f"incoming-custom-call/{scenario_id}",
                "websocket_endpoint": f"{endpoint_type}/{scenario_id}",
                "message": f"📅 Scenario {'WILL' if has_calendar else 'will NOT'} use calendar-enhanced features"
            }

        except Exception as e:
            logger.error(f"🧪 Custom scenario calendar check error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar check failed: {str(e)}")

    @router.post("/test-create-calendar-scenario")
    async def test_create_calendar_scenario(
        persona: str = "Calendar Assistant",
        prompt: str = "You are a helpful calendar assistant who can schedule meetings and check availability.",
        voice_type: str = "alloy",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Create a test custom scenario for calendar testing."""
        try:
            from app.models import CustomScenario
            from app.app_config import VOICES
            import time

            if voice_type not in VOICES:
                voice_type = "alloy"  # Default fallback

            # Generate unique ID
            scenario_id = f"test_cal_{current_user.id}_{int(time.time())}"

            # Store in database
            db_custom_scenario = CustomScenario(
                scenario_id=scenario_id,
                user_id=current_user.id,
                persona=persona,
                prompt=prompt,
                voice_type=voice_type,
                temperature=0.7
            )

            db.add(db_custom_scenario)
            db.commit()
            db.refresh(db_custom_scenario)

            return {
                "status": "✅ TEST CALENDAR SCENARIO CREATED",
                "scenario_id": scenario_id,
                "user_id": current_user.id,
                "persona": persona,
                "voice_type": voice_type,
                "webhook_url": f"incoming-custom-call/{scenario_id}",
                "test_url": f"http://localhost:5051/testing/test-custom-scenario-calendar-check?scenario_id={scenario_id}",
                "message": "📅 Test calendar scenario created successfully! Use the test_url to check calendar integration."
            }

        except Exception as e:
            logger.error(f"🧪 Create calendar scenario test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Create calendar scenario failed: {str(e)}")

    @router.get("/test-calendar-integration-status")
    async def test_calendar_integration_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING ONLY: Check overall calendar integration status for current user."""
        try:
            from app.models import GoogleCalendarCredentials, CustomScenario

            # Check if user has calendar credentials
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == current_user.id
            ).first()

            # Get user's custom scenarios
            scenarios = db.query(CustomScenario).filter(
                CustomScenario.user_id == current_user.id
            ).all()

            scenario_list = []
            for scenario in scenarios:
                scenario_list.append({
                    "scenario_id": scenario.scenario_id,
                    "persona": scenario.persona[:50] + "..." if len(scenario.persona) > 50 else scenario.persona,
                    "calendar_enhanced": bool(credentials),
                    "endpoint": f"media-stream-custom{'calendar' if credentials else ''}/{scenario.scenario_id}"
                })

            return {
                "status": "✅ CALENDAR INTEGRATION STATUS",
                "user_id": current_user.id,
                "has_google_calendar": bool(credentials),
                "calendar_token_expiry": credentials.token_expiry.isoformat() if credentials and credentials.token_expiry else None,
                "total_scenarios": len(scenarios),
                "calendar_enhanced_scenarios": len(scenarios) if credentials else 0,
                "scenarios": scenario_list,
                "features": {
                    "sms_calendar_integration": bool(credentials),
                    "voice_calendar_integration": bool(credentials),
                    "custom_scenario_calendar": bool(credentials)
                },
                "message": f"📅 User {'HAS' if credentials else 'does NOT have'} Google Calendar integration. {len(scenarios)} custom scenarios {'will use' if credentials else 'cannot use'} calendar features."
            }

        except Exception as e:
            logger.error(f"🧪 Calendar integration status test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Calendar integration status failed: {str(e)}")

    # =================================================================
    # AUTOMATIC CALENDAR CREATION TESTING ENDPOINTS
    # =================================================================

    @router.post("/test-conversation-calendar-processing")
    async def test_conversation_calendar_processing(
        conversation_text: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Test conversation analysis and calendar event creation"""
        try:
            from app.services.calendar_event_creator import CalendarEventCreator

            # Test conversation analysis
            calendar_creator = CalendarEventCreator()
            result = await calendar_creator.process_conversation(conversation_text, current_user.id, db)

            if result:
                return {
                    "status": "✅ SUCCESS",
                    "message": "Calendar event created successfully",
                    "event_details": result,
                    "analysis": "Scheduling commitment detected and processed"
                }
            else:
                return {
                    "status": "ℹ️ NO ACTION",
                    "message": "No scheduling commitments detected",
                    "analysis": "Conversation does not contain calendar booking requests"
                }

        except Exception as e:
            logger.error(f"Error testing conversation processing: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to process conversation: {str(e)}")

    @router.post("/test-post-call-processing")
    async def test_post_call_processing(
        call_sid: str = "test_call_123",
        scenario_id: str = "custom_1_test",
        conversation_text: str = "AI: Hello! How can I help you today?\nUser: Hi, I'd like to schedule a consultation for tomorrow at 2 PM.\nAI: Perfect! I'll add that to your calendar right away. Let me get your details.\nUser: My name is John Doe and my number is 555-1234.\nAI: Great! I've scheduled your consultation for tomorrow at 2 PM.",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Test full post-call processing pipeline"""
        try:
            from app.services.post_call_processor import post_call_processor

            # Test the full post-call processing
            result = await post_call_processor.process_call_end(
                call_sid=call_sid,
                user_id=current_user.id,
                scenario_id=scenario_id,
                conversation_content=conversation_text
            )

            return {
                "status": "✅ SUCCESS",
                "message": "Post-call processing completed",
                "processing_result": result
            }

        except Exception as e:
            logger.error(f"Error testing post-call processing: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to test post-call processing: {str(e)}")

    @router.post("/test-reprocess-pending-transcripts")
    async def test_reprocess_pending_transcripts(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Reprocess any pending conversation transcripts"""
        try:
            from app.services.post_call_processor import post_call_processor

            result = await post_call_processor.reprocess_pending_transcripts()

            return {
                "status": "✅ SUCCESS",
                "message": "Reprocessing completed",
                "reprocessing_result": result
            }

        except Exception as e:
            logger.error(f"Error testing reprocessing: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to test reprocessing: {str(e)}")

    @router.post("/test-sms-calendar-integration")
    async def test_sms_calendar_integration(
        customer_message: str = "Hi, I'd like to schedule a consultation for tomorrow at 2 PM",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Test SMS calendar integration end-to-end"""
        try:
            from app.services.user_sms_service import UserSMSService
            from app.models import GoogleCalendarCredentials

            # Check if user has calendar credentials
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == current_user.id
            ).first()

            if not credentials:
                return {
                    "status": "⚠️ NO CALENDAR CREDENTIALS",
                    "message": "User needs to authorize Google Calendar first",
                    "setup_url": "/google-calendar/authorize"
                }

            # Test SMS processing
            sms_service = UserSMSService(current_user.id)

            # Simulate an SMS webhook call
            result = await sms_service.handle_incoming_sms(
                from_number="+15551234567",
                to_number="+15559876543",
                body=customer_message,
                message_sid=f"test_sms_{datetime.utcnow().timestamp()}",
                db=db
            )

            return {
                "status": "✅ SMS CALENDAR INTEGRATION TEST",
                "user_id": current_user.id,
                "customer_message": customer_message,
                "sms_result": result,
                "has_calendar_credentials": True,
                "message": "SMS calendar integration test completed"
            }

        except Exception as e:
            logger.error(f"🧪 SMS calendar integration test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"SMS calendar integration test failed: {str(e)}")

    @router.post("/test-transcript-webhook-processing")
    async def test_transcript_webhook_processing(
        transcript_text: str = "Customer: Hi, I'd like to book a meeting for tomorrow at 3 PM. Assistant: Perfect! I'll add that to your calendar right away. Your meeting is scheduled for tomorrow at 3 PM.",
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Test transcript webhook calendar processing"""
        try:
            from app.routers.twilio_webhooks import should_process_for_calendar
            from app.models import Conversation, GoogleCalendarCredentials

            # Create a test conversation
            test_conversation = Conversation(
                user_id=current_user.id,
                scenario="custom_test",
                phone_number="+15551234567",
                direction="inbound",
                status="completed",
                call_sid=f"test_call_{datetime.utcnow().timestamp()}",
                transcript=transcript_text
            )
            db.add(test_conversation)
            db.commit()
            db.refresh(test_conversation)

            # Check calendar processing eligibility
            should_process = await should_process_for_calendar(db, test_conversation)

            if should_process:
                from app.services.post_call_processor import PostCallProcessor

                processor = PostCallProcessor()
                calendar_result = await processor.process_call_end(
                    call_sid=test_conversation.call_sid,
                    user_id=current_user.id,
                    scenario_id="custom_test",
                    conversation_content=transcript_text
                )

                # Clean up test conversation
                db.delete(test_conversation)
                db.commit()

                return {
                    "status": "✅ TRANSCRIPT WEBHOOK PROCESSING TEST",
                    "user_id": current_user.id,
                    "should_process_calendar": should_process,
                    "calendar_result": calendar_result,
                    "message": "Transcript webhook processing test completed"
                }
            else:
                # Clean up test conversation
                db.delete(test_conversation)
                db.commit()

                return {
                    "status": "⚠️ CALENDAR NOT ENABLED",
                    "user_id": current_user.id,
                    "should_process_calendar": should_process,
                    "message": "User doesn't have calendar integration enabled"
                }

        except Exception as e:
            logger.error(
                f"🧪 Transcript webhook processing test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Transcript webhook processing test failed: {str(e)}")

    @router.get("/test-complete-calendar-flow")
    async def test_complete_calendar_flow(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """🧪 TESTING: Test complete calendar integration flow status"""
        try:
            from app.models import GoogleCalendarCredentials, UserBusinessConfig

            # Check prerequisites
            calendar_creds = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == current_user.id
            ).first()

            business_config = db.query(UserBusinessConfig).filter(
                UserBusinessConfig.user_id == current_user.id
            ).first()

            return {
                "status": "✅ COMPLETE CALENDAR FLOW STATUS",
                "user_id": current_user.id,
                "prerequisites": {
                    "google_calendar_connected": bool(calendar_creds),
                    "business_config_exists": bool(business_config),
                    "calendar_integration_enabled": business_config.calendar_integration_enabled if business_config else False
                },
                "features_available": {
                    "voice_calendar": bool(calendar_creds),
                    "sms_calendar": bool(calendar_creds and business_config and business_config.calendar_integration_enabled),
                    "automatic_event_creation": bool(calendar_creds)
                },
                "test_endpoints": {
                    "sms_test": "/testing/test-sms-calendar-integration",
                    "voice_test": "/testing/test-transcript-webhook-processing",
                    "conversation_test": "/testing/test-conversation-calendar-processing"
                },
                "setup_urls": {
                    "google_calendar_auth": "/google-calendar/authorize",
                    "business_config": "/business/config"
                },
                "message": f"Calendar integration {'READY' if calendar_creds else 'REQUIRES SETUP'}"
            }

        except Exception as e:
            logger.error(f"🧪 Complete calendar flow test error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Complete calendar flow test failed: {str(e)}")

else:
    # Production - create empty router
    router = APIRouter()
    logger.info("🔒 Testing endpoints disabled in production mode")
