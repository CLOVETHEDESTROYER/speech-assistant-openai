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


class SubscriptionUpgradeRequest(BaseModel):
    receipt_data: str  # Base64 encoded receipt data from App Store
    is_sandbox: bool = False  # Whether this is a sandbox receipt
    subscription_tier: str = "mobile_weekly"


class AppStorePurchaseRequest(BaseModel):
    receipt_data: str  # Base64 encoded receipt data
    is_sandbox: bool = False
    product_id: str  # e.g., "speech_assistant_basic_weekly"


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
async def get_mobile_usage_stats(
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
async def make_mobile_call(
    request: Request,
    call_request: MobileCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enhanced mobile call with duration tracking and limits"""
    try:
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

        # Store call info in Conversation before making the call
        from app.models import Conversation
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
        webhook_url = f"{base_url}/outgoing-call/{call_request.scenario}"
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


@router.post("/upgrade-subscription")
async def upgrade_mobile_subscription(
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
async def purchase_subscription(
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

        # Validate product ID
        if subscription_info.get("product_id") != purchase_request.product_id:
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

        # Process based on product type
        if purchase_request.product_id == "speech_assistant_basic_weekly":
            success = UsageService.upgrade_to_basic_subscription(
                current_user.id, subscription_info, db
            )
        elif purchase_request.product_id == "speech_assistant_premium_monthly":
            success = UsageService.upgrade_to_premium_subscription(
                current_user.id, subscription_info, db
            )
        elif purchase_request.product_id == "speech_assistant_addon_calls":
            success = UsageService.purchase_addon_calls(
                current_user.id, subscription_info, db
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid product ID"
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
async def get_mobile_scenarios():
    """Get available scenarios for mobile app (enhanced entertainment list)"""
    return {
        "scenarios": [
            {
                "id": "fake_doctor",
                "name": "Fake Doctor Call",
                "description": "Emergency exit with medical urgency",
                "icon": "🏥",
                "category": "emergency_exit",
                "difficulty": "easy"
            },
            {
                "id": "fake_boss",
                "name": "Fake Boss Call",
                "description": "Work emergency for quick escape",
                "icon": "💼",
                "category": "work_exit",
                "difficulty": "medium"
            },
            {
                "id": "fake_tech_support",
                "name": "Fake Tech Support",
                "description": "Security breach emergency",
                "icon": "🔒",
                "category": "emergency_exit",
                "difficulty": "medium"
            },
            {
                "id": "fake_celebrity",
                "name": "Celebrity Fan Call",
                "description": "Chat with a famous person",
                "icon": "🌟",
                "category": "fun_interaction",
                "difficulty": "hard"
            },
            {
                "id": "fake_lottery_winner",
                "name": "Lottery Winner",
                "description": "You've won big!",
                "icon": "💰",
                "category": "fun_interaction",
                "difficulty": "hard"
            },
            {
                "id": "fake_restaurant_manager",
                "name": "Restaurant Manager",
                "description": "Special reservation confirmation",
                "icon": "🍴",
                "category": "social_exit",
                "difficulty": "easy"
            },
            {
                "id": "fake_dating_app_match",
                "name": "Dating App Match",
                "description": "Meet your new match",
                "icon": "💕",
                "category": "social_interaction",
                "difficulty": "hard"
            },
            {
                "id": "fake_old_friend",
                "name": "Old Friend",
                "description": "Reconnect with someone from the past",
                "icon": "👥",
                "category": "social_interaction",
                "difficulty": "medium"
            },
            {
                "id": "fake_news_reporter",
                "name": "News Reporter",
                "description": "Interview opportunity",
                "icon": "📰",
                "category": "social_interaction",
                "difficulty": "medium"
            },
            {
                "id": "fake_car_accident",
                "name": "Car Accident",
                "description": "Minor accident drama",
                "icon": "🚗",
                "category": "emergency_exit",
                "difficulty": "easy"
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
