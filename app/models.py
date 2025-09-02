# models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float, JSON, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
from datetime import datetime, date
import enum

# Add enums for app types and subscription tiers


class AppType(enum.Enum):
    MOBILE_CONSUMER = "mobile_consumer"
    WEB_BUSINESS = "web_business"


class SubscriptionTier(enum.Enum):
    # Mobile Consumer Tiers
    MOBILE_FREE_TRIAL = "mobile_free_trial"
    MOBILE_BASIC = "mobile_basic"        # $4.99/week, 5 calls/week
    MOBILE_PREMIUM = "mobile_premium"    # $25/month, 30 calls/month

    # Business Tiers
    BUSINESS_FREE_TRIAL = "business_free_trial"
    BUSINESS_BASIC = "business_basic"        # $49.99/month, 20 calls/week
    BUSINESS_PROFESSIONAL = "business_professional"  # $99/month
    BUSINESS_ENTERPRISE = "business_enterprise"      # $299/month


class SubscriptionStatus(enum.Enum):
    """Subscription status for App Store compliance"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    BILLING_RETRY = "billing_retry"
    EXPIRED = "expired"
    GRACE_PERIOD = "grace_period"
    PENDING = "pending"


class AnonymousOnboardingSession(Base):
    __tablename__ = "anonymous_onboarding_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)

    # Mobile 4-step onboarding data collected before registration
    user_name = Column(String, nullable=True)  # Step 2: Profile
    phone_number = Column(String, nullable=True)  # Step 2: Profile
    preferred_voice = Column(String, nullable=True)  # Step 2: Profile
    notifications_enabled = Column(Boolean, default=True)  # Step 2: Profile

    # Step tracking for mobile flow
    welcome_completed = Column(Boolean, default=False)  # Step 1
    profile_completed = Column(Boolean, default=False)  # Step 2
    tutorial_completed = Column(Boolean, default=False)  # Step 3
    # welcome, profile, tutorial, ready_for_registration
    current_step = Column(String, default="welcome")

    # Legacy field for backward compatibility
    selected_scenario_id = Column(String, nullable=True)

    # Session metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    # Sessions expire after 24 hours
    expires_at = Column(DateTime, nullable=False)
    is_completed = Column(Boolean, default=False)

    # When user registers, this gets linked to their account
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationship (optional, only after registration)
    user = relationship("User", back_populates="anonymous_onboarding_session")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    # Made nullable for Apple Sign In users
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # Apple Sign In fields
    apple_user_id = Column(String, unique=True, index=True, nullable=True)
    # Email from Apple (may be private)
    apple_email = Column(String, nullable=True)
    # Full name from Apple (may be private)
    apple_full_name = Column(String, nullable=True)
    # "email", "apple", "google"
    auth_provider = Column(String, default="email")
    email_verified = Column(Boolean, default=False)

    # User profile fields
    full_name = Column(String, nullable=True)  # General name field
    # Voice preference for AI calls
    preferred_voice = Column(String, nullable=True)
    notifications_enabled = Column(
        Boolean, default=True)  # Notification preferences

    call_schedules = relationship("CallSchedule", back_populates="user")
    tokens = relationship("Token", back_populates="user")
    custom_scenarios = relationship("CustomScenario", back_populates="user")
    google_credentials = relationship(
        "GoogleCalendarCredentials", back_populates="user")
    stored_transcripts = relationship(
        "StoredTwilioTranscript", back_populates="user")
    phone_numbers = relationship("UserPhoneNumber", back_populates="user")
    onboarding_status = relationship(
        "UserOnboardingStatus", back_populates="user", uselist=False)
    usage_limits = relationship(
        "UsageLimits", back_populates="user", uselist=False)
    provider_credentials = relationship(
        "ProviderCredentials", back_populates="user", uselist=False)
    anonymous_onboarding_session = relationship(
        "AnonymousOnboardingSession", back_populates="user", uselist=False)
    business_config = relationship(
        "UserBusinessConfig", back_populates="user", uselist=False)
    conversation_transcripts = relationship(
        "ConversationTranscript", back_populates="user")


class CallSchedule(Base):
    __tablename__ = "call_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    scenario = Column(String, nullable=False)

    # Relationships
    user = relationship("User", back_populates="call_schedules")


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    access_token = Column(String, unique=True, nullable=False)
    token_type = Column(String, default="bearer")
    refresh_token = Column(String, nullable=True)
    is_valid = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="tokens")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    scenario = Column(String)
    phone_number = Column(String)
    direction = Column(String)
    status = Column(String)
    call_sid = Column(String)
    recording_sid = Column(String)
    transcript = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    transcript_sid = Column(String, nullable=True)
    duration_limit = Column(Integer, nullable=True)  # seconds


class TranscriptRecord(Base):
    __tablename__ = "transcript_records"

    id = Column(Integer, primary_key=True)
    transcript_sid = Column(String, nullable=False, index=True, unique=True)
    status = Column(String, nullable=False)
    full_text = Column(Text)
    date_created = Column(DateTime)
    date_updated = Column(DateTime)
    duration = Column(Integer)
    language_code = Column(String)
    sentences_json = Column(Text)  # JSON string of sentence data
    created_at = Column(DateTime, default=datetime.now())
    user_id = Column(Integer, ForeignKey('users.id'))

    # Enhanced fields for better transcript management
    # When the actual call occurred
    call_date = Column(DateTime, nullable=True)
    # Structured participant data
    participant_info = Column(JSON, nullable=True)
    # Ordered conversation with speaker identification
    conversation_flow = Column(JSON, nullable=True)
    # Link to original recording if available
    media_url = Column(String, nullable=True)
    # "Recording", "ExternalRecording", "Call", etc.
    source_type = Column(String, nullable=True)
    call_direction = Column(String, nullable=True)  # "inbound", "outbound"
    # The scenario used for the call
    scenario_name = Column(String, nullable=True)
    # Summary statistics and metadata
    summary_data = Column(JSON, nullable=True)


class CustomScenario(Base):
    __tablename__ = "custom_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    persona = Column(Text, nullable=False)
    prompt = Column(Text, nullable=False)
    voice_type = Column(String, nullable=False)
    temperature = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="custom_scenarios")


class GoogleCalendarCredentials(Base):
    __tablename__ = "google_calendar_credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String)
    refresh_token = Column(String)
    token_expiry = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    user = relationship("User", back_populates="google_credentials")


class ConversationTranscript(Base):
    __tablename__ = "conversation_transcripts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    call_sid = Column(String, unique=True, index=True)
    scenario_id = Column(String)
    transcript = Column(Text)
    calendar_processed = Column(Boolean, default=False)
    calendar_event_created = Column(Boolean, default=False)
    calendar_event_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversation_transcripts")


class StoredTwilioTranscript(Base):
    __tablename__ = "stored_twilio_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False)  # User isolation

    # Store exact Twilio response format
    transcript_sid = Column(String, unique=True,
                            nullable=False, index=True)  # Twilio's sid
    status = Column(String, nullable=False)  # "completed", "processing", etc.
    # Keep as ISO string like Twilio
    date_created = Column(String, nullable=False)
    # Keep as ISO string like Twilio
    date_updated = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # seconds
    language_code = Column(String, nullable=False, default="en-US")
    # CRITICAL: Store full Twilio sentences array
    sentences = Column(JSON, nullable=False)

    # Optional call metadata (can be enhanced later)
    call_sid = Column(String, nullable=True)
    scenario_name = Column(String, default="Voice Call")
    call_direction = Column(String, default="outbound")
    phone_number = Column(String, nullable=True)

    # Storage metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="stored_transcripts")


class UserPhoneNumber(Base):
    __tablename__ = "user_phone_numbers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone_number = Column(String, unique=True, nullable=False, index=True)
    twilio_sid = Column(String, unique=True, nullable=False)
    friendly_name = Column(String, nullable=True)
    date_provisioned = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Twilio capabilities
    voice_capable = Column(Boolean, default=True)
    sms_capable = Column(Boolean, default=True)

    # Relationship
    user = relationship("User", back_populates="phone_numbers")


class UserOnboardingStatus(Base):
    __tablename__ = "user_onboarding_status"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, unique=True)

    # Onboarding steps completion tracking
    phone_number_setup = Column(Boolean, default=False)
    calendar_connected = Column(Boolean, default=False)
    first_scenario_created = Column(Boolean, default=False)
    welcome_call_completed = Column(Boolean, default=False)

    # Metadata
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    # phone_setup, calendar, scenarios, complete
    current_step = Column(String, default="phone_setup")

    # Relationship
    user = relationship("User", back_populates="onboarding_status")


class UsageLimits(Base):
    __tablename__ = "usage_limits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, unique=True)
    app_type = Column(Enum(AppType), nullable=False)

    # Call tracking
    calls_made_today = Column(Integer, default=0)
    calls_made_this_week = Column(Integer, default=0)
    calls_made_this_month = Column(Integer, default=0)
    calls_made_total = Column(Integer, default=0)

    # Date tracking for resets
    last_call_date = Column(Date, nullable=True)
    week_start_date = Column(Date, nullable=True)  # For weekly limits
    month_start_date = Column(Date, nullable=True)  # For monthly limits

    # Trial and free calls
    # 3 for mobile, 4 for business
    trial_calls_remaining = Column(Integer, default=0)
    trial_calls_used = Column(Integer, default=0)
    trial_start_date = Column(DateTime, nullable=True)
    trial_end_date = Column(DateTime, nullable=True)
    is_trial_active = Column(Boolean, default=True)

    # Subscription status
    subscription_tier = Column(Enum(SubscriptionTier), default=None)
    is_subscribed = Column(Boolean, default=False)
    subscription_start_date = Column(DateTime, nullable=True)
    subscription_end_date = Column(DateTime, nullable=True)
    subscription_status = Column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING)

    # Weekly/Monthly limits based on subscription
    # For business basic: 20
    weekly_call_limit = Column(Integer, nullable=True)
    monthly_call_limit = Column(Integer, nullable=True)

    # Payment tracking
    billing_cycle = Column(String, nullable=True)  # "weekly", "monthly"
    last_payment_date = Column(DateTime, nullable=True)
    next_payment_date = Column(DateTime, nullable=True)

    # App Store integration
    app_store_transaction_id = Column(String, nullable=True)
    app_store_product_id = Column(String, nullable=True)

    # Enhanced mobile usage tracking
    total_call_duration_this_week = Column(Integer, default=0)  # seconds
    total_call_duration_this_month = Column(Integer, default=0)  # seconds
    addon_calls_remaining = Column(Integer, default=0)
    addon_calls_expiry = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="usage_limits")


class ProviderCredentials(Base):
    __tablename__ = "provider_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, unique=True)

    # Encrypted fields
    openai_api_key = Column(String, nullable=True)
    twilio_account_sid = Column(String, nullable=True)
    twilio_auth_token = Column(String, nullable=True)
    twilio_phone_number = Column(String, nullable=True)
    twilio_vi_sid = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="provider_credentials")


class SMSConversation(Base):
    __tablename__ = "sms_conversations"

    id = Column(Integer, primary_key=True, index=True)
    # User who owns this conversation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone_number = Column(String, nullable=False,
                          index=True)  # Customer's phone
    twilio_phone_number = Column(String, nullable=False)  # Our Twilio number
    # List of recent messages for AI context
    conversation_context = Column(JSON, default=list)

    # Conversation metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="active")  # active, closed, archived

    # Customer information (optional, gathered during conversation)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    # mobile, business, demo, etc.
    customer_interest = Column(String, nullable=True)

    # Business intelligence
    total_messages = Column(Integer, default=0)
    lead_score = Column(Integer, default=0)  # 0-100 based on engagement
    # prospect, demo_scheduled, converted
    conversion_status = Column(String, default="prospect")

    # Relationships
    messages = relationship(
        "SMSMessage", back_populates="conversation", cascade="all, delete-orphan")
    user = relationship("User")


class SMSMessage(Base):
    __tablename__ = "sms_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey(
        "sms_conversations.id"), nullable=False)
    # Twilio's unique message ID
    message_sid = Column(String, unique=True, nullable=False)

    # Message details
    direction = Column(String, nullable=False)  # 'inbound' or 'outbound'
    from_number = Column(String, nullable=False)
    to_number = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    # AI processing
    # The AI-generated response (for inbound messages)
    ai_response = Column(Text, nullable=True)
    # pricing, demo, support, etc.
    intent_detected = Column(String, nullable=True)
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    # Names, dates, email addresses, etc.
    entities_extracted = Column(JSON, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    # When AI response was generated
    processed_at = Column(DateTime, nullable=True)
    # When response was sent via Twilio
    sent_at = Column(DateTime, nullable=True)

    # Status tracking
    # received, processing, responded, failed
    status = Column(String, default="received")
    error_message = Column(String, nullable=True)  # If processing failed
    # If message was handled by calendar service
    calendar_processed = Column(Boolean, default=False)

    # Relationships
    conversation = relationship("SMSConversation", back_populates="messages")


__all__ = ["User", "Token", "Base", "CallSchedule",
           "Conversation", "TranscriptRecord", "CustomScenario", "GoogleCalendarCredentials",
           "StoredTwilioTranscript", "UserPhoneNumber", "UserOnboardingStatus",
           "UsageLimits", "ProviderCredentials", "SMSConversation", "SMSMessage",
           "UserBusinessConfig", "SMSUsageLog", "SMSPlan", "ResponseTone",
           "AppType", "SubscriptionTier", "SubscriptionStatus", "AnonymousOnboardingSession",
           "ConversationTranscript"]

# Add new enums for SMS bot features


class SMSPlan(enum.Enum):
    """SMS Bot subscription plans"""
    FREE_TRIAL = "free_trial"           # 10 conversations/month
    BASIC = "basic"                     # 100 conversations/month - $19.99
    PROFESSIONAL = "professional"      # 500 conversations/month - $49.99
    ENTERPRISE = "enterprise"          # Unlimited conversations - $99.99


class ResponseTone(enum.Enum):
    """AI response tone options"""
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    CASUAL = "casual"
    FORMAL = "formal"
    ENTHUSIASTIC = "enthusiastic"


class UserBusinessConfig(Base):
    __tablename__ = "user_business_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, unique=True)

    # Business Information
    company_name = Column(String, nullable=False)
    tagline = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    # e.g., "Technology", "Healthcare"
    industry = Column(String, nullable=True)
    website = Column(String, nullable=True)

    # Services and Pricing (JSON arrays/objects)
    # List of services: ["Web Development", "Consulting"]
    services = Column(JSON, nullable=True)
    pricing_info = Column(JSON, nullable=True)  # Pricing structure with plans
    # {"email": "...", "phone": "...", "address": "..."}
    contact_info = Column(JSON, nullable=True)

    # Bot Persona Configuration
    bot_name = Column(String, default="Assistant")
    # Detailed personality description
    bot_personality = Column(Text, nullable=True)
    response_tone = Column(
        Enum(ResponseTone), default=ResponseTone.PROFESSIONAL)
    custom_greeting = Column(Text, nullable=True)  # Custom welcome message

    # SMS Bot Settings
    sms_enabled = Column(Boolean, default=True)
    auto_responses_enabled = Column(Boolean, default=True)
    calendar_integration_enabled = Column(Boolean, default=True)
    lead_scoring_enabled = Column(Boolean, default=True)

    # Business Hours (JSON)
    # {"monday": {"start": "09:00", "end": "17:00"}, ...}
    business_hours = Column(JSON, nullable=True)
    timezone = Column(String, default="America/Los_Angeles")

    # Custom Response Templates (JSON)
    # {"pricing": "Custom pricing message", ...}
    custom_responses = Column(JSON, nullable=True)

    # Usage and Plan Information
    sms_plan = Column(Enum(SMSPlan), default=SMSPlan.FREE_TRIAL)
    monthly_conversation_limit = Column(Integer, default=10)
    conversations_used_this_month = Column(Integer, default=0)
    plan_start_date = Column(DateTime, nullable=True)
    plan_end_date = Column(DateTime, nullable=True)

    # Analytics and Performance
    total_conversations = Column(Integer, default=0)
    total_leads_generated = Column(Integer, default=0)
    total_demos_booked = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)  # seconds
    customer_satisfaction = Column(Float, default=0.0)  # 0-5 rating
    conversion_rate = Column(Float, default=0.0)  # percentage

    # Employee-Based Booking Configuration
    employee_count = Column(Integer, default=1)
    max_concurrent_bookings = Column(Integer, default=1)
    booking_policy = Column(String, default="strict")  # strict, flexible, unlimited
    allow_overbooking = Column(Boolean, default=False)

    # Feature Flags
    advanced_analytics = Column(Boolean, default=False)
    white_label_enabled = Column(Boolean, default=False)
    api_access_enabled = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="business_config")
    sms_usage_logs = relationship(
        "SMSUsageLog", back_populates="business_config")


class SMSUsageLog(Base):
    __tablename__ = "sms_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_config_id = Column(Integer, ForeignKey(
        "user_business_configs.id"), nullable=False)

    # Usage tracking
    conversation_id = Column(Integer, ForeignKey(
        "sms_conversations.id"), nullable=True)
    customer_phone = Column(String, nullable=False)
    messages_exchanged = Column(Integer, default=0)
    # seconds from first to last message
    conversation_duration = Column(Integer, nullable=True)

    # Business intelligence
    intent_detected = Column(String, nullable=True)
    lead_quality_score = Column(Integer, default=0)  # 0-100
    conversion_achieved = Column(Boolean, default=False)
    # "demo_booked", "info_provided", "escalated", etc.
    outcome = Column(String, nullable=True)

    # Cost tracking
    estimated_cost = Column(Float, default=0.0)  # OpenAI + Twilio costs

    # Timestamps
    conversation_started_at = Column(DateTime, default=datetime.utcnow)
    conversation_ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
    business_config = relationship(
        "UserBusinessConfig", back_populates="sms_usage_logs")
    sms_conversation = relationship("SMSConversation")
