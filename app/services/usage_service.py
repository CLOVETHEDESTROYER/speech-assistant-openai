from sqlalchemy.orm import Session
from app.models import User, UsageLimits, AppType, SubscriptionTier
from datetime import datetime, date, timedelta
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class UsageService:

    @staticmethod
    def initialize_user_usage(user_id: int, app_type: AppType, db: Session) -> UsageLimits:
        """Initialize usage tracking for a new user based on app type"""
        try:
            # Check if usage limits already exist
            existing = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()
            if existing:
                return existing

            # Set trial limits based on app type
            trial_calls = 3 if app_type == AppType.MOBILE_CONSUMER else 4
            trial_end = datetime.utcnow() + timedelta(days=7)  # 7-day trial for both

            # Determine subscription tier
            if app_type == AppType.MOBILE_CONSUMER:
                tier = SubscriptionTier.MOBILE_FREE_TRIAL
            else:
                tier = SubscriptionTier.BUSINESS_FREE_TRIAL

            usage_limits = UsageLimits(
                user_id=user_id,
                app_type=app_type,
                trial_calls_remaining=trial_calls,
                trial_start_date=datetime.utcnow(),
                trial_end_date=trial_end,
                subscription_tier=tier,
                week_start_date=date.today(),
                month_start_date=date.today()
            )

            db.add(usage_limits)
            db.commit()
            db.refresh(usage_limits)

            logger.info(
                f"Initialized usage limits for user {user_id} with app type {app_type.value}")
            return usage_limits

        except Exception as e:
            logger.error(f"Error initializing user usage: {str(e)}")
            db.rollback()
            raise

    @staticmethod
    def can_make_call(user_id: int, db: Session) -> Tuple[bool, str, Dict]:
        """Check if user can make a call and return detailed status"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False, "Usage limits not initialized", {}

            # Check if trial is still active
            if usage.is_trial_active and usage.trial_end_date > datetime.utcnow():
                if usage.trial_calls_remaining > 0:
                    return True, "trial_call_available", {
                        "calls_remaining": usage.trial_calls_remaining,
                        "trial_ends": usage.trial_end_date.isoformat(),
                        "app_type": usage.app_type.value
                    }
                else:
                    return False, "trial_calls_exhausted", {
                        "message": "Trial calls exhausted. Please upgrade to continue.",
                        "app_type": usage.app_type.value,
                        "trial_ends": usage.trial_end_date.isoformat()
                    }

            # Check subscription status
            if usage.is_subscribed and usage.subscription_end_date > datetime.utcnow():
                # Check weekly/monthly limits for business users
                if usage.app_type == AppType.WEB_BUSINESS:
                    if usage.weekly_call_limit and usage.calls_made_this_week >= usage.weekly_call_limit:
                        return False, "weekly_limit_reached", {
                            "message": f"Weekly limit of {usage.weekly_call_limit} calls reached",
                            "resets_on": (usage.week_start_date + timedelta(days=7)).isoformat()
                        }

                return True, "subscription_active", {
                    "subscription_tier": usage.subscription_tier.value,
                    "calls_this_week": usage.calls_made_this_week,
                    "weekly_limit": usage.weekly_call_limit
                }

            # No active trial or subscription
            return False, "upgrade_required", {
                "message": "Please upgrade to continue making calls",
                "app_type": usage.app_type.value,
                "pricing": UsageService.get_pricing_info(usage.app_type)
            }

        except Exception as e:
            logger.error(f"Error checking call permissions: {str(e)}")
            return False, "error", {"message": "Unable to verify call permissions"}

    @staticmethod
    def record_call(user_id: int, db: Session) -> bool:
        """Record a call made by the user and update usage statistics"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()
            if not usage:
                return False

            today = date.today()

            # Reset daily counter if needed
            if usage.last_call_date != today:
                usage.calls_made_today = 0
                usage.last_call_date = today

            # Reset weekly counter if needed
            if usage.week_start_date and (today - usage.week_start_date).days >= 7:
                usage.calls_made_this_week = 0
                usage.week_start_date = today

            # Reset monthly counter if needed
            if usage.month_start_date and today.month != usage.month_start_date.month:
                usage.calls_made_this_month = 0
                usage.month_start_date = today

            # Update counters
            usage.calls_made_today += 1
            usage.calls_made_this_week += 1
            usage.calls_made_this_month += 1
            usage.calls_made_total += 1

            # Deduct trial call if in trial
            if usage.is_trial_active and usage.trial_calls_remaining > 0:
                usage.trial_calls_remaining -= 1
                usage.trial_calls_used += 1

                # End trial if no calls remaining
                if usage.trial_calls_remaining == 0:
                    usage.is_trial_active = False

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Recorded call for user {user_id}. Calls remaining: {usage.trial_calls_remaining}")
            return True

        except Exception as e:
            logger.error(f"Error recording call: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def upgrade_subscription(user_id: int, subscription_tier: SubscriptionTier,
                             app_store_transaction_id: str, db: Session) -> bool:
        """Upgrade user to paid subscription"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()
            if not usage:
                return False

            usage.subscription_tier = subscription_tier
            usage.is_subscribed = True
            usage.subscription_start_date = datetime.utcnow()
            usage.app_store_transaction_id = app_store_transaction_id

            # Set limits based on subscription tier
            if subscription_tier == SubscriptionTier.MOBILE_WEEKLY:
                usage.subscription_end_date = datetime.utcnow() + timedelta(days=7)
                usage.billing_cycle = "weekly"
                usage.app_store_product_id = "speech_assistant_weekly"

            elif subscription_tier == SubscriptionTier.BUSINESS_BASIC:
                usage.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = 20
                usage.monthly_call_limit = 80

            elif subscription_tier == SubscriptionTier.BUSINESS_PROFESSIONAL:
                usage.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = 50
                usage.monthly_call_limit = 200

            elif subscription_tier == SubscriptionTier.BUSINESS_ENTERPRISE:
                usage.subscription_end_date = datetime.utcnow() + timedelta(days=30)
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = None  # Unlimited
                usage.monthly_call_limit = None  # Unlimited

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Upgraded user {user_id} to {subscription_tier.value}")
            return True

        except Exception as e:
            logger.error(f"Error upgrading subscription: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def get_usage_stats(user_id: int, db: Session) -> Dict:
        """Get comprehensive usage statistics for a user"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()
            if not usage:
                return {}

            stats = {
                "app_type": usage.app_type.value,
                "subscription_tier": usage.subscription_tier.value if usage.subscription_tier else None,
                "is_subscribed": usage.is_subscribed,
                "is_trial_active": usage.is_trial_active,
                "trial_calls_remaining": usage.trial_calls_remaining,
                "trial_calls_used": usage.trial_calls_used,
                "calls_made_today": usage.calls_made_today,
                "calls_made_this_week": usage.calls_made_this_week,
                "calls_made_this_month": usage.calls_made_this_month,
                "calls_made_total": usage.calls_made_total,
                "weekly_call_limit": usage.weekly_call_limit,
                "monthly_call_limit": usage.monthly_call_limit,
                "trial_end_date": usage.trial_end_date.isoformat() if usage.trial_end_date else None,
                "subscription_end_date": usage.subscription_end_date.isoformat() if usage.subscription_end_date else None,
                "billing_cycle": usage.billing_cycle,
                "next_payment_date": usage.next_payment_date.isoformat() if usage.next_payment_date else None
            }

            # Add upgrade recommendation
            if not usage.is_subscribed and usage.trial_calls_remaining <= 1:
                stats["upgrade_recommended"] = True
                stats["pricing"] = UsageService.get_pricing_info(
                    usage.app_type)

            return stats

        except Exception as e:
            logger.error(f"Error getting usage stats: {str(e)}")
            return {}

    @staticmethod
    def get_pricing_info(app_type: AppType) -> Dict:
        """Get pricing information based on app type"""
        if app_type == AppType.MOBILE_CONSUMER:
            return {
                "weekly_plan": {
                    "price": "$4.99",
                    "billing": "weekly",
                    "features": ["Unlimited calls", "Fun scenarios", "Call friends"]
                }
            }
        else:
            return {
                "basic_plan": {
                    "price": "$49.99",
                    "billing": "monthly",
                    "features": ["20 calls per week", "Basic scenarios", "Call transcripts"]
                },
                "professional_plan": {
                    "price": "$99.00",
                    "billing": "monthly",
                    "features": ["50 calls per week", "Custom scenarios", "Calendar integration"]
                },
                "enterprise_plan": {
                    "price": "$299.00",
                    "billing": "monthly",
                    "features": ["Unlimited calls", "Advanced features", "Priority support"]
                }
            }

    @staticmethod
    def detect_app_type_from_request(request) -> AppType:
        """Detect app type from request headers or user agent"""
        # Check for mobile app identifier in headers
        user_agent = request.headers.get("user-agent", "").lower()
        app_identifier = request.headers.get("x-app-type", "").lower()

        if "speech-assistant-mobile" in user_agent or app_identifier == "mobile":
            return AppType.MOBILE_CONSUMER
        else:
            return AppType.WEB_BUSINESS
