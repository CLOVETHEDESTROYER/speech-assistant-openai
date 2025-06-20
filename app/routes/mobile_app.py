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
    """Make a call specifically for mobile users with usage tracking"""
    try:
        # Check if user can make a call
        can_call, status_code, details = UsageService.can_make_call(
            current_user.id, db)

        if not can_call:
            if status_code == "trial_calls_exhausted":
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail={
                        "error": "trial_exhausted",
                        "message": "Your 3 free trial calls have been used. Upgrade to $4.99/week for unlimited calls!",
                        "upgrade_url": "/mobile/upgrade"
                    }
                )
            elif status_code == "upgrade_required":
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "upgrade_required",
                        "message": "Please upgrade to continue making calls",
                        "pricing": details.get("pricing")
                    }
                )
            else:
                raise HTTPException(status_code=400, detail=details.get(
                    "message", "Cannot make call"))

        # Use system phone number for mobile users (they don't need individual numbers)
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        if not from_number:
            raise HTTPException(
                status_code=500, detail="System phone number not configured")

        # Import Twilio client
        from twilio.rest import Client

        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )

        # Create call using shared system number
        call = client.calls.create(
            to=call_request.phone_number,
            from_=from_number,
            url=f"{os.getenv('PUBLIC_URL', 'https://your-domain.com')}/outgoing-call/{call_request.scenario}",
            method='POST'
        )

        # Record the call in usage statistics
        UsageService.record_call(current_user.id, db)

        # Get updated stats
        updated_stats = UsageService.get_usage_stats(current_user.id, db)

        return {
            "call_sid": call.sid,
            "status": "initiated",
            "usage_stats": {
                "trial_calls_remaining": updated_stats.get("trial_calls_remaining", 0),
                "calls_made_total": updated_stats.get("calls_made_total", 0),
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


@router.get("/pricing")
async def get_mobile_pricing():
    """Get pricing information for mobile app"""
    return UsageService.get_pricing_info(AppType.MOBILE_CONSUMER)


@router.get("/scenarios")
async def get_mobile_scenarios():
    """Get available scenarios for mobile app (simplified list)"""
    return {
        "scenarios": [
            {
                "id": "default",
                "name": "Friendly Chat",
                "description": "A casual, friendly conversation",
                "icon": "💬"
            },
            {
                "id": "celebrity",
                "name": "Celebrity Interview",
                "description": "Chat with a virtual celebrity",
                "icon": "🌟"
            },
            {
                "id": "comedian",
                "name": "Stand-up Comedian",
                "description": "Funny jokes and comedy bits",
                "icon": "😂"
            },
            {
                "id": "therapist",
                "name": "Life Coach",
                "description": "Supportive and motivational conversation",
                "icon": "🧠"
            },
            {
                "id": "storyteller",
                "name": "Storyteller",
                "description": "Engaging stories and tales",
                "icon": "📚"
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
