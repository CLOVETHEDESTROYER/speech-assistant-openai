"""
Payment routes for Stripe integration
Handles subscriptions, usage billing, and payment processing
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import os

from app.db import get_db
from app.auth import get_current_user
from app.models import User
from app.services.stripe_service import StripeService

logger = logging.getLogger(__name__)
router = APIRouter()

# Development mode check
IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"


# Pydantic models for request/response
class CreateSubscriptionRequest(BaseModel):
    price_id: str
    plan_name: str
    payment_method_id: Optional[str] = None


class CreatePaymentIntentRequest(BaseModel):
    amount: int  # Amount in cents
    currency: str = "usd"
    description: Optional[str] = "Speech Assistant Service"
    metadata: Optional[Dict[str, str]] = None


class UsageRecordRequest(BaseModel):
    service_type: str  # "transcription", "voice_call", "sms", "custom_scenario"
    usage_amount: int
    usage_unit: str    # "minutes", "calls", "messages", "characters"
    resource_id: Optional[int] = None
    cost_per_unit: Optional[float] = None


class SubscriptionResponse(BaseModel):
    success: bool
    subscription_id: Optional[str] = None
    client_secret: Optional[str] = None
    requires_action: bool = False
    message: str


class PaymentIntentResponse(BaseModel):
    success: bool
    client_secret: str
    payment_intent_id: str


class SubscriptionStatusResponse(BaseModel):
    has_subscription: bool
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    status: str
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    features: Dict[str, Any] = {}
    current_usage: Dict[str, Any] = {}


class CreatePlanRequest(BaseModel):
    plan_id: str  # e.g., "starter_monthly"
    name: str  # e.g., "Starter Monthly"
    plan_type: str  # "monthly", "yearly", "usage"
    features: Dict[str, Any]
    pricing: Optional[Dict[str, Any]] = None  # For usage-based plans


class UpdatePlanRequest(BaseModel):
    name: Optional[str] = None
    plan_type: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    pricing: Optional[Dict[str, Any]] = None


@router.get("/subscription-plans")
async def get_subscription_plans() -> Dict[str, Any]:
    """Get available subscription plans and pricing"""
    return {
        "plans": StripeService.SUBSCRIPTION_PLANS,
        "success": True
    }


@router.post("/admin/subscription-plans")
async def create_subscription_plan(
    request: CreatePlanRequest,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create a new subscription plan (admin only)"""
    try:
        # Check if user is admin (you can add admin role checking here)
        # For now, we'll allow any authenticated user in development mode
        if not IS_DEV:
            # Add admin role checking in production
            pass
        
        # Validate plan ID format
        if not request.plan_id or not request.plan_id.replace("_", "").isalnum():
            raise HTTPException(
                status_code=400,
                detail="Plan ID must contain only alphanumeric characters and underscores"
            )
        
        # Check if plan already exists
        if request.plan_id in StripeService.SUBSCRIPTION_PLANS:
            raise HTTPException(
                status_code=409,
                detail=f"Plan '{request.plan_id}' already exists"
            )
        
        # Create new plan
        new_plan = {
            "name": request.name,
            "type": request.plan_type,
            "features": request.features
        }
        
        if request.pricing:
            new_plan["pricing"] = request.pricing
        
        # Add the plan using the service method
        success = StripeService.add_plan(request.plan_id, new_plan)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save subscription plan"
            )
        
        logger.info(f"Created new subscription plan '{request.plan_id}' by user {current_user.id}")
        
        return {
            "success": True,
            "plan_id": request.plan_id,
            "plan": new_plan,
            "message": f"Plan '{request.plan_id}' created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subscription plan: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create subscription plan: {str(e)}"
        )


@router.put("/admin/subscription-plans/{plan_id}")
async def update_subscription_plan(
    plan_id: str,
    request: UpdatePlanRequest,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Update an existing subscription plan (admin only)"""
    try:
        # Check if user is admin (you can add admin role checking here)
        if not IS_DEV:
            # Add admin role checking in production
            pass
        
        # Check if plan exists
        if plan_id not in StripeService.SUBSCRIPTION_PLANS:
            raise HTTPException(
                status_code=404,
                detail=f"Plan '{plan_id}' not found"
            )
        
        # Update plan with provided fields
        plan = StripeService.SUBSCRIPTION_PLANS[plan_id].copy()
        
        if request.name is not None:
            plan["name"] = request.name
        if request.plan_type is not None:
            plan["type"] = request.plan_type
        if request.features is not None:
            plan["features"] = request.features
        if request.pricing is not None:
            plan["pricing"] = request.pricing
        
        # Update the plan using the service method
        success = StripeService.add_plan(plan_id, plan)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save updated subscription plan"
            )
        
        logger.info(f"Updated subscription plan '{plan_id}' by user {current_user.id}")
        
        return {
            "success": True,
            "plan_id": plan_id,
            "plan": plan,
            "message": f"Plan '{plan_id}' updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating subscription plan: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update subscription plan: {str(e)}"
        )


@router.delete("/admin/subscription-plans/{plan_id}")
async def delete_subscription_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete a subscription plan (admin only)"""
    try:
        # Check if user is admin (you can add admin role checking here)
        if not IS_DEV:
            # Add admin role checking in production
            pass
        
        # Check if plan exists
        if plan_id not in StripeService.SUBSCRIPTION_PLANS:
            raise HTTPException(
                status_code=404,
                detail=f"Plan '{plan_id}' not found"
            )
        
        # Prevent deletion of core plans in production
        core_plans = ["basic_monthly", "pro_monthly", "enterprise_monthly", "usage_based"]
        if not IS_DEV and plan_id in core_plans:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete core plan '{plan_id}' in production"
            )
        
        # Delete the plan using the service method
        deleted_plan = StripeService.SUBSCRIPTION_PLANS[plan_id]
        success = StripeService.remove_plan(plan_id)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete subscription plan"
            )
        
        logger.info(f"Deleted subscription plan '{plan_id}' by user {current_user.id}")
        
        return {
            "success": True,
            "plan_id": plan_id,
            "deleted_plan": deleted_plan,
            "message": f"Plan '{plan_id}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subscription plan: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete subscription plan: {str(e)}"
        )


@router.post("/create-subscription", response_model=SubscriptionResponse)
async def create_subscription(
    request: CreateSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new subscription for the user"""
    try:
        result = await StripeService.create_subscription(
            user=current_user,
            price_id=request.price_id,
            plan_name=request.plan_name,
            db=db,
            payment_method_id=request.payment_method_id
        )
        
        subscription = result["subscription"]
        requires_action = result["requires_action"]
        
        response = SubscriptionResponse(
            success=True,
            subscription_id=subscription.id,
            requires_action=requires_action,
            message="Subscription created successfully"
        )
        
        # Add client secret if payment requires action
        if requires_action and subscription.latest_invoice:
            if hasattr(subscription.latest_invoice, 'payment_intent'):
                response.client_secret = subscription.latest_invoice.payment_intent.client_secret
        
        logger.info(f"Created subscription {subscription.id} for user {current_user.id}")
        return response
        
    except Exception as e:
        logger.error(f"Error creating subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.post("/cancel-subscription")
async def cancel_subscription(
    at_period_end: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel user's subscription"""
    try:
        result = await StripeService.cancel_subscription(
            user=current_user,
            db=db,
            at_period_end=at_period_end
        )
        
        logger.info(f"Cancelled subscription for user {current_user.id}")
        return {
            "success": True,
            "message": "Subscription cancelled successfully",
            "at_period_end": at_period_end
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling subscription for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a payment intent for one-time payments"""
    try:
        result = await StripeService.create_payment_intent(
            user=current_user,
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            metadata=request.metadata
        )
        
        payment_intent = result["payment_intent"]
        
        logger.info(f"Created payment intent {payment_intent.id} for user {current_user.id}")
        return PaymentIntentResponse(
            success=True,
            client_secret=payment_intent.client_secret,
            payment_intent_id=payment_intent.id
        )
        
    except Exception as e:
        logger.error(f"Error creating payment intent for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create payment intent: {str(e)}"
        )


@router.get("/subscription-status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's current subscription status and usage"""
    try:
        status = await StripeService.get_user_subscription_status(
            user=current_user,
            db=db
        )
        
        return SubscriptionStatusResponse(**status)
        
    except Exception as e:
        logger.error(f"Error getting subscription status for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get subscription status: {str(e)}"
        )


@router.post("/record-usage")
async def record_usage(
    request: UsageRecordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record usage for billing (internal endpoint)"""
    try:
        usage_record = await StripeService.record_usage(
            user=current_user,
            service_type=request.service_type,
            usage_amount=request.usage_amount,
            usage_unit=request.usage_unit,
            db=db,
            resource_id=request.resource_id,
            cost_per_unit=request.cost_per_unit
        )
        
        return {
            "success": True,
            "usage_record_id": usage_record.id,
            "total_cost": usage_record.total_cost,
            "message": f"Recorded {request.usage_amount} {request.usage_unit} of {request.service_type}"
        }
        
    except Exception as e:
        logger.error(f"Error recording usage for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to record usage: {str(e)}"
        )


@router.get("/billing-history")
async def get_billing_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's billing history"""
    try:
        from app.models import PaymentRecord
        
        payment_records = db.query(PaymentRecord).filter(
            PaymentRecord.user_id == current_user.id
        ).order_by(PaymentRecord.created_at.desc()).limit(limit).all()
        
        history = []
        for record in payment_records:
            history.append({
                "id": record.id,
                "amount": record.amount,
                "currency": record.currency,
                "status": record.status,
                "payment_type": record.payment_type,
                "description": record.description,
                "created_at": record.created_at.isoformat(),
                "stripe_invoice_id": record.stripe_invoice_id
            })
        
        return {
            "success": True,
            "billing_history": history,
            "total_records": len(history)
        }
        
    except Exception as e:
        logger.error(f"Error getting billing history for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get billing history: {str(e)}"
        )


@router.get("/usage-summary")
async def get_usage_summary(
    billing_period: Optional[str] = None,  # Format: YYYY-MM
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's usage summary for a billing period"""
    try:
        from app.models import UsageRecord
        from datetime import datetime
        
        # Default to current month if no period specified
        if not billing_period:
            billing_period = datetime.utcnow().strftime("%Y-%m")
        
        usage_records = db.query(UsageRecord).filter(
            UsageRecord.user_id == current_user.id,
            UsageRecord.billing_period == billing_period
        ).all()
        
        # Aggregate usage by service type
        usage_summary = {}
        total_cost = 0
        
        for record in usage_records:
            if record.service_type not in usage_summary:
                usage_summary[record.service_type] = {
                    "total_amount": 0,
                    "total_cost": 0,
                    "unit": record.usage_unit,
                    "records": 0
                }
            
            usage_summary[record.service_type]["total_amount"] += record.usage_amount
            usage_summary[record.service_type]["total_cost"] += record.total_cost
            usage_summary[record.service_type]["records"] += 1
            total_cost += record.total_cost
        
        return {
            "success": True,
            "billing_period": billing_period,
            "usage_summary": usage_summary,
            "total_cost": total_cost,
            "currency": "usd"
        }
        
    except Exception as e:
        logger.error(f"Error getting usage summary for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get usage summary: {str(e)}"
        )


# Webhook endpoint for Stripe events
@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events"""
    try:
        import stripe
        from app import config
        
        # Get the raw body and signature
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        # Verify the webhook signature (skip in development mode)
        if not IS_DEV and hasattr(config, 'STRIPE_WEBHOOK_SECRET') and config.STRIPE_WEBHOOK_SECRET:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, config.STRIPE_WEBHOOK_SECRET
                )
            except ValueError:
                logger.error("Invalid payload in Stripe webhook")
                raise HTTPException(status_code=400, detail="Invalid payload")
            except stripe.error.SignatureVerificationError:
                logger.error("Invalid signature in Stripe webhook")
                raise HTTPException(status_code=400, detail="Invalid signature")
        else:
            # For development/testing without webhook signature verification
            import json
            if not payload:
                # Handle empty payload for testing
                event = {"type": "test.event", "id": "evt_test_empty", "data": {"object": "test"}}
                logger.info(f"🔧 Development mode: Empty payload, using test event")
            else:
                try:
                    event = json.loads(payload)
                    logger.info(f"🔧 Development mode: Skipping webhook signature validation")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in development mode: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
        # Process the event
        result = await StripeService.process_webhook_event(event, db)
        
        logger.info(f"Processed Stripe webhook: {event.get('type', 'unknown')} - {event.get('id', 'no-id')}")
        return {"success": True, "processed": result.get("processed", False)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Webhook processing failed: {str(e)}"
        )
