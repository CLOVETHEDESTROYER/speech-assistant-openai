# app/services/usage_service.py
from sqlalchemy.orm import Session
from app.models import UsageLimits, AppType, User
from fastapi import Request
import datetime
from typing import Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class UsageService:
    @staticmethod
    def detect_app_type_from_request(request: Request) -> AppType:
        """Detect app type from request headers or user agent"""
        user_agent = request.headers.get("User-Agent", "").lower()
        
        # Check for mobile app indicators
        if "aifriendchat" in user_agent or "ios" in user_agent or "mobile" in user_agent:
            return AppType.MOBILE
        elif "business" in user_agent:
            return AppType.WEB_BUSINESS
        else:
            return AppType.MOBILE  # Default to mobile for iOS app
    
    @staticmethod
    def initialize_user_usage(user_id: int, app_type: AppType, db: Session) -> UsageLimits:
        """Initialize usage limits for a new user"""
        
        # Set trial limits based on app type
        if app_type == AppType.MOBILE:
            trial_calls = 2  # iOS app gets 2 free trial calls
        else:
            trial_calls = 4  # Web business gets 4 free trial calls
        
        usage_limits = UsageLimits(
            user_id=user_id,
            app_type=app_type,
            trial_calls_remaining=trial_calls,
            trial_calls_used=0,
            is_trial_active=True,
            is_subscribed=False,
            calls_made_total=0,
            calls_made_today=0,
            calls_made_this_week=0,
            calls_made_this_month=0,
            week_start_date=datetime.datetime.utcnow(),
            month_start_date=datetime.datetime.utcnow(),
            trial_start_date=datetime.datetime.utcnow()
        )
        
        db.add(usage_limits)
        db.commit()
        db.refresh(usage_limits)
        
        logger.info(f"Initialized usage limits for user {user_id} with {trial_calls} trial calls")
        return usage_limits
    
    @staticmethod
    def can_make_call(user_id: int, db: Session) -> Tuple[bool, str, Dict[str, Any]]:
        """Check if user can make a call and return status details"""
        
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == user_id).first()
        
        if not usage_limits:
            # User doesn't have usage limits - this shouldn't happen
            return False, "no_limits_found", {
                "message": "Usage limits not found. Please contact support.",
                "error": "no_limits_found"
            }
        
        # Check if user is subscribed
        if usage_limits.is_subscribed and usage_limits.subscription_status == "active":
            # Subscribed users can make calls (within subscription limits if any)
            return True, "subscribed", {
                "message": "Call authorized - subscribed user",
                "subscription_tier": usage_limits.subscription_tier,
                "calls_remaining": "unlimited" if not usage_limits.weekly_call_limit else usage_limits.weekly_call_limit - usage_limits.calls_made_this_week
            }
        
        # Check trial status
        if usage_limits.is_trial_active:
            if usage_limits.trial_calls_remaining > 0:
                return True, "trial_active", {
                    "message": f"{usage_limits.trial_calls_remaining} trial calls remaining",
                    "calls_remaining": usage_limits.trial_calls_remaining,
                    "trial_calls_used": usage_limits.trial_calls_used
                }
            else:
                # Trial exhausted
                return False, "trial_calls_exhausted", {
                    "message": "Your trial calls have been used. Upgrade to continue making calls.",
                    "calls_remaining": 0,
                    "trial_calls_used": usage_limits.trial_calls_used,
                    "pricing": {
                        "basic": {"price": "$4.99", "calls": "20 per month"},
                        "premium": {"price": "$9.99", "calls": "unlimited"}
                    },
                    "upgrade_url": "/pricing"
                }
        
        # Trial inactive and not subscribed
        return False, "trial_exhausted", {
            "message": "Please upgrade to continue making calls",
            "upgrade_url": "/pricing"
        }
    
    @staticmethod
    def record_call_made(user_id: int, db: Session) -> bool:
        """Record that a call was made and update usage statistics"""
        
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == user_id).first()
        
        if not usage_limits:
            logger.error(f"No usage limits found for user {user_id}")
            return False
        
        now = datetime.datetime.utcnow()
        
        # Update call counts
        usage_limits.calls_made_total += 1
        usage_limits.calls_made_today += 1
        usage_limits.calls_made_this_week += 1
        usage_limits.calls_made_this_month += 1
        usage_limits.last_call_date = now
        usage_limits.updated_at = now
        
        # Update trial calls if on trial
        if usage_limits.is_trial_active and usage_limits.trial_calls_remaining > 0:
            usage_limits.trial_calls_remaining -= 1
            usage_limits.trial_calls_used += 1
            
            # Deactivate trial if no calls remaining
            if usage_limits.trial_calls_remaining <= 0:
                usage_limits.is_trial_active = False
                logger.info(f"Trial exhausted for user {user_id}")
        
        db.commit()
        
        logger.info(f"Recorded call for user {user_id}. Total calls: {usage_limits.calls_made_total}, Trial remaining: {usage_limits.trial_calls_remaining}")
        return True
    
    @staticmethod
    def get_usage_stats(user_id: int, db: Session) -> Dict[str, Any]:
        """Get usage statistics for a user"""
        
        usage_limits = db.query(UsageLimits).filter(
            UsageLimits.user_id == user_id).first()
        
        if not usage_limits:
            # Return default stats for new users
            return {
                "trial_calls_remaining": 2,
                "calls_made_total": 0,
                "is_trial_active": True,
                "is_subscribed": False,
                "subscription_status": None,
                "app_type": "mobile"
            }
        
        return {
            "trial_calls_remaining": usage_limits.trial_calls_remaining,
            "calls_made_total": usage_limits.calls_made_total,
            "calls_made_today": usage_limits.calls_made_today,
            "calls_made_this_week": usage_limits.calls_made_this_week,
            "calls_made_this_month": usage_limits.calls_made_this_month,
            "is_trial_active": usage_limits.is_trial_active,
            "is_subscribed": usage_limits.is_subscribed,
            "subscription_status": usage_limits.subscription_status,
            "subscription_tier": usage_limits.subscription_tier,
            "app_type": usage_limits.app_type.value,
            "last_call_date": usage_limits.last_call_date.isoformat() if usage_limits.last_call_date else None,
            "trial_start_date": usage_limits.trial_start_date.isoformat() if usage_limits.trial_start_date else None
        }
    
    @staticmethod
    def reset_daily_counts(db: Session):
        """Reset daily call counts - should be run daily via cron"""
        try:
            db.query(UsageLimits).update({
                UsageLimits.calls_made_today: 0
            })
            db.commit()
            logger.info("Daily call counts reset")
        except Exception as e:
            logger.error(f"Error resetting daily counts: {e}")
            db.rollback()
    
    @staticmethod
    def reset_weekly_counts(db: Session):
        """Reset weekly call counts - should be run weekly via cron"""
        try:
            now = datetime.datetime.utcnow()
            db.query(UsageLimits).update({
                UsageLimits.calls_made_this_week: 0,
                UsageLimits.week_start_date: now
            })
            db.commit()
            logger.info("Weekly call counts reset")
        except Exception as e:
            logger.error(f"Error resetting weekly counts: {e}")
            db.rollback() 