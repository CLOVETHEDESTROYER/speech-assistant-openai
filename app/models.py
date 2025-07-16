# models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.db import Base
import datetime
import enum


class AppType(str, enum.Enum):
    MOBILE = "mobile"
    WEB_BUSINESS = "web_business"
    WEB_CONSUMER = "web_consumer"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String, nullable=True)  # Add name field for mobile app
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    call_schedules = relationship("CallSchedule", back_populates="user")
    tokens = relationship("Token", back_populates="user")
    usage_limits = relationship("UsageLimits", back_populates="user", uselist=False)


class UsageLimits(Base):
    __tablename__ = "usage_limits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    app_type = Column(SQLEnum(AppType), nullable=False, default=AppType.MOBILE)
    calls_made_today = Column(Integer, default=0)
    calls_made_this_week = Column(Integer, default=0)
    calls_made_this_month = Column(Integer, default=0)
    calls_made_total = Column(Integer, default=0)
    last_call_date = Column(DateTime, nullable=True)
    week_start_date = Column(DateTime, default=datetime.datetime.utcnow)
    month_start_date = Column(DateTime, default=datetime.datetime.utcnow)
    trial_calls_remaining = Column(Integer, default=2)  # 2 free trial calls for mobile
    trial_calls_used = Column(Integer, default=0)
    trial_start_date = Column(DateTime, default=datetime.datetime.utcnow)
    trial_end_date = Column(DateTime, nullable=True)
    is_trial_active = Column(Boolean, default=True)
    subscription_tier = Column(String, nullable=True)
    is_subscribed = Column(Boolean, default=False)
    subscription_start_date = Column(DateTime, nullable=True)
    subscription_end_date = Column(DateTime, nullable=True)
    subscription_status = Column(String, nullable=True)
    weekly_call_limit = Column(Integer, nullable=True)
    monthly_call_limit = Column(Integer, nullable=True)
    billing_cycle = Column(String, nullable=True)
    last_payment_date = Column(DateTime, nullable=True)
    next_payment_date = Column(DateTime, nullable=True)
    app_store_transaction_id = Column(String, nullable=True)
    app_store_product_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="usage_limits")


class CallSchedule(Base):
    __tablename__ = "call_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    scenario = Column(String, nullable=False)

    # Relationships
    user = relationship("User", back_populates="call_schedules")


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    access_token = Column(String, unique=True, nullable=False)
    token_type = Column(String, default="bearer")
    refresh_token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="tokens")


__all__ = ["User", "Token", "CallSchedule", "UsageLimits", "AppType", "Base"]
