# models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    call_schedules = relationship("CallSchedule", back_populates="user")
    tokens = relationship("Token", back_populates="user")
    custom_scenarios = relationship("CustomScenario", back_populates="user")
    google_credentials = relationship(
        "GoogleCalendarCredentials", back_populates="user")


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
    token = Column(String, unique=True, nullable=False)
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


__all__ = ["User", "Token", "Base", "CallSchedule",
           "Conversation", "TranscriptRecord", "CustomScenario", "GoogleCalendarCredentials"]
