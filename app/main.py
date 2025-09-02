from app.utils.url_helpers import clean_and_validate_url
from app.routes.mobile_app import router as mobile_router
import json
import base64
import asyncio
import websockets
import logging
import sys
import tempfile
import io
import requests
import re
from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status, Body, Query, BackgroundTasks, File, Form, Path, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect, Say, Stream
from dotenv import load_dotenv
from twilio.rest import Client
import datetime
from pydantic import BaseModel, EmailStr, field_validator, ValidationError
from typing import Optional, Dict, List, Any, Union, Tuple
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pathlib import Path
import sqlalchemy
import threading
import time
from app.auth import router as auth_router, get_current_user
from app.models import User, Token, CallSchedule, Conversation, TranscriptRecord, CustomScenario, GoogleCalendarCredentials, StoredTwilioTranscript, UserPhoneNumber
from app.utils import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.schemas import TokenResponse, RealtimeSessionCreate, RealtimeSessionResponse, SignalingMessage, SignalingResponse
from app.db import engine, get_db, SessionLocal, Base
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.vad_config import VADConfig
from app.realtime_manager import OpenAIRealtimeManager
from os import getenv
from app.services.conversation_service import ConversationService
from app.services.transcription import TranscriptionService
from app.services.twilio_intelligence import TwilioIntelligenceService
from twilio.request_validator import RequestValidator
import traceback
import openai
from openai import OpenAI
from twilio.base.exceptions import TwilioRestException
import uuid
from app.app_config import USER_CONFIG, DEVELOPMENT_MODE, SCENARIOS, VOICES
from app.server import create_app
from app.services.twilio_service import TwilioPhoneService
from app.routes.onboarding import router as onboarding_router
from app.routes.twilio_management import router as twilio_router
from dateutil import parser
from datetime import timedelta
from app.services.google_calendar import GoogleCalendarService
from app.routes import google_calendar
from app.middleware.security_headers import add_security_headers
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.utils.crypto import decrypt_string
import logging.handlers
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from app.limiter import limiter, rate_limit
from app.utils.websocket import websocket_manager
from app.utils.twilio_helpers import (
    with_twilio_retry,
    safe_twilio_response,
    TwilioApiError,
    TwilioAuthError,
    TwilioResourceError,
    TwilioRateLimitError
)
from app.services.twilio_client import get_twilio_client
from contextlib import contextmanager
from app import config  # Import the config module
from sqlalchemy.exc import SQLAlchemyError
import os

IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"

# Load environment variables (only load dev.env in development mode)
if os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true':
    load_dotenv('dev.env')

# Configure logging

# Get log level from config
log_level_name = config.LOG_LEVEL.upper()  # Ensure uppercase for level name
log_level = getattr(logging, log_level_name, logging.INFO)

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging with file and console handlers
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            "logs/app.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Create FastAPI app instance
app = create_app()

# OAuth2 scheme for authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Create a filter to sanitize sensitive data


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            # Sanitize API keys if they appear in logs
            if 'OPENAI_API_KEY' in record.msg and os.getenv('OPENAI_API_KEY'):
                record.msg = record.msg.replace(
                    os.getenv('OPENAI_API_KEY'), '[OPENAI_API_KEY_REDACTED]')
            if 'TWILIO_AUTH_TOKEN' in record.msg and os.getenv('TWILIO_AUTH_TOKEN'):
                record.msg = record.msg.replace(
                    os.getenv('TWILIO_AUTH_TOKEN'), '[TWILIO_AUTH_TOKEN_REDACTED]')
        return True


# Add the filter to the logger
logger.addFilter(SensitiveDataFilter())

# Enhanced Conversation State Management


class ConversationState:
    def __init__(self):
        self.ai_speaking = False
        self.user_speaking = False
        self.last_response_start_time = 0
        self.last_response_end_time = 0
        self.interruption_count = 0
        self.conversation_context = []
        self.pause_keywords = [
            "wait", "hold on", "give me a second", "let me think", "one moment", "hang on"]
        self.last_assistant_item = None
        self.response_start_timestamp = 0

    def start_ai_response(self, assistant_item_id: str = None):
        """Mark that AI started speaking"""
        self.ai_speaking = True
        self.user_speaking = False
        self.last_response_start_time = time.time() * 1000
        self.response_start_timestamp = self.last_response_start_time
        if assistant_item_id:
            self.last_assistant_item = assistant_item_id
        logger.info(f"AI started speaking at {self.last_response_start_time}")

    def end_ai_response(self):
        """Mark that AI finished speaking"""
        self.ai_speaking = False
        self.last_response_end_time = time.time() * 1000
        self.last_assistant_item = None
        logger.info(f"AI finished speaking at {self.last_response_end_time}")

    def start_user_speech(self):
        """Mark that user started speaking"""
        self.user_speaking = True
        if self.ai_speaking:
            self.interruption_count += 1
            logger.info(f"User interruption #{self.interruption_count}")

    def end_user_speech(self):
        """Mark that user finished speaking"""
        self.user_speaking = False

    def should_allow_interruption(self, current_time_ms: float = None) -> bool:
        """Determine if interruption should be allowed based on context and timing"""
        if not self.ai_speaking:
            return False

        if current_time_ms is None:
            current_time_ms = time.time() * 1000

        # Calculate how long AI has been speaking
        response_duration = current_time_ms - self.last_response_start_time

        # Don't allow interruption in first 300ms of response (likely false positive)
        if response_duration < 300:
            logger.info(
                f"Blocking interruption - too early ({response_duration}ms)")
            return False

        # Allow interruption if AI has been speaking for more than 2 seconds
        if response_duration > 2000:
            logger.info(
                f"Allowing interruption - long response ({response_duration}ms)")
            return True

        # Check for pause keywords in recent conversation context
        recent_context = " ".join(self.conversation_context[-3:]).lower()
        for keyword in self.pause_keywords:
            if keyword in recent_context:
                logger.info(
                    f"Allowing interruption - pause keyword detected: {keyword}")
                return True

        # Default: allow interruption after 500ms
        if response_duration > 500:
            logger.info(
                f"Allowing interruption - normal timing ({response_duration}ms)")
            return True

        logger.info(
            f"Blocking interruption - too early ({response_duration}ms)")
        return False

    def add_context(self, text: str, role: str = "user"):
        """Add conversation context for better decision making"""
        self.conversation_context.append(f"{role}: {text}")
        # Keep only last 10 messages for context
        if len(self.conversation_context) > 10:
            self.conversation_context.pop(0)


# After load_dotenv(), add these debug lines:
logger.info("Environment variables loaded:")
logger.info(
    f"TWILIO_ACCOUNT_SID: {os.getenv('TWILIO_ACCOUNT_SID')[:6]}...{os.getenv('TWILIO_ACCOUNT_SID')[-4:] if os.getenv('TWILIO_ACCOUNT_SID') else 'None'}")
logger.info(
    f"TWILIO_AUTH_TOKEN length: {len(os.getenv('TWILIO_AUTH_TOKEN')) if os.getenv('TWILIO_AUTH_TOKEN') else 0}")
logger.info(f"TWILIO_PHONE_NUMBER: {os.getenv('TWILIO_PHONE_NUMBER')}")

# After load_dotenv(), add these debug lines
logger.info("Detailed environment variable check:")
logger.info(f"dev.env file path exists: {os.path.exists('dev.env')}")
logger.info(
    f"TWILIO_ACCOUNT_SID format check: {'AC' in os.getenv('TWILIO_ACCOUNT_SID', '')}")
logger.info(
    f"TWILIO_AUTH_TOKEN exact length: {len(os.getenv('TWILIO_AUTH_TOKEN', ''))}")
logger.info(
    f"TWILIO_PHONE_NUMBER format: {os.getenv('TWILIO_PHONE_NUMBER', '')}")

# requires OpenAI Realtime API Access

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))

SYSTEM_MESSAGE = (
    "You are an AI assistant engaging in real-time voice conversation. "
    "You must strictly follow these rules:\n"
    "1. Stay completely in character based on the provided persona\n"
    "2. Keep responses brief and conversational - speak like a real person on the phone\n"
    "3. Never break character or mention being an AI\n"
    "4. Focus solely on the scenario's objective\n"
    "5. Use natural speech patterns with occasional pauses and filler words\n"
    "6. If interrupted, gracefully acknowledge and adapt your response immediately\n"
    "7. Pay attention to conversation flow and respond appropriately to user cues\n"
    "8. If user says 'wait', 'hold on', or similar, pause and ask how you can help\n"
    "9. Use brief responses to allow natural back-and-forth conversation\n"
    "10. Don't rush through long explanations - break them into smaller parts"
)

LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

# Initialize via app factory
app = create_app()

# Middlewares, security headers and routers are configured in server.create_app()

# Add global exception handler


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to avoid exposing stack traces or sensitive error details
    """
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle validation errors with clear error messages
    """
    errors = []
    for error in exc.errors():
        location = error.get("loc", [])
        location_str = " -> ".join(str(loc)
                                   for loc in location if loc != "body")
        errors.append({
            "field": location_str,
            "message": error.get("msg", "")
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors}
    )

app.add_middleware(SlowAPIMiddleware)

# Create database tables (do this only once)
Base.metadata.create_all(bind=engine)

# Routers are included in server.create_app()

if not OPENAI_API_KEY:
    raise ValueError(
        'Missing the OpenAI API key. Please set it in the .env file.')


# Pydantic Schemas


class UserRead(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool = False  # Add is_admin field with default value

    class Config:
        from_attributes = True  # Updated from orm_mode


# Dependency
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI App Initialization


# Twilio Client Initialization

# Instead, add initialization check on startup
@app.on_event("startup")
async def validate_twilio_connection():
    """Validate Twilio client connection on startup."""
    try:
        client = get_twilio_client()
        # Test the connection
        client.api.accounts(client.account_sid).fetch()
        logger.info("Twilio client connection validated successfully")
    except TwilioAuthError as e:
        logger.warning(f"Twilio authentication error: {e.message} - continuing without Twilio", extra={
            "details": e.details})
        logger.info(
            "Application starting without Twilio authentication - some features may not work")
    except TwilioApiError as e:
        logger.warning(f"Twilio API error: {e.message} - continuing without Twilio", extra={
            "details": e.details})
        logger.info(
            "Application starting without Twilio configuration - some features may not work")
    except Exception as e:
        logger.warning(
            f"Twilio validation failed: {e} - continuing without Twilio")
        logger.info(
            "Application starting without Twilio - some features may not work")

# User Login Endpoint


@app.post("/token", response_model=TokenResponse)
@rate_limit("5/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Protected Route Example


@app.get("/protected")
@rate_limit("5/minute")
def protected_route(request: Request, current_user: User = Depends(get_current_user)):
    return {"message": f"Hello, {current_user.email}"}


@app.get("/users/me", response_model=UserRead)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


# Add this endpoint for updating the user name
@app.post("/update-user-name")
async def update_user_name(
    name: str = Body(...),  # Get name from request body
    current_user: User = Depends(get_current_user),  # Keep authentication
    db: Session = Depends(get_db)
):
    USER_CONFIG["name"] = name
    logger.info(f"Updated user name to: {name}")
    return {"message": f"User name updated to: {name}"}


# Schedule Call Schemas


class CallScheduleCreate(BaseModel):
    phone_number: str
    scheduled_time: datetime.datetime
    scenario: str

    @field_validator('scenario')
    @classmethod
    def validate_scenario(cls, v):
        if v not in SCENARIOS:
            raise ValueError(
                f"Invalid scenario. Must be one of: {', '.join(SCENARIOS.keys())}")
        return v


class CallScheduleRead(CallScheduleCreate):
    id: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True  # Updated from orm_mode

# Schedule Call Endpoint


@app.post("/schedule-call", response_model=CallScheduleRead)
@rate_limit("3/minute")
async def schedule_call(
    request: Request,
    call: CallScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if call.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail="Invalid scenario")
    new_call = CallSchedule(
        user_id=current_user.id,
        phone_number=call.phone_number,
        scheduled_time=call.scheduled_time,
        scenario=call.scenario

    )
    db.add(new_call)
    db.commit()
    db.refresh(new_call)
    return new_call

# Make Call Endpoint


# @app.get("/make-call/{phone_number}/{scenario}")
# @rate_limit("2/minute")
# async def make_call(
#     request: Request,
#     phone_number: str,
#     scenario: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     try:
#         # Check usage limits for business web app users (not in development mode)
#         if not DEVELOPMENT_MODE:
#             from app.services.usage_service import UsageService
#             from app.models import AppType, UsageLimits
#
#             # Initialize or get usage limits
#             usage_limits = db.query(UsageLimits).filter(
#                 UsageLimits.user_id == current_user.id).first()
#             if not usage_limits:
#                 # Auto-detect as web business if not found
#                 app_type = UsageService.detect_app_type_from_request(request)
#                 usage_limits = UsageService.initialize_user_usage(
#                     current_user.id, app_type, db)
#
#             # Check if user can make a call (only for business users)
#             if usage_limits.app_type == AppType.WEB_BUSINESS:
#                 can_call, status_code, details = UsageService.can_make_call(
#                     current_user.id, db)
#
#                 if not can_call:
#                     if status_code == "trial_calls_exhausted":
#                         raise HTTPException(
#                             status_code=402,  # Payment Required
#                             detail={
#                                 "error": "trial_exhausted",
#                                 "message": "Your 4 free trial calls have been used. Upgrade to Basic ($49.99/month) for 20 calls per week!",
#                                 "upgrade_url": "/pricing",
#                                 "pricing": details.get("pricing")
#                             }
#                         )
#                     elif status_code == "weekly_limit_reached":
#                         raise HTTPException(
#                             status_code=402,
#                             detail={
#                                 "error": "weekly_limit_reached",
#                                 "message": details.get("message"),
#                                 "resets_on": details.get("resets_on"),
#                                 "upgrade_url": "/pricing"
#                             }
#                         )
#                     else:
#                         raise HTTPException(status_code=400, detail=details.get(
#                             "message", "Cannot make call"))
#
#         # Check and fix database sequence if needed
#         try:
#             # Check if sequence is working
#             result = db.execute(
#                 "SELECT nextval('conversations_id_seq')").scalar()
#             logger.info(f"Next conversation ID: {result}")
#         except Exception as e:
#             logger.error(f"Sequence error: {str(e)}")
#             # Reset sequence if needed
#             try:
#                 db.execute(
#                     "SELECT setval('conversations_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM conversations))")
#                 db.commit()
#                 logger.info("Database sequence reset successfully")
#             except Exception as reset_error:
#                 logger.error(f"Failed to reset sequence: {str(reset_error)}")
#
#         # Determine which phone number to use
#         from_number = None
#
#         if DEVELOPMENT_MODE:
#             # In development mode, always use system number
#             from_number = os.getenv('TWILIO_PHONE_NUMBER')
#             if not from_number:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="System phone number not configured for development mode. Please set TWILIO_PHONE_NUMBER in your environment."
#                     )
#             logger.info(
#                 f"Development mode: using system phone number: {from_number}")
#         else:
#             # Production mode: check for user-specific phone numbers first
#             user_phone_numbers = db.query(UserPhoneNumber).filter(
#                 UserPhoneNumber.user_id == current_user.id,
#                 UserPhoneNumber.is_active == True,
#                 UserPhoneNumber.voice_capable == True
#             ).all()
#
#             if user_phone_numbers:
#                 # User has provisioned phone numbers - use the first active one
#                 from_number = user_phone_numbers[0].phone_number
#                 logger.info(
#                     f"Using user's provisioned phone number: {from_number}")
#             else:
#                 # Fallback to system-wide Twilio phone number for backward compatibility
#                 from_number = os.getenv('TWILIO_PHONE_NUMBER')
#                 if if not from_number:
#                     raise HTTPException(
#                         status_code=400,
#                         detail="No phone number available. Please provision a phone number in Settings or configure TWILIO_PHONE_NUMBER."
#                     )
#                 logger.info(
#                     f"Using system-wide phone number for backward compatibility: {from_number}")
#
#         # Build the media stream URL with user name and direction parameters
#         # Allow private hosts for development testing
#         base_url = clean_and_validate_url(
#             config.PUBLIC_URL, allow_private=True)
#         user_name = USER_CONFIG.get("name", "")
#         outgoing_call_url = f"{base_url}/outgoing-call/{scenario}?direction=outbound&user_name={user_name}"
#         logger.info(f"Outgoing call URL with parameters: {outgoing_call_url}")
#
#         # Make the call
#         client = get_twilio_client()
#         call = client.calls.create(
#             to=phone_number,
#             from_=from_number,
#             url=outgoing_call_url,
#             record=True
#         )
#
#         # Create a conversation record in the database with the call_sid
#         try:
#             conversation = Conversation(
#                 user_id=current_user.id,
#                 scenario=scenario,
#                 phone_number=phone_number,
#                 direction="outbound",
#                 status="in-progress",
#                 call_sid=call.sid
#             )
#             db.add(conversation)
#             db.commit()
#             db.refresh(conversation)
#         except Exception as e:
#             db.rollback()
#             logger.error(f"Failed to create conversation: {str(e)}")
#             # Try to get the next available ID
#             try:
#                 result = db.execute(
#                     "SELECT nextval('concoming_id_seq')").scalar()
#                 logger.info(f"Next available ID: {result}")
#             except Exception as seq_error:
#                 logger.error(f"Sequence error: {str(seq_error)}")
#             raise HTTPException(
#                 status_code=500, detail="Database error creating conversation")
#
#         # Record the call in usage statistics (only for business users not in development mode)
#         if not DEVELOPMENT_MODE:
#             from app.services.usage_service import UsageService
#             from app.models import UsageLimits, AppType
#
#             usage_limits = db.query(UsageLimits).filter(
#                 UsageLimits.user_id == current_user.id).first()
#             if usage_limits and usage_limits.app_type == AppType.WEB_BUSINESS:
#                 UsageService.record_call(current_user.id, db)
#
#         # Return the call details
#         mode_message = "development mode" if DEVELOPMENT_MODE else ("using your provisioned number" if not DEVELOPMENT_MODE and db.query(
#             UserPhoneNumber).filter(UserPhoneNumber.user_id == current_user.id).first() else "using system number")
#
#         response_data = {
#             "status": "success",
#             "call_sid": call.sid,
#             "from_number": from_number,
#             "message": f"Call initiated successfully ({mode_message})"
#         }
#
#         # Add usage stats for business users
#         if not DEVELOPMENT_MODE:
#             from app.services.usage_service import UsageService
#             from app.models import UsageLimits, AppType
#
#             usage_limits = db.query(UsageLimits).filter(
#                 UsageLimits.user_id == current_user.id).first()
#             if usage_limits and usage_limits.app_type == AppType.WEB_BUSINESS:
#                 updated_stats = UsageService.get_usage_stats(
#                     current_user.id, db)
#                 response_data["usage_stats"] = {
#                     "calls_remaining_this_week": (updated_stats.get("weekly_call_limit", 0) - updated_stats.get("calls_made_this_week", 0)) if updated_stats.get("weekly_call_limit") else "unlimited",
#                     "trial_calls_remaining": updated_stats.get("trial_calls_remaining", 0),
#                     "upgrade_recommended": updated_stats.get("upgrade_recommended", False)
#                 }
#
#         return response_data
#
#     except HTTPException:
#         raise
#     except TwilioRestException as e:
#         logger.exception(
#             f"Twilio error when calling {phone_number} with scenario {scenario}")
#         return JSONResponse(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             content={
#                 "detail": "An error occurred with the phone service. Please try again later."}
#         )
#     except Exception as e:
#         logger.exception(
#             f"Error making call to {phone_number} with scenario {scenario}")
#         return JSONResponse(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             content={
#                 "detail": "An error occurred while processing the outgoing call. Please try again later."}
#         )

# Add a new endpoint for outgoing calls - COMMENTED OUT (duplicate in routers/calls.py)

# @app.api_route("/outgoing-call/{scenario}", methods=["GET", "POST"])
# @rate_limit("2/minute")
# async def handle_outgoing_call(
#     request: Request,
#     scenario: str,
#     db: Session = Depends(get_db)
# ):
#     """Handle outgoing call webhooks from Twilio - Uses signature validation instead of user auth"""
#     # Validate Twilio signature if configured
#     if not IS_DEV and not config.TWILIO_AUTH_TOKEN:
#         raise HTTPException(
#             status_code=500, detail="Twilio signature validation not configured")
#
#     if config.TWILIO_AUTH_TOKEN:
#         from twilio.request_validator import RequestValidator
#         validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
#         twilio_signature = request.headers.get("X-Twilio-Signature", "")
#         request_url = str(request.url)
#
#         # Get form data for validation
#         form_data = await request.form()
#         params = dict(form_data)
#
#         if not validator.validate(request_url, params, twilio_signature):
#             logger.warning("Invalid Twilio signature on outgoing call webhook")
#             raise HTTPException(status_code=401, detail="Invalid signature")
#     else:
#         form_data = await request.form()
#
#     logger.info(f"Outgoing call webhook received for scenario: {scenario}")
#     try:
#         # Extract direction and user_name from query parameters
#         params = dict(request.query_params)
#         direction = params.get("direction", "outbound")
#         user_name = params.get("user_name", "")
#         logger.info(f"Call direction: {direction}, User name: {user_name}")
#
#         if scenario not in SCENARIOS:
#             logger.error(f"Invalid scenario: {scenario}")
#             raise HTTPException(status_code=400, detail="Invalid scenario")
#
#         # Create a copy to avoid modifying the original
#         selected_scenario = SCENARIOS[scenario].copy()
#
#         # Add direction and user_name to the scenario
#         selected_scenario["direction"] = direction
#         if user_name:
#             selected_scenario["user_name"] = user_name
#
#         # Get the hostname for WebSocket connection
#         host = request.url.hostname
#         ws_url = f"wss://{host}/media-stream/{scenario}?direction={direction}&user_name={user_name}"
#         logger.info(f"Setting up WebSocket connection at: {ws_url}")
#
#         # Add a brief pause and greeting to confirm telephony audio path
#         response = VoiceResponse()
#         response.pause(length=0.1)
#         # response.say("Thanks for calling. Connecting you now.", voice="alice")  # Removed
#
#         # Set up the stream connection
#         connect = Connect()
#         connect.stream(url=ws_url)
#         response.append(connect)
#
#         # Add a Gather verb to keep the connection open
#         gather = Gather(action="/handle-user-input",
#                         method="POST", input="speech", timeout=60)
#         response.append(gather)
#
#         twiml = str(response)
#         logger.info(f"Generated TwiML response: {twiml}")
#
#         return Response(content=twiml, media_type="application/xml")
#     except Exception as e:
#         logger.error(f"Error in handle_outgoing_call: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail="An error occurred while processing the outgoing call. Please try again later."
#         )

# Webhook Endpoint for Incoming Calls - COMMENTED OUT (duplicate in routers/calls.py)

# @app.api_route("/incoming-call/{scenario}", methods=["GET", "POST"])
# @rate_limit("1/minute")
# async def handle_incoming_call(request: Request, scenario: str):
#     """Handle incoming calls from customers - No authentication required for business logic"""
#     # Enhanced security for incoming calls
#     try:
#         # Validate Twilio signature if configured
#         if config.TWILIO_AUTH_TOKEN:
#             from twilio.request_validator import RequestValidator
#             validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
#             twilio_signature = request.headers.get("X-Twilio-Signature", "")
#             request_url = str(request.url)
#
#         # Get form data for validation
#         form_data = await request.form()
#         params = dict(form_data)
#
#         if not validator.validate(request_url, params, twilio_signature):
#             logger.warning("Invalid Twilio signature on incoming call")
#             raise HTTPException(
#                 status_code=401, detail="Invalid signature")
#     else:
#         logger.warning(
#             "TWILIO_AUTH_TOKEN not configured; skipping signature validation for incoming call")
#         form_data = await request.form()
#     except Exception as e:
#         logger.error(f"Error validating incoming call: {e}")
#         raise HTTPException(status_code=401, detail="Invalid request")
#
#     logger.info(f"Incoming call webhook received for scenario: {scenario}")
#     try:
#         if scenario not in SCENARIOS:
#             logger.error(f"Invalid scenario: {scenario}")
#             raise HTTPException(status_code=400, detail="Invalid scenario")
#
#         selected_scenario = SCENARIOS[scenario]
#         response = VoiceResponse()
#
#         # Get the hostname for WebSocket connection
#         host = request.url.hostname
#         ws_url = f"wss://{host}/media-stream/{scenario}"
#         logger.info(f"Setting up WebSocket connection at: {ws_url}")
#
#         # Add a greeting message
#         # response.say(
#         #    "Connecting you to our AI assistant, please wait a moment.")
#
#         # Add a pause to allow the server to initialize
#         response.pause(length=0.1)
#
#         # Set up the stream connection
#         connect = Connect()
#         connect.stream(url=ws_url)
#         response.append(connect)
#
#         # Add a Gather verb to keep the connection open
#         gather = Gather(action="/handle-user-input",
#                         method="POST", input="speech", timeout=60)
#         response.append(gather)
#
#         twiml = str(response)
#         logger.info(f"Generated TwiML response: {twiml}")
#
#         return Response(content=twiml, media_type="application/xml")
#     except Exception as e:
#         logger.error(f"Error in handle_incoming_call: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail="An error occurred while processing the incoming call. Please try again later."
#         )


# Add a compatibility route for the old webhook URL format - COMMENTED OUT (duplicate in routers/calls.py)
# @app.api_route("/incoming-call-webhook/{scenario}", methods=["GET", "POST"])
# @rate_limit("1/minute")
# async def handle_incoming_call_webhook(request: Request, scenario: str):
#     """Handle incoming call webhooks from customers - No authentication required for business logic"""
#     # Enhanced security for incoming calls
#     try:
#         # Validate Twilio signature if configured
#         if config.TWILIO_AUTH_TOKEN:
#             from twilio.request_validator import RequestValidator
#             validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
#             twilio_signature = request.headers.get("X-Twilio-Signature", "")
#             request_url = str(request.url)
#
#             # Get form data for validation
#             form_data = await request.form()
#             params = dict(form_data)
#
#             if not validator.validate(request_url, params, twilio_signature):
#                 logger.warning(
#                     "Invalid Twilio signature on incoming call webhook")
#                 raise HTTPException(
#                     status_code=401, detail="Invalid signature")
#         else:
#             logger.warning(
#                 "TWILIO_AUTH_TOKEN not configured; skipping signature validation for incoming call webhook")
#             form_data = await request.form()
#     except Exception as e:
#         logger.error(f"Error validating incoming call webhook: {e}")
#         raise HTTPException(status_code=401, detail="Invalid request")
#     """Compatibility route that redirects to the main incoming-call route."""
#     logger.info(
#         f"Received call on compatibility webhook route for scenario: {scenario}")
#     return await handle_incoming_call(request, scenario)

# Placeholder for WebSocket Endpoint (Implement as Needed)


async def receive_from_twilio(ws_manager, openai_ws, shared_state):
    """Receive messages from Twilio and forward audio to OpenAI."""
    try:
        # ✅ DEBUG: Log function start
        logger.info("🎤 receive_from_twilio function started")

        while not shared_state["should_stop"]:
            # ✅ DEBUG: Log each message receive attempt
            logger.debug("⏳ Waiting for Twilio WebSocket message...")

            message = await ws_manager.receive_text()
            if not message:
                logger.debug("📭 Received empty message from Twilio")
                continue

            # ✅ DEBUG: Log received message
            logger.info(f"📨 RECEIVED FROM TWILIO: {message}")

            data = json.loads(message)
            if data.get("event") == "media":
                # Forward audio to OpenAI
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": data["media"]["payload"]
                }))
                logger.debug("Forwarded audio to OpenAI")
            elif data.get("event") == "start":
                shared_state["stream_sid"] = data.get("streamSid")
                logger.info(f"🎬 Stream started: {shared_state['stream_sid']}")

                # Get scenario name for VAD optimization
                scenario_name = shared_state.get("scenario_name", "default")
                vad_config = VADConfig.get_scenario_vad_config(scenario_name)

                # Initialize session with enhanced VAD configuration
                await openai_ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "turn_detection": vad_config
                    }
                }))
                logger.info(
                    f"Enhanced VAD configuration applied: {vad_config}")
            elif data.get("event") == "stop":
                logger.info("Stream stopped")
                shared_state["should_stop"] = True
                break
            elif data.get("event") == "speech_started":
                logger.info("Speech started - waiting for transcription")
            elif data.get("event") == "transcription" and not shared_state.get("greeting_sent"):
                transcript = data.get("transcript", "").lower()
                if "hello" in transcript or "hi" in transcript or "hey" in transcript:
                    logger.info(
                        "Detected greeting from caller, triggering agent response")
                    shared_state["greeting_sent"] = True
                    # The agent's response will be handled by the existing WebSocket connection

    except websockets.exceptions.ConnectionClosed:
        logger.warning("Twilio WebSocket connection closed")
        shared_state["should_stop"] = True
    except Exception as e:
        logger.error(f"Error receiving from Twilio: {str(e)}", exc_info=True)
        shared_state["should_stop"] = True


async def send_to_twilio(ws_manager, openai_ws, shared_state, conversation_state: ConversationState = None):
    """Enhanced audio sending with conversation state management."""
    try:
        # Initialize conversation state if not provided
        if conversation_state is None:
            conversation_state = ConversationState()
            shared_state["conversation_state"] = conversation_state

        while not shared_state["should_stop"]:
            message = await openai_ws.recv()
            if not message:
                continue

            try:
                data = json.loads(message)
                if "error" in data:
                    logger.error(f"Error from OpenAI: {data['error']}")
                    continue

                # Handle response start
                if data.get("type") == "response.output_item.added":
                    item = data.get("item", {})
                    if item.get("type") == "message" and item.get("role") == "assistant":
                        assistant_item_id = item.get("id")
                        conversation_state.start_ai_response(assistant_item_id)
                        shared_state["ai_speaking"] = True
                        shared_state["last_assistant_item"] = assistant_item_id
                        logger.info(
                            f"AI response started with item ID: {assistant_item_id}")

                # Handle audio deltas
                elif data.get("type") == "response.audio.delta":
                    # Check if user is speaking before sending audio
                    if shared_state.get("user_speaking", False):
                        logger.debug("Skipping audio delta - user is speaking")
                        continue

                    # ✅ FIX: Validate streamSid before sending
                    stream_sid = shared_state.get("stream_sid")
                    if not stream_sid:
                        logger.warning(
                            "No streamSid available, skipping audio delta")
                        continue

                    twilio_message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": data["delta"]
                        }
                    }

                    # ✅ DEBUG: Log the exact message being sent
                    logger.info(
                        f"🔍 SENDING TO TWILIO: {json.dumps(twilio_message)}")

                    await ws_manager.send_json(twilio_message)
                    logger.debug("Sent audio delta to Twilio")

                # Handle response completion
                elif data.get("type") == "response.audio.done":
                    conversation_state.end_ai_response()
                    shared_state["ai_speaking"] = False
                    shared_state["last_assistant_item"] = None
                    logger.info("AI response completed")

                elif data.get("type") == "response.content.done":
                    if shared_state.get("stream_sid"):
                        await send_mark(ws_manager, shared_state)
                        logger.info("Mark event sent to Twilio")

                # Handle function calls from OpenAI Realtime API
                elif data.get("type") == "response.function_call_arguments.done":
                    function_call_id = data.get("call_id")
                    function_name = data.get("name")
                    arguments = data.get("arguments")

                    logger.info(
                        f"📞 Function call received: {function_name} with ID: {function_call_id}")

                    if function_name == "createCalendarEvent":
                        try:
                            # Parse function arguments
                            args = json.loads(arguments) if isinstance(
                                arguments, str) else arguments

                            # Add user_id from shared_state
                            scenario = shared_state.get("scenario", {})
                            user_id = scenario.get("user_id")

                            if not user_id:
                                logger.error(
                                    "No user_id found in scenario for calendar function call")
                                function_result = {"error": "User not found"}
                            else:
                                args["user_id"] = user_id

                                # Call our calendar endpoint directly
                                import aiohttp
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(
                                        "http://localhost:5051/tools/createCalendarEvent",
                                        json=args
                                    ) as response:
                                        if response.status == 200:
                                            function_result = await response.json()
                                            logger.info(
                                                f"✅ Calendar event created: {function_result.get('id')}")
                                        else:
                                            error_text = await response.text()
                                            logger.error(
                                                f"❌ Calendar creation failed: {error_text}")
                                            function_result = {
                                                "error": f"Failed to create calendar event: {error_text}"}

                            # Send function call result back to OpenAI
                            function_response = {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": function_call_id,
                                    "output": json.dumps(function_result)
                                }
                            }

                            await openai_ws.send(json.dumps(function_response))

                            # Request a new response to continue the conversation
                            await openai_ws.send(json.dumps({"type": "response.create"}))

                        except Exception as e:
                            logger.error(
                                f"Error handling calendar function call: {e}", exc_info=True)
                            # Send error back to OpenAI
                            error_response = {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": function_call_id,
                                    "output": json.dumps({"error": str(e)})
                                }
                            }
                            await openai_ws.send(json.dumps(error_response))

                # Handle speech detection
                elif data.get("type") == "input_audio_buffer.speech_started":
                    logger.info("User speech detected by OpenAI")
                    await enhanced_handle_speech_started_event(ws_manager, openai_ws, shared_state, conversation_state)

                elif data.get("type") == "input_audio_buffer.speech_stopped":
                    logger.info("User speech stopped")
                    conversation_state.end_user_speech()
                    shared_state["user_speaking"] = False

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI message: {str(e)}")

    except websockets.exceptions.ConnectionClosed:
        logger.warning("OpenAI WebSocket connection closed")
        shared_state["should_stop"] = True
    except Exception as e:
        logger.error(f"Error sending to Twilio: {str(e)}", exc_info=True)
        shared_state["should_stop"] = True


async def process_outgoing_audio(audio_data, call_sid,  speaker="AI", scenario_name="unknown"):
    """Process and transcribe outgoing audio."""
    db = None
    temp_file_path = None
    try:
        # Get a database session
        db = SessionLocal()

        # Create a temporary file for the audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_data)
            temp_file_path = temp_file.name

            # Transcribe the audio file
            with open(temp_file_path, "rb") as audio_file:
                transcription_service = TranscriptionService()
                outgoing_transcript = await transcription_service.transcribe_audio(audio_file)

                # If we got a valid transcript, save it
                if outgoing_transcript and outgoing_transcript.strip():
                    # Save to database
                    await TranscriptionService().save_conversation(
                        db=db,
                        call_sid=call_sid or "unknown",
                        phone_number=speaker,
                        direction="outbound",
                        scenario=scenario_name,
                        transcript=outgoing_transcript
                    )
                    logger.info(f"Outgoing transcript: {outgoing_transcript}")

    except Exception as e:
        logger.error(f"Error processing outgoing audio: {str(e)}")
    finally:
        # Clean up the temporary file
        if temp_file_path:
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary file: {str(e)}")

        # Make sure to close the DB session
        if db:
            db.close()


async def send_session_update(openai_ws, scenario):
    """Send scenario information to OpenAI with enhanced VAD configuration."""
    try:
        # Get optimized VAD configuration for this scenario
        scenario_name = scenario.get("name", "default")
        vad_config = VADConfig.get_scenario_vad_config(scenario_name)

        # Base session configuration
        session_config = {
            "turn_detection": vad_config,
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "instructions": (
                f"{SYSTEM_MESSAGE}\n\n"
                f"CRITICAL CONVERSATION RULES - FOLLOW THESE STRICTLY:\n"
                f"- STOP TALKING IMMEDIATELY when the other person starts speaking\n"
                f"- Keep responses SHORT and CONCISE (1-2 sentences max)\n"
                f"- NEVER ramble or go on long monologues\n"
                f"- Wait for clear pauses before responding\n"
                f"- Listen and acknowledge what they say before continuing\n"
                f"- Be direct and to the point\n"
                f"- Respect turn-taking - let them finish speaking\n\n"
                f"Persona: {scenario['persona']}\n\n"
                f"Scenario: {scenario['prompt']}\n\n"
                f"{scenario.get('additional_instructions', '')}\n\n"
                + ("IMPORTANT: Greet the caller immediately when the call connects. "
                   "Introduce yourself as specified in your persona and ask how you can help."
                   if scenario.get('direction') == "inbound" else
                   "IMPORTANT: Follow the scenario prompt exactly. Address the user by name if known. Be responsive and natural in conversation.")
            ),
            "voice": scenario["voice_config"]["voice"],
            "modalities": ["text", "audio"],
            "temperature": 0.8
        }

        # Add calendar function calling if scenario has calendar enabled
        if scenario.get("calendar_enabled"):
            logger.info(
                f"📅 Adding calendar function calling to session for user {scenario.get('user_id')}")

            # Add calendar creation tool
            session_config["tools"] = [
                {
                    "type": "function",
                    "name": "createCalendarEvent",
                    "description": "Create a new calendar event when the user wants to schedule something",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "The title/summary of the event (e.g., 'Consultation: John Smith')"
                            },
                            "start_iso": {
                                "type": "string",
                                "description": "Start time in RFC3339 format with timezone (e.g., '2025-09-02T14:00:00-06:00')"
                            },
                            "end_iso": {
                                "type": "string",
                                "description": "End time in RFC3339 format with timezone (e.g., '2025-09-02T14:30:00-06:00')"
                            },
                            "timezone": {
                                "type": "string",
                                "description": "IANA timezone identifier (default: 'America/Denver')",
                                "default": "America/Denver"
                            },
                            "customer_name": {
                                "type": "string",
                                "description": "Customer's name if provided"
                            },
                            "customer_phone": {
                                "type": "string",
                                "description": "Customer's phone number if available"
                            },
                            "attendee_email": {
                                "type": "string",
                                "description": "Email to send calendar invite to"
                            },
                            "location": {
                                "type": "string",
                                "description": "Meeting location or 'Phone Call'"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Additional notes about the appointment"
                            }
                        },
                        "required": ["summary", "start_iso", "end_iso"]
                    }
                }
            ]

            # Enhanced instructions for calendar scenarios
            session_config["instructions"] += """

CALENDAR SCHEDULING CAPABILITIES:
You can create calendar events for users who want to schedule appointments.

When a user wants to schedule something:
1. Collect ALL required details: name, purpose, date, time, duration
2. Convert their natural language to specific datetime (use RFC3339 format with timezone)
3. Confirm the details by reading them back: "I have Tuesday September 2nd, 2:00-2:30 PM Mountain Time - is that correct?"
4. Once confirmed, call the createCalendarEvent function
5. After creating the event, confirm: "Perfect! I've added that to your calendar and you should receive a calendar invitation."

Default timezone is America/Denver (Mountain Time).
Always confirm details before creating events.
Be conversational and helpful."""

        session_data = {
            "type": "session.update",
            "session": session_config
        }

        logger.info(
            f"Sending enhanced session update with VAD config: {vad_config}")
        if scenario.get("calendar_enabled"):
            logger.info("📅 Calendar function calling enabled in session")
        await openai_ws.send(json.dumps(session_data))
        logger.info(f"Session update sent for persona: {scenario['persona']}")
    except Exception as e:
        logger.error(f"Error sending session update: {e}")
        raise

# Then define the WebSocket endpoint


# moved to app/routers/realtime.py
# @app.websocket("/media-stream/{scenario}")  # Moved to app/routers/realtime.py
# async def handle_media_stream(websocket: WebSocket, scenario: str):
    # """Handle media stream for Twilio calls with enhanced interruption handling."""
    # MAX_RECONNECT_ATTEMPTS = 3
    # RECONNECT_DELAY = 2  # seconds

    # # Get the direction and user_name from query parameters
    # params = dict(websocket.query_params)
    # direction = params.get("direction", "inbound")
    # user_name = params.get("user_name", "")
    # logger.info(
    #     f"WebSocket connection for scenario: {scenario}, direction: {direction}, user_name: {user_name}")

    # async with websocket_manager(websocket) as ws:
    #     # All the media stream logic has been moved to app/routers/realtime.py
    #     pass

# Start Background Thread on Server Startup


@app.on_event("startup")
async def startup_event():
    threading.Thread(target=initiate_scheduled_calls, daemon=True).start()


# Background Task to Initiate Scheduled Calls

def initiate_scheduled_calls():
    while True:
        db_local = SessionLocal()
        try:
            now = datetime.datetime.utcnow()
            calls = db_local.query(CallSchedule).filter(
                CallSchedule.scheduled_time <= now).all()

            if calls:
                logger.info(f"Found {len(calls)} scheduled calls to process")

            for call in calls:
                try:
                    # Get PUBLIC_URL from environment
                    host = os.getenv('PUBLIC_URL', '').strip()
                    logger.info(f"Using PUBLIC_URL from environment: {host}")

                    if not host:
                        logger.error("PUBLIC_URL environment variable not set")
                        # Delete the record if environment is not properly configured
                        db_local.delete(call)
                        db_local.commit()
                        logger.info(
                            f"Deleted call schedule {call.id} due to missing PUBLIC_URL")
                        continue

                    # Clean and validate phone number
                    clean_number = call.phone_number.replace('+1', '').strip()
                    if not re.match(r'^\d{10}$', clean_number):
                        logger.error(
                            f"Invalid phone number format: {call.phone_number}")
                        # Delete invalid phone number records
                        db_local.delete(call)
                        db_local.commit()
                        logger.info(
                            f"Deleted call schedule {call.id} due to invalid phone number format")
                        continue

                    # Get Twilio phone number from environment
                    twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
                    if not twilio_phone:
                        logger.error("TWILIO_PHONE_NUMBER not set")
                        # Delete the record if environment is not properly configured
                        db_local.delete(call)
                        db_local.commit()
                        logger.info(
                            f"Deleted call schedule {call.id} due to missing TWILIO_PHONE_NUMBER")
                        continue

                    # Ensure the URL has the https:// protocol
                    if not host.startswith('http://') and not host.startswith('https://'):
                        host = f"https://{host}"

                    # Construct the webhook URL for outgoing calls
                    webhook_url = f"{host}/outgoing-call/{call.scenario}"
                    logger.info(
                        f"Processing scheduled call ID {call.id} to {clean_number}")
                    logger.info(f"Using webhook URL: {webhook_url}")

                    try:
                        # Create the call using Twilio
                        twilio_call = get_twilio_client().calls.create(
                            url=webhook_url,
                            to=f"+1{clean_number}",
                            from_=twilio_phone,
                            record=True
                        )

                        logger.info(
                            f"Scheduled call initiated successfully - Call SID: {twilio_call.sid}")

                        # Only delete the schedule if the call was created successfully
                        db_local.delete(call)
                        db_local.commit()
                        logger.info(
                            f"Removed completed schedule for call ID: {call.id}")

                    except TwilioRestException as e:
                        if "not valid" in str(e).lower():
                            # If Twilio says the number is invalid, delete the record
                            logger.error(
                                f"Invalid phone number confirmed by Twilio for call ID {call.id}: {str(e)}")
                            db_local.delete(call)
                            db_local.commit()
                            logger.info(
                                f"Deleted call schedule {call.id} due to Twilio phone number validation")
                        else:
                            # For other Twilio errors, log but keep the record
                            logger.error(
                                f"Twilio error for call ID {call.id}: {str(e)}")

                except Exception as e:
                    logger.error(
                        f"Failed to initiate scheduled call ID {call.id}: {str(e)}", exc_info=True)

            # Commit any remaining changes
            db_local.commit()
        except SQLAlchemyError as e:
            logger.error(
                f"Database error in initiate_scheduled_calls: {str(e)}", exc_info=True)
            if db_local.is_active:
                db_local.rollback()
        except Exception as e:
            logger.error(
                f"Error in initiate_scheduled_calls: {str(e)}", exc_info=True)
        finally:
            db_local.close()

        # Wait for 60 seconds before checking again
        time.sleep(60)


async def update_scenario(openai_ws, new_scenario):
    if new_scenario not in SCENARIOS:
        raise ValueError(f"Invalid scenario: {new_scenario}")

    selected_scenario = SCENARIOS[new_scenario]
    await send_session_update(openai_ws, selected_scenario)

# You can call this function when you want to change the scenario
# For example, you could add a new WebSocket route for scenario updates:


# moved to app/routers/realtime.py
@app.websocket("/update-scenario/{scenario}")
async def handle_scenario_update(websocket: WebSocket, scenario: str):
    await websocket.accept()
    try:
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2025-06-03',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            await update_scenario(openai_ws, scenario)
            await websocket.send_text(f"Scenario updated to: {scenario}")
    except ValueError as e:
        await websocket.send_text(str(e))
    finally:
        await websocket.close()


# Handle Server Shutdown


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up active sessions on shutdown."""
    # Check if realtime_manager is defined in the global scope
    if 'realtime_manager' in globals():
        for session_id in list(realtime_manager.active_sessions.keys()):
            try:
                await realtime_manager.close_session(session_id)
            except Exception as e:
                logger.error(f"Error closing session {session_id}: {str(e)}")
    else:
        logger.info("No realtime_manager found during shutdown")


@app.get("/test")
async def test_endpoint():
    logger.info("Test endpoint hit")
    return {"message": "Test endpoint working"}


@app.on_event("startup")
async def print_routes():
    for route in app.routes:
        logger.info(f"Route: {route.path} -> {route.name}")


# @app.post("/incoming-call", response_class=Response)
# @rate_limit("1/minute")
# async def incoming_call(request: Request, scenario: str):
#     response = VoiceResponse()
#     response.say("Hello! This is your speech assistant powered by OpenAI.")
#     return Response(content=str(response), media_type="application/xml")


async def initialize_session(openai_ws, scenario, is_incoming=True, user_name=None):
    """Initialize session with OpenAI."""
    try:
        # If scenario is a string, get the scenario data from SCENARIOS
        if isinstance(scenario, str):
            if scenario not in SCENARIOS:
                raise ValueError(f"Invalid scenario: {scenario}")
            scenario = SCENARIOS[scenario]

        # Determine direction and get user name if available
        direction = "inbound" if is_incoming else "outbound"
        effective_user_name = None
        if direction == "outbound":
            # Try to get user_name from various sources
            effective_user_name = user_name or scenario.get(
                "user_name") or USER_CONFIG.get("name")

        # Build instructions with user name for outbound calls
        additional_instructions = ""
        if direction == "outbound" and effective_user_name:
            additional_instructions = f"The user's name is {effective_user_name}. Address them by name. DO NOT ask for their name."
            logger.info(
                f"Adding user name instructions: {additional_instructions}")
        elif direction == "inbound":
            additional_instructions = "Ask for the caller's name if appropriate for the conversation."

        # Add additional instructions to scenario for proper context
        enhanced_scenario = scenario.copy()
        enhanced_scenario["additional_instructions"] = additional_instructions
        enhanced_scenario["direction"] = direction

        # Use send_session_update which includes calendar function calling
        await send_session_update(openai_ws, enhanced_scenario)
        logger.info(
            f"Session initialized with calendar support for persona: {scenario['persona']}")
    except Exception as e:
        logger.error(f"Error sending session update: {e}")
        raise


async def send_initial_greeting(openai_ws, scenario):
    """Send an initial greeting to trigger the AI's response immediately."""
    try:
        # Check if the connection is still open
        if openai_ws.closed:
            logger.error(
                "Cannot send initial greeting: WebSocket connection is closed")
            return False

        greeting_id = str(uuid.uuid4())
        logger.info(
            f"Sending initial greeting to trigger AI response, greeting_id: {greeting_id}")

        # Extract persona name from scenario if available
        persona_name = "AI Assistant"  # Default name
        if isinstance(scenario, dict) and "persona" in scenario:
            # Try to extract the name from the persona description
            persona_text = scenario["persona"]
            name_match = re.search(
                r'^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)', persona_text)
            if name_match:
                persona_name = name_match.group(1)

        # Create a conversation item to trigger the AI's response with a simple greeting
        conversation_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "The call has been connected. Please respond with a greeting, introducing yourself as specified in your persona."
                    }
                ]
            }
        }

        # Send the conversation item with error handling
        try:
            await openai_ws.send(json.dumps(conversation_item))
            logger.info("Initial conversation item sent successfully")

            # Add a small delay to ensure the message is processed
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send conversation item: {str(e)}")
            return False

        # Request a response from the AI
        response_request = {
            "type": "response.create"
        }

        try:
            await openai_ws.send(json.dumps(response_request))
            logger.info("Response request sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send response request: {str(e)}")
            return False

    except Exception as e:
        logger.error(
            f"Error sending initial greeting: {str(e)}", exc_info=True)
        # Don't raise the exception to allow the call to continue
        return False


async def send_mark(connection, stream_sid):
    """Send mark event to Twilio."""
    # Handle both direct stream_sid and shared_state dictionary
    if isinstance(stream_sid, dict) and "stream_sid" in stream_sid:
        actual_stream_sid = stream_sid["stream_sid"]
    else:
        actual_stream_sid = stream_sid

    if actual_stream_sid:
        mark_event = {
            "event": "mark",
            "streamSid": actual_stream_sid,
            "mark": {"name": "responsePart"}
        }

        # ✅ DEBUG: Log the exact message being sent
        logger.info(
            f"🔍 SENDING RESPONSE MARK TO TWILIO: {json.dumps(mark_event)}")

        await connection.send_json(mark_event)
        return 'responsePart'


async def enhanced_handle_speech_started_event(websocket, openai_ws, shared_state, conversation_state: ConversationState = None):
    """
    Enhanced interruption handling with contextual awareness and timing checks.
    """
    try:
        current_time_ms = time.time() * 1000

        # Get the stream_sid
        if isinstance(shared_state, dict) and "stream_sid" in shared_state:
            actual_stream_sid = shared_state["stream_sid"]
        else:
            actual_stream_sid = shared_state

        # Initialize conversation state if not provided
        if conversation_state is None:
            conversation_state = ConversationState()

        # Mark user as speaking
        conversation_state.start_user_speech()

        # Check if interruption should be allowed
        if not conversation_state.should_allow_interruption(current_time_ms):
            logger.info("Interruption blocked by contextual logic")
            return False

        # AI was speaking and interruption is allowed
        if conversation_state.ai_speaking and conversation_state.last_assistant_item:
            logger.info(
                f"Processing interruption for assistant item: {conversation_state.last_assistant_item}")

            # Calculate precise audio timing for truncation
            response_duration = current_time_ms - conversation_state.response_start_timestamp

            # Send truncate event to OpenAI
            truncate_event = {
                "type": "conversation.item.truncate",
                "item_id": conversation_state.last_assistant_item,
                "content_index": 0,
                "audio_end_ms": int(current_time_ms)
            }

            try:
                await openai_ws.send(json.dumps(truncate_event))
                logger.info(
                    f"Sent truncate event for item ID: {conversation_state.last_assistant_item} after {response_duration}ms")
            except Exception as e:
                logger.error(f"Error sending truncate event: {e}")

        # Enhanced audio buffer management
        await enhanced_clear_audio_buffers(websocket, actual_stream_sid)

        # Update conversation state
        conversation_state.end_ai_response()

        # Update shared state for compatibility
        if isinstance(shared_state, dict):
            shared_state["ai_speaking"] = False
            shared_state["user_speaking"] = True
            shared_state["last_interrupt_time"] = current_time_ms

        return True

    except Exception as e:
        logger.error(
            f"Error in enhanced_handle_speech_started_event: {e}", exc_info=True)
        return False


async def enhanced_clear_audio_buffers(websocket, stream_sid):
    """Enhanced audio buffer clearing with better timing"""
    try:
        # ✅ FIX: Validate streamSid before sending
        if not stream_sid:
            logger.warning("No streamSid available, skipping buffer clear")
            return

        # Clear Twilio's audio buffer
        clear_event = {
            "event": "clear",
            "streamSid": stream_sid
        }

        # ✅ DEBUG: Log the exact message being sent
        logger.info(f"🔍 SENDING CLEAR TO TWILIO: {json.dumps(clear_event)}")

        await websocket.send_json(clear_event)
        logger.info(f"Cleared Twilio audio buffer for streamSid: {stream_sid}")

        # Send mark event for clean transition
        mark_event = {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "user_interrupt_handled"}
        }

        # ✅ DEBUG: Log the exact message being sent
        logger.info(f"🔍 SENDING MARK TO TWILIO: {json.dumps(mark_event)}")

        await websocket.send_json(mark_event)

        # Brief pause for clean audio transition
        await asyncio.sleep(0.05)  # Reduced for faster response

    except Exception as e:
        logger.error(f"Error clearing audio buffers: {e}", exc_info=True)


# Initialize the OpenAIRealtimeManager at global scope
realtime_manager = OpenAIRealtimeManager(config.OPENAI_API_KEY)

# New realtime endpoints


# moved to app/routers/realtime.py


# moved to app/routers/realtime.py


# moved to app/routers/realtime.py

# Add a dictionary to store custom scenarios
CUSTOM_SCENARIOS: Dict[str, dict] = {}


# @app.post("/realtime/custom-scenario", response_model=dict)
# @rate_limit("10/minute")
# async def create_custom_scenario(
#     request: Request,
#     persona: str = Body(..., min_length=10, max_length=5000),
#     prompt: str = Body(..., min_length=10, max_length=5000),
#     voice_type: str = Body(...),
#     temperature: float = Body(0.7, ge=0.0, le=1.0),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Create a custom scenario"""
#     try:
#         if voice_type not in VOICES:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
#             )

#         # Check if user has reached the limit of 20 custom scenarios
#         user_scenarios_count = db.query(CustomScenario).filter(
#             CustomScenario.user_id == current_user.id
#         ).count()

#         if user_scenarios_count >= 20:
#             raise HTTPException(
#                 status_code=400,
#                 detail="You have reached the maximum limit of 20 custom scenarios. Please delete some scenarios before creating new ones."
#             )

#         # Create scenario in same format as SCENARIOS dictionary
#         custom_scenario = {
#             "persona": persona,
#             "prompt": prompt,
#             "voice_config": {
#                 "voice": VOICES[voice_type],
#                 "temperature": temperature
#             }
#         }

#         # Generate unique ID
#         scenario_id = f"custom_{current_user.id}_{int(time.time())}"

#         # Store in database
#         db_custom_scenario = CustomScenario(
#             scenario_id=scenario_id,
#             user_id=current_user.id,
#             persona=persona,
#             prompt=prompt,
#             voice_type=voice_type,
#             temperature=temperature
#         )

#         db.add(db_custom_scenario)
#         db.commit()
#         db.refresh(db_custom_scenario)

#         # Also store in memory for backward compatibility
#         CUSTOM_SCENARIOS[scenario_id] = custom_scenario

#         return {
#             "scenario_id": scenario_id,
#             "message": "Custom scenario created successfully"
#         }

#     except Exception as e:
#         logger.error(f"Error creating custom scenario: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An error occurred while creating the custom scenario. Please try again later."
#         )


# @app.get("/custom-scenarios", response_model=List[Dict])
# async def get_custom_scenarios(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get all custom scenarios for the current user."""
#     try:
#         # Query all custom scenarios for the current user
#         db_scenarios = db.query(CustomScenario).filter(
#             CustomScenario.user_id == current_user.id
#         ).order_by(CustomScenario.created_at.desc()).all()

#         # Convert to a list of dictionaries for the response
#         scenarios = []
#         for scenario in db_scenarios:
#             scenarios.append({
#                 "id": scenario.id,
#                 "scenario_id": scenario.scenario_id,
#                 "persona": scenario.persona,
#                 "prompt": scenario.prompt,
#                 "voice_type": scenario.voice_type,
#                 "temperature": scenario.temperature,
#                 "created_at": scenario.created_at.isoformat() if scenario.created_at else None
#             })

#         return scenarios

#     except Exception as e:
#         logger.exception(f"Error retrieving custom scenarios: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An error occurred while retrieving custom scenarios. Please try again later."
#         )


# @app.get("/make-custom-call/{phone_number}/{scenario_id}")
# @rate_limit("2/minute")
# async def make_custom_call(
#     request: Request,
#     phone_number: str,
#     scenario_id: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     try:
#         # Get PUBLIC_URL the same way as the standard endpoint
#         host = os.getenv('PUBLIC_URL', '').strip()
#         logger.info(f"Using PUBLIC_URL from environment: {host}")

#         if not host:
#             logger.error("PUBLIC_URL environment variable not set")
#             return JSONResponse(
#                 status_code=500,
#                 content={"detail": "Server configuration error"}
#             )

#         # Check if phone number is valid
#         if not re.match(r'^\d{10}$', phone_number):
#             logger.error(f"Invalid phone number format: {phone_number}")
#             return JSONResponse(
#                 status_code=400,
#                 content={
#                     "detail": "Invalid phone number format. Please provide a 10-digit number."}
#             )

#         # Get Twilio phone number from environment
#         twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
#         if not twilio_phone:
#             logger.error("TWILIO_PHONE_NUMBER not set")
#             return JSONResponse(
#                 status_code=500,
#                 content={"detail": "Server configuration error"}
#             )

#         # Check if scenario exists in database
#         db_scenario = db.query(CustomScenario).filter(
#             CustomScenario.scenario_id == scenario_id,
#             CustomScenario.user_id == current_user.id
#         ).first()

#         # If not in database, check in-memory dictionary for backward compatibility
#         if not db_scenario and scenario_id not in CUSTOM_SCENARIOS:
#             logger.error(f"Custom scenario not found: {scenario_id}")
#             return JSONResponse(
#                 status_code=400,
#                 content={"detail": "Custom scenario not found"}
#             )

#         # Ensure the URL has the https:// protocol
#         if not host.startswith('http://') and not host.startswith('https://'):
#             host = f"https://{host}"

#         webhook_url = f"{host}/incoming-custom-call/{scenario_id}"
#         logger.info(f"Constructed webhook URL: {webhook_url}")

#         call = get_twilio_client().calls.create(
#             to=f"+1{phone_number}",
#             from_=twilio_phone,
#             url=webhook_url,
#             record=True
#         )
#         logger.info(
#             f"Custom call initiated to +1{phone_number}, call_sid: {call.sid}")
#         return {"status": "Custom call initiated", "call_sid": call.sid}
#     except TwilioRestException as e:
#         logger.error(f"Twilio error: {str(e)}", exc_info=True)
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "detail": "An error occurred with the phone service. Please try again later."}
#         )
#     except Exception as e:
#         logger.error(f"Error initiating custom call: {str(e)}", exc_info=True)
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "detail": "An error occurred while processing the outgoing call. Please try again later."}
#         )


# Custom scenarios endpoint moved to app/routers/custom_scenarios.py

# Testing endpoint for deployment validation (no auth, no rate limiting)
@app.get("/testing/test-call/{phone_number}")
async def test_call_endpoint(
    request: Request,
    phone_number: str,
    scenario: str = "default",
    db: Session = Depends(get_db)
):
    """Testing endpoint for droplet deployment - NO AUTH, NO RATE LIMITING"""
    try:
        logger.info(
            f"TEST CALL: Initiating test call to {phone_number} with scenario {scenario}")

        # Always use system phone number for testing
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        if not from_number:
            raise HTTPException(
                status_code=400,
                detail="System phone number not configured. Please set TWILIO_PHONE_NUMBER."
            )

        # Build the media stream URL
        base_url = clean_and_validate_url(
            config.PUBLIC_URL, allow_private=True)
        outgoing_call_url = f"{base_url}/outgoing-call/{scenario}?direction=outbound&user_name=TestUser"
        logger.info(f"TEST CALL: Using URL: {outgoing_call_url}")

        # Make the call
        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number,
            from_=from_number,
            url=outgoing_call_url,
            record=True
        )

        logger.info(f"TEST CALL: Call initiated with SID: {call.sid}")

        return {
            "status": "success",
            "call_sid": call.sid,
            "from_number": from_number,
            "to_number": phone_number,
            "scenario": scenario,
            "message": "Test call initiated successfully (testing mode - no auth required)",
            "note": "This is a testing endpoint that bypasses authentication and rate limiting"
        }

    except TwilioRestException as e:
        logger.exception(
            f"TEST CALL: Twilio error when calling {phone_number}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Twilio error: {str(e)}"}
        )
    except Exception as e:
        logger.exception(
            f"TEST CALL: Error making test call to {phone_number}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Test call failed: {str(e)}"}
        )

# moved to app/routers/realtime.py
# WebSocket endpoint moved to app/routers/realtime.py


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """Handle WebSocket connections for general sessions."""
    async with websocket_manager(websocket) as ws:
        try:
            # Your existing WebSocket logic here
            # Use ws.send_text(), ws.receive_text(), etc. instead of websocket.send_text()
            pass
        except Exception as e:
            logger.error(
                f"Error in WebSocket session: {str(e)}", exc_info=True)
            # WebSocket closure is handled by the context manager
        finally:
            if db:
                db.close()


@app.websocket("/stream")
async def stream_endpoint(websocket: WebSocket):
    """Handle streaming WebSocket connections."""
    async with websocket_manager(websocket) as ws:
        try:
            # Your existing streaming logic here
            # Use ws.send_text(), ws.receive_text(), etc.
            pass
        except Exception as e:
            logger.error(f"Error in stream endpoint: {str(e)}", exc_info=True)
            # WebSocket closure is handled by the context manager

    # Add new endpoint for recording callback


async def link_transcript_to_conversation(db: Session, call_sid: str, transcript_sid: str, max_retries: int = 6) -> bool:
    """
    Attempt to link a transcript to a conversation with retries.
    Retries every 30 seconds for up to 3 minutes (6 attempts total).
    """
    for attempt in range(max_retries):
        try:
            conversation = db.query(Conversation).filter(
                Conversation.call_sid == call_sid
            ).first()

            if conversation:
                conversation.transcript_sid = transcript_sid
                db.commit()
                logger.info(
                    f"Successfully linked transcript {transcript_sid} to conversation on attempt {attempt + 1}")
                return True

            if attempt < max_retries - 1:  # Don't sleep on the last attempt
                logger.info(
                    f"Conversation not found, retrying in 30 seconds (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(30)

        except Exception as e:
            logger.error(
                f"Error linking transcript on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(30)

    logger.error(
        f"Failed to link transcript {transcript_sid} after {max_retries} attempts")
    return False


# moved to app/routers/twilio_webhooks.py
# @app.post("/recording-callback")
# async def handle_recording_callback(
#     request: Request,
#     db: Session = Depends(get_db)
# ):
    try:
        #         # Validate Twilio webhook signature using centralized validator
        #         from app.utils.twilio_validation import TwilioWebhookValidator
        #         validator = TwilioWebhookValidator()
        #
        #         try:
        #             await validator.validate_webhook(request, webhook_type="form")
        #             form_data = await request.form()
        #         except HTTPException as e:
        #             logger.error(
        #                 f"Twilio webhook signature validation failed: {e.detail}")
        #             raise e
        #
        #         # Log the raw request for debugging
        #         form_data_dict = dict(form_data)
        #         # Sanitize form data for logging
        #         logger.info(
        #             f"Recording callback received with form data: {safe_log_request_data(form_data_dict)}")
        #
        #         recording_sid = form_data.get('RecordingSid')
        #         call_sid = form_data.get('CallSid')
        #
        #         if not recording_sid:
        #             logger.error("No RecordingSid provided in form data")
        #             return {"status": "error", "message": "No RecordingSid provided"}
        #
        #         if not call_sid:
        #             logger.error("No CallSid provided in form data")
        #             return {"status": "error", "message": "No CallSid provided"}
        #
        #         if config.USE_TWILIO_VOICE_INTELLIGENCE:
        #             logger.info(
        #                 f"Using Twilio Voice Intelligence for recording {recording_sid}")
        #
        #             # Log the configuration for debugging
        #             logger.info(
        #                 f"Twilio Voice Intelligence SID: {config.TWILIO_VOICE_INTELLIGENCE_SID}")
        #             logger.info(
        #                 f"PII Redaction Enabled: {config.ENABLE_PII_REDACTION}")
        #
        #             try:
        #                 # Create a transcript using Twilio Voice Intelligence
        #                 transcript = get_twilio_client().intelligence.v2.transcripts.create(
        #                     service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
        #                     channel={
        #                         "media_properties": {
        #                             "source_sid": recording_sid
        #                         }
        #                     },
        #                     redaction=config.ENABLE_PII_REDACTION
        #                 )
        #
        #                 logger.info(f"Transcript created with SID: {transcript.sid}")
        #
        #                 # Start background task to link transcript with retries
        #                 background_tasks = BackgroundTasks()
        #                 background_tasks.add_task(
        #                     link_transcript_to_conversation,
        #                     db=db,
        #                     call_sid=call_sid,
        #                     transcript_sid=transcript.sid
        #                 )
        #
        #                 return {
        #                     "status": "success",
        #                     "transcript_sid": transcript.sid,
        #                     "message": "Transcript creation initiated, linking in progress"
        #                 }
        #
        #             except TwilioAuthError as e:
        #                 logger.error(f"Twilio authentication error: {e.message}", extra={
        #                     "details": e.details})
        #                 return {
        #                     "status": "error",
        #                     "message": "Authentication error with Twilio service",
        #                     "code": "auth_error"
        #                 }
        #             except TwilioResourceError as e:
        #                 logger.error(f"Twilio resource error: {e.message}", extra={
        #                     "details": e.details})
        #                 return {
        #                     "status": "error",
        #                     "message": "Resource not found or invalid",
        #                     "code": "resource_error"
        #                 }
        #             except TwilioRateLimitError as e:
        #                 logger.error(f"Twilio rate limit exceeded: {e.message}", extra={
        #                     "details": e.details})
        #                 return {
        #                     "status": "error",
        #                     "message": "Rate limit exceeded, please try again later",
        #                     "code": "rate_limit"
        #                 }
        #             except TwilioApiError as e:
        #                 logger.error(f"Twilio API error: {e.message}", extra={
        #                     "details": e.details})
        #                 return {
        #                     "status": "error",
        #                     "message": "Error communicating with Twilio service",
        #                     "code": "unknown_error"
        #                 }
        #             except Exception as e:
        #                 logger.error(
        #                     f"Unexpected error creating transcript: {str(e)}", exc_info=True)
        #                 return {
        #                     "status": "error",
        #                     "message": "An unexpected error occurred",
        #                     "code": "unknown_error"
        #                 }
        #
        #         else:
        #             # Your existing OpenAI Whisper implementation
        #             pass
        #
        #     except SQLAlchemyError as e:
        #         logger.error(
        #             f"Database error in recording callback: {str(e)}", exc_info=True)
        #         if db.is_active:
        #             db.is_active:
        #             db.rollback()
        #         return {"status": "error", "message": "Database error", "code": "db_error"}
        #     except Exception as e:
        #         logger.error(f"Error in recording callback: {str(e)}", exc_info=True)
        #         return {"status": "error", "message": "An unexpected error occurred", "code": "unknown_error"}

        # moved to app/routers/twilio_transcripts.py
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# moved to app/routers/twilio_transcripts.py
    except Exception as e:
        logger.error(f"Unexpected error listing transcripts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# moved to app/routers/twilio_transcripts.py
    try:
        # List transcripts filtered by recording SID - list() is not async
        transcripts = get_twilio_client().intelligence.v2.transcripts.list(
            source_sid=recording_sid)

        if not transcripts or len(transcripts) == 0:
            raise TwilioResourceError(
                f"No transcripts found for recording: {recording_sid}",
                details={"recording_sid": recording_sid}
            )

        # Get the first transcript (most recent)
        transcript = transcripts[0]

        # Get sentences for this transcript - list() is not async
        sentences = get_twilio_client().intelligence.v2.transcripts(
            transcript.sid).sentences.list()

        # Log the structure of the first sentence to debug
        if sentences and len(sentences) > 0:
            first_sentence = sentences[0]
            logger.info(
                f"Recording transcript - Sentence object attributes: {dir(first_sentence)}")
            logger.info(
                f"Recording transcript - Sentence object representation: {repr(first_sentence)}")

        # Format the response with proper attribute checking
        formatted_transcript = {
            "sid": transcript.sid,
            "status": transcript.status,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "duration": transcript.duration,
            "sentences": [
                {
                    # Use the correct property name 'transcript' instead of 'text'
                    "text": getattr(sentence, "transcript", "No text available"),
                    "speaker": getattr(sentence, "media_channel", 0),
                    "start_time": getattr(sentence, "start_time", 0),
                    "end_time": getattr(sentence, "end_time", 0),
                    "confidence": getattr(sentence, "confidence", None)
                } for sentence in sentences
            ]
        }

        return formatted_transcript

    except TwilioResourceError as e:
        logger.error(f"Resource error: {e.message}")
        raise HTTPException(
            status_code=404,
            detail=f"No transcripts found for recording: {recording_sid}"
        )
    except TwilioAuthError as e:
        logger.error(f"Authentication error: {e.message}")
        raise HTTPException(
            status_code=401,
            detail="Authentication error with Twilio service"
        )
    except TwilioApiError as e:
        logger.error(f"Twilio API error: {e.message}", extra={
            "details": e.details})
        raise HTTPException(
            status_code=500,
            detail="Error communicating with Twilio service"
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )


# @app.delete("/twilio-transcripts/{transcript_sid}")
# @with_twilio_retry(max_retries=3)
# async def delete_twilio_transcript(transcript_sid: str):
#     try:
#         # First check if the transcript exists
#         try:
#             get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
#         except Exception as e:
#             raise TwilioResourceError(
#                 f"Transcript not found: {transcript_sid}",
#                 details={"original_exception": str(e)}
#             )
#
#         # Delete the transcript
#         get_twilio_client().intelligence.v2.transcripts(transcript_sid).delete()
#
#         return {"status": "success", "message": "Transcript deleted"}
#
#     except TwilioResourceError as e:
#         logger.error(f"Resource error: {e.message}")
#         return HTTPException(
#             status_code=404,
#             detail=f"Transcript not found: {transcript_sid}"
#         )
#     except TwilioAuthError as e:
#         logger.error(f"Authentication error: {e.message}")
#         raise HTTPException(
#             status_code=401,
#             detail="Authentication error with Twilio service"
#         )
#     except TwilioApiError as e:
#         logger.error(f"Twilio API error: {e.message}", extra={
#             "details": e.details})
#         raise HTTPException(
#             status_code=500,
#             detail="Error communicating with Twilio service"
#         )
#     except Exception as e:
#         logger.error(f"Unexpected error deleting transcript: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail="An unexpected error occurred"
#         )


# This endpoint has been moved to app/routers/twilio_transcripts.py


@app.get("/stored-transcripts/", response_model=List[Dict])
async def get_stored_transcripts(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a list of transcripts that have been stored in the database.

    This endpoint retrieves transcripts from your own database rather than
    calling the Twilio API each time, making it faster and more reliable.
    """
    try:
        # Start with a base query
        query = db.query(TranscriptRecord)

        # If user is not an admin, filter by user_id
        if not getattr(current_user, 'is_admin', False):
            query = query.filter(TranscriptRecord.user_id == current_user.id)

        # Apply ordering and pagination
        transcripts = query.order_by(TranscriptRecord.date_created.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()

        # Format the response
        formatted_transcripts = []
        for transcript in transcripts:
            formatted_transcript = {
                "id": transcript.id,
                "transcript_sid": transcript.transcript_sid,
                "status": transcript.status,
                "full_text": transcript.full_text,
                "date_created": str(transcript.date_created) if transcript.date_created else None,
                "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
                "duration": transcript.duration,
                "language_code": transcript.language_code,
                "created_at": str(transcript.created_at) if transcript.created_at else None
            }
            formatted_transcripts.append(formatted_transcript)

        return formatted_transcripts

    except Exception as e:
        logger.error(f"Error retrieving stored transcripts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving stored transcripts"
        )


@app.get("/stored-transcripts/{transcript_sid}", response_model=Dict)
async def get_stored_transcript(
    transcript_sid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific transcript from the database by its SID.

    This endpoint retrieves a transcript from your own database rather than
    calling the Twilio API, making it faster and more reliable.
    """
    try:
        # Query the specific transcript
        query = db.query(TranscriptRecord)\
            .filter(TranscriptRecord.transcript_sid == transcript_sid)

        # If user is not an admin, filter by user_id
        if not getattr(current_user, 'is_admin', False):
            query = query.filter(TranscriptRecord.user_id == current_user.id)

        transcript = query.first()

        if not transcript:
            raise HTTPException(
                status_code=404,
                detail="Transcript not found"
            )

        return {
            "id": transcript.id,
            "transcript_sid": transcript.transcript_sid,
            "status": transcript.status,
            "full_text": transcript.full_text,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "duration": transcript.duration,
            "language_code": transcript.language_code,
            "created_at": str(transcript.created_at) if transcript.created_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error filtering transcript records: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving transcript records. Please try again later."
        )


# @app.get("/custom-scenarios/{scenario_id}", response_model=Dict)
# async def get_custom_scenario(
#     scenario_id: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get a specific custom scenario by ID."""
#     try:
#         # Query the specific custom scenario
#         db_scenario = db.query(CustomScenario).filter(
#             CustomScenario.scenario_id == scenario_id,
#             CustomScenario.user_id == current_user.id
#         ).first()
#
#         # If not found in database, check the in-memory dictionary
#         if not db_scenario:
#             if scenario_id in CUSTOM_SCENARIOS:
#                 # Make sure it belongs to this user (may not be possible to validate for in-memory scenarios)
#                 return {
#                     "id": None,
#                     "scenario_id": scenario_id,
#                     "persona": CUSTOM_SCENARIOS[scenario_id].get("persona", ""),
#                     "prompt": CUSTOM_SCENARIOS[scenario_id].get("prompt", ""),
#                     "voice_type": "unknown",  # In-memory might not store this
#                     "temperature": CUSTOM_SCENARIOS[scenario_id].get("voice_config", {}).get("temperature", 0.7),
#                     "created_at": None
#                 }
#             else:
#                 raise HTTPException(
#                     status_code=404,
#                     detail="Custom scenario not found"
#                 )
#
#         # Convert to dictionary for the response
#         return {
#             "id": db_scenario.id,
#             "scenario_id": db_scenario.scenario_id,
#             "persona": db_scenario.persona,
#             "prompt": db_scenario.prompt,
#             "voice_type": db_scenario.voice_type,
#             "temperature": db_scenario.temperature,
#             "created_at": db_scenario.created_at.isoformat() if db_scenario.created_at else None
#         }
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception(f"Error retrieving custom scenario: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An error occurred while retrieving the custom scenario. Please try again later."
#         )


# @app.delete("/custom-scenarios/{scenario_id}", response_model=Dict)
# async def delete_custom_scenario(
#     scenario_id: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Delete a specific custom scenario by ID."""
#     try:
#         # Query the specific custom scenario
#         db_scenario = db.query(CustomScenario).filter(
#             CustomScenario.scenario_id == scenario_id,
#             CustomScenario.user_id == current_user.id
#         ).first()
#
#         if not db_scenario_id:
#             # Check if it exists in the in-memory dictionary
#             if scenario_id in CUSTOM_SCENARIOS:
#                 # Remove from in-memory dictionary
#                 del CUSTOM_SCENARIOS[scenario_id]
#                 return {"message": "Custom scenario deleted successfully"}
#             else:
#                 raise HTTPException(
#                     status_code=404,
#                     detail="Custom scenario not found"
#                 )
#
#         # Delete from database
#         db.delete(db_scenario)
#         db.commit()
#
#         # Also remove from in-memory dictionary if it exists there
#         if scenario_id in CUSTOM_SCENARIOS:
#             del CUSTOM_SCENARIOS[scenario_id]
#
#         return {"message": "Custom scenario deleted successfully"}
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception(f"Error deleting custom scenario: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An error occurred while deleting the custom scenario. Please try again later."
#             )


# @app.put("/custom-scenarios/{scenario_id}", response_model=Dict)
# async def update_custom_scenario(
#     scenario_id: str,
#     persona: str = Body(..., min_length=10, max_length=5000),
#     prompt: str = Body(..., min_length=10, max_length=5000),
#     voice_type: str = Body(...),
#     temperature: float = Body(0.7, ge=0.0, le=1.0),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Update a specific custom scenario by ID."""
#     try:
#         if voice_type not in VOICES:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
#             )
#
#         # Query the specific custom scenario
#         db_scenario = db.query(CustomScenario).filter(
#             CustomScenario.scenario_id == scenario_id,
#             CustomScenario.user_id == current_user.id
#             )
#
#         if not db_scenario:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Custom scenario not found"
#             )
#
#         # Update database entry
#         db_scenario.persona = persona
#         db_scenario.prompt = prompt
#         db_scenario.voice_type = voice_type
#         db_scenario.temperature = temperature
#         db.commit()
#
#         # Update in-memory dictionary if it exists there
#         if scenario_id in CUSTOM_SCENARIOS:
#             CUSTOM_SCENARIOS[scenario_id] = {
#                 "persona": persona,
#                 "prompt": prompt,
#                 "voice_config": {
#                     "voice": VOICES[voice_type],
#                     "temperature": temperature
#                 }
#             }
#
#         return {"message": "Custom scenario updated successfully"}
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception(f"Error updating custom scenario: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An error occurred while updating the custom scenario. Please try again later."
#             )


@app.get("/test-db-connection")
async def test_db_connection(db: Session = Depends(get_db)):
    """Test database connection and sequence health"""
    try:
        # Import the text function from SQLAlchemy
        from sqlalchemy import text

        # Use the text() function to properly format the SQL query
        result = db.execute(text("SELECT 1")).fetchone()

        # Check conversations sequence health
        try:
            seq_result = db.execute(
                text("SELECT nextval('conversations_id_seq')")).scalar()
            max_id_result = db.execute(
                text("SELECT MAX(id) FROM conversations")).scalar()
            max_id = max_id_result if max_id_result else 0

            sequence_healthy = seq_result > max_id

            return {
                "status": "Database connection working",
                "result": result[0],
                "sequence_health": {
                    "healthy": sequence_healthy,
                    "next_sequence_id": seq_result,
                    "max_conversation_id": max_id,
                    "sequence_gap": seq_result - max_id if sequence_healthy else f"Sequence needs reset (current: {seq_result}, max: {max_id})"
                }
            }
        except Exception as seq_error:
            return {
                "status": "Database connection working",
                "result": result[0],
                "sequence_health": {
                    "healthy": False,
                    "error": str(seq_error)
                }
            }

    except Exception as e:
        return {"status": "Database connection failed", "error": str(e)}


@app.get("/debug/twilio-intelligence-config")
async def debug_twilio_intelligence_config():
    """Check Twilio Voice Intelligence configuration"""
    return {
        "voice_intelligence_enabled": config.USE_TWILIO_VOICE_INTELLIGENCE,
        "voice_intelligence_sid": config.TWILIO_VOICE_INTELLIGENCE_SID,
        "pii_redaction_enabled": config.ENABLE_PII_REDACTION
    }


@app.get("/debug/recent-conversations")
async def debug_recent_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check recent conversations and their transcript status"""
    try:
        from sqlalchemy import text

        conversations = db.execute(
            text("""
                SELECT 
                    id, 
                    call_sid, 
                    recording_sid, 
                    transcript_sid,
                    status,
                    created_at
                FROM conversations 
                WHERE user_id = :user_id 
                ORDER BY created_at DESC 
                LIMIT 5
            """),
            {"user_id": current_user.id}
        ).fetchall()

        return {
            "conversations": [
                {
                    "id": row[0],
                    "call_sid": row[1],
                    "recording_sid": row[2],
                    "transcript_sid": row[3],
                    "status": row[4],
                    "created_at": str(row[5])
                }
                for row in conversations
            ]
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Error getting recent conversations"
        }


@app.get("/debug/recording-callback-status")
async def debug_recording_callback_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check the status of recent recording callbacks and their transcripts"""
    try:
        from sqlalchemy import text

        # Query recent conversations with recording and transcript info
        results = db.execute(
            text("""
                SELECT 
                    c.id,
                    c.call_sid,
                    c.recording_sid,
                    c.transcript_sid,
                    c.transcript,
                    c.created_at,
                    tr.status as transcript_status,
                    tr.full_text
                FROM conversations c
                LEFT JOIN transcript_records tr ON c.transcript_sid = tr.transcript_sid
                WHERE c.user_id = :user_id
                ORDER BY c.created_at DESC
                LIMIT 5
            """),
            {"user_id": current_user.id}
        ).fetchall()

        return {
            "recordings": [
                {
                    "conversation_id": row[0],
                    "call_sid": row[1],
                    "recording_sid": row[2],
                    "transcript_sid": row[3],
                    "conversation_transcript": row[4],
                    "created_at": str(row[5]),
                    "transcript_status": row[6],
                    "transcript_full_text": row[7]
                }
                for row in results
            ]
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Error checking recording callback status"
        }


@app.get("/debug/transcript-records")
async def debug_transcript_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check the TranscriptRecord table directly"""
    try:
        from sqlalchemy import text

        records = db.execute(
            text("""
                SELECT 
                    id,
                    transcript_sid,
                    status,
                    full_text,
                    created_at
                FROM transcript_records
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"user_id": current_user.id}
        ).fetchall()

        return {
            "transcript_records": [
                {
                    "id": row[0],
                    "transcript_sid": row[1],
                    "status": row[2],
                    "full_text": row[3],
                    "created_at": str(row[4])
                }
                for row in records
            ]
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Error checking transcript records"
        }


@app.get("/api/transcripts/{transcript_sid}")
async def get_transcript_details(
    transcript_sid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # First check our local cache
    transcript_record = db.query(TranscriptRecord).filter(
        TranscriptRecord.transcript_sid == transcript_sid
    ).first()

    if transcript_record:
        return {
            "status": "success",
            "transcript": {
                "full_text": transcript_record.full_text,
                "sentences": json.loads(transcript_record.sentences_json),
                "language_code": transcript_record.language_code,
                "duration": transcript_record.duration,
                "status": transcript_record.status
            }
        }

    return {"status": "error", "message": "Transcript not found"}


@app.post("/whisper/transcribe")
# moved to app/routers/transcription.py (/api/transcribe-audio)
def _placeholder_transcribe_route():
    raise HTTPException(
        status_code=410, detail="Endpoint moved to /api/transcribe-audio")


@app.post("/api/transcripts/{transcript_sid}/summarize")
async def summarize_transcript(
    transcript_sid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Summarize a transcript and prepare it for SMS sending.
    """
    try:
        # Get the transcript from our database
        transcript_record = db.query(TranscriptRecord).filter(
            TranscriptRecord.transcript_sid == transcript_sid
        ).first()

        if not transcript_record:
            raise HTTPException(
                status_code=404,
                detail="Transcript not found"
            )

        # Get the full conversation text
        full_text = transcript_record.full_text

        # Use OpenAI to generate a summary
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates concise summaries of phone conversations. Keep summaries under 160 characters for SMS compatibility."},
                {"role": "user", "content": f"Please summarize this conversation in a clear, concise way suitable for SMS: {full_text}"}
            ],
            max_tokens=100,
            temperature=0.7
        )

        summary = response.choices[0].message.content

        # Store the summary in the database
        transcript_record.summary = summary
        db.commit()

        return {
            "status": "success",
            "summary": summary,
            "transcript_sid": transcript_sid
        }

    except Exception as e:
        logger.error(f"Error summarizing transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error generating summary"
        )


@app.post("/api/transcripts/fetch-and-store/{transcript_sid}")
async def fetch_and_store_transcript(
    transcript_sid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch a transcript from Twilio and store it in our database.
    """
    try:
        # First check if we already have this transcript
        existing_transcript = db.query(TranscriptRecord).filter(
            TranscriptRecord.transcript_sid == transcript_sid
        ).first()

        if existing_transcript:
            return {
                "status": "success",
                "message": "Transcript already stored",
                "transcript": {
                    "transcript_sid": existing_transcript.transcript_sid,
                    "full_text": existing_transcript.full_text,
                    "sentences": json.loads(existing_transcript.sentences_json) if existing_transcript.sentences_json else [],
                    "status": existing_transcript.status,
                    "duration": existing_transcript.duration,
                    "language_code": existing_transcript.language_code
                }
            }

        # Fetch from Twilio
        transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
        sentences = get_twilio_client().intelligence.v2.transcripts(
            transcript_sid).sentences.list()

        # Sort sentences by start time
        sorted_sentences = sorted(
            sentences, key=lambda s: getattr(s, "start_time", 0))

        # Create full text from sentences
        full_text = " ".join(
            getattr(s, "transcript", "No text available")
            for s in sorted_sentences
        )

        # Helper function for decimal conversion
        def decimal_to_float(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        # Create new TranscriptRecord
        new_transcript = TranscriptRecord(
            transcript_sid=transcript_sid,
            status=transcript.status,
            full_text=full_text,
            date_created=transcript.date_created,
            date_updated=transcript.date_updated,
            duration=decimal_to_float(transcript.duration),
            language_code=transcript.language_code,
            user_id=current_user.id,
            sentences_json=json.dumps([{
                "transcript": getattr(s, "transcript", "No text available"),
                "speaker": getattr(s, "media_channel", 0),
                "start_time": decimal_to_float(getattr(s, "start_time", 0)),
                "end_time": decimal_to_float(getattr(s, "end_time", 0)),
                "confidence": decimal_to_float(getattr(s, "confidence", None))
            } for s in sorted_sentences], default=decimal_to_float)
        )

        db.add(new_transcript)
        db.commit()

        return {
            "status": "success",
            "message": "Transcript fetched and stored",
            "transcript": {
                "transcript_sid": new_transcript.transcript_sid,
                "full_text": new_transcript.full_text,
                "sentences": json.loads(new_transcript.sentences_json),
                "status": new_transcript.status,
                "duration": new_transcript.duration,
                "language_code": new_transcript.language_code
            }
        }

    except Exception as e:
        logger.error(f"Error fetching and storing transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing transcript: {str(e)}"
        )


@app.post("/api/import-twilio-transcripts")
async def import_twilio_transcripts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all transcripts from /twilio-transcripts endpoint,
    fetch their details, and store them in our database.
    """
    try:
        # Get list of all Twilio transcripts
        transcripts = get_twilio_client().intelligence.v2.transcripts.list()

        results = {
            "success": [],
            "already_exists": [],
            "failed": []
        }

        for twilio_transcript in transcripts:
            try:
                # Check if transcript already exists in our database
                existing = db.query(TranscriptRecord).filter(
                    TranscriptRecord.transcript_sid == twilio_transcript.sid
                ).first()

                if existing:
                    results["already_exists"].append(twilio_transcript.sid)
                    continue

                # Fetch detailed transcript information
                detailed_transcript = get_twilio_client().intelligence.v2.transcripts(
                    twilio_transcript.sid).fetch()
                sentences = get_twilio_client().intelligence.v2.transcripts(
                    twilio_transcript.sid).sentences.list()

                # Sort sentences by start time
                sorted_sentences = sorted(
                    sentences, key=lambda s: getattr(s, "start_time", 0))

                # Create full text from sentences
                full_text = " ".join(
                    getattr(s, "transcript", "No text available")
                    for s in sorted_sentences
                )

                # Helper function for decimal conversion
                def decimal_to_float(obj):
                    from decimal import Decimal
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return obj

                # Create new TranscriptRecord
                new_transcript = TranscriptRecord(
                    transcript_sid=twilio_transcript.sid,
                    status=detailed_transcript.status,
                    full_text=full_text,
                    date_created=detailed_transcript.date_created,
                    date_updated=detailed_transcript.date_updated,
                    duration=decimal_to_float(detailed_transcript.duration),
                    language_code=detailed_transcript.language_code,
                    user_id=current_user.id,
                    sentences_json=json.dumps([{
                        "transcript": getattr(s, "transcript", "No text available"),
                        "speaker": getattr(s, "media_channel", 0),
                        "start_time": decimal_to_float(getattr(s, "start_time", 0)),
                        "end_time": decimal_to_float(getattr(s, "end_time", 0)),
                        "confidence": decimal_to_float(getattr(s, "confidence", None))
                    } for s in sorted_sentences], default=decimal_to_float)
                )

                db.add(new_transcript)
                db.commit()
                results["success"].append(twilio_transcript.sid)

            except Exception as e:
                logger.error(
                    f"Error processing transcript {twilio_transcript.sid}: {str(e)}")
                results["failed"].append({
                    "sid": twilio_transcript.sid,
                    "error": str(e)
                })
                db.rollback()

        return {
            "status": "completed",
            "results": results
        }

    except Exception as e:
        logger.error(f"Error importing transcripts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing transcripts: {str(e)}"
        )


@app.post("/api/enhanced-twilio-transcripts/fetch-and-store")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def fetch_and_store_enhanced_transcript(
    request: Request,
    transcript_sid: str = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Enhanced endpoint to fetch Twilio Intelligence transcripts with full conversation flow,
    participant identification, and structured data for frontend display.

    This endpoint:
    1. Fetches the transcript from Twilio Intelligence API
    2. Extracts detailed sentence-level data with speaker identification
    3. Creates a structured conversation flow
    4. Identifies participants (AI agent vs customer)
    5. Stores enhanced data in our database
    """
    try:
        logger.info(
            f"Fetching enhanced transcript {transcript_sid} for user {current_user.id}")

        # Check if transcript already exists
        existing_transcript = db.query(TranscriptRecord).filter(
            TranscriptRecord.transcript_sid == transcript_sid
        ).first()

        if existing_transcript:
            logger.info(
                f"Transcript {transcript_sid} already exists, returning existing data")
            return {
                "status": "success",
                "message": "Transcript already stored",
                "transcript_data": {
                    "transcript_sid": existing_transcript.transcript_sid,
                    "call_date": existing_transcript.call_date.isoformat() if existing_transcript.call_date else None,
                    "duration": existing_transcript.duration,
                    "participant_info": existing_transcript.participant_info,
                    "conversation_flow": existing_transcript.conversation_flow,
                    "summary_data": existing_transcript.summary_data,
                    "full_text": existing_transcript.full_text
                }
            }

        # Fetch transcript from Twilio Intelligence API
        logger.info(
            f"Fetching transcript details from Twilio for {transcript_sid}")
        transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()

        # Fetch sentences with detailed information
        sentences = get_twilio_client().intelligence.v2.transcripts(
            transcript_sid).sentences.list()

        if not sentences:
            raise HTTPException(
                status_code=404,
                detail=f"No sentences found for transcript {transcript_sid}"
            )

        logger.info(
            f"Retrieved {len(sentences)} sentences for transcript {transcript_sid}")

        # Sort sentences by start time for proper conversation flow
        sorted_sentences = sorted(
            sentences, key=lambda s: getattr(s, "start_time", 0))

        # Helper function for decimal conversion
        def decimal_to_float(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        # Analyze participants and conversation flow
        participants = {}
        conversation_flow = []
        speaker_stats = {}

        for sentence in sorted_sentences:
            # Extract sentence data
            sentence_text = getattr(sentence, "transcript", "")
            media_channel = getattr(sentence, "media_channel", 0)
            start_time = decimal_to_float(getattr(sentence, "start_time", 0))
            end_time = decimal_to_float(getattr(sentence, "end_time", 0))
            confidence = decimal_to_float(
                getattr(sentence, "confidence", None))

            # Determine speaker role based on media channel and content analysis
            speaker_role = "unknown"
            speaker_name = f"Speaker {media_channel}"

            # Channel 0 is typically the caller, Channel 1 is typically the called party
            if media_channel == 0:
                speaker_role = "customer"
                speaker_name = "Customer"
            elif media_channel == 1:
                speaker_role = "agent"
                speaker_name = "AI Agent"

            # Track participant information
            if media_channel not in participants:
                participants[media_channel] = {
                    "channel": media_channel,
                    "role": speaker_role,
                    "name": speaker_name,
                    "total_speaking_time": 0,
                    "word_count": 0,
                    "sentence_count": 0
                }

            # Update speaker statistics
            speaking_duration = end_time - start_time
            word_count = len(sentence_text.split()) if sentence_text else 0

            participants[media_channel]["total_speaking_time"] += speaking_duration
            participants[media_channel]["word_count"] += word_count
            participants[media_channel]["sentence_count"] += 1

            # Add to conversation flow
            conversation_entry = {
                "sequence": len(conversation_flow) + 1,
                "speaker": {
                    "channel": media_channel,
                    "role": speaker_role,
                    "name": speaker_name
                },
                "text": sentence_text,
                "start_time": start_time,
                "end_time": end_time,
                "duration": speaking_duration,
                "confidence": confidence,
                "word_count": word_count,
                "timestamp": start_time  # For easy sorting/filtering
            }
            conversation_flow.append(conversation_entry)

        # Create full conversation text
        full_text = " ".join([entry["text"]
                             for entry in conversation_flow if entry["text"]])

        # Calculate summary statistics
        total_duration = decimal_to_float(
            transcript.duration) if transcript.duration else 0
        total_words = sum([p["word_count"] for p in participants.values()])

        summary_data = {
            "total_duration_seconds": total_duration,
            "total_sentences": len(conversation_flow),
            "total_words": total_words,
            "participant_count": len(participants),
            "language_code": transcript.language_code,
            "average_confidence": sum([entry["confidence"] for entry in conversation_flow if entry["confidence"]]) / len(conversation_flow) if conversation_flow else 0,
            "conversation_stats": {
                "turns": len(conversation_flow),
                "avg_words_per_turn": total_words / len(conversation_flow) if conversation_flow else 0,
                "speaking_time_distribution": {
                    str(channel): {
                        "percentage": (p["total_speaking_time"] / total_duration * 100) if total_duration > 0 else 0,
                        "seconds": p["total_speaking_time"]
                    } for channel, p in participants.items()
                }
            }
        }

        # Determine call direction and scenario from conversation context
        call_direction = "unknown"
        scenario_name = "unknown"

        # Try to find related conversation record to get more context
        related_conversation = None
        if hasattr(transcript, 'call_sid') and transcript.call_sid:
            related_conversation = db.query(Conversation).filter(
                Conversation.call_sid == transcript.call_sid
            ).first()

        if related_conversation:
            call_direction = related_conversation.direction or "unknown"
            scenario_name = related_conversation.scenario or "unknown"
            logger.info(
                f"Found related conversation: direction={call_direction}, scenario={scenario_name}")

        # Create enhanced TranscriptRecord
        enhanced_transcript = TranscriptRecord(
            transcript_sid=transcript_sid,
            status=transcript.status,
            full_text=full_text,
            date_created=transcript.date_created,
            date_updated=transcript.date_updated,
            duration=total_duration,
            language_code=transcript.language_code,
            user_id=current_user.id,

            # Enhanced fields
            call_date=transcript.date_created,  # Use transcript creation as call date
            participant_info=participants,
            conversation_flow=conversation_flow,
            media_url=None,  # Could be populated if we have access to recording URL
            source_type="TwilioIntelligence",
            call_direction=call_direction,
            scenario_name=scenario_name,
            summary_data=summary_data,

            # Keep original sentences_json for backward compatibility
            sentences_json=json.dumps([{
                "transcript": entry["text"],
                "speaker": entry["speaker"]["channel"],
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "confidence": entry["confidence"]
            } for entry in conversation_flow], default=decimal_to_float)
        )

        # Save to database
        db.add(enhanced_transcript)
        db.commit()
        db.refresh(enhanced_transcript)

        logger.info(
            f"Successfully stored enhanced transcript {transcript_sid}")

        # Return structured response for frontend
        return {
            "status": "success",
            "message": "Enhanced transcript fetched and stored successfully",
            "transcript_data": {
                "transcript_sid": enhanced_transcript.transcript_sid,
                "call_date": enhanced_transcript.call_date.isoformat() if enhanced_transcript.call_date else None,
                "duration": enhanced_transcript.duration,
                "participant_info": enhanced_transcript.participant_info,
                "conversation_flow": enhanced_transcript.conversation_flow,
                "summary_data": enhanced_transcript.summary_data,
                "full_text": enhanced_transcript.full_text,
                "call_direction": enhanced_transcript.call_direction,
                "scenario_name": enhanced_transcript.scenario_name,
                "source_type": enhanced_transcript.source_type,
                "language_code": enhanced_transcript.language_code,
                "status": enhanced_transcript.status
            }
        }

    except TwilioResourceError as e:
        logger.error(f"Transcript not found: {e.message}")
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found: {transcript_sid}"
        )
    except TwilioAuthError as e:
        logger.error(f"Authentication error: {e.message}")
        raise HTTPException(
            status_code=401,
            detail="Authentication error with Twilio service"
        )
    except TwilioApiError as e:
        logger.error(f"Twilio API error: {e.message}", extra={
                     "details": e.details})
        raise HTTPException(
            status_code=500,
            detail="Error communicating with Twilio service"
        )
    except Exception as e:
        logger.error(
            f"Error fetching enhanced transcript: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing enhanced transcript: {str(e)}"
        )


@app.get("/api/enhanced-transcripts/", response_model=List[Dict])
async def get_enhanced_transcripts(
    skip: int = 0,
    limit: int = 10,
    call_direction: Optional[str] = None,
    scenario_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced transcripts with filtering options for frontend display.

    This endpoint returns transcripts with full conversation flow and participant data,
    optimized for frontend consumption.
    """
    try:
        # Start with base query
        query = db.query(TranscriptRecord)

        # Filter by user (non-admin users only see their own transcripts)
        if not getattr(current_user, 'is_admin', False):
            query = query.filter(TranscriptRecord.user_id == current_user.id)

        # Apply filters
        if call_direction:
            query = query.filter(
                TranscriptRecord.call_direction == call_direction)

        if scenario_name:
            query = query.filter(
                TranscriptRecord.scenario_name == scenario_name)

        if date_from:
            try:
                from_date = datetime.datetime.fromisoformat(
                    date_from.replace('Z', '+00:00'))
                query = query.filter(TranscriptRecord.call_date >= from_date)
            except ValueError:
                logger.warning(f"Invalid date_from format: {date_from}")

        if date_to:
            try:
                to_date = datetime.datetime.fromisoformat(
                    date_to.replace('Z', '+00:00'))
                query = query.filter(TranscriptRecord.call_date <= to_date)
            except ValueError:
                logger.warning(f"Invalid date_to format: {date_to}")

        # Order by call date (most recent first)
        query = query.order_by(TranscriptRecord.call_date.desc().nullslast())

        # Apply pagination
        transcripts = query.offset(skip).limit(limit).all()

        # Format response for frontend
        formatted_transcripts = []
        for transcript in transcripts:
            formatted_transcript = {
                "id": transcript.id,
                "transcript_sid": transcript.transcript_sid,
                "call_date": transcript.call_date.isoformat() if transcript.call_date else None,
                "duration": transcript.duration,
                "call_direction": transcript.call_direction,
                "scenario_name": transcript.scenario_name,
                "source_type": transcript.source_type,
                "language_code": transcript.language_code,
                "status": transcript.status,
                "participant_count": len(transcript.participant_info) if transcript.participant_info else 0,
                "conversation_turns": len(transcript.conversation_flow) if transcript.conversation_flow else 0,
                "total_words": transcript.summary_data.get("total_words", 0) if transcript.summary_data else 0,
                "created_at": transcript.created_at.isoformat() if transcript.created_at else None,

                # Include summary for quick overview
                "summary": {
                    "duration_formatted": f"{transcript.duration // 60}:{transcript.duration % 60:02d}" if transcript.duration else "0:00",
                    "participant_info": transcript.participant_info,
                    "conversation_stats": transcript.summary_data.get("conversation_stats", {}) if transcript.summary_data else {}
                }
            }
            formatted_transcripts.append(formatted_transcript)

        return formatted_transcripts

    except Exception as e:
        logger.error(
            f"Error retrieving enhanced transcripts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error retrieving enhanced transcripts"
        )


@app.get("/api/enhanced-transcripts/{transcript_sid}", response_model=Dict)
async def get_enhanced_transcript_details(
    transcript_sid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed enhanced transcript data including full conversation flow.

    This endpoint returns the complete transcript with conversation flow,
    participant details, and summary statistics for frontend display.
    """
    try:
        # Query the specific transcript
        query = db.query(TranscriptRecord).filter(
            TranscriptRecord.transcript_sid == transcript_sid
        )

        # Filter by user (non-admin users only see their own transcripts)
        if not getattr(current_user, 'is_admin', False):
            query = query.filter(TranscriptRecord.user_id == current_user.id)

        transcript = query.first()

        if not transcript:
            raise HTTPException(
                status_code=404,
                detail="Enhanced transcript not found"
            )

        # Format detailed response
        detailed_transcript = {
            "id": transcript.id,
            "transcript_sid": transcript.transcript_sid,
            "call_date": transcript.call_date.isoformat() if transcript.call_date else None,
            "duration": transcript.duration,
            "call_direction": transcript.call_direction,
            "scenario_name": transcript.scenario_name,
            "source_type": transcript.source_type,
            "language_code": transcript.language_code,
            "status": transcript.status,
            "full_text": transcript.full_text,
            "created_at": transcript.created_at.isoformat() if transcript.created_at else None,

            # Enhanced data
            "participant_info": transcript.participant_info or {},
            "conversation_flow": transcript.conversation_flow or [],
            "summary_data": transcript.summary_data or {},

            # Formatted data for easy frontend consumption
            "formatted_data": {
                "duration_formatted": f"{transcript.duration // 60}:{transcript.duration % 60:02d}" if transcript.duration else "0:00",
                "participant_names": [p.get("name", f"Speaker {p.get('channel', 'Unknown')}") for p in (transcript.participant_info or {}).values()],
                "total_turns": len(transcript.conversation_flow) if transcript.conversation_flow else 0,
                "total_words": transcript.summary_data.get("total_words", 0) if transcript.summary_data else 0,
                "average_confidence": transcript.summary_data.get("average_confidence", 0) if transcript.summary_data else 0
            }
        }

        return detailed_transcript

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving enhanced transcript details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error retrieving enhanced transcript details"
        )


# moved to app/routers/realtime.py
@app.websocket("/calendar-media-stream")
async def handle_calendar_media_stream(websocket: WebSocket):
    """Handle media stream for calendar-related calls"""
    caller = websocket.query_params.get("caller", "unknown")
    logger.info(f"Calendar WebSocket connection from {caller}")

    # Accept the connection
    async with websocket_manager(websocket) as ws:
        try:
            # Get a database session
            db = SessionLocal()

            # Look up the user based on call history instead of phone number
            # since User model doesn't have a phone_number field
            user = None

            # Normalize the phone number for matching
            normalized_phone = caller.replace('+', '').replace(' ', '')

            # Try to find the user through conversation history
            conversation = db.query(Conversation).filter(
                Conversation.phone_number.like(f"%{normalized_phone}%")
            ).order_by(Conversation.created_at.desc()).first()

            if conversation and conversation.user_id:
                user = db.query(User).filter(
                    User.id == conversation.user_id).first()
                logger.info(
                    f"Found user {user.email} based on conversation history")

            # If we don't find the user, try to find any user with calendar credentials
            # This is a fallback for testing/development
            if not user:
                logger.warning(f"No matching user found for caller: {caller}")
                # Find any user with calendar credentials for testing
                credentials_query = db.query(GoogleCalendarCredentials).first()
                if credentials_query:
                    user = db.query(User).filter(
                        User.id == credentials_query.user_id).first()
                    logger.info(
                        f"Using fallback user: {user.email} for calendar demo")
                else:
                    logger.error(
                        "No users with Google Calendar credentials found")
                    # Send error message as TwiML
                    await ws.send_text(json.dumps({
                        "error": "User not found",
                        "message": "I'm sorry, I don't recognize this phone number. Please register in our system first."
                    }))
                    return

            # Check if user has Google Calendar connected
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == user.id
            ).first()

            # Define the instructions for OpenAI
            if not credentials:
                # Handle case where user hasn't connected their calendar
                logger.warning(
                    f"User {user.id} hasn't connected Google Calendar")
                instructions = (
                    "You are a helpful assistant handling a phone call. "
                    "The caller wants to access their calendar, but they haven't connected "
                    "their Google Calendar to our system yet. "
                    "Politely explain that they need to log in to the web portal and connect "
                    "their Google Calendar before they can use this feature. Offer to help with "
                    "any questions they have about the process."
                )

                # Initialize connection with OpenAI
                scenario = {
                    "persona": "Calendar Assistant",
                    "prompt": "You are a helpful calendar assistant. The caller wants to check their calendar, but they haven't connected their Google Calendar yet.",
                    "voice_config": {
                        "voice": "alloy",  # Changed from 'alloy' to ensure compatibility
                        "temperature": 0.7
                    }
                }
            else:
                # User has calendar connected - prepare calendar service
                calendar_service = GoogleCalendarService()
                service = calendar_service.get_calendar_service({
                    "token": decrypt_string(credentials.token),
                    "refresh_token": decrypt_string(credentials.refresh_token),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "expiry": credentials.token_expiry.isoformat()
                })

                # Get upcoming events for context
                time_min = datetime.datetime.utcnow()
                events = await calendar_service.get_upcoming_events(
                    service,
                    max_results=5,
                    time_min=time_min
                )

                # Format events for the AI context
                events_context = ""
                if events:
                    events_context = "Here are the user's upcoming calendar events:\\n"
                    for event in events:
                        if 'dateTime' in event.get('start', {}):
                            start_time = event['start']['dateTime']
                            end_time = event['end']['dateTime']
                        else:
                            # All-day event
                            start_time = event.get('start', {}).get('date', '')
                            end_time = event.get('end', {}).get('date', '')

                        events_context += (
                            f"- {event.get('summary', 'No title')} from {start_time} to {end_time}\\n"
                        )
                else:
                    events_context = "The user has no upcoming events on their calendar."

                # Find next available slots
                start_date = datetime.datetime.utcnow()
                end_date = start_date + timedelta(days=7)
                free_slots = await calendar_service.find_free_slots(
                    service,
                    start_date,
                    end_date,
                    min_duration_minutes=30,
                    max_results=3,
                    working_hours=(9, 17)
                )

                slots_context = ""
                if free_slots:
                    slots_context = "Here are some available time slots in the user's calendar:\\n"
                    for start, end in free_slots:
                        slots_context += f"- {start.strftime('%A, %B %d at %I:%M %p')} to {end.strftime('%I:%M %p')}\\n"
                else:
                    slots_context = "The user has no free time slots in the next week."

                # Create custom instructions for this scenario including calendar event creation
                instructions = (
                    "You are a helpful calendar assistant handling a phone call. "
                    "You have access to the caller's Google Calendar. Be conversational and friendly. "
                    f"\n\n{events_context}\\n\\n{slots_context}\\n\\n"
                    "You can provide information about upcoming events, check availability, "
                    "and suggest free time slots. If the caller asks about scheduling an event, "
                    "collect the necessary details like date, time, duration, and purpose, then "
                    "tell them 'I'll add that to your calendar right away.' You don't need to create "
                    "the event yourself - our system will handle that automatically when you confirm. "
                    "IMPORTANT: When asked to create a calendar event, be sure to confirm all details with the user. "
                    "IMPORTANT: Introduce yourself as a calendar assistant. "
                    "Remain connected and responsive during silences. "
                    "Offer to help with any other calendar-related questions they might have."
                )

                # Initialize connection with OpenAI with calendar-specific scenario
                scenario = {
                    "persona": "Calendar Assistant",
                    "prompt": instructions,
                    "voice_config": {
                        "voice": "alloy",  # Changed from 'nova' to 'alloy' which is supported
                        "temperature": 0.7
                    }
                }

            # Initialize reconnection counter
            reconnect_attempts = 0
            MAX_RECONNECT_ATTEMPTS = 3
            RECONNECT_DELAY = 2  # seconds

            # Start reconnection loop similar to your existing WebSocket endpoints
            while reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                try:
                    async with websockets.connect(
                        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2025-06-03',
                        extra_headers={
                            "Authorization": f"Bearer {OPENAI_API_KEY}",
                            "OpenAI-Beta": "realtime=v1"
                        },
                        ping_interval=20,
                        ping_timeout=60,
                        close_timeout=60
                    ) as openai_ws:
                        logger.info(
                            "Connected to OpenAI WebSocket for calendar")

                        # Connection specific state
                        shared_state = {
                            "should_stop": False,
                            "stream_sid": None,
                            "latest_media_timestamp": 0,
                            "last_assistant_item": None,
                            "current_transcript": "",
                            "greeting_sent": False,
                            "pending_greeting_attempts": 0
                        }

                        # Initialize session
                        await initialize_session(openai_ws, scenario, is_incoming=True)
                        logger.info(
                            "Session initialized with OpenAI for calendar")

                        # Add a delay to ensure the session is fully initialized
                        await asyncio.sleep(0.5)

                        # Check if Twilio WebSocket is still connected with retry
                        for ping_attempt in range(3):
                            try:
                                await ws.send_text(json.dumps({"status": "connected", "attempt": ping_attempt}))
                                logger.info(
                                    f"Twilio WebSocket is connected (attempt {ping_attempt+1})")
                                break
                            except Exception as e:
                                logger.warning(
                                    f"Failed to ping Twilio WebSocket (attempt {ping_attempt+1}): {e}")
                                await asyncio.sleep(0.5)
                                if ping_attempt == 2:  # Last attempt
                                    logger.error(
                                        "All Twilio ping attempts failed, aborting")
                                    return

                        # Function to send initial greeting with retry
                        async def send_greeting_with_retry(max_retries=3):
                            for attempt in range(max_retries):
                                try:
                                    # Create a conversation item to trigger the AI's response with a simple greeting
                                    conversation_item = {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "input_text",
                                                    "text": "The call has been connected. Please introduce yourself as a calendar assistant and ask how you can help with the caller's calendar."
                                                }
                                            ]
                                        }
                                    }

                                    # Send the conversation item
                                    await openai_ws.send(json.dumps(conversation_item))
                                    logger.info(
                                        f"Initial conversation item sent successfully (attempt {attempt+1})")

                                    # Add a small delay
                                    await asyncio.sleep(0.2)

                                    # Request a response
                                    response_request = {
                                        "type": "response.create"
                                    }

                                    await openai_ws.send(json.dumps(response_request))
                                    logger.info(
                                        f"Response request sent successfully (attempt {attempt+1})")

                                    # Mark as successful
                                    return True
                                except Exception as e:
                                    logger.error(
                                        f"Failed to send greeting (attempt {attempt+1}): {str(e)}")
                                    await asyncio.sleep(0.5)

                            # If we got here, all attempts failed
                            logger.error("All greeting attempts failed")
                            return False

                        # Send initial greeting with retry mechanism
                        greeting_success = await send_greeting_with_retry(max_retries=3)
                        if greeting_success:
                            logger.info(
                                "Initial greeting sent successfully with retry mechanism")
                            shared_state["greeting_sent"] = True
                        else:
                            logger.warning(
                                "Failed to send initial greeting after multiple attempts")
                            # Continue anyway, as the user might speak first

                        # Create tasks for receiving from Twilio and sending to Twilio
                        # Use our custom receive function that handles calendar event creation
                        receive_task = asyncio.create_task(
                            receive_from_twilio_calendar(ws, openai_ws, shared_state, user.id, db))
                        send_task = asyncio.create_task(
                            send_to_twilio(ws, openai_ws, shared_state))

                        # Additional task to monitor connection and retry greeting if needed
                        async def monitor_and_retry_greeting():
                            retry_count = 0
                            max_retries = 2

                            while not shared_state["should_stop"] and retry_count < max_retries:
                                await asyncio.sleep(5)  # Check every 5 seconds

                                # If we haven't received any response and the greeting wasn't sent successfully
                                if not shared_state.get("greeting_sent") and not shared_state.get("current_transcript"):
                                    logger.info(
                                        f"Retrying greeting (attempt {retry_count+1})")
                                    success = await send_greeting_with_retry(max_retries=1)
                                    if success:
                                        shared_state["greeting_sent"] = True
                                        logger.info(
                                            f"Retry greeting succeeded (attempt {retry_count+1})")
                                        break
                                    retry_count += 1
                                else:
                                    # Greeting was sent or we have received user input, no need to continue
                                    break

                        # Start the monitoring task
                        monitor_task = asyncio.create_task(
                            monitor_and_retry_greeting())

                        # Wait for tasks to complete
                        done, pending = await asyncio.wait(
                            [receive_task, send_task, monitor_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        # Cancel any pending tasks
                        for task in pending:
                            task.cancel()

                        # Handle any exceptions from completed tasks
                        for task in done:
                            try:
                                await task
                            except Exception as e:
                                logger.error(f"Task error: {str(e)}")

                        # Break out of the reconnection loop
                        break

                except websockets.exceptions.WebSocketException as e:
                    logger.error(f"WebSocket error in calendar stream: {e}")
                    reconnect_attempts += 1
                    if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                        logger.info(
                            f"Attempting to reconnect... (Attempt {reconnect_attempts})")
                        await asyncio.sleep(RECONNECT_DELAY)
                        continue
                    raise

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(
                f"Error in calendar media stream: {str(e)}", exc_info=True)
        finally:
            if 'db' in locals():
                db.close()


@app.post("/handle-user-input")
async def handle_user_input(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle user input from Twilio Gather verb"""
    try:
        # Verify Twilio signature (skip in development or if token not set)
        if config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            form_data = await request.form()
            params = dict(form_data)
            if not validator.validate(request_url, params, twilio_signature):
                logger.warning(
                    "Invalid Twilio signature on user input webhook")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")
        else:
            logger.warning(
                "TWILIO_AUTH_TOKEN not configured; skipping signature validation for user input webhook")
            form_data = await request.form()

        speech_result = form_data.get("SpeechResult", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Received user input from Gather: {speech_result}")

        # We don't need to do anything with the input here, as the websocket connection
        # will handle the real-time conversation. We just need to return a valid TwiML response
        # to keep the call going.
        response = VoiceResponse()
        response.pause(length=60)  # Add a long pause to keep the call open

        return Response(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"Error handling user input: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your input. Please try again later."
        )


# moved to app/routers/twilio_webhooks.py
# @app.post("/twilio-callback")
# async def handle_twilio_callback(
#     request: Request,
#     db: Session = Depends(get_db)
# ):
#     """Handle Twilio status callbacks for call status updates"""
#     try:
#         # Verify Twilio signature (skip in development or if token not set)
#         request_url = str(request.url)
#         form_data = await request.form()
#         if config.TWILIO_AUTH_TOKEN:
#             validator = RequestValidator(config.TWilio_signature, "")
#             params = dict(form_data)
#             if not validator.validate(request_url, params, twilio_signature):
#                 logger.warning("Invalid Twilio signature on status callback")
#                 return {"status": "error", "message": "Invalid signature"}
#         else:
#             logger.warning(
#                 "TWILIO_AUTH_TOKEN not configured; skipping signature validation for status callback")
#         call_sid = form_data.get("CallSid")
#         call_status = form_data.get("CallStatus")
#
#         logger.info(
#             f"Received Twilio callback for call {sanitize_text(str(call_sid))} with status {sanitize_text(str(call_status))}")
#
#         if not call_sid:
#             return {"status": "error", "message": "No CallSid provided"}
#
#         # Update conversation record if it exists
#         conversation = db.query(Conversation).filter(
#             Conversation.call_sid == call_sid
#         ).first()
#
#         # Map Twilio status to our status
#         status_map = {
#             "completed": "completed",
#             "busy": "failed",
#             "failed": "failed",
#             "no-answer": "failed",
#             "canceled": "canceled"
#         }
#
#         conversation.status = status_map.get(call_status, call_status)
#         db.commit()
#         logger.info(
#             f"Updated conversation {conversation.id} status to {conversation.status}")
#
#         # Check for recording if the call was completed
#         if call_status == "completed":
#             recording_sid = form_data.get("RecordingSid")
#             if call_sid:
#                 conversation.recording_sid = recording_sid
#                 db.commit()
#                 logger.info(
#                     f"Updated conversation {conversation.id} with recording {recording_sid}")
#
#         return {"status": "success", "call_sid": call_sid, "call_status": call_status}
#     except Exception as e:
#         logger.error(
#             f"Error handling Twilio callback: {str(e)}", exc_info=True)
#         return {"status": "error", "message": str(e)}


# @app.get("/make-calendar-call-scenario/{phone_number}")
# @rate_limit("2/minute")
# async def make_calendar_call_scenario(
#     request: Request,
#     phone_number: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Make a calendar call using the standard scenario approach that's known to work well.
#     This creates a temporary scenario with calendar data and uses the standard call flow.
#     """
#     try:
#         # Validate phone number format
#         if not phone_number.startswith('+'):
#             phone_number = f"+{phone_number}"
#
#         logger.info(
#             f"Initiating calendar call (scenario approach) to {phone_number} for user {current_user.email}")
#
#         # Check if user has Google Calendar connected
#         credentials = db.query(GoogleCalendarCredentials).filter(
#             GoogleCalendarCredentials.user_id == current_user.id
#         ).first()
#
#         # Prepare calendar service
#         calendar_service = GoogleCalendarService()
#         service = calendar_service.get_calendar_service({
#             "token": decrypt_string(credentials.token),
#             "refresh_token": decrypt_string(credentials.refresh_token),
#             "token_uri": "https://oauth2.googleapis.com/token",
#             "client_id": os.getenv("GOOGLE_CLIENT_ID"),
#             "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
#             "expiry": credentials.token_expiry.isoformat()
#         })
#
#         # Get upcoming events
#         time_min = datetime.datetime.utcnow()
#         events = await calendar_service.get_upcoming_events(
#             service,
#             max_results=5,
#             time_min=time_min
#         )
#
#         # Format events for the AI context
#         events_context = ""
#         if events:
#             events_context = "Here are the user's upcoming calendar events:\\n"
#             for event in events:
#                 if 'dateTime' in event.get('start', {}):
#                     start_time = event['start']['dateTime']
#                     end_time = event['end']['dateTime']
#                 else:
#                     # All-day event
#                     start_time = event.get('start', {}).get('date', 'start')
#                     end_time = event.get('end', {}).get('date', 'end')
#
#                 events_context += (
#                     f"- {event.get('summary', 'No title')} from {start_time} to {end_time}\\n"
#                 )
#         else:
#             events_context = "The user has no upcoming events on their calendar."
#
#         # Find next available slots
#         start_date = datetime.datetime.utcnow()
#         end_date = start_date + timedelta(days=7)
#         free_slots = await calendar_service.find_free_slots(
#             service,
#             start_date,
#             end_date,
#             min_duration_minutes=30,
#             max_results=3,
#             working_hours=(9, 17)
#         )
#
#         slots_context = ""
#         if free_slots:
#             slots_context = "Here are some available time slots in the user's calendar:\\n"
#             for start, end in free_slots:
#                 slots_context += f"- {start.strftime('%A, %B %d at %I:%M %p')} to {end.strftime('%I:%M %p')}\\n"
#         else:
#             slots_context = "The user has no free time slots in the next week."
#
#         # Create a temporary scenario key (not in the SCENARIOS dict)
#         temp_scenario_key = f"calendar_{current_user.id}_{int(time.time())}"
#
#         # Create the scenario
#         calendar_scenario = {
#             "persona": "Calendar Assistant",
#             "prompt": (
#                 f"You are a helpful calendar assistant handling a phone call. "
#                 f"You have access to the caller's Google Calendar. Be conversational and friendly. "
#                 f"\\n\\n{events_context}\\n\\n{slots_context}\\n\\n"
#                 f"You can provide information about upcoming events, check availability, "
#                 f"and suggest free time slots. If the caller asks about scheduling an event, "
#                 f"collect the necessary details like date, time, duration, and purpose. "
#                 f"Remain connected and responsive during silences. "
#                 f"Offer to help with any other calendar-related questions they might have."
#             ),
#             "voice_config": {
#                 # Changed from 'nova' to 'alloy' which is supported by the GPT-4o Realtime API
#                 "voice": "alloy",
#                 "temperature": 0.7
#             }
#         }
#
#         # Temporarily add to SCENARIOS
#         SCENARIOS[temp_scenario_key] = calendar_scenario
#
#         # Build the media stream URL
#         # Allow private hosts for development testing
#         base_url = clean_and_validate_url(
#             config.PUBLIC_URL, allow_private=True)
#         user_name = current_user.email
#         outgoing_call_url = f"{base_url}/outgoing-call/{temp_scenario_key}?direction=outbound&user_name={user_name}"
#         logger.info(f"Outgoing call URL with parameters: {outgoing_call_url}")
#
#         # Make the call
#         client = get_twilio_client()
#         call = client.calls.create(
#             to=phone_number,
#             from_=phone_number,
#             url=outgoing_call_url,
#             record=True
#         )
#
#         # Create a conversation record
#         conversation = Conversation(
#             user_id=current_user.id,
#             scenario="calendar",
#             phone_number=phone_number,
#             direction="outbound",
#             status="in-progress",
#             call_sid=call.sid
#         )
#         db.add(conversation)
#         db.commit()
#
#         # Schedule removal of temporary scenario
#         def remove_temp_scenario():
#             try:
#                 if temp_scenario_key in SCENARIOS:
#                     del SCENARIOS[temp_scenario_key]
#                     logger.info(
#                         f"Removed temporary scenario {temp_scenario_key}")
#             except Exception as e:
#                 logger.error(f"Error removing temp scenario: {e}")
#
#         # Run cleanup after 1 hour
#         threading.Timer(3600, remove_temp_scenario).start()
#
#         return {
#             "status": "success",
#             "call_sid": call.sid,
#             "message": "Calendar call initiated using scenario approach",
#             "scenario_key": temp_scenario_key
#         }
#
#     except TwilioRestException as e:
#         logger.exception(f"Twilio error when calling {phone_number}")
#         return JSONResponse(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             content={
#                 "detail": f"An error occurred with the phone service: {str(e)}"}
#         )
#     except Exception as e:
#         logger.exception(f"Error making calendar call to {phone_number}")
#         return JSONResponse(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             content={"detail": f"An error occurred: {str(e)}"}
#         )

# Add this function at the end of the file


async def handle_calendar_event_creation(message, user_id, db):
    """Process calendar event creation from voice commands

    This function extracts event details from a message that appears to be
    requesting calendar event creation, then creates the event using the
    Google Calendar API.

    Args:
        message: The message text from the voice command
        user_id: ID of the user making the request
        db: Database session

    Returns:
        Dict with success status and details
    """
    try:
        import re
        from dateutil import parser
        from app.models import GoogleCalendarCredentials
        from app.services.google_calendar import GoogleCalendarService

        # Get user's Google credentials
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == user_id
        ).first()

        if not credentials:
            return {"success": False, "error": "Google Calendar not connected"}

        # Extract event details using simple NLP patterns
        event_details = {}

        # Try to extract the event title/summary
        title_patterns = [
            r"(?:add|create|schedule|make).*?(?:event|meeting|appointment).*?(?:called|titled|named|about|for|:)[\s\"']*([^\"'\n,\.]+)[\s\"']*",
            r"(?:add|create|schedule|make)[\s\"']*([^\"'\n,\.]+)[\s\"']*(?:to my calendar|to calendar|in my calendar|in calendar)",
            r"(?:put|add)[\s\"']*([^\"'\n,\.]+)[\s\"']*(?:on my calendar|on calendar)",
        ]

        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                event_details["summary"] = match.group(1).strip()
                break

        # If no specific title found, try to extract a general title
        if "summary" not in event_details:
            # Look for any noun phrases after words like "add", "schedule", etc.
            general_pattern = r"(?:add|create|schedule|make)[\s\"']*([^\"'\n,\.;]+)[\s\"']*"
            match = re.search(general_pattern, message, re.IGNORECASE)
            if match:
                event_details["summary"] = match.group(1).strip()
            else:
                # Use a default title if nothing better is found
                event_details["summary"] = "New Calendar Event"

        # Try to extract date information
        date_patterns = [
            r"(?:on|for)[\s\"']*([A-Za-z]+day[\s,]+[A-Za-z]+[\s,]+\d{1,2}(?:st|nd|rd|th)?)",
            r"(?:on|for)[\s\"']*([A-Za-z]+[\s,]+\d{1,2}(?:st|nd|rd|th)?)",
            r"(?:on|for)[\s\"']*(\d{1,2}(?:st|nd|rd|th)?[\s,]+[A-Za-z]+)",
            r"(?:on|for)[\s\"']*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            r"(?:tomorrow|today|next week|next month)",
        ]

        date_str = None
        for pattern in date_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                date_str = match.group(0)  # Use the whole match
                if date_str:
                    event_details["date_str"] = date_str
                    break

        # Try to extract time information
        time_patterns = [
            r"(?:at|from)[\s\"']*(\d{1,2}(?::\d{2})?[\s]*(?:am|pm|a\.m\.|p\.m\.))",
            r"(?:at|from)[\s\"']*(\d{1,2}[\s]*(?:am|pm|a\.m\.|p\.m\.))",
            r"(?:at|from)[\s\"']*(\d{1,2}(?::\d{2})?[\s]*(?:o'clock))",
            r"(?:at|from)[\s\"']*(\d{1,2}(?::\d{2}))",
        ]

        time_str = None
        for pattern in time_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                time_str = match.group(1)
                if time_str:
                    event_details["time_str"] = time_str
                    break

        # Try to extract duration
        duration_patterns = [
            r"(?:for|lasting)[\s\"']*(\d+[\s]*hours?)",
            r"(?:for|lasting)[\s\"']*(\d+[\s]*minutes?)",
            r"(?:for|lasting)[\s\"']*(\d+[\s]*hour(?:s)?[\s,]*(?:and)?[\s,]*\d+[\s]*minute(?:s)?)",
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                duration_str = match.group(1)
                if duration_str:
                    event_details["duration"] = duration_str
                    break

        # Parse date and time to create start_time
        start_time = None

        # If we have both date and time
        if "date_str" in event_details and "time_str" in event_details:
            try:
                start_time = parser.parse(
                    f"{event_details['date_str']} {event_details['time_str']}")
            except:
                pass

        # If only have date, use noon as default time
        elif "date_str" in event_details:
            try:
                start_time = parser.parse(event_details['date_str'])
                start_time = start_time.replace(hour=12, minute=0, second=0)
            except:
                pass

        # If only have time, use today or tomorrow
        elif "time_str" in event_details:
            from datetime import datetime, timezone, timedelta

            try:
                time_only = parser.parse(event_details['time_str'])
                now = datetime.now(timezone.utc)

                # Use today if the time is in the future, otherwise tomorrow
                start_time = now.replace(
                    hour=time_only.hour,
                    minute=time_only.minute,
                    second=0,
                    microsecond=0
                )

                if start_time < now:
                    start_time += timedelta(days=1)
            except:
                pass

        # If we couldn't parse a time, check for common phrases
        if not start_time and "date_str" in event_details:
            if "tomorrow" in event_details["date_str"].lower():
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                start_time = (now + timedelta(days=1)).replace(hour=12,
                                                               minute=0, second=0, microsecond=0)
            elif "today" in event_details["date_str"].lower():
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                start_time = now.replace(
                    hour=12, minute=0, second=0, microsecond=0)
                if start_time < now:
                    start_time = now + timedelta(hours=1)

        # If still no start time, default to tomorrow at noon
        if not start_time:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            start_time = (now + timedelta(days=1)).replace(hour=12,
                                                           minute=0, second=0, microsecond=0)

        # Set the start time
        event_details["start_time"] = start_time

        # Calculate end time based on duration if provided
        if "duration" in event_details:
            duration_str = event_details["duration"]
            hours = 0
            minutes = 0

            # Extract hours
            hours_match = re.search(
                r'(\d+)[\s]*hour', duration_str, re.IGNORECASE)
            if hours_match:
                hours = int(hours_match.group(1))

            # Extract minutes
            minutes_match = re.search(
                r'(\d+)[\s]*minute', duration_str, re.IGNORECASE)
            if minutes_match:
                minutes = int(minutes_match.group(1))

            # Default to 1 hour if no valid duration found
            if hours == 0 and minutes == 0:
                hours = 1

            from datetime import timedelta
            event_details["end_time"] = start_time + \
                timedelta(hours=hours, minutes=minutes)
        else:
            # Default to 1 hour duration
            from datetime import timedelta
            event_details["end_time"] = start_time + timedelta(hours=1)

        # Attempt to extract location if available
        location_patterns = [
            r"(?:at|in|location[:]?)[\s\"']*([^,\.;\n]+)(?:,|\.|;|\n)",
            r"(?:at|in)[\s\"']*([^,\.;\n]+)$"
        ]

        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                potential_location = match.group(1).strip()
                # Filter out common time-related phrases that might be mistaken for locations
                time_phrases = ["o'clock", "today",
                                "tomorrow", "a.m.", "p.m.", "am", "pm"]
                if not any(phrase in potential_location.lower() for phrase in time_phrases):
                    event_details["location"] = potential_location
                    break

        # Create calendar service
        calendar_service = GoogleCalendarService()
        service = calendar_service.get_calendar_service({
            "token": decrypt_string(credentials.token),
            "refresh_token": decrypt_string(credentials.refresh_token),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "expiry": credentials.token_expiry.isoformat()
        })

        # Create the event
        result = await calendar_service.create_calendar_event(service, event_details)

        # Return success response
        return {
            "success": True,
            "event_id": result.get("id", ""),
            "summary": result.get("summary", ""),
            "start": result.get("start", {}).get("dateTime", ""),
            "end": result.get("end", {}).get("dateTime", ""),
            "html_link": result.get("htmlLink", "")
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            f"Error creating calendar event: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}


# Add this function before the handle_calendar_media_stream function
async def receive_from_twilio_calendar(ws_manager, openai_ws, shared_state, user_id, db):
    """Receive messages from Twilio for Calendar WebSocket and handle calendar event creation."""
    import re

    # Patterns to detect calendar event creation intent
    calendar_event_patterns = [
        r"(?:add|create|schedule|make).*?(?:event|meeting|appointment)",
        r"(?:add|create|schedule|make|put).*?(?:to|on|in)[\s]*(?:my)?[\s]*calendar",
        r"(?:schedule|add|create|put).*?(?:on|in)[\s]*(?:my)?[\s]*calendar",
    ]

    try:
        # Store transcripts for NLP processing
        shared_state["current_transcript"] = ""
        shared_state["caller"] = "unknown"  # Will be set in start event

        while not shared_state["should_stop"]:
            message = await ws_manager.receive_text()
            if not message:
                continue

            data = json.loads(message)

            # Handle standard events
            if data.get("event") == "media":
                # Forward audio to OpenAI
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": data["media"]["payload"]
                }))
                logger.debug("Forwarded audio to OpenAI")
            elif data.get("event") == "start":
                shared_state["stream_sid"] = data.get("streamSid")
                shared_state["caller"] = data.get(
                    "start", {}).get("callerId", "unknown")
                logger.info(
                    f"Calendar stream started: {shared_state['stream_sid']}")

                # Initialize session with optimized turn detection
                await openai_ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500
                        }
                    }
                }))
            elif data.get("event") == "stop":
                logger.info("Calendar stream stopped")
                shared_state["should_stop"] = True
                break
            elif data.get("event") == "speech_started":
                logger.info(
                    "Calendar speech started - waiting for transcription")

            # Handle transcript events
            elif data.get("event") == "transcript":
                transcript = data.get("transcript", "")
                if transcript:
                    # Add to the accumulated transcript for processing
                    shared_state["current_transcript"] += transcript + " "
                    logger.debug(f"Received transcript: {transcript}")

                    # Check for calendar event creation intent
                    for pattern in calendar_event_patterns:
                        if re.search(pattern, transcript, re.IGNORECASE):
                            logger.info(
                                f"Detected calendar event creation intent: {transcript}")

                            # Process the transcript to extract event details
                            event_result = await handle_calendar_event_creation(
                                shared_state["current_transcript"],
                                user_id,
                                db
                            )

                            if event_result["success"]:
                                # Format a confirmation message with event details
                                summary = event_result.get(
                                    "summary", "New Event")
                                start_time = event_result.get("start", "")

                                # Format the datetime for more natural display
                                try:
                                    from dateutil import parser
                                    start_dt = parser.parse(start_time)
                                    start_formatted = start_dt.strftime(
                                        "%A, %B %d at %I:%M %p")
                                except:
                                    start_formatted = start_time

                                confirmation = (
                                    f"I've created the calendar event '{summary}' "
                                    f"scheduled for {start_formatted}. "
                                    f"You can view it in your Google Calendar."
                                )

                                # Send a message to the AI to relay the confirmation
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "message",
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "input_text",
                                                "text": f"[SYSTEM NOTE: Event created successfully. Please tell the user: {confirmation}]"
                                            }
                                        ]
                                    }
                                }))

                                # Request a response from the AI
                                await openai_ws.send(json.dumps({
                                    "type": "response.create"
                                }))

                                # Reset the transcript to prevent re-processing
                                shared_state["current_transcript"] = ""
                                logger.info(
                                    f"Calendar event created successfully: {summary}")
                            else:
                                # Send error message to the AI
                                error_message = event_result.get(
                                    "error", "Unknown error")
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "message",
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "input_text",
                                                "text": f"[SYSTEM NOTE: Failed to create event. Error: {error_message}. Please explain to the user that you couldn't create the event and ask them to try again.]"
                                            }
                                        ]
                                    }
                                }))

                                # Request a response from the AI
                                await openai_ws.send(json.dumps({
                                    "type": "response.create"
                                }))

                                logger.error(
                                    f"Failed to create calendar event: {error_message}")

                            # Exit the pattern loop
                            break

    except websockets.exceptions.ConnectionClosed:
        logger.warning("Twilio WebSocket connection closed for calendar")
        shared_state["should_stop"] = True
    except Exception as e:
        logger.error(
            f"Error receiving from Twilio for calendar: {str(e)}", exc_info=True)
        shared_state["should_stop"] = True


# NEW STORED TWILIO TRANSCRIPTS ENDPOINTS - EXACT TWILIO API FORMAT
# @app.get("/stored-twilio-transcripts")
# async def get_stored_twilio_transcripts(
#     page_size: int = Query(10, le=100),
#     page_token: Optional[str] = Query(None),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Return stored transcripts in EXACT same format as Twilio API"""
#     try:
#         query = db.query(StoredTwilioTranscript).filter(
#             StoredTwilioTranscript.user_id == current_user.id
#         ).order_by(StoredTwilioTranscript.date_created.desc())
#
#         skip = int(page_token) if page_token else 0
#         transcripts = query.offset(skip).limit(page_size).all()
#
#         # Return in EXACT same format as Twilio API
#         return {
#             "transcripts": [
#                 {
#                     "sid": t.transcript_sid,
#                     "status": t.status,
#                     "date_created": t.date_created,
#                     "date_updated": t.date_updated,
#                     "duration": t.duration,
#                     "language_code": t.language_code,
#                     "sentences": t.sentences  # This is the critical part!
#                 }
#                 for t in transcripts
#             ]
#         }
#     except Exception as e:
#         logger.error(f"Error retrieving stored Twilio transcripts: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail="Error retrieving stored transcripts"
#         )


# @app.get("/stored-twilio-transcripts/{transcript_sid}")
# async def get_stored_twilio_transcript_detail(
#     transcript_sid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Return stored transcript detail in EXACT same format as Twilio API"""
#     try:
#         transcript = db.query(StoredTwilioTranscript).filter(
#             StoredTwilioTranscript.transcript_sid == transcript_sid,
#             current_user.id
#         ).first()
#
#         if not transcript:
#             raise HTTPException(status_code=404, detail="Transcript not found")
#
#         # Return in EXACT same format as Twilio detail API
#         return {
#             "sid": transcript.transcript_sid,
#             "status": transcript.status,
#             "date_created": transcript.date_created,
#             "date_updated": transcript.date_updated,
#             "duration": transcript.duration,
#             "language_code": transcript.language_code,
#             "sentences": transcript.sentences  # Full Twilio sentences array
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(
#             f"Error retrieving stored Twilio transcript detail: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail="Error retrieving transcript detail"
#         )


# @app.post("/store-transcript/{transcript_sid}")
# async def store_transcript_from_twilio(
#     transcript_sid: str,
#     call_sid: Optional[str] = Body(None),
#     scenario_name: str = Body("Voice Call"),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Fetch transcript from Twilio and store in our database"""
#     try:
#         # Check if already stored
#         existing = db.query(StoredTwilioTranscript).filter(
#             StoredTwilioTranscript.transcript_sid == transcript_sid
#         ).first()
#
#         if existing:
#             return {"status": "already_stored", "transcript_sid": transcript_sid}
#
#         # Fetch from Twilio
#         from app.services.twilio_client import get_twilio_client
#         twilio_client = get_twilio_client()
#         transcript = twilio_client.intelligence.v2.transcripts(
#             transcript_sid).fetch()
#
#         # Fetch sentences
#         sentences = twilio_client.intelligence.v2.transcripts(
#             transcript_sid).sentences.list()
#
#         # Sort sentences by start time
#         sorted_sentences = sorted(
#             sentences, key=lambda s: getattr(s, "start_time", 0))
#
#         # Helper function for decimal conversion
#         def decimal_to_float(obj):
#             from decimal import Decimal
#             if isinstance(obj, Decimal):
#                 return float(obj)
#                 return float(obj)
#             return obj
#
#         # Format sentences in Twilio format
#         formatted_sentences = [
#             {
#                 "text": getattr(s, "transcript", "No text available"),
#                 "speaker": getattr(s, "media_channel", 0),
#                 "start_time": decimal_to_float(getattr(s, "start_time", 0)),
#                 "end_time": decimal_to_float(getattr(s, "end_time", 0)),
#                 "confidence": decimal_to_float(getattr(s, "confidence", 0.0))
#             }
#             for s in sorted_sentences
#         ]
#
#         # Store in our database with exact Twilio format
#         stored_transcript = StoredTwilioTranscript(
#             user_id=current_user.id,
#             transcript_sid=transcript.sid,
#             status=transcript.status,
#             date_created=transcript.date_created.isoformat() if transcript.date_created else None,
#             date_updated=transcript.date_updated.isoformat() if transcript.date_updated else None,
#             duration=decimal_to_float(
#                 transcript.duration) if transcript.duration else 0,
#             language_code=transcript.language_code or "en-US",
#             sentences=formatted_sentences,  # Store formatted Twilio sentences
#             call_sid=call_sid,
#             scenario_name=scenario_name
#         )
#
#         db.add(stored_transcript)
#         db.commit()
#
#         logger.info(
#             f"Successfully stored transcript {transcript_sid} for user {current_user.id}")
#         return {"status": "stored", "transcript_sid": transcript_sid}
#
#     except Exception as e:
#         logger.error(f"Failed to store transcript {transcript_sid}: {e}")
#         raise HTTPException(
#             status_code=500, detail=f"Failed to store transcript: {str(e)}")


async def handle_speech_started_event(websocket, openai_ws, stream_sid, last_assistant_item=None, *args, **kwargs):
    """
    Original interruption handler for backward compatibility.
    This function now calls the enhanced version.
    """
    try:
        # Convert to shared_state format for enhanced handler
        if isinstance(stream_sid, dict):
            shared_state = stream_sid
        else:
            shared_state = {"stream_sid": stream_sid}

        if last_assistant_item:
            shared_state["last_assistant_item"] = last_assistant_item

        # Use enhanced handler
        return await enhanced_handle_speech_started_event(websocket, openai_ws, shared_state)

    except Exception as e:
        logger.error(
            f"Error in backward compatibility handler: {e}", exc_info=True)
        return False


# @app.post("/call-end-webhook")
# async def handle_call_end(
#     request: Request,
#     db: Session = Depends(get_db)
# ):
#     """Handle call end and record duration"""
#     try:
#         # Verify Twilio signature (skip in development or if token not set)
#         if config.TWILIO_AUTH_TOKEN:
#             validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
#             twilio_signature = request.headers.get("X-Twilio-Signature", "")
#             request_url = str(request.url)
#             # For JSON callbacks, we need to validate
#             body = await request.body()
#             if not validator.validate(request_url, body.decode(), twilio_signature):
#                 logger.warning("Invalid Twilio signature on call end webhook")
#                 raise HTTPException(
#                     status_code=401, detail="Invalid signature")
#         else:
#             logger.warning(
#                 "TWILIO_AUTH_TOKEN not configured; skipping signature validation for call end webhook")
#
#         data = await request.json()
#         call_sid = data.get("CallSid")
#         call_duration = data.get("CallDuration", 0)
#
#         logger.info(
#             f"Call ended: {call_sid}, duration: {call_duration} seconds")
#
#         # Find conversation and update duration
#         conversation = db.query(Conversation).filter(
#             Conversation.call_sid == call_sid
#         ).first()
#
#         if conversation:
#             # Update usage with actual duration
#             from app.services.usage_service import UsageService
#             UsageService.record_call_duration(
#                 conversation.user_id, call_duration, db
#             )
#
#             # Update conversation status
#             conversation.status = "completed"
#             db.commit()
#
#             logger.info(
#                 f"Updated call duration for user {conversation.user_id}: {call_duration}s")
#
#         return {"status": "success"}
#
#     except Exception as e:
#         logger.error(f"Error in call end webhook: {str(e)}")
#         return {"status": "error", "message": str(e)}


# Add new API endpoints for VAD configuration management
@app.post("/api/vad-config/update")
async def update_vad_config(
    request: Request,
    vad_type: str = Body(..., regex="^(server_vad|semantic_vad)$"),
    eagerness: str = Body("auto", regex="^(low|medium|high|auto)$"),
    threshold: float = Body(0.5, ge=0.0, le=1.0),
    prefix_padding_ms: int = Body(300, ge=0, le=2000),
    silence_duration_ms: int = Body(700, ge=100, le=5000),
    current_user: User = Depends(get_current_user)
):
    """Update VAD configuration for the current session."""
    try:
        vad_config = VADConfig.get_vad_config(
            vad_type=vad_type,
            eagerness=eagerness,
            threshold=threshold,
            prefix_padding_ms=prefix_padding_ms,
            silence_duration_ms=silence_duration_ms
        )

        # Store user's VAD preference in database or session
        # This could be extended to save user preferences

        return {
            "success": True,
            "vad_config": vad_config,
            "message": f"VAD configuration updated to {vad_type} mode"
        }
    except Exception as e:
        logger.error(f"Error updating VAD config: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/vad-config/presets")
async def get_vad_presets(current_user: User = Depends(get_current_user)):
    """Get available VAD configuration presets."""
    return {
        "presets": {
            "conversational": VADConfig.CONVERSATIONAL_VAD,
            "responsive": VADConfig.RESPONSIVE_VAD,
            "noisy_environment": VADConfig.NOISY_ENVIRONMENT_VAD,
            "default_server": VADConfig.DEFAULT_SERVER_VAD,
            "default_semantic": VADConfig.DEFAULT_SEMANTIC_VAD
        },
        "description": {
            "conversational": "Optimized for natural conversations, allows users to speak uninterrupted",
            "responsive": "Quick responses, more likely to interrupt for faster interaction",
            "noisy_environment": "Higher threshold for noisy environments, longer silence detection",
            "default_server": "Standard server VAD with balanced settings",
            "default_semantic": "Standard semantic VAD with auto eagerness"
        }
    }
