"""
SMS AI Service for Business Intelligence
Handles AI-powered responses for SMS customer inquiries
"""

import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from openai import AsyncOpenAI
import json

from app.business_config import (
    BUSINESS_INFORMATION,
    SMS_BOT_PERSONA,
    SMS_INTENT_PATTERNS,
    SMS_RESPONSE_TEMPLATES,
    SMS_BOT_CONFIG
)

logger = logging.getLogger(__name__)


class SMSAIService:
    """AI-powered SMS customer service bot"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.business_info = BUSINESS_INFORMATION
        self.persona = SMS_BOT_PERSONA
        self.response_templates = SMS_RESPONSE_TEMPLATES

    async def generate_response(
        self,
        message: str,
        conversation_context: List[Dict],
        customer_info: Optional[Dict] = None
    ) -> Dict:
        """
        Generate AI response to customer SMS with business intelligence

        Args:
            message: The customer's message
            conversation_context: Previous messages in conversation
            customer_info: Optional customer data (name, email, interests)

        Returns:
            Dict with response, intent, sentiment, and extracted entities
        """
        try:
            # Detect intent and sentiment
            intent = self.detect_intent(message)
            sentiment = await self.analyze_sentiment(message)
            entities = self.extract_entities(message)

            # Build context-aware prompt
            prompt = self._build_ai_prompt(
                message,
                conversation_context,
                intent,
                customer_info
            )

            # Generate AI response
            ai_response = await self._call_openai(prompt)

            # Post-process response (length check, template enhancement)
            final_response = self._post_process_response(
                ai_response, intent, entities)

            return {
                "response": final_response,
                "intent": intent,
                "sentiment_score": sentiment,
                "entities": entities,
                "context_used": len(conversation_context),
                "processing_time": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating SMS response: {str(e)}")
            return {
                "response": "I apologize, but I'm having trouble processing that right now. Can you try again or call our support line?",
                "intent": "error",
                "sentiment_score": 0.0,
                "entities": {},
                "error": str(e)
            }

    def detect_intent(self, message: str) -> str:
        """Detect customer intent from message using keyword patterns"""
        message_lower = message.lower()

        # Check each intent pattern
        for intent, keywords in SMS_INTENT_PATTERNS.items():
            if any(keyword in message_lower for keyword in keywords):
                return intent

        # Default intent
        return "general_inquiry"

    async def analyze_sentiment(self, message: str) -> float:
        """Analyze message sentiment (-1.0 to 1.0)"""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "system",
                    "content": "Analyze the sentiment of this message. Respond with only a number between -1.0 (very negative) and 1.0 (very positive)."
                }, {
                    "role": "user",
                    "content": message
                }],
                max_tokens=10,
                temperature=0.1
            )

            sentiment_text = response.choices[0].message.content.strip()
            # Clean up the response and ensure it's a valid float
            sentiment_text = sentiment_text.replace(
                '"', '').replace("'", '').strip()
            try:
                sentiment_value = float(sentiment_text)
                # Ensure it's within valid range
                return max(-1.0, min(1.0, sentiment_value))
            except (ValueError, TypeError):
                logger.warning(
                    f"Could not parse sentiment value: {sentiment_text}")
                return 0.0

        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return 0.0  # Neutral default

    def extract_entities(self, message: str) -> Dict:
        """Extract useful entities from message (emails, phone numbers, dates, names)"""
        entities = {}

        # Email extraction
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, message)
        if emails:
            entities["emails"] = emails

        # Phone number extraction (basic)
        phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        phones = re.findall(phone_pattern, message)
        if phones:
            entities["phone_numbers"] = phones

        # Time/date mentions (simple patterns)
        time_patterns = [
            r'\b(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b\d{1,2}:\d{2}\s?(am|pm|AM|PM)?\b',
            r'\b(morning|afternoon|evening|night)\b',
            r'\b(next week|this week|next month)\b'
        ]

        time_mentions = []
        for pattern in time_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            time_mentions.extend(matches)

        if time_mentions:
            entities["time_mentions"] = time_mentions

        # Name extraction (simple - capitalized words that aren't common words)
        name_candidates = re.findall(
            r'\bmy name is ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b', message, re.IGNORECASE)
        if name_candidates:
            entities["names"] = name_candidates

        return entities

    def _build_ai_prompt(
        self,
        message: str,
        context: List[Dict],
        intent: str,
        customer_info: Optional[Dict] = None
    ) -> str:
        """Build comprehensive AI prompt with business context"""

        # Format conversation context
        context_str = ""
        if context:
            recent_context = context[-5:]  # Last 5 messages
            context_lines = []
            for msg in recent_context:
                direction = "Customer" if msg.get(
                    "direction") == "inbound" else "Sarah"
                context_lines.append(f"{direction}: {msg.get('body', '')}")
            context_str = "\n".join(context_lines)

        # Customer info string
        customer_str = ""
        if customer_info:
            if customer_info.get("name"):
                customer_str += f"Customer name: {customer_info['name']}\n"
            if customer_info.get("email"):
                customer_str += f"Customer email: {customer_info['email']}\n"
            if customer_info.get("interest"):
                customer_str += f"Previous interest: {customer_info['interest']}\n"

        # Intent-specific instructions
        intent_instructions = self._get_intent_instructions(intent)

        prompt = f"""
You are {self.persona['name']}, a {self.persona['role']} for {self.business_info['company_name']}.

COMPANY INFORMATION:
- Company: {self.business_info['company_name']} - {self.business_info['tagline']}
- Mobile App: {self.business_info['platforms']['mobile_app']['pricing']} - {self.business_info['platforms']['mobile_app']['description']}
- Business Platform: {self.business_info['platforms']['business_web']['pricing']} - Professional AI voice solutions
- Key Services: {', '.join(self.business_info['services'][:4])}
- Contact: {self.business_info['contact']['website']} | {self.business_info['contact']['support_email']}

CONVERSATION CONTEXT:
{context_str}

CUSTOMER INFORMATION:
{customer_str}

DETECTED INTENT: {intent}
INTENT-SPECIFIC GUIDANCE:
{intent_instructions}

RESPONSE GUIDELINES:
- Keep responses under 160 characters when possible (SMS-friendly)
- Be {self.persona['personality']['tone']} and {self.persona['personality']['style']}
- Focus solely on Hyper Labs AI business and services
- If asked about competitors, redirect to our unique strengths
- For complex questions, offer to schedule a call or demo
- For scheduling requests, ask for preferred time and offer calendar booking
- Always be helpful and solution-oriented

CURRENT CUSTOMER MESSAGE: "{message}"

Respond as Sarah would, keeping it concise and professional:
"""

        return prompt

    def _get_intent_instructions(self, intent: str) -> str:
        """Get specific instructions based on detected intent"""
        instructions = {
            "pricing": "Provide clear pricing for both mobile ($4.99/week) and business (starting $49.99/month) platforms. Ask which interests them more.",

            "demo_request": "Offer to schedule a 30-minute demo. Ask for their preferred time (e.g., 'tomorrow 2pm' or 'Friday morning').",

            "scheduling": "Help them book a time. Ask for specific preferences and mention you can check calendar availability.",

            "support": "Acknowledge their issue and offer to connect with support team or schedule a support call.",

            "features": "Highlight key features: real-time AI conversations, custom scenarios, call transcripts, calendar integration. Ask what interests them most.",

            "comparison": "Focus on our unique strengths: enterprise-grade AI voice technology, real-time conversations, and custom scenarios. Offer a demo.",

            "integration": "Explain our API capabilities and integrations. Offer to connect with technical team for detailed discussion.",

            "general_inquiry": "Be helpful and guide them toward their specific need. Ask clarifying questions to better assist them."
        }

        return instructions.get(intent, instructions["general_inquiry"])

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API with optimized settings for SMS responses"""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",  # Latest GPT-4 model
                messages=[{"role": "system", "content": prompt}],
                max_tokens=200,  # Limit for SMS-appropriate responses
                temperature=0.7,  # Balanced creativity and consistency
                presence_penalty=0.1,  # Slight encouragement for varied responses
                frequency_penalty=0.1   # Reduce repetition
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return "I'm having trouble processing that right now. Please try again or contact support@hyperlabs.ai"

    def _post_process_response(self, response: str, intent: str, entities: Dict) -> str:
        """Post-process AI response for SMS optimization"""
        # Remove any quotes that might be added by AI
        response = response.strip('"').strip("'")

        # Ensure response isn't too long (SMS limit considerations)
        if len(response) > 1500:  # Leave room for Twilio overhead
            # Try to split at a sentence boundary
            sentences = response.split('. ')
            if len(sentences) > 1:
                response = '. '.join(sentences[:-1]) + '.'
            else:
                response = response[:1500] + "..."

        # Add helpful follow-ups based on intent
        if intent == "pricing" and len(response) < 100:
            response += " Would you like to schedule a demo?"

        elif intent == "demo_request" and "calendar" not in response.lower():
            response += " I can check our calendar for you!"

        # Ensure professional closing for important intents
        if intent in ["support", "demo_request"] and not any(phrase in response.lower() for phrase in ["let me", "i can", "would you like"]):
            response += " How can I help you with this?"

        return response

    def calculate_lead_score(
        self,
        conversation_context: List[Dict],
        customer_info: Optional[Dict] = None
    ) -> int:
        """Calculate lead score (0-100) based on conversation engagement"""
        score = 0

        # Base score for any conversation
        score += 10

        # Message volume (engagement)
        message_count = len(conversation_context)
        if message_count > 5:
            score += 20
        elif message_count > 2:
            score += 10

        # Intent diversity (shows genuine interest)
        intents = set()
        for msg in conversation_context:
            if msg.get("intent_detected"):
                intents.add(msg["intent_detected"])

        intent_bonus = min(len(intents) * 15, 30)  # Max 30 points
        score += intent_bonus

        # High-value intents
        high_value_intents = ["demo_request",
                              "pricing", "scheduling", "features"]
        for msg in conversation_context:
            if msg.get("intent_detected") in high_value_intents:
                score += 10
                break  # Only count once

        # Customer information provided
        if customer_info:
            if customer_info.get("email"):
                score += 20
            if customer_info.get("name"):
                score += 10
            if customer_info.get("phone_number"):
                score += 10

        # Positive sentiment
        positive_messages = [msg for msg in conversation_context
                             if (msg.get("sentiment_score") or 0) > 0.3]
        if len(positive_messages) > len(conversation_context) / 2:
            score += 15

        # Recent activity (engaged recently)
        if conversation_context:
            last_message = conversation_context[-1]
            if last_message.get("created_at"):
                try:
                    last_time = datetime.fromisoformat(
                        last_message["created_at"].replace('Z', '+00:00'))
                    if datetime.utcnow() - last_time.replace(tzinfo=None) < timedelta(hours=2):
                        score += 10
                except:
                    pass

        return min(score, 100)  # Cap at 100
