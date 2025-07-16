# app/routes/mobile.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, UsageLimits, AppType
from app.services.usage_service import UsageService
from pydantic import BaseModel
from typing import Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

# Check if in development mode
DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'False').lower() == 'true'

router = APIRouter(prefix="/mobile", tags=["mobile"])


class CallPermissionResponse(BaseModel):
    can_make_call: bool
    status: str
    details: Dict[str, Any]


class UsageStatsResponse(BaseModel):
    trial_calls_remaining: int
    calls_made_total: int
    is_trial_active: bool
    is_subscribed: bool
    subscription_status: str = None
    app_type: str = "mobile"


class MakeCallRequest(BaseModel):
    phone_number: str
    scenario: str = "default"


@router.post("/check-call-permission", response_model=CallPermissionResponse)
async def check_call_permission(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user can make a call and return permission status"""
    try:
        # Skip limits in development mode
        if DEVELOPMENT_MODE:
            return CallPermissionResponse(
                can_make_call=True,
                status="development_mode",
                details={
                    "message": "Development mode - unlimited calls",
                    "calls_remaining": "unlimited"
                }
            )
        
        # Initialize usage limits if they don't exist
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == current_user.id).first()
        
        if not usage_limits:
            app_type = UsageService.detect_app_type_from_request(request)
            usage_limits = UsageService.initialize_user_usage(
                current_user.id, app_type, db)
        
        # Check if user can make a call
        can_call, status_code, details = UsageService.can_make_call(
            current_user.id, db)
        
        return CallPermissionResponse(
            can_make_call=can_call,
            status=status_code,
            details=details
        )
        
    except Exception as e:
        logger.error(f"Error checking call permission for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking call permission"
        )


@router.get("/usage-stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get usage statistics for the current user"""
    try:
        # Skip limits in development mode
        if DEVELOPMENT_MODE:
            return UsageStatsResponse(
                trial_calls_remaining=999,
                calls_made_total=0,
                is_trial_active=True,
                is_subscribed=False,
                subscription_status=None,
                app_type="mobile"
            )
        
        stats = UsageService.get_usage_stats(current_user.id, db)
        
        return UsageStatsResponse(
            trial_calls_remaining=stats["trial_calls_remaining"],
            calls_made_total=stats["calls_made_total"],
            is_trial_active=stats["is_trial_active"],
            is_subscribed=stats["is_subscribed"],
            subscription_status=stats["subscription_status"],
            app_type=stats["app_type"]
        )
        
    except Exception as e:
        logger.error(f"Error getting usage stats for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving usage statistics"
        )


@router.post("/make-call")
async def make_call(
    call_request: MakeCallRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Make a call - mobile version with proper usage tracking"""
    try:
        # Skip limits in development mode
        if not DEVELOPMENT_MODE:
            # Check usage limits first
            usage_limits = db.query(UsageLimits).filter(
                UsageLimits.user_id == current_user.id).first()
            
            if not usage_limits:
                app_type = UsageService.detect_app_type_from_request(request)
                usage_limits = UsageService.initialize_user_usage(
                    current_user.id, app_type, db)
            
            # Check if user can make a call
            can_call, status_code, details = UsageService.can_make_call(
                current_user.id, db)
            
            if not can_call:
                if status_code == "trial_calls_exhausted":
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail="Please upgrade to continue making calls"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=details.get("message", "Call not authorized")
                    )
        
        # Make the actual call using Twilio
        from twilio.rest import Client
        
        TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
        TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
        TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
        PUBLIC_URL = os.getenv('PUBLIC_URL', '').strip()
        
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, PUBLIC_URL]):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Twilio configuration incomplete"
            )
        
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Construct webhook URL
        webhook_url = f"https://{PUBLIC_URL}/incoming-call/{call_request.scenario}"
        
        # Make the call
        call = twilio_client.calls.create(
            to=f"+1{call_request.phone_number}",
            from_=TWILIO_PHONE_NUMBER,
            url=webhook_url,
            record=True
        )
        
        # Record the call if not in development mode
        if not DEVELOPMENT_MODE:
            UsageService.record_call_made(current_user.id, db)
        
        logger.info(f"Call initiated for user {current_user.id}, call SID: {call.sid}")
        
        return {
            "message": "Call initiated successfully",
            "call_sid": call.sid,
            "status": "initiated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making call for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error initiating call"
        ) 