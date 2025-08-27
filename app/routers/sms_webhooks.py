"""
SMS Webhook Handlers for Twilio
Handles incoming SMS messages and generates TwiML responses
"""

import logging
import os
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.db import get_db
from app.services.sms_service import SMSService
from app.business_config import SMS_BOT_CONFIG
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.limiter import rate_limit
from app import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize SMS service
sms_service = SMSService()

# Development mode check
IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"


@router.post("/sms/webhook")
@rate_limit("30/minute")  # Rate limit per IP to prevent abuse
async def handle_sms_webhook(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handle incoming SMS from Twilio
    
    Twilio sends SMS data as form fields:
    - From: Customer's phone number
    - To: Our Twilio phone number  
    - Body: The SMS message content
    - MessageSid: Twilio's unique message identifier
    """
    
    try:
        # Validate Twilio signature for security
        if not IS_DEV and config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            
            # Get form data for signature validation
            form_data = await request.form()
            params = dict(form_data)
            
            if not validator.validate(request_url, params, twilio_signature):
                logger.warning(f"Invalid Twilio signature for SMS from {sanitize_text(From)}")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            if not config.TWILIO_AUTH_TOKEN:
                logger.warning("TWILIO_AUTH_TOKEN not configured; skipping SMS signature validation")
        
        # Log incoming SMS (sanitized)
        logger.info(f"SMS received from {sanitize_text(From)} to {sanitize_text(To)}: {sanitize_text(Body[:100])}")
        
        # Check if SMS bot is enabled
        if not SMS_BOT_CONFIG.get("enabled", True):
            logger.info("SMS bot is disabled, ignoring message")
            return Response(content="", media_type="application/xml")
        
        # Process SMS with AI service
        result = await sms_service.handle_incoming_sms(
            from_number=From,
            to_number=To,
            body=Body,
            message_sid=MessageSid,
            db=db
        )
        
        # Create TwiML response
        twiml_response = MessagingResponse()
        
        if result["success"]:
            # Add AI response to TwiML
            twiml_response.message(result["response"])
            
            # Send notification to business owner if configured
            owner_phone = SMS_BOT_CONFIG.get("notification_phone")
            if owner_phone:
                try:
                    await sms_service.send_notification_to_owner(
                        customer_phone=From,
                        customer_message=Body,
                        ai_response=result["response"],
                        owner_phone=owner_phone
                    )
                except Exception as e:
                    logger.error(f"Failed to send owner notification: {str(e)}")
            
            logger.info(f"SMS response sent to {sanitize_text(From)}: {sanitize_text(result['response'][:100])}")
        else:
            # Send error response
            error_message = "I'm having trouble right now. Please try again or contact support@hyperlabs.ai"
            twiml_response.message(error_message)
            logger.error(f"SMS processing failed for {sanitize_text(From)}: {result.get('error')}")
        
        # Return TwiML XML response
        return Response(content=str(twiml_response), media_type="application/xml")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in SMS webhook: {str(e)}")
        
        # Send fallback response even if processing fails
        fallback_response = MessagingResponse()
        fallback_response.message("Sorry, I'm having technical difficulties. Please try again later or contact support@hyperlabs.ai")
        
        return Response(content=str(fallback_response), media_type="application/xml")


@router.post("/sms/status-callback")
async def handle_sms_status_callback(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    To: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Handle SMS delivery status callbacks from Twilio
    
    Twilio sends status updates for sent messages:
    - MessageSid: Unique identifier for the message
    - MessageStatus: delivered, failed, undelivered, etc.
    - To: Recipient phone number
    """
    
    try:
        # Validate Twilio signature
        if not IS_DEV and config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            
            form_data = await request.form()
            params = dict(form_data)
            
            if not validator.validate(request_url, params, twilio_signature):
                logger.warning(f"Invalid Twilio signature for SMS status callback")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Log status update
        logger.info(f"SMS status update: {sanitize_text(MessageSid)} -> {MessageStatus}")
        
        # Update message status in database
        from app.models import SMSMessage
        message = db.query(SMSMessage).filter(
            SMSMessage.message_sid == MessageSid
        ).first()
        
        if message:
            # Update status based on Twilio callback
            if MessageStatus in ["delivered", "sent"]:
                message.status = "sent"
            elif MessageStatus in ["failed", "undelivered"]:
                message.status = "failed"
                message.error_message = f"Delivery failed: {MessageStatus}"
            
            db.commit()
            logger.info(f"Updated message {sanitize_text(MessageSid)} status to {MessageStatus}")
        else:
            logger.warning(f"Message {sanitize_text(MessageSid)} not found in database")
        
        return {"status": "ok", "message_sid": MessageSid, "status": MessageStatus}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling SMS status callback: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.get("/sms/stats")
async def get_sms_stats(db: Session = Depends(get_db)):
    """Get SMS bot statistics (for internal monitoring)"""
    try:
        stats = sms_service.get_conversation_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Error getting SMS stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.post("/sms/send-manual")
@rate_limit("5/minute")
async def send_manual_sms(
    request: Request,
    to_number: str = Form(...),
    message: str = Form(...),
    from_number: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Send manual SMS (for testing or manual customer outreach)
    
    Note: This should be protected with authentication in production
    """
    try:
        # Use default Twilio number if not specified
        if not from_number:
            from_number = config.TWILIO_PHONE_NUMBER or "+1234567890"  # Replace with your actual number
        
        # Validate message length
        if len(message) > SMS_BOT_CONFIG.get("max_message_length", 1600):
            raise HTTPException(status_code=400, detail="Message too long")
        
        # Send SMS
        success = await sms_service.send_sms_response(from_number, to_number, message)
        
        if success:
            # Store as manual outbound message
            conversation = await sms_service.get_or_create_conversation(
                to_number, from_number, db
            )
            
            sms_service._store_outbound_message(
                conversation.id, from_number, to_number, message, db
            )
            
            logger.info(f"Manual SMS sent to {sanitize_text(to_number)}")
            return {"success": True, "message": "SMS sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send SMS")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending manual SMS: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send SMS")


@router.get("/sms/conversations")
async def list_sms_conversations(
    limit: int = 20,
    offset: int = 0,
    status: str = None,
    db: Session = Depends(get_db)
):
    """List SMS conversations (for admin/monitoring)"""
    try:
        from app.models import SMSConversation
        from sqlalchemy import desc
        
        query = db.query(SMSConversation)
        
        if status:
            query = query.filter(SMSConversation.status == status)
        
        conversations = query.order_by(
            desc(SMSConversation.last_message_at)
        ).offset(offset).limit(limit).all()
        
        result = []
        for conv in conversations:
            result.append({
                "id": conv.id,
                "phone_number": conv.phone_number[-4:] + "***",  # Partially hide number
                "status": conv.status,
                "total_messages": conv.total_messages,
                "lead_score": conv.lead_score,
                "conversion_status": conv.conversion_status,
                "customer_interest": conv.customer_interest,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            })
        
        return {
            "conversations": result,
            "total": len(result),
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error listing conversations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/sms/conversation/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """Get messages for a specific conversation (for admin/monitoring)"""
    try:
        from app.models import SMSMessage, SMSConversation
        from sqlalchemy import desc
        
        # Verify conversation exists
        conversation = db.query(SMSConversation).filter(
            SMSConversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = db.query(SMSMessage).filter(
            SMSMessage.conversation_id == conversation_id
        ).order_by(SMSMessage.created_at).all()
        
        result = []
        for msg in messages:
            result.append({
                "id": msg.id,
                "direction": msg.direction,
                "body": msg.body,
                "intent": msg.intent_detected,
                "sentiment": msg.sentiment_score,
                "status": msg.status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            })
        
        return {
            "conversation_id": conversation_id,
            "phone_number": conversation.phone_number[-4:] + "***",
            "messages": result,
            "total_messages": len(result)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get messages")
