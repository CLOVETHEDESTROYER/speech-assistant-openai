"""
SMS Service Layer
Handles SMS conversation management, message processing, and Twilio integration
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models import SMSConversation, SMSMessage
from app.services.sms_ai_service import SMSAIService
from app.services.twilio_client import get_twilio_client
from app.business_config import SMS_BOT_CONFIG
from app.utils.log_helpers import sanitize_text

logger = logging.getLogger(__name__)


class SMSService:
    """Core SMS service for handling customer conversations"""
    
    def __init__(self):
        self.twilio_client = get_twilio_client()
        self.ai_service = SMSAIService()
        self.config = SMS_BOT_CONFIG
        
    async def handle_incoming_sms(
        self, 
        from_number: str, 
        to_number: str, 
        body: str, 
        message_sid: str,
        db: Session
    ) -> Dict:
        """
        Process incoming SMS message and generate AI response
        
        Args:
            from_number: Customer's phone number
            to_number: Our Twilio phone number
            body: Message content
            message_sid: Twilio's unique message ID
            db: Database session
            
        Returns:
            Dict with processing results and response
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit(from_number, db):
                logger.warning(f"Rate limit exceeded for {sanitize_text(from_number)}")
                return {
                    "success": False,
                    "error": "rate_limited",
                    "message": "Too many messages. Please wait before sending another."
                }
            
            # Get or create conversation
            conversation = await self.get_or_create_conversation(
                from_number, to_number, db
            )
            
            # Store incoming message
            incoming_message = self._store_incoming_message(
                conversation.id, from_number, to_number, body, message_sid, db
            )
            
            # Get conversation context for AI
            context = self._get_conversation_context(conversation.id, db)
            
            # Get customer info if available
            customer_info = self._extract_customer_info(conversation)
            
            # Generate AI response
            ai_result = await self.ai_service.generate_response(
                body, context, customer_info
            )
            
            # Update message with AI processing results
            self._update_message_with_ai_results(incoming_message, ai_result, db)
            
            # Update conversation metadata
            self._update_conversation_metadata(
                conversation, ai_result, body, db
            )
            
            # Send response via Twilio
            response_sent = await self.send_sms_response(
                to_number, from_number, ai_result["response"]
            )
            
            if response_sent:
                # Store outbound message
                self._store_outbound_message(
                    conversation.id, to_number, from_number, 
                    ai_result["response"], db
                )
                
                incoming_message.status = "responded"
                incoming_message.processed_at = datetime.utcnow()
            else:
                incoming_message.status = "failed"
                incoming_message.error_message = "Failed to send response"
            
            db.commit()
            
            return {
                "success": response_sent,
                "response": ai_result["response"],
                "intent": ai_result.get("intent"),
                "conversation_id": conversation.id,
                "message_id": incoming_message.id
            }
            
        except Exception as e:
            logger.error(f"Error handling SMS: {str(e)}")
            db.rollback()
            
            # Send fallback response
            fallback_response = "I'm having trouble processing that right now. Please try again or contact support@hyperlabs.ai"
            await self.send_sms_response(to_number, from_number, fallback_response)
            
            return {
                "success": False,
                "error": str(e),
                "response": fallback_response
            }
    
    async def get_or_create_conversation(
        self, 
        phone_number: str, 
        twilio_number: str, 
        db: Session
    ) -> SMSConversation:
        """Get existing conversation or create a new one"""
        
        # Look for active conversation within last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=self.config["conversation_timeout_hours"])
        
        conversation = db.query(SMSConversation).filter(
            and_(
                SMSConversation.phone_number == phone_number,
                SMSConversation.twilio_phone_number == twilio_number,
                SMSConversation.status == "active",
                SMSConversation.last_message_at > cutoff_time
            )
        ).first()
        
        if conversation:
            # Update last message time
            conversation.last_message_at = datetime.utcnow()
            conversation.updated_at = datetime.utcnow()
            db.commit()
            return conversation
        
        # Create new conversation
        new_conversation = SMSConversation(
            phone_number=phone_number,
            twilio_phone_number=twilio_number,
            conversation_context=[],
            status="active",
            total_messages=0,
            lead_score=0,
            conversion_status="prospect"
        )
        
        db.add(new_conversation)
        db.commit()
        db.refresh(new_conversation)
        
        logger.info(f"Created new SMS conversation for {sanitize_text(phone_number)}")
        return new_conversation
    
    async def send_sms_response(
        self, 
        from_number: str, 
        to_number: str, 
        message: str
    ) -> bool:
        """Send SMS response via Twilio"""
        try:
            # Add small delay to appear more human
            if self.config.get("response_delay_seconds", 0) > 0:
                await asyncio.sleep(self.config["response_delay_seconds"])
            
            message_instance = self.twilio_client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )
            
            logger.info(f"SMS sent successfully: {message_instance.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS: {str(e)}")
            return False
    
    def _check_rate_limit(self, phone_number: str, db: Session) -> bool:
        """Check if phone number is within rate limits"""
        if not self.config.get("rate_limit_per_hour"):
            return True
        
        # Count messages from this number in the last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        message_count = db.query(SMSMessage).join(SMSConversation).filter(
            and_(
                SMSConversation.phone_number == phone_number,
                SMSMessage.direction == "inbound",
                SMSMessage.created_at > one_hour_ago
            )
        ).count()
        
        return message_count < self.config["rate_limit_per_hour"]
    
    def _store_incoming_message(
        self,
        conversation_id: int,
        from_number: str,
        to_number: str,
        body: str,
        message_sid: str,
        db: Session
    ) -> SMSMessage:
        """Store incoming message in database"""
        
        message = SMSMessage(
            conversation_id=conversation_id,
            message_sid=message_sid,
            direction="inbound",
            from_number=from_number,
            to_number=to_number,
            body=body,
            status="received"
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        return message
    
    def _store_outbound_message(
        self,
        conversation_id: int,
        from_number: str,
        to_number: str,
        body: str,
        db: Session
    ) -> SMSMessage:
        """Store outbound message in database"""
        
        message = SMSMessage(
            conversation_id=conversation_id,
            message_sid=f"outbound_{datetime.utcnow().timestamp()}",  # Generate unique ID
            direction="outbound",
            from_number=from_number,
            to_number=to_number,
            body=body,
            status="sent",
            sent_at=datetime.utcnow(),
            processed_at=datetime.utcnow()
        )
        
        db.add(message)
        db.commit()
        
        return message
    
    def _get_conversation_context(self, conversation_id: int, db: Session) -> List[Dict]:
        """Get recent conversation context for AI processing"""
        
        max_messages = self.config.get("max_context_messages", 10)
        
        messages = db.query(SMSMessage).filter(
            SMSMessage.conversation_id == conversation_id
        ).order_by(desc(SMSMessage.created_at)).limit(max_messages).all()
        
        # Reverse to get chronological order
        messages = list(reversed(messages))
        
        context = []
        for msg in messages:
            context.append({
                "direction": msg.direction,
                "body": msg.body,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "intent_detected": msg.intent_detected,
                "sentiment_score": msg.sentiment_score
            })
        
        return context
    
    def _extract_customer_info(self, conversation: SMSConversation) -> Optional[Dict]:
        """Extract available customer information"""
        if not any([conversation.customer_name, conversation.customer_email, conversation.customer_interest]):
            return None
        
        return {
            "name": conversation.customer_name,
            "email": conversation.customer_email,
            "interest": conversation.customer_interest,
            "lead_score": conversation.lead_score,
            "conversion_status": conversation.conversion_status
        }
    
    def _update_message_with_ai_results(
        self, 
        message: SMSMessage, 
        ai_result: Dict, 
        db: Session
    ):
        """Update message with AI processing results"""
        
        message.ai_response = ai_result.get("response")
        message.intent_detected = ai_result.get("intent")
        message.sentiment_score = ai_result.get("sentiment_score")
        message.entities_extracted = ai_result.get("entities", {})
        message.processed_at = datetime.utcnow()
        
        db.commit()
    
    def _update_conversation_metadata(
        self,
        conversation: SMSConversation,
        ai_result: Dict,
        customer_message: str,
        db: Session
    ):
        """Update conversation with metadata and extracted information"""
        
        # Increment message count
        conversation.total_messages += 1
        conversation.last_message_at = datetime.utcnow()
        conversation.updated_at = datetime.utcnow()
        
        # Extract and update customer information
        entities = ai_result.get("entities", {})
        
        if entities.get("emails") and not conversation.customer_email:
            conversation.customer_email = entities["emails"][0]
        
        if entities.get("names") and not conversation.customer_name:
            conversation.customer_name = entities["names"][0]
        
        # Update interest based on intent
        intent = ai_result.get("intent")
        if intent in ["pricing", "demo_request", "features"] and not conversation.customer_interest:
            if "mobile" in customer_message.lower() or "app" in customer_message.lower():
                conversation.customer_interest = "mobile"
            elif "business" in customer_message.lower() or "enterprise" in customer_message.lower():
                conversation.customer_interest = "business"
            else:
                conversation.customer_interest = intent
        
        # Update conversion status based on intent progression
        if intent == "demo_request":
            conversation.conversion_status = "demo_requested"
        elif intent == "scheduling":
            conversation.conversion_status = "demo_scheduled"
        
        # Update lead score
        context = self._get_conversation_context(conversation.id, db)
        customer_info = self._extract_customer_info(conversation)
        conversation.lead_score = self.ai_service.calculate_lead_score(context, customer_info)
        
        # Update conversation context (keep last few messages)
        max_context = self.config.get("max_context_messages", 10)
        conversation.conversation_context = conversation.conversation_context or []
        
        conversation.conversation_context.append({
            "direction": "inbound",
            "body": customer_message,
            "timestamp": datetime.utcnow().isoformat(),
            "intent": intent,
            "sentiment": ai_result.get("sentiment_score")
        })
        
        # Keep only recent context
        if len(conversation.conversation_context) > max_context:
            conversation.conversation_context = conversation.conversation_context[-max_context:]
        
        db.commit()
    
    def get_conversation_stats(self, db: Session) -> Dict:
        """Get SMS conversation statistics"""
        try:
            # Active conversations (last 24 hours)
            last_24h = datetime.utcnow() - timedelta(hours=24)
            active_conversations = db.query(SMSConversation).filter(
                SMSConversation.last_message_at > last_24h
            ).count()
            
            # Total messages today
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            messages_today = db.query(SMSMessage).filter(
                SMSMessage.created_at > today
            ).count()
            
            # Lead quality stats
            high_quality_leads = db.query(SMSConversation).filter(
                SMSConversation.lead_score > 70
            ).count()
            
            # Conversion stats
            demo_requested = db.query(SMSConversation).filter(
                SMSConversation.conversion_status == "demo_requested"
            ).count()
            
            demo_scheduled = db.query(SMSConversation).filter(
                SMSConversation.conversion_status == "demo_scheduled"
            ).count()
            
            return {
                "active_conversations_24h": active_conversations,
                "messages_today": messages_today,
                "high_quality_leads": high_quality_leads,
                "demos_requested": demo_requested,
                "demos_scheduled": demo_scheduled,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation stats: {str(e)}")
            return {"error": str(e)}
    
    async def send_notification_to_owner(
        self, 
        customer_phone: str, 
        customer_message: str, 
        ai_response: str,
        owner_phone: str
    ) -> bool:
        """Send SMS notification to business owner about new customer message"""
        try:
            if not owner_phone:
                return False
            
            notification_text = f"""🤖 SMS Bot Alert:
From: {customer_phone[-4:]}***
Message: {customer_message[:100]}{'...' if len(customer_message) > 100 else ''}
Bot Reply: {ai_response[:100]}{'...' if len(ai_response) > 100 else ''}"""
            
            # Use the same Twilio number to send notification
            message_instance = self.twilio_client.messages.create(
                body=notification_text,
                from_="+1234567890",  # Replace with your actual Twilio number
                to=owner_phone
            )
            
            logger.info(f"Notification sent to owner: {message_instance.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send owner notification: {str(e)}")
            return False
