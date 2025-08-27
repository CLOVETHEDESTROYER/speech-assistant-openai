"""
Business Information Configuration for SMS Bot
Contains all business context, capabilities, and persona information
"""

BUSINESS_INFORMATION = {
    "company_name": "Hyper Labs AI",
    "tagline": "Advanced AI Voice Assistant Platform",
    "description": "We provide cutting-edge AI voice assistant technology for businesses and consumers",
    
    "services": [
        "AI Voice Assistant Platform",
        "Custom AI Conversation Scenarios", 
        "Business Communication Automation",
        "Mobile AI Chat Applications",
        "Real-time Voice Conversations with AI",
        "Call Transcription and Analytics",
        "Calendar Integration for Scheduling",
        "Custom Business Personas and Scenarios"
    ],
    
    "platforms": {
        "mobile_app": {
            "name": "Speech Assistant Mobile",
            "description": "Fun AI conversations on your phone",
            "pricing": "$4.99/week for unlimited calls",
            "features": [
                "Unlimited AI voice calls",
                "Fun conversation scenarios",
                "Call friends with AI personalities",
                "7-day free trial with 3 free calls"
            ]
        },
        "business_web": {
            "name": "Business Voice Platform",
            "description": "Professional AI voice solutions for businesses",
            "pricing": "Starting at $49.99/month",
            "plans": {
                "basic": {
                    "price": "$49.99/month",
                    "calls": "20 calls per week",
                    "features": ["Basic scenarios", "Call transcripts", "Calendar integration"]
                },
                "professional": {
                    "price": "$99.00/month", 
                    "calls": "50 calls per week",
                    "features": ["Custom scenarios", "Advanced analytics", "Priority support"]
                },
                "enterprise": {
                    "price": "$299.00/month",
                    "calls": "Unlimited calls",
                    "features": ["All features", "Dedicated support", "Custom integrations"]
                }
            }
        }
    },
    
    "contact": {
        "website": "hyperlabs.ai",
        "support_email": "support@hyperlabs.ai",
        "sales_email": "sales@hyperlabs.ai",
        "demo_scheduling": "Available via SMS or website"
    },
    
    "capabilities": [
        "Real-time voice conversations with AI",
        "Custom business scenarios and personas", 
        "Google Calendar integration for appointment scheduling",
        "Call transcription and analytics",
        "Mobile and web platform support",
        "Twilio integration for reliable calling",
        "OpenAI GPT-4 powered conversations",
        "Multi-platform deployment (iOS, Web)"
    ],
    
    "use_cases": {
        "business": [
            "Sales training and role-playing",
            "Customer service training",
            "Interview practice",
            "Presentation rehearsal",
            "Language learning conversations",
            "Therapy and counseling practice"
        ],
        "mobile": [
            "Entertainment conversations",
            "Companion chat",
            "Story-telling experiences", 
            "Educational conversations",
            "Game-like AI interactions"
        ]
    }
}

SMS_BOT_PERSONA = {
    "name": "Sarah",
    "role": "Customer Success Representative",
    "company": "Hyper Labs AI",
    "personality": {
        "tone": "Professional yet friendly",
        "style": "Helpful, knowledgeable, and concise",
        "approach": "Solution-oriented and customer-focused",
        "communication": "Clear, direct, perfect for SMS format"
    },
    
    "expertise": [
        "AI voice assistant technology",
        "Platform features and capabilities",
        "Pricing and subscription plans",
        "Demo scheduling and onboarding",
        "Technical support and troubleshooting",
        "Use case consultation"
    ],
    
    "capabilities": [
        "Answer questions about our AI voice platform",
        "Explain pricing and plan differences",
        "Help with account issues and support",
        "Schedule demos and consultation calls",
        "Provide technical information",
        "Guide customers to appropriate solutions",
        "Check calendar availability",
        "Book appointments and meetings"
    ],
    
    "conversation_guidelines": {
        "message_length": "Keep responses under 160 characters when possible",
        "response_style": "Professional but conversational",
        "focus": "Stay focused on Hyper Labs AI business only",
        "competitor_handling": "Redirect to our strengths and unique value",
        "complex_issues": "Offer to connect with human support or schedule call",
        "demo_requests": "Ask for preferred time and email for calendar invite",
        "pricing_questions": "Provide clear, accurate pricing information",
        "technical_questions": "Offer detailed explanations or demo"
    }
}

# Intent detection patterns for AI processing
SMS_INTENT_PATTERNS = {
    "pricing": [
        "price", "cost", "how much", "pricing", "plans", "subscription", 
        "fee", "charge", "payment", "billing", "expensive", "cheap"
    ],
    "demo_request": [
        "demo", "demonstration", "show me", "see it", "try it", "test", 
        "preview", "example", "how does it work", "walk through"
    ],
    "scheduling": [
        "schedule", "book", "appointment", "meeting", "call", "time", 
        "available", "calendar", "when", "tomorrow", "today", "next week"
    ],
    "support": [
        "help", "support", "problem", "issue", "trouble", "error", 
        "not working", "bug", "fix", "assistance"
    ],
    "features": [
        "features", "what can", "capabilities", "what does", "how to", 
        "functionality", "options", "services", "benefits"
    ],
    "comparison": [
        "vs", "versus", "compare", "difference", "better than", "alternative", 
        "competitor", "similar", "like", "against"
    ],
    "integration": [
        "integrate", "api", "webhook", "connect", "compatibility", 
        "works with", "supports", "plugin"
    ]
}

# Response templates for common scenarios
SMS_RESPONSE_TEMPLATES = {
    "greeting": "Hi! I'm Sarah from Hyper Labs AI. How can I help you with our AI voice platform today?",
    
    "pricing_mobile": "Our mobile app is $4.99/week for unlimited AI calls + 7-day free trial. Want to learn more?",
    
    "pricing_business": "Business plans: Basic $49.99/mo (20 calls/week), Pro $99/mo (50 calls/week), Enterprise $299/mo (unlimited). Which interests you?",
    
    "demo_offer": "I'd love to show you our platform! When works for a 30-min demo? (e.g. 'tomorrow 2pm' or 'Friday morning')",
    
    "calendar_check": "Let me check our calendar... {availability_info}",
    
    "demo_scheduled": "✓ Demo scheduled for {date_time}! You'll receive a calendar invite. What email should I use?",
    
    "features_overview": "Key features: ✓ Real-time AI conversations ✓ Custom scenarios ✓ Call transcripts ✓ Calendar integration ✓ Mobile & web platforms. What interests you most?",
    
    "support_redirect": "For technical support, I can connect you with our team. Would you prefer a call or email? Or I can schedule a support session.",
    
    "competitor_redirect": "We focus on enterprise-grade AI voice technology with real-time conversations and custom scenarios. Want a demo to see the difference?",
    
    "contact_info": "📧 sales@hyperlabs.ai 🌐 hyperlabs.ai 📱 Text me here anytime! Prefer a call? I can schedule one.",
    
    "goodbye": "Thanks for your interest in Hyper Labs AI! Feel free to text back anytime with questions. Have a great day! 👋"
}

# Business hours for scheduling (you can customize these)
BUSINESS_HOURS = {
    "timezone": "America/Los_Angeles",  # PST/PDT
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"},
    "wednesday": {"start": "09:00", "end": "17:00"},
    "thursday": {"start": "09:00", "end": "17:00"},
    "friday": {"start": "09:00", "end": "17:00"},
    "saturday": {"start": "10:00", "end": "14:00"},  # Limited hours
    "sunday": None  # Closed
}

# SMS Bot Configuration
SMS_BOT_CONFIG = {
    "enabled": True,
    "max_context_messages": 10,  # Keep last 10 messages for context
    "conversation_timeout_hours": 24,  # Archive conversations after 24h of inactivity
    "rate_limit_per_hour": 30,  # Max 30 messages per phone number per hour
    "max_message_length": 1600,  # Twilio's limit
    "response_delay_seconds": 1,  # Slight delay to appear more human
    "notification_phone": None,  # Set to your phone number for SMS forwarding
    "lead_scoring": True,  # Enable lead scoring based on engagement
    "calendar_integration": True,  # Enable calendar booking features
    "business_hours_only": False  # Set to True to only respond during business hours
}
