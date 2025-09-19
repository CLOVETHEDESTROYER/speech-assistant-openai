from app.models import UsageLimits
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, AppType, SubscriptionTier, SubscriptionStatus
from app.services.usage_service import UsageService
from app.services.app_store_service import AppStoreService
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
import os
from datetime import datetime
from twilio.rest import Client
from app import config
from app.utils.url_helpers import clean_and_validate_url
from app.limiter import rate_limit

# Development mode check
DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'


def is_development_mode():
    """Check if we're in development mode at runtime"""
    return os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'


def create_error_response(error_type: str, message: str, upgrade_options: list = None):
    """Create consistent error responses"""
    return {
        "error": error_type,
        "message": message,
        "upgrade_options": upgrade_options or [],
        "timestamp": datetime.utcnow().isoformat()
    }


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile", tags=["mobile"])

# Pydantic models for mobile app


class MobileCallRequest(BaseModel):
    phone_number: str
    scenario: str = "default"


class MobileCustomCallRequest(BaseModel):
    phone_number: str
    scenario_id: str  # Custom scenario ID


class SubscriptionUpgradeRequest(BaseModel):
    receipt_data: str  # Base64 encoded receipt data from App Store
    is_sandbox: bool = False  # Whether this is a sandbox receipt
    subscription_tier: str = "mobile_weekly"


class AppStorePurchaseRequest(BaseModel):
    receipt_data: str  # Base64 encoded receipt data
    is_sandbox: bool = False
    product_id: str  # e.g., "com.aifriendchat.premium.weekly.v2"


class AppStoreWebhookRequest(BaseModel):
    signedPayload: str
    notificationType: str
    data: Dict


class UsageStatsResponse(BaseModel):
    app_type: str
    is_trial_active: bool
    trial_calls_remaining: int
    trial_calls_used: int
    calls_made_today: int
    calls_made_total: int
    is_subscribed: bool
    subscription_tier: Optional[str]
    upgrade_recommended: bool
    pricing: Optional[Dict]


@router.get("/usage-stats", response_model=UsageStatsResponse)
@rate_limit("3/minute")
async def get_mobile_usage_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get usage statistics for mobile app user"""
    try:
        # Ensure user has usage limits initialized
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == current_user.id).first()
        if not usage_limits:
            usage_limits = UsageService.initialize_user_usage(
                current_user.id, AppType.MOBILE_CONSUMER, db
            )

        stats = UsageService.get_usage_stats(current_user.id, db)

        return UsageStatsResponse(
            app_type=stats.get("app_type", "mobile_consumer"),
            is_trial_active=stats.get("is_trial_active", False),
            trial_calls_remaining=stats.get("trial_calls_remaining", 0),
            trial_calls_used=stats.get("trial_calls_used", 0),
            calls_made_today=stats.get("calls_made_today", 0),
            calls_made_total=stats.get("calls_made_total", 0),
            is_subscribed=stats.get("is_subscribed", False),
            subscription_tier=stats.get("subscription_tier"),
            upgrade_recommended=stats.get("upgrade_recommended", False),
            pricing=stats.get("pricing")
        )

    except Exception as e:
        logger.error(f"Error getting mobile usage stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch usage statistics")


@router.get("/subscription-metadata")
async def subscription_metadata():
    """Provide subscription info for iOS Settings screen and App Store requirements"""
    return {
        "title": config.APP_STORE_SUBSCRIPTION_TITLE,
        "duration": config.APP_STORE_SUBSCRIPTION_DURATION,
        "group_name": config.APP_STORE_SUBSCRIPTION_GROUP,
        "product_id": config.APP_STORE_PRODUCT_ID,
        "privacy_url": f"{config.PUBLIC_URL}/legal/privacy",
        "terms_url": f"{config.PUBLIC_URL}/legal/terms",
        "auto_renew": True,
        "manage_instructions": "Settings > Apple ID > Subscriptions"
    }


@router.post("/check-call-permission")
async def check_mobile_call_permission(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if mobile user can make a call"""
    try:
        # Ensure user has usage limits initialized
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == current_user.id).first()
        if not usage_limits:
            usage_limits = UsageService.initialize_user_usage(
                current_user.id, AppType.MOBILE_CONSUMER, db
            )

        can_call, status_code, details = UsageService.can_make_call(
            current_user.id, db)

        return {
            "can_make_call": can_call,
            "status": status_code,
            "details": details
        }

    except Exception as e:
        logger.error(f"Error checking call permission: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to check call permissions")


@router.post("/make-call")
@rate_limit("2/minute")
async def make_mobile_call(
    request: Request,
    call_request: MobileCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enhanced mobile call with duration tracking and limits"""
    try:
        # SKIP USAGE LIMITS IN DEVELOPMENT MODE
        if not DEVELOPMENT_MODE:
            # Check and reset limits if needed (7-day/30-day cycles)
            UsageService.check_and_reset_limits(current_user.id, db)

            # Check if user can make a call
            can_call, status_code, details = UsageService.can_make_call(
                current_user.id, db)

            if not can_call:
                error_response = create_error_response(
                    status_code,
                    details.get("message", "Cannot make call"),
                    details.get("upgrade_options", [])
                )
                raise HTTPException(status_code=402, detail=error_response)

            # Get duration limit from permission check
            duration_limit = details.get("duration_limit", 60)
        else:
            # Development mode - no limits
            duration_limit = 300  # 5 minutes for dev testing
            logger.info(
                f"🧪 DEV MODE: Skipping usage limits for user {current_user.id}")

        # Store call info in Conversation before making the call
        from app.models import Conversation
        try:
            conversation = Conversation(
                user_id=current_user.id,
                scenario=call_request.scenario,
                phone_number=call_request.phone_number,
                direction="outbound",
                status="initiated",
                call_sid=None,  # Will be set after call creation
                duration_limit=duration_limit
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create conversation: {str(e)}")
            # Try to get the next available ID
            try:
                result = db.execute(
                    "SELECT nextval('conversations_id_seq')").scalar()
                logger.info(f"Next available ID: {result}")
            except Exception as seq_error:
                logger.error(f"Sequence error: {str(seq_error)}")
            raise HTTPException(
                status_code=500, detail="Database error creating conversation")

        # Use system phone number for mobile users
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        if not from_number:
            raise HTTPException(
                status_code=500, detail="System phone number not configured")

        # Create call with duration tracking
        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )

        # Use the same URL construction pattern as the regular endpoint
        base_url = clean_and_validate_url(config.PUBLIC_URL)
        # Add user_name parameter to webhook URL for user name support
        user_name = current_user.full_name or current_user.email.split('@')[0]
        webhook_url = f"{base_url}/outgoing-call/{call_request.scenario}?direction=outbound&user_name={user_name}"
        status_callback_url = f"{base_url}/call-end-webhook"

        call = client.calls.create(
            to=call_request.phone_number,
            from_=from_number,
            url=webhook_url,
            method='POST',
            status_callback=status_callback_url,
            status_callback_event=['completed']
        )

        # Update conversation with call SID
        conversation.call_sid = call.sid
        db.commit()

        # Record the call start (duration will be recorded when call ends)
        UsageService.record_call_start(current_user.id, db)

        # Get updated stats
        updated_stats = UsageService.get_usage_stats(current_user.id, db)

        return {
            "call_sid": call.sid,
            "status": "initiated",
            "duration_limit": duration_limit,
            "usage_stats": {
                "calls_remaining_this_week": updated_stats.get("calls_remaining_this_week", 0),
                "calls_remaining_this_month": updated_stats.get("calls_remaining_this_month", 0),
                "addon_calls_remaining": updated_stats.get("addon_calls_remaining", 0),
                "upgrade_recommended": updated_stats.get("upgrade_recommended", False)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making mobile call: {str(e)}")
        raise HTTPException(status_code=500, detail="Unable to initiate call")


@router.post("/make-custom-call")
@rate_limit("2/minute")
async def make_mobile_custom_call(
    request: Request,
    call_request: MobileCustomCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Make a custom call using a custom scenario - Premium feature only"""
    try:
        # Check if user has premium subscription (custom scenarios are premium-only)
        if not is_development_mode():
            usage_limits = db.query(UsageLimits).filter(
                UsageLimits.user_id == current_user.id).first()

            if not usage_limits or not usage_limits.is_subscribed:
                raise HTTPException(
                    status_code=402,
                    detail="Custom scenarios require premium subscription. Please upgrade to access this feature."
                )

            # Check and reset limits if needed (7-day/30-day cycles)
            UsageService.check_and_reset_limits(current_user.id, db)

            # Check if user can make a call
            can_call, status_code, details = UsageService.can_make_call(
                current_user.id, db)

            if not can_call:
                error_response = create_error_response(
                    status_code,
                    details.get("message", "Cannot make call"),
                    details.get("upgrade_options", [])
                )
                raise HTTPException(status_code=402, detail=error_response)

            # Get duration limit from permission check
            duration_limit = details.get("duration_limit", 60)
        else:
            # Development mode - no limits
            duration_limit = 300  # 5 minutes for dev testing
            logger.info(
                f"🧪 DEV MODE: Skipping usage limits for user {current_user.id}")

        # Validate custom scenario exists and belongs to user
        from app.models import CustomScenario
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == call_request.scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not custom_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found or you don't have permission to use it"
            )

        # Store call info in Conversation before making the call
        from app.models import Conversation
        try:
            conversation = Conversation(
                user_id=current_user.id,
                scenario=call_request.scenario_id,  # Use scenario_id for custom scenarios
                phone_number=call_request.phone_number,
                direction="outbound",
                status="initiated",
                call_sid=None,  # Will be set after call creation
                duration_limit=duration_limit
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create conversation: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Database error creating conversation")

        # Use system phone number for mobile users
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        if not from_number:
            raise HTTPException(
                status_code=500, detail="System phone number not configured")

        # Create call with duration tracking
        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )

        # Use the same URL construction pattern as the regular endpoint
        base_url = clean_and_validate_url(config.PUBLIC_URL)
        webhook_url = f"{base_url}/incoming-custom-call/{call_request.scenario_id}"
        status_callback_url = f"{base_url}/call-end-webhook"

        call = client.calls.create(
            to=call_request.phone_number,
            from_=from_number,
            url=webhook_url,
            method='POST',
            status_callback=status_callback_url,
            status_callback_event=['completed']
        )

        # Update conversation with call SID
        conversation.call_sid = call.sid
        db.commit()

        # Record the call start (duration will be recorded when call ends)
        UsageService.record_call_start(current_user.id, db)

        # Get updated stats
        updated_stats = UsageService.get_usage_stats(current_user.id, db)

        return {
            "call_sid": call.sid,
            "status": "initiated",
            "duration_limit": duration_limit,
            "scenario_id": call_request.scenario_id,
            "scenario_name": custom_scenario.persona,
            "usage_stats": {
                "calls_remaining_this_week": updated_stats.get("calls_remaining_this_week", 0),
                "calls_remaining_this_month": updated_stats.get("calls_remaining_this_month", 0),
                "addon_calls_remaining": updated_stats.get("addon_calls_remaining", 0),
                "upgrade_recommended": updated_stats.get("upgrade_recommended", False)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making mobile custom call: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to initiate custom call")


@router.post("/upgrade-subscription")
@rate_limit("3/minute")
async def upgrade_mobile_subscription(
    request: Request,
    upgrade_request: SubscriptionUpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upgrade mobile user to paid subscription with App Store receipt validation"""
    try:
        # Validate subscription tier
        if upgrade_request.subscription_tier not in ["mobile_weekly"]:
            raise HTTPException(
                status_code=400, detail="Invalid subscription tier for mobile app")

        tier = SubscriptionTier.MOBILE_WEEKLY

        # Validate the App Store receipt
        try:
            receipt_validation = AppStoreService.validate_receipt(
                upgrade_request.receipt_data,
                is_sandbox=upgrade_request.is_sandbox
            )

            # Extract subscription information from validated receipt
            subscription_info = AppStoreService.extract_subscription_info(
                receipt_validation)

            # Validate product ID matches expected subscription
            if subscription_info.get("product_id") != "speech_assistant_weekly":
                raise HTTPException(
                    status_code=400,
                    detail="Invalid product ID in receipt"
                )

            # Check if this transaction has already been processed
            existing_usage = db.query(UsageLimits).filter(
                UsageLimits.app_store_transaction_id == subscription_info.get(
                    "transaction_id")
            ).first()

            if existing_usage:
                raise HTTPException(
                    status_code=400,
                    detail="This transaction has already been processed"
                )

        except ValueError as e:
            logger.error(f"Receipt validation failed: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Receipt validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error validating receipt: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Error validating App Store receipt")

        # Update user subscription with validated receipt data
        success = UsageService.upgrade_subscription_with_receipt(
            current_user.id,
            tier,
            subscription_info,
            db
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to upgrade subscription")

        # Get updated usage stats
        stats = UsageService.get_usage_stats(current_user.id, db)

        return {
            "success": True,
            "message": "Successfully upgraded to weekly subscription!",
            "subscription_tier": tier.value,
            "usage_stats": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upgrading subscription: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to upgrade subscription")


@router.post("/purchase-subscription")
@rate_limit("3/minute")
async def purchase_subscription(
    request: Request,
    purchase_request: AppStorePurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Purchase subscription or addon calls via App Store"""
    try:
        # Validate the App Store receipt
        receipt_validation = AppStoreService.validate_receipt(
            purchase_request.receipt_data,
            is_sandbox=purchase_request.is_sandbox
        )

        # Extract subscription information
        subscription_info = AppStoreService.extract_subscription_info(
            receipt_validation)

        # Validate product ID against configured expected product
        expected_product = config.APP_STORE_PRODUCT_ID
        if subscription_info.get("product_id") != expected_product:
            raise HTTPException(
                status_code=400,
                detail="Product ID mismatch"
            )

        # Check if transaction already processed
        existing_usage = db.query(UsageLimits).filter(
            UsageLimits.app_store_transaction_id == subscription_info.get(
                "transaction_id")
        ).first()

        if existing_usage:
            raise HTTPException(
                status_code=400,
                detail="This transaction has already been processed"
            )

        # Process single mobile weekly product
        success = UsageService.upgrade_subscription_with_receipt(
            current_user.id,
            SubscriptionTier.MOBILE_WEEKLY,
            subscription_info,
            db
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to process purchase")

        # Get updated stats
        updated_stats = UsageService.get_usage_stats(current_user.id, db)

        return {
            "success": True,
            "message": "Purchase processed successfully!",
            "usage_stats": updated_stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing purchase: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to process purchase")


@router.get("/pricing")
async def get_mobile_pricing():
    """Get enhanced pricing information for mobile app"""
    return {
        "plans": [
            {
                "id": "basic",
                "name": "Basic Plan",
                "price": "$4.99",
                "billing": "weekly",
                "calls": "5 calls per week",
                "duration_limit": "1 minute per call",
                "features": ["Unlimited scenarios", "Call history", "Basic support"]
            },
            {
                "id": "premium",
                "name": "Premium Plan",
                "price": "$25.00",
                "billing": "monthly",
                "calls": "30 calls per month",
                "duration_limit": "2 minutes per call",
                "features": ["All Basic features", "Priority support", "Advanced analytics"]
            }
        ],
        "addon": {
            "id": "addon",
            "name": "Additional Calls",
            "price": "$4.99",
            "calls": "5 additional calls",
            "expires": "30 days",
            "description": "Perfect when you need a few more calls"
        }
    }


@router.get("/scenarios")
@rate_limit("5/minute")
async def get_mobile_scenarios(request: Request):
    """Get available scenarios for mobile app (enhanced entertainment list with full scenario data)"""
    return {
        "scenarios": [
            {
                "id": "fake_doctor",
                "name": "Fake Doctor Call",
                "description": "Emergency exit with medical urgency",
                "icon": "🏥",
                "category": "emergency_exit",
                "difficulty": "easy",
                "persona": "You are Dr. Sarah Mitchell, a concerned emergency room physician at City General Hospital. You speak with professional urgency but maintain a calm, authoritative tone. You're calling about a critical medical situation that requires immediate attention.",
                "prompt": "You're calling about an urgent medical matter that requires the person to leave their current situation immediately. Be professional but urgent - explain there's been an emergency and they need to come to the hospital right away. Don't give specific medical details, just emphasize the urgency and need for immediate action. Keep the call brief and professional.",
                "voice_config": {
                    "voice": "coral",
                    "temperature": 0.7
                }
            },
            {
                "id": "fake_boss",
                "name": "Fake Boss Call",
                "description": "Work emergency for quick escape",
                "icon": "💼",
                "category": "work_exit",
                "difficulty": "medium",
                "persona": "You are Michael Chen, the senior project manager at TechCorp Solutions. You speak with authority and urgency, using business terminology and a no-nonsense tone. You're calling about a critical work emergency that requires immediate attention.",
                "prompt": "You're calling about an urgent work crisis that requires the person to return to the office immediately. Be authoritative and urgent - explain there's been a major client issue, system failure, or urgent meeting that can't wait. Use business language and emphasize the professional consequences of not responding. Keep the call professional but urgent. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "echo",
                    "temperature": 0.6
                }
            },
            {
                "id": "fake_tech_support",
                "name": "Fake Tech Support",
                "description": "Security breach emergency",
                "icon": "🔒",
                "category": "emergency_exit",
                "difficulty": "medium",
                "persona": "You are Alex Rodriguez, a cybersecurity specialist from SecureNet Systems. You speak with technical authority and urgency, using security terminology and a serious, concerned tone. You're calling about a critical security incident.",
                "prompt": "You're calling about a serious security breach or system compromise that requires immediate action. Be technical but urgent - explain there's been unauthorized access, suspicious activity, or a potential data breach. Use security terminology and emphasize the urgency of the situation. Keep the call professional and urgent. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "echo",
                    "temperature": 0.6
                }
            },
            {
                "id": "fake_celebrity",
                "name": "Celebrity Fan Call",
                "description": "Chat with a famous person",
                "icon": "🌟",
                "category": "fun_interaction",
                "difficulty": "hard",
                "persona": "You are Emma Thompson, a famous Hollywood actress known for your warm personality and engaging conversation style. You speak with enthusiasm and charm, using casual language and showing genuine interest in others. You're calling to connect with a fan.",
                "prompt": "You're calling as a famous celebrity who wants to chat with a fan. Be warm, engaging, and genuinely interested in the person. Ask about their life, share positive energy, and make them feel special. Keep the conversation light, fun, and uplifting. Don't break character - stay in your celebrity persona throughout. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "alloy",
                    "temperature": 0.8
                }
            },
            {
                "id": "fake_lottery_winner",
                "name": "Lottery Winner",
                "description": "You've won big!",
                "icon": "💰",
                "category": "fun_interaction",
                "difficulty": "hard",
                "persona": "You are Jennifer Martinez, a lottery official from the State Lottery Commission. You speak with excitement and official authority, using formal language mixed with genuine enthusiasm. You're calling to deliver life-changing news.",
                "prompt": "You're calling to inform someone they've won a major lottery prize. Be excited but professional - explain the win, the amount, and what happens next. Use official lottery terminology and emphasize the life-changing nature of the news. Keep the call exciting and official. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "shimmer",
                    "temperature": 0.9
                }
            },
            {
                "id": "fake_restaurant_manager",
                "name": "Restaurant Manager",
                "description": "Special reservation confirmation",
                "icon": "🍴",
                "category": "social_exit",
                "difficulty": "easy",
                "persona": "You are David Kim, the general manager of Le Grand Bistro, an upscale restaurant. You speak with professional hospitality, using polite language and a warm, accommodating tone. You're calling about a special reservation.",
                "prompt": "You're calling to confirm a special reservation or VIP table at an upscale restaurant. Be polite and professional - explain the special arrangements, confirm details, and emphasize the exclusive nature of the reservation. Keep the call courteous and professional. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "echo",
                    "temperature": 0.6
                }
            },
            {
                "id": "fake_dating_app_match",
                "name": "Dating App Match",
                "description": "Meet your new match",
                "icon": "💕",
                "category": "social_interaction",
                "difficulty": "hard",
                "persona": "You are Sophia Rodriguez, a 28-year-old marketing professional who's excited about a new dating app match. You speak with enthusiasm and genuine interest, using casual, friendly language and showing curiosity about the other person. You're calling to connect with a potential romantic interest.",
                "prompt": "You're calling as someone who matched with the person on a dating app and wants to get to know them better. Be genuinely interested, ask thoughtful questions, and show enthusiasm about the connection. Keep the conversation light, fun, and engaging. Don't be overly aggressive - be natural and curious. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "alloy",
                    "temperature": 0.8
                }
            },
            {
                "id": "fake_old_friend",
                "name": "Old Friend",
                "description": "Reconnect with someone from the past",
                "icon": "👥",
                "category": "social_interaction",
                "difficulty": "medium",
                "persona": "You are James Wilson, an old friend from high school who's excited to reconnect. You speak with genuine warmth and nostalgia, using casual language and showing real interest in catching up. You're calling to reconnect after years apart.",
                "prompt": "You're calling as an old friend who wants to reconnect and catch up. Be warm and nostalgic - mention shared memories, ask about their life now, and show genuine interest in reconnecting. Keep the conversation friendly and engaging. Don't force the connection - let it flow naturally. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "verse",
                    "temperature": 0.7
                }
            },
            {
                "id": "fake_news_reporter",
                "name": "News Reporter",
                "description": "Interview opportunity",
                "icon": "📰",
                "category": "social_interaction",
                "difficulty": "medium",
                "persona": "You are Rachel Green, a news reporter from City News Network. You speak with professional enthusiasm and curiosity, using journalistic language and showing genuine interest in the story. You're calling about a potential news interview.",
                "prompt": "You're calling as a news reporter who wants to interview the person about a story or event. Be professional but enthusiastic - explain the story angle, why they're the right person to interview, and what the interview would involve. Keep the call professional and engaging. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "coral",
                    "temperature": 0.7
                }
            },
            {
                "id": "fake_car_accident",
                "name": "Car Accident",
                "description": "Minor accident drama",
                "icon": "🚗",
                "category": "emergency_exit",
                "difficulty": "easy",
                "persona": "You are Officer Sarah Johnson, a police officer from the local police department. You speak with authority and concern, using official language and a serious, professional tone. You're calling about a traffic incident.",
                "prompt": "You're calling about a minor traffic incident that requires the person's attention. Be professional and concerned - explain there's been an accident involving their vehicle, it's not serious but they need to come to the scene. Keep the call official but not overly alarming. Address the person by name when you know it.",
                "voice_config": {
                    "voice": "echo",
                    "temperature": 0.6
                }
            }
        ],
        "categories": [
            {
                "id": "emergency_exit",
                "name": "Emergency Exit",
                "description": "Get out of awkward situations quickly",
                "icon": "🚨"
            },
            {
                "id": "work_exit",
                "name": "Work Emergency",
                "description": "Professional excuses for work situations",
                "icon": "💼"
            },
            {
                "id": "social_exit",
                "name": "Social Escape",
                "description": "Polite ways to exit social situations",
                "icon": "👥"
            },
            {
                "id": "fun_interaction",
                "name": "Fun Interactions",
                "description": "Pure entertainment scenarios",
                "icon": "🎉"
            },
            {
                "id": "social_interaction",
                "name": "Social Connection",
                "description": "Meet new people or reconnect",
                "icon": "🤝"
            }
        ]
    }


@router.post("/schedule-call")
async def schedule_mobile_call(
    phone_number: str,
    scenario: str = "default",
    scheduled_time: str = None,  # ISO format datetime string
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Schedule a call for mobile user"""
    try:
        # Check if user can make a call
        can_call, status_code, details = UsageService.can_make_call(
            current_user.id, db)

        if not can_call:
            if status_code == "trial_calls_exhausted":
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "trial_exhausted",
                        "message": "Upgrade to $4.99/week to schedule calls"
                    }
                )

        # Use the existing schedule_call endpoint logic
        from datetime import datetime
        from app.models import CallSchedule

        if scheduled_time:
            scheduled_datetime = datetime.fromisoformat(
                scheduled_time.replace('Z', '+00:00'))
        else:
            # Default to 1 minute from now
            from datetime import timedelta
            scheduled_datetime = datetime.utcnow() + timedelta(minutes=1)

        # Create the scheduled call
        call_schedule = CallSchedule(
            user_id=current_user.id,
            phone_number=phone_number,
            scheduled_time=scheduled_datetime,
            scenario=scenario
        )

        db.add(call_schedule)
        db.commit()
        db.refresh(call_schedule)

        return {
            "schedule_id": call_schedule.id,
            "phone_number": phone_number,
            "scenario": scenario,
            "scheduled_time": scheduled_datetime.isoformat(),
            "status": "scheduled"
        }

    except Exception as e:
        logger.error(f"Error scheduling mobile call: {str(e)}")
        raise HTTPException(status_code=500, detail="Unable to schedule call")


@router.get("/call-history")
async def get_mobile_call_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get call history for mobile user"""
    try:
        from app.models import Conversation

        conversations = db.query(Conversation).filter(
            Conversation.user_id == current_user.id
        ).order_by(Conversation.created_at.desc()).limit(limit).all()

        history = []
        for conv in conversations:
            history.append({
                "id": conv.id,
                "phone_number": conv.phone_number,
                "scenario": conv.scenario,
                "status": conv.status,
                "created_at": conv.created_at.isoformat(),
                "call_sid": conv.call_sid
            })

        return {
            "call_history": history,
            "total_calls": len(history)
        }

    except Exception as e:
        logger.error(f"Error getting mobile call history: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch call history")


@router.post("/app-store/webhook")
@rate_limit("10/minute")
async def handle_app_store_webhook(
    request: Request,
    webhook_data: AppStoreWebhookRequest,
    db: Session = Depends(get_db)
):
    """Handle App Store server notifications for subscription events"""
    try:
        # Get the raw body for signature verification
        body = await request.body()
        signature = request.headers.get("x-apple-signature")

        # Verify webhook signature
        if signature:
            if not AppStoreService.verify_webhook_signature(body.decode(), signature):
                logger.error("Invalid webhook signature")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")

        # Process the subscription notification
        notification_data = {
            "notification_type": webhook_data.notificationType,
            "signedPayload": webhook_data.signedPayload,
            "data": webhook_data.data
        }

        success = AppStoreService.process_subscription_notification(
            notification_data, db)

        if success:
            return {"status": "success", "message": "Notification processed successfully"}
        else:
            logger.error("Failed to process App Store notification")
            raise HTTPException(
                status_code=500, detail="Failed to process notification")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing App Store webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing webhook")


@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed subscription status for mobile user"""
    try:
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == current_user.id).first()

        if not usage_limits:
            raise HTTPException(
                status_code=404, detail="Usage limits not found")

        return {
            "subscription_tier": usage_limits.subscription_tier.value if usage_limits.subscription_tier else None,
            "subscription_status": usage_limits.subscription_status.value if usage_limits.subscription_status else None,
            "is_subscribed": usage_limits.is_subscribed,
            "subscription_start_date": usage_limits.subscription_start_date.isoformat() if usage_limits.subscription_start_date else None,
            "subscription_end_date": usage_limits.subscription_end_date.isoformat() if usage_limits.subscription_end_date else None,
            "next_payment_date": usage_limits.next_payment_date.isoformat() if usage_limits.next_payment_date else None,
            "billing_cycle": usage_limits.billing_cycle,
            "app_store_transaction_id": usage_limits.app_store_transaction_id,
            "app_store_product_id": usage_limits.app_store_product_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription status: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch subscription status")

# Import the required models at the top of the file
