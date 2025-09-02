"""
User-Specific SMS Service
Handles SMS bot functionality for individual users with their custom business configuration
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
import os

from app.models import (
    User, UserBusinessConfig, SMSConversation, SMSMessage, SMSUsageLog,
    SMSPlan, ResponseTone
)
from app.services.twilio_client import get_twilio_client
from app.services.sms_calendar_service import SMSCalendarService
from app.utils.log_helpers import sanitize_text

logger = logging.getLogger(__name__)


class UserSMSService:
    """SMS service for individual users with custom business configuration"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.twilio_client = get_twilio_client()
        self.ai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.calendar_service = SMSCalendarService()  # Add calendar integration

    async def get_or_create_business_config(self, db: Session) -> UserBusinessConfig:
        """Get user's business configuration or create default one"""
        config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == self.user_id
        ).first()

        if not config:
            config = self._create_default_business_config(db)

        return config

    def _create_default_business_config(self, db: Session) -> UserBusinessConfig:
        """Create default business configuration for new user"""
        user = db.query(User).filter(User.id == self.user_id).first()
        if not user:
            raise ValueError(f"User {self.user_id} not found")

        # Extract company name from email domain or use generic name
        email_domain = user.email.split(
            '@')[1] if '@' in user.email else "company"
        default_company_name = email_domain.split('.')[0].title() + " Inc"

        config = UserBusinessConfig(
            user_id=self.user_id,
            company_name=default_company_name,
            description="A forward-thinking company focused on providing excellent customer service.",
            services=["Customer Support",
                      "Information Services", "Consultation"],
            bot_name="Assistant",
            bot_personality="Professional, helpful, and knowledgeable customer service representative",
            response_tone=ResponseTone.PROFESSIONAL,
            custom_greeting=f"Hi! I'm an AI assistant for {default_company_name}. How can I help you today?",
            sms_enabled=True,
            sms_plan=SMSPlan.FREE_TRIAL,
            monthly_conversation_limit=10,
            business_hours={
                "monday": {"start": "09:00", "end": "17:00"},
                "tuesday": {"start": "09:00", "end": "17:00"},
                "wednesday": {"start": "09:00", "end": "17:00"},
                "thursday": {"start": "09:00", "end": "17:00"},
                "friday": {"start": "09:00", "end": "17:00"},
                "saturday": None,
                "sunday": None
            },
            contact_info={
                "email": user.email,
                "website": f"https://{email_domain}"
            }
        )

        db.add(config)
        db.commit()
        db.refresh(config)

        logger.info(f"Created default business config for user {self.user_id}")
        return config

    async def handle_incoming_sms(
        self,
        from_number: str,
        to_number: str,
        body: str,
        message_sid: str,
        db: Session
    ) -> Dict:
        """Handle incoming SMS for this specific user"""
        try:
            # Get user's business configuration
            business_config = await self.get_or_create_business_config(db)

            # Check if SMS bot is enabled
            if not business_config.sms_enabled:
                logger.info(f"SMS bot disabled for user {self.user_id}")
                return {"success": False, "reason": "sms_disabled"}

            # Check usage limits
            if not self._check_usage_limits(business_config, db):
                logger.warning(f"Usage limit exceeded for user {self.user_id}")
                return {
                    "success": False,
                    "reason": "usage_limit_exceeded",
                    "response": "I apologize, but we've reached our monthly conversation limit. Please contact us directly for assistance."
                }

            # Get or create conversation
            conversation = await self.get_or_create_conversation(
                from_number, to_number, db
            )

            # Store incoming message
            incoming_message = self._store_incoming_message(
                conversation.id, from_number, to_number, body, message_sid, db
            )

            # Get conversation context
            context = self._get_conversation_context(conversation.id, db)

            # Check for calendar/scheduling requests BEFORE generating response
            calendar_handled = False
            if business_config.calendar_integration_enabled:
                calendar_result = await self._handle_calendar_request(
                    body, conversation, from_number, db
                )
                if calendar_result:
                    ai_response = calendar_result["response"]
                    calendar_handled = True

            # Generate regular AI response if calendar didn't handle it
            if not calendar_handled:
                ai_response = await self._generate_business_response(
                    body, context, business_config
                )

            # Update message with AI response
            incoming_message.ai_response = ai_response
            incoming_message.processed_at = datetime.utcnow()
            incoming_message.status = "responded"

            # Add calendar context flag if calendar was used
            if calendar_handled:
                incoming_message.calendar_processed = True

            # Update conversation
            conversation.total_messages += 1
            conversation.last_message_at = datetime.utcnow()

            # Log usage
            self._log_usage(business_config, conversation,
                            incoming_message, db)

            db.commit()

            # 🚀 NEW: Post-SMS Calendar Processing
            # Check if we should trigger automatic calendar processing
            await self._post_sms_calendar_processing(
                conversation, body, ai_response, db
            )

            return {
                "success": True,
                "response": ai_response,
                "conversation_id": conversation.id,
                "business_config": business_config
            }

        except Exception as e:
            logger.error(
                f"Error handling SMS for user {self.user_id}: {str(e)}")
            db.rollback()
            return {
                "success": False,
                "error": str(e),
                "response": "I apologize, but I'm having trouble processing your message right now. Please try again or contact us directly."
            }

    async def get_or_create_conversation(
        self,
        customer_phone: str,
        twilio_phone: str,
        db: Session
    ) -> SMSConversation:
        """Get or create conversation for this user"""
        # Look for active conversation
        conversation = db.query(SMSConversation).filter(
            SMSConversation.user_id == self.user_id,
            SMSConversation.phone_number == customer_phone,
            SMSConversation.twilio_phone_number == twilio_phone,
            SMSConversation.status == "active"
        ).first()

        if conversation:
            return conversation

        # Create new conversation
        conversation = SMSConversation(
            user_id=self.user_id,
            phone_number=customer_phone,
            twilio_phone_number=twilio_phone,
            status="active",
            conversation_context=[],
            total_messages=0,
            lead_score=0
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation

    async def _generate_business_response(
        self,
        message: str,
        context: List[Dict],
        business_config: UserBusinessConfig
    ) -> str:
        """Generate AI response using user's business configuration"""
        try:
            # Build business-specific prompt
            prompt = self._build_business_prompt(
                message, context, business_config)

            # Generate response
            response = await self.ai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(
                f"Error generating AI response for user {self.user_id}: {str(e)}")
            return f"Thank you for contacting {business_config.company_name}. I'm having trouble processing your message right now, but someone from our team will get back to you soon!"

    def _build_business_prompt(
        self,
        message: str,
        context: List[Dict],
        business_config: UserBusinessConfig
    ) -> str:
        """Build AI prompt with user's business information"""

        # Format conversation context
        context_str = ""
        if context:
            recent_context = context[-5:]  # Last 5 messages
            context_lines = []
            for msg in recent_context:
                direction = "Customer" if msg.get(
                    "direction") == "inbound" else business_config.bot_name
                context_lines.append(f"{direction}: {msg.get('body', '')}")
            context_str = "\n".join(context_lines)

        # Format services
        services_str = ", ".join(
            business_config.services or ["customer service"])

        # Build comprehensive prompt
        prompt = f"""
You are {business_config.bot_name}, a {business_config.bot_personality} for {business_config.company_name}.

COMPANY INFORMATION:
- Company: {business_config.company_name}
- Description: {business_config.description or "A professional service company"}
- Services: {services_str}
- Website: {business_config.contact_info.get('website') if business_config.contact_info else 'Contact us for more info'}
- Communication Style: {business_config.response_tone.value}

PERSONALITY & TONE:
{business_config.bot_personality}

CONVERSATION CONTEXT:
{context_str}

RESPONSE GUIDELINES:
- Keep responses under 160 characters when possible (SMS-friendly)
- Be {business_config.response_tone.value.lower()} and helpful
- Focus solely on {business_config.company_name} and our services
- If asked about services, mention: {services_str}
- For complex questions, offer to connect with our team
- Stay in character as {business_config.bot_name}
{"- CALENDAR: Help with scheduling appointments when requested" if business_config.calendar_integration_enabled else ""}

CUSTOMER MESSAGE: "{message}"

Respond as {business_config.bot_name} would, representing {business_config.company_name}:
"""

        return prompt

    def _check_usage_limits(self, business_config: UserBusinessConfig, db: Session) -> bool:
        """Check if user is within usage limits"""
        # Count conversations this month
        start_of_month = datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        conversations_this_month = db.query(SMSConversation).filter(
            SMSConversation.user_id == self.user_id,
            SMSConversation.created_at >= start_of_month
        ).count()

        # Check against limit
        return conversations_this_month < business_config.monthly_conversation_limit

    def _store_incoming_message(
        self,
        conversation_id: int,
        from_number: str,
        to_number: str,
        body: str,
        message_sid: str,
        db: Session
    ) -> SMSMessage:
        """Store incoming message"""
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

    def _get_conversation_context(self, conversation_id: int, db: Session) -> List[Dict]:
        """Get recent conversation context"""
        messages = db.query(SMSMessage).filter(
            SMSMessage.conversation_id == conversation_id
        ).order_by(SMSMessage.created_at.desc()).limit(10).all()

        context = []
        for msg in reversed(messages):  # Chronological order
            context.append({
                "direction": msg.direction,
                "body": msg.body,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            })

        return context

    def _log_usage(
        self,
        business_config: UserBusinessConfig,
        conversation: SMSConversation,
        message: SMSMessage,
        db: Session
    ):
        """Log usage for analytics and billing"""
        try:
            usage_log = SMSUsageLog(
                user_id=self.user_id,
                business_config_id=business_config.id,
                conversation_id=conversation.id,
                customer_phone=conversation.phone_number,
                messages_exchanged=1,
                conversation_started_at=datetime.utcnow(),
                estimated_cost=0.02  # Rough estimate for OpenAI + Twilio
            )

            db.add(usage_log)

            # Update business config stats
            business_config.total_conversations += 1
            business_config.conversations_used_this_month += 1

            db.commit()

        except Exception as e:
            logger.error(
                f"Error logging usage for user {self.user_id}: {str(e)}")

    async def send_sms_response(
        self,
        from_number: str,
        to_number: str,
        message: str
    ) -> bool:
        """Send SMS response via Twilio"""
        try:
            message_instance = self.twilio_client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )

            logger.info(
                f"SMS sent successfully for user {self.user_id}: {message_instance.sid}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to send SMS for user {self.user_id}: {str(e)}")
            return False

    def get_usage_stats(self, db: Session) -> Dict:
        """Get usage statistics for this user"""
        try:
            business_config = db.query(UserBusinessConfig).filter(
                UserBusinessConfig.user_id == self.user_id
            ).first()

            if not business_config:
                return {"error": "Business config not found"}

            # Current month stats
            start_of_month = datetime.utcnow().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0)
            conversations_this_month = db.query(SMSConversation).filter(
                SMSConversation.user_id == self.user_id,
                SMSConversation.created_at >= start_of_month
            ).count()

            return {
                "user_id": self.user_id,
                "company_name": business_config.company_name,
                "plan": business_config.sms_plan.value,
                "conversations_this_month": conversations_this_month,
                "monthly_limit": business_config.monthly_conversation_limit,
                "usage_percentage": (conversations_this_month / business_config.monthly_conversation_limit) * 100,
                "total_conversations": business_config.total_conversations,
                "total_leads": business_config.total_leads_generated,
                "webhook_url": f"https://your-domain.com/sms/{self.user_id}/webhook"
            }

        except Exception as e:
            logger.error(
                f"Error getting usage stats for user {self.user_id}: {str(e)}")
            return {"error": str(e)}

    async def _handle_calendar_request(
        self,
        message: str,
        conversation: SMSConversation,
        customer_phone: str,
        db: Session
    ) -> Optional[Dict]:
        """Handle calendar/scheduling requests in SMS"""
        try:
            # Check if message contains scheduling keywords
            scheduling_keywords = [
                "schedule", "book", "appointment", "meeting", "demo",
                "call", "available", "free", "calendar", "time"
            ]

            message_lower = message.lower()
            if not any(keyword in message_lower for keyword in scheduling_keywords):
                return None  # Not a scheduling request

            # Try to parse date/time from message
            parsed_datetime = await self.calendar_service.parse_datetime_from_message(message)

            if parsed_datetime:
                # Attempt to schedule
                customer_name = conversation.customer_name or "SMS Customer"
                customer_email = conversation.customer_email

                booking_result = await self.calendar_service.schedule_demo(
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    requested_datetime=parsed_datetime,
                    customer_name=customer_name,
                    user_id=self.user_id,
                    db_session=db
                )

                if booking_result["success"]:
                    if booking_result.get("calendar_created", False):
                        response = f"✅ Perfect! I've scheduled your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. You'll receive a calendar invite shortly!"
                    else:
                        response = f"✅ Great! I've noted your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. Our team will confirm the details with you soon."

                    # Update conversation with scheduling info
                    conversation.customer_interest = "Demo/Appointment Scheduled"
                    conversation.lead_score = min(
                        conversation.lead_score + 20, 100)
                    conversation.conversion_status = "qualified_lead"

                else:
                    # Booking failed - suggest alternatives
                    suggested_times = booking_result.get("suggested_times", [])
                    if suggested_times:
                        response = f"That time isn't available. How about: {', '.join(suggested_times[:2])}?"
                    else:
                        response = "I'm having trouble with that time. What other times work for you?"

                db.commit()
                return {"response": response, "calendar_handled": True}

            else:
                # Couldn't parse time - ask for clarification
                if any(word in message_lower for word in ["schedule", "book", "appointment"]):
                    return {
                        "response": "I'd be happy to help schedule that! What day and time works best for you? (e.g., 'tomorrow at 2pm' or 'Friday morning')",
                        "calendar_handled": True
                    }

            return None  # Let regular AI handle it

        except Exception as e:
            logger.error(
                f"Error handling calendar request for user {self.user_id}: {str(e)}")
            return None  # Fall back to regular AI response

    async def _post_sms_calendar_processing(
        self,
        conversation: SMSConversation,
        customer_message: str,
        ai_response: str,
        db: Session
    ):
        """
        Post-SMS processing to detect and create calendar events using conversation analysis
        """
        try:
            # Check if user has calendar integration enabled
            business_config = db.query(UserBusinessConfig).filter(
                UserBusinessConfig.user_id == self.user_id
            ).first()

            if not business_config or not business_config.calendar_integration_enabled:
                return

            # Check if user has calendar credentials
            from app.models import GoogleCalendarCredentials
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == self.user_id
            ).first()

            if not credentials:
                logger.info(
                    f"User {self.user_id} has no calendar credentials - skipping SMS calendar processing")
                return

            # Build conversation text for analysis
            full_conversation = f"Customer: {customer_message}\nAssistant: {ai_response}"

            # Check if AI committed to scheduling something
            scheduling_commitment_phrases = [
                "i've scheduled",
                "i'll add that to your calendar",
                "i'll schedule that",
                "scheduled your appointment",
                "added to your calendar",
                "appointment is booked",
                "calendar invite"
            ]

            ai_response_lower = ai_response.lower()
            has_scheduling_commitment = any(
                phrase in ai_response_lower for phrase in scheduling_commitment_phrases
            )

            if has_scheduling_commitment:
                logger.info(
                    f"🗓️ SMS scheduling commitment detected for user {self.user_id} - processing calendar")

                # Use the post-call processor to create calendar events
                from app.services.post_call_processor import PostCallProcessor

                processor = PostCallProcessor()
                calendar_result = await processor.process_call_end(
                    call_sid=f"sms_{conversation.id}_{datetime.utcnow().timestamp()}",
                    user_id=self.user_id,
                    scenario_id="sms_bot",
                    conversation_content=full_conversation
                )

                if calendar_result and calendar_result.get("calendar_events_created"):
                    logger.info(
                        f"✅ SMS Calendar events created: {calendar_result['calendar_events_created']}")

                    # Mark conversation as having calendar processing
                    conversation.conversion_status = "demo_scheduled"
                    conversation.lead_score = min(
                        conversation.lead_score + 25, 100)
                    db.commit()
                else:
                    logger.info(
                        f"ℹ️ No calendar events created from SMS for user {self.user_id}")

        except Exception as e:
            logger.error(
                f"Error in post-SMS calendar processing for user {self.user_id}: {str(e)}")
