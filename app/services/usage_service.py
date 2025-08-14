from sqlalchemy.orm import Session
from app.models import User, UsageLimits, AppType, SubscriptionTier, SubscriptionStatus
from datetime import datetime, date, timedelta
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class UsageService:
    # Constants for mobile usage limits
    BASIC_WEEKLY_CALLS = 5
    BASIC_CALL_DURATION_LIMIT = 60  # seconds
    PREMIUM_MONTHLY_CALLS = 30
    PREMIUM_CALL_DURATION_LIMIT = 120  # seconds
    ADDON_CALLS_COUNT = 5
    ADDON_CALLS_PRICE = 4.99

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
            trial_calls = 1 if app_type == AppType.MOBILE_CONSUMER else 5
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
                week_start_date=date.today(),  # Start counting from now
                month_start_date=date.today(),  # Start counting from now
                is_trial_active=True
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
                        "duration_limit": UsageService.BASIC_CALL_DURATION_LIMIT,
                        "trial_ends": usage.trial_end_date.isoformat(),
                        "app_type": usage.app_type.value
                    }
                else:
                    # Context-aware upgrade messages based on app type
                    if usage.app_type == AppType.MOBILE_CONSUMER:
                        return False, "trial_exhausted", {
                            "message": "Your free call is used up! 🎉 Ready for unlimited fun? Upgrade to Basic for just $4.99/week and get 5 calls per week!",
                            "upgrade_options": [
                                {"plan": "basic", "price": "$4.99", "calls": "5/week",
                                    "product_id": "speech_assistant_basic_weekly"},
                                {"plan": "premium", "price": "$25.00", "calls": "30/month",
                                    "product_id": "speech_assistant_premium_monthly"}
                            ]
                        }
                    else:
                        return False, "trial_exhausted", {
                            "message": "Your 5 free trial calls have been used. Upgrade to Business Basic ($49.99/month) for 20 calls per week to continue using our service.",
                            "upgrade_options": [
                                {"plan": "business_basic", "price": "$49.99", "calls": "20/week",
                                    "product_id": "speech_assistant_business_basic"},
                                {"plan": "business_professional", "price": "$99.00", "calls": "unlimited",
                                    "product_id": "speech_assistant_business_pro"}
                            ]
                        }

            # Check subscription status
            if usage.is_subscribed and usage.subscription_end_date > datetime.utcnow():
                if usage.subscription_tier == SubscriptionTier.MOBILE_BASIC:
                    # Check weekly limits (reset every 7 days from start date)
                    if usage.calls_made_this_week >= UsageService.BASIC_WEEKLY_CALLS:
                        # Check if they have valid addon calls
                        if (usage.addon_calls_remaining > 0 and
                            usage.addon_calls_expiry and
                                usage.addon_calls_expiry > datetime.utcnow()):
                            return True, "addon_call_available", {
                                "addon_calls_remaining": usage.addon_calls_remaining,
                                "duration_limit": UsageService.BASIC_CALL_DURATION_LIMIT
                            }
                        else:
                            return False, "weekly_limit_reached", {
                                "message": "Weekly limit reached. Upgrade to Premium or buy 5 more calls for $4.99!",
                                "upgrade_options": [
                                    {"plan": "premium", "price": "$25.00", "calls": "30/month",
                                        "product_id": "speech_assistant_premium_monthly"},
                                    {"plan": "addon", "price": "$4.99", "calls": "5 additional",
                                        "product_id": "speech_assistant_addon_calls"}
                                ]
                            }
                    else:
                        return True, "basic_call_available", {
                            "calls_remaining_this_week": UsageService.BASIC_WEEKLY_CALLS - usage.calls_made_this_week,
                            "duration_limit": UsageService.BASIC_CALL_DURATION_LIMIT
                        }

                elif usage.subscription_tier == SubscriptionTier.MOBILE_PREMIUM:
                    # Check monthly limits (reset every 30 days from start date)
                    if usage.calls_made_this_month >= UsageService.PREMIUM_MONTHLY_CALLS:
                        return False, "monthly_limit_reached", {
                            "message": "Monthly limit reached. Buy 5 more calls for $4.99!",
                            "upgrade_options": [
                                {"plan": "addon", "price": "$4.99", "calls": "5 additional",
                                    "product_id": "speech_assistant_addon_calls"}
                            ]
                        }
                    else:
                        return True, "premium_call_available", {
                            "calls_remaining_this_month": UsageService.PREMIUM_MONTHLY_CALLS - usage.calls_made_this_month,
                            "duration_limit": UsageService.PREMIUM_CALL_DURATION_LIMIT
                        }

                # Handle business users (existing logic)
                elif usage.app_type == AppType.WEB_BUSINESS:
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

            # No active trial or subscription - context-aware messaging
            if usage.app_type == AppType.MOBILE_CONSUMER:
                return False, "upgrade_required", {
                    "message": "Want to keep the fun going? 🎮 Upgrade to start making calls again!",
                    "upgrade_options": [
                        {"plan": "basic", "price": "$4.99", "calls": "5/week",
                            "product_id": "speech_assistant_basic_weekly"},
                        {"plan": "premium", "price": "$25.00", "calls": "30/month",
                            "product_id": "speech_assistant_premium_monthly"}
                    ]
                }
            else:
                return False, "upgrade_required", {
                    "message": "Please upgrade to a Business plan to continue making calls for your organization.",
                    "upgrade_options": [
                        {"plan": "business_basic", "price": "$49.99", "calls": "20/week",
                            "product_id": "speech_assistant_business_basic"},
                        {"plan": "business_professional", "price": "$99.00", "calls": "unlimited",
                            "product_id": "speech_assistant_business_pro"}
                    ]
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
    def upgrade_subscription_with_receipt(user_id: int, subscription_tier: SubscriptionTier,
                                          subscription_info: Dict, db: Session) -> bool:
        """Upgrade user to paid subscription using validated App Store receipt data"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()
            if not usage:
                return False

            # Extract data from validated receipt
            transaction_id = subscription_info.get("transaction_id")
            original_transaction_id = subscription_info.get(
                "original_transaction_id")
            product_id = subscription_info.get("product_id")
            purchase_date_str = subscription_info.get("purchase_date")
            expires_date_str = subscription_info.get("expires_date")
            is_trial_period = subscription_info.get("is_trial_period", False)

            # Convert Apple's date format to datetime
            if purchase_date_str:
                purchase_date = datetime.fromisoformat(
                    purchase_date_str.replace('Z', '+00:00'))
            else:
                purchase_date = datetime.utcnow()

            if expires_date_str:
                expires_date = datetime.fromisoformat(
                    expires_date_str.replace('Z', '+00:00'))
            else:
                # Fallback: set expiration based on subscription tier
                if subscription_tier == SubscriptionTier.MOBILE_WEEKLY:
                    expires_date = purchase_date + timedelta(days=7)
                else:
                    expires_date = purchase_date + timedelta(days=30)

            # Update usage limits with validated receipt data
            usage.subscription_tier = subscription_tier
            usage.is_subscribed = True
            usage.subscription_status = SubscriptionStatus.ACTIVE
            usage.subscription_start_date = purchase_date
            usage.subscription_end_date = expires_date
            usage.app_store_transaction_id = original_transaction_id or transaction_id
            usage.app_store_product_id = product_id
            usage.last_payment_date = purchase_date
            usage.next_payment_date = expires_date

            # Set limits based on subscription tier
            if subscription_tier == SubscriptionTier.MOBILE_WEEKLY:
                usage.billing_cycle = "weekly"
                # For mobile weekly, no call limits (unlimited)
                usage.weekly_call_limit = None
                usage.monthly_call_limit = None

            elif subscription_tier == SubscriptionTier.BUSINESS_BASIC:
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = 20
                usage.monthly_call_limit = 80

            elif subscription_tier == SubscriptionTier.BUSINESS_PROFESSIONAL:
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = 50
                usage.monthly_call_limit = 200

            elif subscription_tier == SubscriptionTier.BUSINESS_ENTERPRISE:
                usage.billing_cycle = "monthly"
                usage.weekly_call_limit = None  # Unlimited
                usage.monthly_call_limit = None  # Unlimited

            # End trial if user was in trial
            if usage.is_trial_active:
                usage.is_trial_active = False
                usage.trial_calls_remaining = 0

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Upgraded user {user_id} to {subscription_tier.value} with validated receipt")
            return True

        except Exception as e:
            logger.error(
                f"Error upgrading subscription with receipt: {str(e)}")
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

    # Enhanced mobile usage methods
    @staticmethod
    def record_call_start(user_id: int, db: Session) -> bool:
        """Record call start (without duration)"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            # Update call counts
            usage.calls_made_today += 1
            usage.calls_made_this_week += 1
            usage.calls_made_this_month += 1
            usage.calls_made_total += 1

            # Update trial calls if applicable
            if usage.is_trial_active:
                usage.trial_calls_remaining = max(
                    0, usage.trial_calls_remaining - 1)
                usage.trial_calls_used += 1

                if usage.trial_calls_remaining == 0:
                    usage.is_trial_active = False

            # Update addon calls if applicable
            if usage.addon_calls_remaining > 0:
                usage.addon_calls_remaining -= 1

            usage.updated_at = datetime.utcnow()
            db.commit()

            return True

        except Exception as e:
            logger.error(f"Error recording call start: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def record_call_duration(user_id: int, call_duration: int, db: Session) -> bool:
        """Record call duration when call ends"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            # Update duration tracking
            usage.total_call_duration_this_week += call_duration
            usage.total_call_duration_this_month += call_duration

            usage.updated_at = datetime.utcnow()
            db.commit()

            return True

        except Exception as e:
            logger.error(f"Error recording call duration: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def check_and_reset_limits(user_id: int, db: Session) -> bool:
        """Check and reset limits based on 7-day/30-day cycles from start date"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            now = datetime.utcnow()
            today = now.date()
            reset_occurred = False

            # Check weekly reset (7 days from week_start_date)
            if usage.week_start_date and (today - usage.week_start_date).days >= 7:
                usage.calls_made_this_week = 0
                usage.total_call_duration_this_week = 0
                usage.week_start_date = today
                reset_occurred = True
                logger.info(f"Reset weekly limits for user {user_id}")

            # Check monthly reset (30 days from month_start_date)
            if usage.month_start_date and (today - usage.month_start_date).days >= 30:
                usage.calls_made_this_month = 0
                usage.total_call_duration_this_month = 0
                usage.month_start_date = today
                reset_occurred = True
                logger.info(f"Reset monthly limits for user {user_id}")

            # Check addon call expiry
            if usage.addon_calls_expiry and usage.addon_calls_expiry < now:
                usage.addon_calls_remaining = 0
                usage.addon_calls_expiry = None
                reset_occurred = True
                logger.info(f"Expired addon calls for user {user_id}")

            if reset_occurred:
                usage.updated_at = now
                db.commit()

            return reset_occurred

        except Exception as e:
            logger.error(f"Error checking/resetting limits: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def upgrade_to_basic_subscription(user_id: int, subscription_info: Dict, db: Session) -> bool:
        """Upgrade user to basic subscription"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            usage.subscription_tier = SubscriptionTier.MOBILE_BASIC
            usage.is_subscribed = True
            usage.subscription_start_date = datetime.utcnow()
            usage.subscription_end_date = datetime.utcnow() + timedelta(days=7)  # Weekly
            usage.app_store_transaction_id = subscription_info.get(
                "transaction_id")

            # Reset trial status
            usage.is_trial_active = False
            usage.trial_calls_remaining = 0

            # Reset weekly counts for new subscription period
            usage.calls_made_this_week = 0
            usage.total_call_duration_this_week = 0
            usage.week_start_date = date.today()

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Upgraded user {user_id} to basic subscription")
            return True

        except Exception as e:
            logger.error(f"Error upgrading to basic subscription: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def upgrade_to_premium_subscription(user_id: int, subscription_info: Dict, db: Session) -> bool:
        """Upgrade user to premium subscription"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            usage.subscription_tier = SubscriptionTier.MOBILE_PREMIUM
            usage.is_subscribed = True
            usage.subscription_start_date = datetime.utcnow()
            usage.subscription_end_date = datetime.utcnow() + timedelta(days=30)  # Monthly
            usage.app_store_transaction_id = subscription_info.get(
                "transaction_id")

            # Reset trial status
            usage.is_trial_active = False
            usage.trial_calls_remaining = 0

            # Reset monthly counts for new subscription period
            usage.calls_made_this_month = 0
            usage.total_call_duration_this_month = 0
            usage.month_start_date = date.today()

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Upgraded user {user_id} to premium subscription")
            return True

        except Exception as e:
            logger.error(f"Error upgrading to premium subscription: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def purchase_addon_calls(user_id: int, subscription_info: Dict, db: Session) -> bool:
        """Purchase additional 5 calls"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.user_id == user_id).first()

            if not usage:
                return False

            # Add 5 calls, expire in 30 days
            usage.addon_calls_remaining += 5
            usage.addon_calls_expiry = datetime.utcnow() + timedelta(days=30)
            usage.app_store_transaction_id = subscription_info.get(
                "transaction_id")

            usage.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Purchased addon calls for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error purchasing addon calls: {str(e)}")
            db.rollback()
            return False
