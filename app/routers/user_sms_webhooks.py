"""
User-Specific SMS Webhook Handlers
Each user gets their own webhook endpoint for their SMS bot
"""

import logging
import os
from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.db import get_db
from app.models import User, UserBusinessConfig, SMSMessage
from app.services.user_sms_service import UserSMSService
from app.utils.log_helpers import sanitize_text
from app.limiter import rate_limit
from app import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Development mode check
IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"


@router.post("/sms/{user_id}/webhook")
@rate_limit("60/minute")  # Per user rate limit
async def handle_user_sms_webhook(
    user_id: int,
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handle SMS webhook for specific user's business

    Each user gets their own endpoint: /sms/{user_id}/webhook
    This allows users to configure their Twilio number to point to their specific endpoint
    """

    try:
        # Validate Twilio signature for security
        if not IS_DEV and config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)

            form_data = await request.form()
            params = dict(form_data)

            if not validator.validate(request_url, params, twilio_signature):
                logger.warning(
                    f"Invalid Twilio signature for user {user_id} SMS from {sanitize_text(From)}")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")

        # Validate user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for SMS webhook")
            raise HTTPException(status_code=404, detail="User not found")

        # Check for duplicate messages
        existing_message = db.query(SMSMessage).filter(
            SMSMessage.message_sid == MessageSid
        ).first()

        if existing_message:
            logger.info(
                f"Duplicate message detected for user {user_id}: {sanitize_text(MessageSid)}")
            return Response(content="", media_type="application/xml")

        # Log incoming SMS
        logger.info(
            f"SMS received for user {user_id} from {sanitize_text(From)}: {sanitize_text(Body[:100])}")

        # Process SMS with user's specific service
        user_sms_service = UserSMSService(user_id)
        result = await user_sms_service.handle_incoming_sms(
            from_number=From,
            to_number=To,
            body=Body,
            message_sid=MessageSid,
            db=db
        )

        # Create TwiML response
        twiml_response = MessagingResponse()

        if result["success"]:
            # Send response via TwiML (Twilio handles the actual sending)
            twiml_response.message(result["response"])

            # Store outbound message for tracking
            outbound_message = SMSMessage(
                conversation_id=result["conversation_id"],
                message_sid=f"outbound_{MessageSid}_{datetime.utcnow().timestamp()}",
                direction="outbound",
                from_number=To,
                to_number=From,
                body=result["response"],
                status="sent",
                sent_at=datetime.utcnow()
            )
            db.add(outbound_message)
            db.commit()

            logger.info(
                f"SMS response sent for user {user_id} to {sanitize_text(From)}")
        else:
            # Handle different failure reasons
            if result.get("reason") == "sms_disabled":
                # SMS bot is disabled for this user
                return Response(content="", media_type="application/xml")
            elif result.get("reason") == "usage_limit_exceeded":
                # Send usage limit message
                twiml_response.message(result["response"])
            else:
                # Generic error
                error_message = result.get(
                    "response", "I'm having trouble right now. Please try again later.")
                twiml_response.message(error_message)

            logger.error(
                f"SMS processing failed for user {user_id}: {result.get('reason', 'unknown')}")

        return Response(content=str(twiml_response), media_type="application/xml")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in SMS webhook for user {user_id}: {str(e)}")

        # Send fallback response
        fallback_response = MessagingResponse()
        fallback_response.message(
            "Sorry, I'm having technical difficulties. Please try again later.")

        return Response(content=str(fallback_response), media_type="application/xml")


@router.get("/sms/{user_id}/info")
async def get_user_sms_info(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get SMS bot information for a specific user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == user_id
        ).first()

        if not business_config:
            return {
                "user_id": user_id,
                "configured": False,
                "webhook_url": f"https://your-domain.com/sms/{user_id}/webhook",
                "message": "SMS bot not configured. Set up your business information first."
            }

        user_sms_service = UserSMSService(user_id)
        usage_stats = user_sms_service.get_usage_stats(db)

        return {
            "user_id": user_id,
            "configured": True,
            "webhook_url": f"https://your-domain.com/sms/{user_id}/webhook",
            "company_name": business_config.company_name,
            "bot_name": business_config.bot_name,
            "sms_enabled": business_config.sms_enabled,
            "plan": business_config.sms_plan.value,
            "usage_stats": usage_stats
        }

    except Exception as e:
        logger.error(f"Error getting SMS info for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to get SMS information")


@router.get("/sms/{user_id}/conversations")
async def list_user_sms_conversations(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List SMS conversations for a specific user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        from app.models import SMSConversation
        from sqlalchemy import desc

        conversations = db.query(SMSConversation).filter(
            SMSConversation.user_id == user_id
        ).order_by(
            desc(SMSConversation.last_message_at)
        ).offset(offset).limit(limit).all()

        result = []
        for conv in conversations:
            result.append({
                "id": conv.id,
                # Partially hide
                "customer_phone": conv.phone_number[-4:] + "***",
                "status": conv.status,
                "total_messages": conv.total_messages,
                "lead_score": conv.lead_score,
                "customer_name": conv.customer_name,
                "customer_interest": conv.customer_interest,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            })

        return {
            "user_id": user_id,
            "conversations": result,
            "total": len(result),
            "offset": offset,
            "limit": limit
        }

    except Exception as e:
        logger.error(
            f"Error listing conversations for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to list conversations")


@router.get("/sms/{user_id}/analytics")
async def get_user_sms_analytics(
    user_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get SMS analytics for a specific user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        from datetime import datetime, timedelta
        from app.models import SMSConversation, SMSUsageLog
        from sqlalchemy import func

        # Date range
        start_date = datetime.utcnow() - timedelta(days=days)

        # Basic stats
        total_conversations = db.query(SMSConversation).filter(
            SMSConversation.user_id == user_id,
            SMSConversation.created_at >= start_date
        ).count()

        total_messages = db.query(SMSMessage).join(SMSConversation).filter(
            SMSConversation.user_id == user_id,
            SMSMessage.created_at >= start_date
        ).count()

        # Business config
        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == user_id
        ).first()

        analytics = {
            "user_id": user_id,
            "period_days": days,
            "period_start": start_date.isoformat(),
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "average_messages_per_conversation": total_messages / total_conversations if total_conversations > 0 else 0,
        }

        if business_config:
            analytics.update({
                "company_name": business_config.company_name,
                "total_leads_generated": business_config.total_leads_generated,
                "total_demos_booked": business_config.total_demos_booked,
                "conversion_rate": business_config.conversion_rate,
                "plan": business_config.sms_plan.value,
                "monthly_limit": business_config.monthly_conversation_limit,
                "conversations_used_this_month": business_config.conversations_used_this_month
            })

        return analytics

    except Exception as e:
        logger.error(f"Error getting analytics for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")
