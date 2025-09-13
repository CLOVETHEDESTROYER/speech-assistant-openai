"""
Stripe Service for handling payments, subscriptions, and billing
Integrates with the speech assistant application for voice/SMS services
"""

import stripe
import logging
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app import config
from app.models import User, UserSubscription, PaymentRecord, UsageRecord, StripeWebhookEvent

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = config.STRIPE_SECRET_KEY if hasattr(
    config, 'STRIPE_SECRET_KEY') else None


class StripeService:
    """Service for handling all Stripe operations"""

    # Subscription Plans Configuration
    PLANS_FILE = "subscription_plans.json"

    SUBSCRIPTION_PLANS = {
        "basic_monthly": {
            "name": "Basic Monthly",
            "type": "monthly",
            "features": {
                "voice_minutes": 100,
                "sms_messages": 500,
                "custom_scenarios": 3,
                "transcription_storage": "30_days"
            }
        },
        "pro_monthly": {
            "name": "Pro Monthly",
            "type": "monthly",
            "features": {
                "voice_minutes": 500,
                "sms_messages": 2000,
                "custom_scenarios": 10,
                "transcription_storage": "90_days",
                "advanced_analytics": True
            }
        },
        "enterprise_monthly": {
            "name": "Enterprise Monthly",
            "type": "monthly",
            "features": {
                "voice_minutes": "unlimited",
                "sms_messages": "unlimited",
                "custom_scenarios": "unlimited",
                "transcription_storage": "1_year",
                "advanced_analytics": True,
                "priority_support": True,
                "white_label": True
            }
        },
        "usage_based": {
            "name": "Pay As You Go",
            "type": "usage",
            "pricing": {
                "voice_per_minute": 0.05,  # $0.05 per minute
                "sms_per_message": 0.01,   # $0.01 per SMS
                "transcription_per_minute": 0.02,  # $0.02 per transcription minute
                "custom_scenario_setup": 5.00     # $5.00 per custom scenario
            }
        }
    }

    @staticmethod
    async def create_customer(user: User, db: Session) -> Dict[str, Any]:
        """Create a Stripe customer for a user"""
        try:
            # Check if customer already exists
            if user.subscription and user.subscription.stripe_customer_id:
                customer = stripe.Customer.retrieve(
                    user.subscription.stripe_customer_id)
                return {"customer": customer, "created": False}

            # Create new Stripe customer
            customer = stripe.Customer.create(
                email=user.email,
                name=user.full_name,
                metadata={
                    'user_id': user.id,
                    'auth_provider': user.auth_provider,
                    'created_from': 'speech_assistant_app'
                }
            )

            logger.info(
                f"Created Stripe customer {customer.id} for user {user.id}")
            return {"customer": customer, "created": True}

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating customer for user {user.id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating customer for user {user.id}: {e}")
            raise

    @staticmethod
    async def create_subscription(
        user: User,
        price_id: str,
        plan_name: str,
        db: Session,
        payment_method_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a subscription for a user"""
        try:
            # Ensure customer exists
            customer_result = await StripeService.create_customer(user, db)
            customer = customer_result["customer"]

            # Create subscription parameters
            subscription_params = {
                'customer': customer.id,
                'items': [{'price': price_id}],
                'metadata': {
                    'user_id': user.id,
                    'plan_name': plan_name
                },
                'expand': ['latest_invoice.payment_intent']
            }

            # Add payment method if provided
            if payment_method_id:
                subscription_params['default_payment_method'] = payment_method_id

            # Create Stripe subscription
            subscription = stripe.Subscription.create(**subscription_params)

            # Determine plan type
            plan_config = StripeService.SUBSCRIPTION_PLANS.get(plan_name, {})
            plan_type = plan_config.get("type", "monthly")

            # Create or update database record
            db_subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id
            ).first()

            if not db_subscription:
                db_subscription = UserSubscription(
                    user_id=user.id,
                    stripe_customer_id=customer.id,
                    stripe_subscription_id=subscription.id,
                    plan_name=plan_name,
                    plan_type=plan_type,
                    status=subscription.status,
                    current_period_start=datetime.fromtimestamp(
                        subscription.current_period_start, tz=timezone.utc
                    ),
                    current_period_end=datetime.fromtimestamp(
                        subscription.current_period_end, tz=timezone.utc
                    )
                )
                db.add(db_subscription)
            else:
                # Update existing subscription
                db_subscription.stripe_subscription_id = subscription.id
                db_subscription.plan_name = plan_name
                db_subscription.plan_type = plan_type
                db_subscription.status = subscription.status
                db_subscription.current_period_start = datetime.fromtimestamp(
                    subscription.current_period_start, tz=timezone.utc
                )
                db_subscription.current_period_end = datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                )
                db_subscription.updated_at = datetime.utcnow()

            db.commit()

            logger.info(
                f"Created subscription {subscription.id} for user {user.id}")
            return {
                "subscription": subscription,
                "db_subscription": db_subscription,
                "requires_action": subscription.status == "incomplete"
            }

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating subscription for user {user.id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Error creating subscription for user {user.id}: {e}")
            raise

    @staticmethod
    async def cancel_subscription(user: User, db: Session, at_period_end: bool = True) -> Dict[str, Any]:
        """Cancel a user's subscription"""
        try:
            db_subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id,
                UserSubscription.status.in_(["active", "trialing"])
            ).first()

            if not db_subscription:
                raise ValueError("No active subscription found")

            # Cancel in Stripe
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    db_subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
            else:
                subscription = stripe.Subscription.cancel(
                    db_subscription.stripe_subscription_id
                )

            # Update database
            db_subscription.status = subscription.status
            db_subscription.cancel_at_period_end = subscription.cancel_at_period_end
            db_subscription.updated_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Cancelled subscription {subscription.id} for user {user.id}")
            return {"subscription": subscription, "cancelled": True}

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error cancelling subscription for user {user.id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Error cancelling subscription for user {user.id}: {e}")
            raise

    @staticmethod
    async def create_payment_intent(
        user: User,
        amount: int,  # Amount in cents
        currency: str = "usd",
        description: str = "Speech Assistant Service",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a payment intent for one-time payments"""
        try:
            # Ensure customer exists
            customer_result = await StripeService.create_customer(user, None)
            customer = customer_result["customer"]

            payment_intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                customer=customer.id,
                description=description,
                metadata={
                    'user_id': str(user.id),
                    **(metadata or {})
                },
                automatic_payment_methods={'enabled': True}
            )

            logger.info(
                f"Created payment intent {payment_intent.id} for user {user.id}")
            return {"payment_intent": payment_intent}

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating payment intent for user {user.id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Error creating payment intent for user {user.id}: {e}")
            raise

    @staticmethod
    async def record_usage(
        user: User,
        service_type: str,  # "transcription", "voice_call", "sms", "custom_scenario"
        usage_amount: int,
        usage_unit: str,    # "minutes", "calls", "messages", "characters"
        db: Session,
        resource_id: Optional[int] = None,
        cost_per_unit: Optional[float] = None
    ) -> UsageRecord:
        """Record usage for billing purposes"""
        try:
            # Get current billing period (YYYY-MM format)
            billing_period = datetime.utcnow().strftime("%Y-%m")

            # Calculate cost if not provided
            if cost_per_unit is None:
                usage_plan = StripeService.SUBSCRIPTION_PLANS.get(
                    "usage_based", {})
                pricing = usage_plan.get("pricing", {})

                if service_type == "transcription":
                    cost_per_unit = pricing.get(
                        "transcription_per_minute", 0.02)
                elif service_type == "voice_call":
                    cost_per_unit = pricing.get("voice_per_minute", 0.05)
                elif service_type == "sms":
                    cost_per_unit = pricing.get("sms_per_message", 0.01)
                elif service_type == "custom_scenario":
                    cost_per_unit = pricing.get("custom_scenario_setup", 5.00)
                else:
                    cost_per_unit = 0.0

            # Convert to cents
            cost_per_unit_cents = int(cost_per_unit * 100)
            total_cost_cents = cost_per_unit_cents * usage_amount

            # Get user's subscription
            subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id
            ).first()

            # Create usage record
            usage_record = UsageRecord(
                user_id=user.id,
                subscription_id=subscription.id if subscription else None,
                service_type=service_type,
                usage_amount=usage_amount,
                usage_unit=usage_unit,
                cost_per_unit=cost_per_unit_cents,
                total_cost=total_cost_cents,
                billing_period=billing_period
            )

            # Set resource references based on service type
            if service_type == "transcription" and resource_id:
                usage_record.transcript_id = resource_id
            elif service_type == "voice_call" and resource_id:
                usage_record.conversation_id = resource_id
            elif service_type == "sms" and resource_id:
                usage_record.sms_conversation_id = resource_id

            db.add(usage_record)
            db.commit()

            logger.info(
                f"Recorded usage: {usage_amount} {usage_unit} of {service_type} for user {user.id}")
            return usage_record

        except Exception as e:
            logger.error(f"Error recording usage for user {user.id}: {e}")
            raise

    @staticmethod
    async def get_user_subscription_status(user: User, db: Session) -> Dict[str, Any]:
        """Get comprehensive subscription status for a user"""
        try:
            subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id
            ).first()

            if not subscription:
                return {
                    "has_subscription": False,
                    "plan_name": None,
                    "status": "no_subscription",
                    "features": {}
                }

            # Get plan features
            plan_config = StripeService.SUBSCRIPTION_PLANS.get(
                subscription.plan_name, {})
            features = plan_config.get("features", {})

            # Get current period usage
            current_period = datetime.utcnow().strftime("%Y-%m")
            usage_records = db.query(UsageRecord).filter(
                UsageRecord.user_id == user.id,
                UsageRecord.billing_period == current_period
            ).all()

            # Calculate usage by service type
            usage_summary = {}
            for record in usage_records:
                if record.service_type not in usage_summary:
                    usage_summary[record.service_type] = {
                        "amount": 0,
                        "cost": 0,
                        "unit": record.usage_unit
                    }
                usage_summary[record.service_type]["amount"] += record.usage_amount
                usage_summary[record.service_type]["cost"] += record.total_cost

            return {
                "has_subscription": True,
                "plan_name": subscription.plan_name,
                "plan_type": subscription.plan_type,
                "status": subscription.status,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "features": features,
                "current_usage": usage_summary,
                "stripe_customer_id": subscription.stripe_customer_id,
                "stripe_subscription_id": subscription.stripe_subscription_id
            }

        except Exception as e:
            logger.error(
                f"Error getting subscription status for user {user.id}: {e}")
            raise

    @staticmethod
    async def process_webhook_event(event_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Process Stripe webhook events"""
        try:
            event_id = event_data.get("id")
            event_type = event_data.get("type")

            # Check if event already processed
            existing_event = db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.stripe_event_id == event_id
            ).first()

            if existing_event and existing_event.processed:
                logger.info(f"Webhook event {event_id} already processed")
                return {"processed": True, "message": "Event already processed"}

            # Create or update webhook event record
            if not existing_event:
                webhook_event = StripeWebhookEvent(
                    stripe_event_id=event_id,
                    event_type=event_type,
                    event_data=event_data
                )
                db.add(webhook_event)
            else:
                webhook_event = existing_event
                webhook_event.event_data = event_data

            try:
                # Process different event types
                if event_type == "invoice.payment_succeeded":
                    await StripeService._handle_payment_succeeded(event_data, db)
                elif event_type == "invoice.payment_failed":
                    await StripeService._handle_payment_failed(event_data, db)
                elif event_type == "customer.subscription.updated":
                    await StripeService._handle_subscription_updated(event_data, db)
                elif event_type == "customer.subscription.deleted":
                    await StripeService._handle_subscription_deleted(event_data, db)

                # Mark as processed
                webhook_event.processed = True
                webhook_event.processed_at = datetime.utcnow()

            except Exception as processing_error:
                webhook_event.processing_error = str(processing_error)
                logger.error(
                    f"Error processing webhook {event_id}: {processing_error}")
                raise

            db.commit()
            logger.info(
                f"Successfully processed webhook event {event_id} of type {event_type}")
            return {"processed": True, "event_type": event_type}

        except Exception as e:
            logger.error(f"Error processing webhook event: {e}")
            raise

    @staticmethod
    async def _handle_payment_succeeded(event_data: Dict[str, Any], db: Session):
        """Handle successful payment webhook"""
        invoice = event_data["data"]["object"]
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")

        # Skip processing if no customer ID (test data)
        if not customer_id:
            logger.info(
                f"Skipping payment processing - no customer ID in test data")
            return

        # Find user by customer ID
        subscription = db.query(UserSubscription).filter(
            UserSubscription.stripe_customer_id == customer_id
        ).first()

        if subscription:
            # Create payment record
            payment_record = PaymentRecord(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                stripe_payment_intent_id=invoice.get("payment_intent", ""),
                stripe_invoice_id=invoice["id"],
                amount=invoice["amount_paid"],
                currency=invoice["currency"],
                status="succeeded",
                payment_type="subscription" if subscription_id else "one_time",
                description=f"Payment for {subscription.plan_name}",
                payment_metadata={"invoice_data": invoice}
            )
            db.add(payment_record)

            # Update subscription status if needed
            if subscription_id:
                subscription.status = "active"
                subscription.updated_at = datetime.utcnow()

    @staticmethod
    async def _handle_payment_failed(event_data: Dict[str, Any], db: Session):
        """Handle failed payment webhook"""
        invoice = event_data["data"]["object"]
        customer_id = invoice.get("customer")

        # Skip processing if no customer ID (test data)
        if not customer_id:
            logger.info(
                f"Skipping payment failed processing - no customer ID in test data")
            return

        # Find user by customer ID
        subscription = db.query(UserSubscription).filter(
            UserSubscription.stripe_customer_id == customer_id
        ).first()

        if subscription:
            # Update subscription status
            subscription.status = "past_due"
            subscription.updated_at = datetime.utcnow()

    @staticmethod
    async def _handle_subscription_updated(event_data: Dict[str, Any], db: Session):
        """Handle subscription update webhook"""
        stripe_subscription = event_data["data"]["object"]

        # Find subscription in database
        db_subscription = db.query(UserSubscription).filter(
            UserSubscription.stripe_subscription_id == stripe_subscription["id"]
        ).first()

        if db_subscription:
            db_subscription.status = stripe_subscription["status"]
            db_subscription.current_period_start = datetime.fromtimestamp(
                stripe_subscription["current_period_start"], tz=timezone.utc
            )
            db_subscription.current_period_end = datetime.fromtimestamp(
                stripe_subscription["current_period_end"], tz=timezone.utc
            )
            db_subscription.cancel_at_period_end = stripe_subscription.get(
                "cancel_at_period_end", False)
            db_subscription.updated_at = datetime.utcnow()

    @staticmethod
    async def _handle_subscription_deleted(event_data: Dict[str, Any], db: Session):
        """Handle subscription deletion webhook"""
        stripe_subscription = event_data["data"]["object"]

        # Find subscription in database
        db_subscription = db.query(UserSubscription).filter(
            UserSubscription.stripe_subscription_id == stripe_subscription["id"]
        ).first()

        if db_subscription:
            db_subscription.status = "canceled"
            db_subscription.updated_at = datetime.utcnow()

    @staticmethod
    def save_plans_to_file():
        """Save current plans to JSON file"""
        try:
            with open(StripeService.PLANS_FILE, 'w') as f:
                json.dump(StripeService.SUBSCRIPTION_PLANS, f, indent=2)
            logger.info(
                f"Saved {len(StripeService.SUBSCRIPTION_PLANS)} plans to {StripeService.PLANS_FILE}")
        except Exception as e:
            logger.error(f"Error saving plans to file: {e}")

    @staticmethod
    def load_plans_from_file():
        """Load plans from JSON file if it exists"""
        try:
            if os.path.exists(StripeService.PLANS_FILE):
                with open(StripeService.PLANS_FILE, 'r') as f:
                    loaded_plans = json.load(f)
                    StripeService.SUBSCRIPTION_PLANS.update(loaded_plans)
                logger.info(
                    f"Loaded {len(loaded_plans)} plans from {StripeService.PLANS_FILE}")
            else:
                logger.info(
                    f"No plans file found at {StripeService.PLANS_FILE}, using defaults")
        except Exception as e:
            logger.error(f"Error loading plans from file: {e}")

    @staticmethod
    def add_plan(plan_id: str, plan_data: Dict[str, Any]) -> bool:
        """Add or update a subscription plan"""
        try:
            StripeService.SUBSCRIPTION_PLANS[plan_id] = plan_data
            StripeService.save_plans_to_file()
            logger.info(f"Added/updated plan '{plan_id}'")
            return True
        except Exception as e:
            logger.error(f"Error adding plan '{plan_id}': {e}")
            return False

    @staticmethod
    def remove_plan(plan_id: str) -> bool:
        """Remove a subscription plan"""
        try:
            if plan_id in StripeService.SUBSCRIPTION_PLANS:
                del StripeService.SUBSCRIPTION_PLANS[plan_id]
                StripeService.save_plans_to_file()
                logger.info(f"Removed plan '{plan_id}'")
                return True
            else:
                logger.warning(f"Plan '{plan_id}' not found")
                return False
        except Exception as e:
            logger.error(f"Error removing plan '{plan_id}': {e}")
            return False


# Load plans from file on startup
StripeService.load_plans_from_file()
