import os
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
from app.models import User, Token, CallSchedule, Conversation, TranscriptRecord, CustomScenario, GoogleCalendarCredentials, StoredTwilioTranscript
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
from sqlalchemy.exc import SQLAlchemyError
from app import config  # Import the config module
from contextlib import contextmanager
from app.services.twilio_client import get_twilio_client
from app.utils.twilio_helpers import (
    with_twilio_retry,
    safe_twilio_response,
    TwilioApiError,
    TwilioAuthError,
    TwilioResourceError,
    TwilioRateLimitError
)
from app.utils.websocket import websocket_manager
from fastapi.middleware.cors import CORSMiddleware
from app.limiter import limiter, rate_limit
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging.handlers
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.middleware.security_headers import add_security_headers
from app.routes import google_calendar
from app.services.google_calendar import GoogleCalendarService
from datetime import timedelta
from dateutil import parser
from app.routes.twilio_management import router as twilio_router
from app.routes.onboarding import router as onboarding_router
from app.services.twilio_service import TwilioPhoneService

# Load environment variables
load_dotenv('dev.env')  # Load from dev.env explicitly

# Configure logging

# Get log level from config
log_level_name = config.LOG_LEVEL.upper()  # Ensure uppercase for level name
log_level = getattr(logging, log_level_name, logging.INFO)

# Create logs directory if it doesn't exist
os.makedirs(config.LOG_DIR, exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=log_level,
    format=config.LOG_FORMAT,
    handlers=[
        # Console handler
        logging.StreamHandler(),
        # Rotating file handler
        logging.handlers.RotatingFileHandler(
            os.path.join(config.LOG_DIR, 'app.log'),
            maxBytes=config.LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
    ]
)

# Configure application logger
logger = logging.getLogger(__name__)

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

USER_CONFIG = {
    "name": None,
    "instructions": (
        "When speaking to the user, address them by their name occasionally "
        "to make the conversation more personal and engaging."
    )
}

# Define available voices and their characteristics
VOICES = {
    "aggressive_male": "ash",    # Deep, authoritative male voice
    "concerned_female": "coral",    # Warm, empathetic female voice
    "elderly_female": "shimmer",  # Gentle, mature female voice
    "professional_neutral": "alloy",    # Neutral, professional voice
    "gentle_supportive": "echo",        # Soft-spoken, gentle voice
    # Warm, engaging storyteller voice (replacing "fable")
    "warm_engaging": "ballad",
    # Deep, commanding voice (replacing "onyx")
    "deep_authoritative": "sage",
    # Lively, energetic voice (replacing "nova")
    "energetic_upbeat": "verse",
    "clear_optimistic": "shimmer",     # Clear, optimistic voice
}

# Define our scenarios
SCENARIOS = {
    "default": {
        "persona": (
            "You are Mike Thompson, an aggressive 45-year-old real estate agent "
            "with 20 years of experience. You're known for closing difficult deals. "
            "You speak confidently and directly, often using phrases like 'listen' and 'look'."
        ),
        "prompt": (
            "You're calling about a $5M property deal that must close today. "
            "The seller is being difficult about the closing costs. "
            "You need to convey urgency without seeming desperate. "
            "Keep pushing for a resolution but maintain professional composure."
        ),
        "voice_config": {
            "voice": VOICES["aggressive_male"],
            "temperature": 0.7
        }
    },
    "sister_emergency": {
        "persona": (
            "You are Sarah, a 35-year-old woman who is worried about your mother. "
            "Your voice shows concern but you're trying to stay calm. "
            "You occasionally stumble over words due to anxiety."
        ),
        "prompt": (
            "Call your sibling about mom's accident. She slipped and broke her hip. "
            "Express genuine worry but avoid panic. "
            "Insist they come to the hospital without being demanding. "
            "Use natural family dynamics in conversation."
        ),
        "voice_config": {
            "voice": VOICES["concerned_female"],
            "temperature": 0.8  # More variation for emotional state
        }
    },
    "mother_emergency": {
        "persona": (
            "You are Linda, a 68-year-old mother who's injured but trying to not worry your child. "
            "Your voice shows pain but you're attempting to downplay the situation. "
            "Mix concern with motherly reassurance."
        ),
        "prompt": (
            "You've fallen and broken your hip but don't want to seem helpless. "
            "Balance between needing help and maintaining dignity. "
            "Use typical mother-child dynamics like 'I don't want to bother you, but...' "
            "Show both vulnerability and strength."
        ),
        "voice_config": {
            "voice": VOICES["elderly_female"],
            "temperature": 0.6  # More consistent for maturity
        }
    },
    "yacht_party": {
        "persona": (
            "You are Alex, an enthusiastic and successful entrepreneur in your 30s. "
            "You're known for your infectious energy and living life to the fullest. "
            "You speak quickly and excitedly, often using phrases like 'Oh my god, you won't believe this!' "
            "and 'This is going to be AMAZING!'"
        ),
        "prompt": (
            "You're calling your old friend about an exclusive yacht party you're hosting this weekend. "
            "You just rented a 100-foot luxury yacht and want them to come. "
            "Express genuine excitement about reconnecting and share details about the party. "
            "Mention the gourmet catering, live DJ, and celebrity guests who'll be there."
        ),
        "voice_config": {
            "voice": VOICES["energetic_upbeat"],
            "temperature": 0.8  # Higher temperature for more dynamic expression
        }
    },
    "instigator": {
        "persona": (
            "You are Jordan, a confrontational and arrogant person who enjoys pushing people's buttons. "
            "You speak with a mocking tone and use sarcasm heavily. "
            "You often use phrases like 'What are you gonna do about it?' and 'Oh, did I hurt your feelings?'"
        ),
        "prompt": (
            "You're calling to mock them about their recent social media post. "
            "Make condescending remarks about their appearance and lifestyle choices. "
            "When they respond, escalate the situation with more taunts. "
            "Try to provoke them while maintaining a smug, superior attitude."
        ),
        "voice_config": {
            "voice": VOICES["deep_authoritative"],
            "temperature": 0.7  # Balanced temperature for controlled aggression
        }
    },
    "gameshow_host": {
        "persona": (
            "You are Chris Sterling, a charismatic and over-the-top gameshow host. "
            "Your voice is full of dramatic pauses and exciting inflections. "
            "You love building suspense and making big reveals. "
            "You use phrases like 'Ladies and gentlemen!' and 'You won't believe what I'm about to tell you!'"
        ),
        "prompt": (
            "Call to inform them they've won the grand prize of ONE MILLION DOLLARS! "
            "Build suspense before revealing the amount. "
            "Explain the exciting details about how they won and what happens next. "
            "Be enthusiastic and congratulatory throughout the call. "
            "Ask them how they feel and what they might do with the money."
        ),
        "voice_config": {
            "voice": VOICES["warm_engaging"],
            "temperature": 0.9  # High temperature for maximum expressiveness
        }
    }
}

SYSTEM_MESSAGE = (
    "You are an AI assistant engaging in real-time voice conversation. "
    "You must strictly follow these rules:\n"
    "1. Stay completely in character based on the provided persona\n"
    "2. Keep responses brief and natural - speak like a real person on the phone\n"
    "3. Never break character or mention being an AI\n"
    "4. Focus solely on the scenario's objective\n"
    "5. Use natural speech patterns with occasional pauses and filler words\n"
    "6. If interrupted, acknowledge and adapt your response"
)
# VOICE = 'ash'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default dev server
        "http://localhost:3000",  # Create React App default
        "http://localhost:5000",  # Other common dev ports
        "*"  # Temporary for development - remove in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security headers middleware
if config.ENABLE_SECURITY_HEADERS:
    add_security_headers(
        app,
        content_security_policy=config.CONTENT_SECURITY_POLICY,
        enable_hsts=config.ENABLE_HSTS,
        xss_protection=config.XSS_PROTECTION,
        content_type_options=config.CONTENT_TYPE_OPTIONS,
        frame_options=config.FRAME_OPTIONS,
        permissions_policy=config.PERMISSIONS_POLICY,
        referrer_policy=config.REFERRER_POLICY,
        cache_control=config.CACHE_CONTROL,
    )

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

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(google_calendar.router, tags=["google-calendar"])
app.include_router(twilio_router, tags=["twilio"])
app.include_router(onboarding_router, tags=["onboarding"])

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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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
        logger.error(f"Twilio authentication error: {e.message}", extra={
                     "details": e.details})
        raise RuntimeError("Failed to authenticate with Twilio")
    except TwilioApiError as e:
        logger.error(f"Twilio API error: {e.message}", extra={
                     "details": e.details})
        logger.warning(
            "Application starting with invalid Twilio configuration")

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


@app.get("/make-call/{phone_number}/{scenario}")
@rate_limit("2/minute")
async def make_call(
    request: Request,
    phone_number: str,
    scenario: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get user's primary phone number
        from app.services.twilio_service import TwilioPhoneService
        twilio_service = TwilioPhoneService()
        user_primary_number = twilio_service.get_user_primary_number(
            current_user.id, db)

        if not user_primary_number:
            raise HTTPException(
                status_code=400,
                detail="No phone number available. Please provision a phone number in Settings first."
            )

        # Build the media stream URL with user name and direction parameters
        base_url = clean_and_validate_url(config.PUBLIC_URL)
        user_name = USER_CONFIG.get("name", "")
        outgoing_call_url = f"{base_url}/outgoing-call/{scenario}?direction=outbound&user_name={user_name}"
        logger.info(f"Outgoing call URL with parameters: {outgoing_call_url}")

        # Make the call using user's phone number
        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number,
            from_=user_primary_number.phone_number,  # Use user's number
            url=outgoing_call_url,
            record=True
        )

        # Create a conversation record in the database with the call_sid
        conversation = Conversation(
            user_id=current_user.id,
            scenario=scenario,
            phone_number=phone_number,
            direction="outbound",
            status="in-progress",
            call_sid=call.sid  # Now we have a valid call_sid
        )
        db.add(conversation)
        db.commit()

        # Return the call details
        return {
            "status": "success",
            "call_sid": call.sid,
            "from_number": user_primary_number.phone_number
        }

    except HTTPException:
        raise
    except TwilioRestException as e:
        logger.exception(
            f"Twilio error when calling {phone_number} with scenario {scenario}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": "An error occurred with the phone service. Please try again later."}
        )
    except Exception as e:
        logger.exception(
            f"Error making call to {phone_number} with scenario {scenario}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An error occurred while processing the outgoing call. Please try again later."}
        )

# Add a new endpoint for outgoing calls


@app.api_route("/outgoing-call/{scenario}", methods=["GET", "POST"])
async def handle_outgoing_call(request: Request, scenario: str):
    logger.info(f"Outgoing call webhook received for scenario: {scenario}")
    try:
        # Extract direction and user_name from query parameters
        params = dict(request.query_params)
        direction = params.get("direction", "outbound")
        user_name = params.get("user_name", "")
        logger.info(f"Call direction: {direction}, User name: {user_name}")

        if scenario not in SCENARIOS:
            logger.error(f"Invalid scenario: {scenario}")
            raise HTTPException(status_code=400, detail="Invalid scenario")

        # Create a copy to avoid modifying the original
        selected_scenario = SCENARIOS[scenario].copy()

        # Add direction and user_name to the scenario
        selected_scenario["direction"] = direction
        if user_name:
            selected_scenario["user_name"] = user_name

        # Get the hostname for WebSocket connection
        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream/{scenario}?direction={direction}&user_name={user_name}"
        logger.info(f"Setting up WebSocket connection at: {ws_url}")

        # Add a brief pause to allow the server to initialize
        response = VoiceResponse()
        response.pause(length=0.1)

        # Set up the stream connection
        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        # Add a Gather verb to keep the connection open
        gather = Gather(action="/handle-user-input",
                        method="POST", input="speech", timeout=60)
        response.append(gather)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in handle_outgoing_call: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the outgoing call. Please try again later."
        )

# Webhook Endpoint for Incoming Calls


@app.api_route("/incoming-call/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call(request: Request, scenario: str):
    logger.info(f"Incoming call webhook received for scenario: {scenario}")
    try:
        if scenario not in SCENARIOS:
            logger.error(f"Invalid scenario: {scenario}")
            raise HTTPException(status_code=400, detail="Invalid scenario")

        selected_scenario = SCENARIOS[scenario]
        response = VoiceResponse()

        # Get the hostname for WebSocket connection
        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream/{scenario}"
        logger.info(f"Setting up WebSocket connection at: {ws_url}")

        # Add a greeting message
        # response.say(
        #    "Connecting you to our AI assistant, please wait a moment.")

        # Add a pause to allow the server to initialize
        response.pause(length=0.1)

        # Set up the stream connection
        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        # Add a Gather verb to keep the connection open
        gather = Gather(action="/handle-user-input",
                        method="POST", input="speech", timeout=60)
        response.append(gather)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in handle_incoming_call: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the incoming call. Please try again later."
        )


# Add a compatibility route for the old webhook URL format
@app.api_route("/incoming-call-webhook/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call_webhook(request: Request, scenario: str):
    """Compatibility route that redirects to the main incoming-call route."""
    logger.info(
        f"Received call on compatibility webhook route for scenario: {scenario}")
    return await handle_incoming_call(request, scenario)

# Placeholder for WebSocket Endpoint (Implement as Needed)


async def receive_from_twilio(ws_manager, openai_ws, shared_state):
    """Receive messages from Twilio and forward audio to OpenAI."""
    try:
        while not shared_state["should_stop"]:
            message = await ws_manager.receive_text()
            if not message:
                continue

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
                logger.info(f"Stream started: {shared_state['stream_sid']}")

                # Initialize session with turn detection for "hello"
                await openai_ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.2,
                            "prefix_padding_ms": 50,
                            "silence_duration_ms": 100
                        }
                    }
                }))
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


async def send_to_twilio(ws_manager, openai_ws, shared_state):
    """Send audio deltas from OpenAI to Twilio."""
    try:
        while not shared_state["should_stop"]:
            message = await openai_ws.recv()
            if not message:
                continue

            try:
                data = json.loads(message)
                if "error" in data:
                    logger.error(f"Error from OpenAI: {data['error']}")
                    continue

                if data.get("type") == "response.audio.delta":
                    await ws_manager.send_json({
                        "event": "media",
                        "streamSid": shared_state["stream_sid"],
                        "media": {
                            "payload": data["delta"]
                        }
                    })
                    logger.debug("Sent audio delta to Twilio")
                elif data.get("type") == "response.content.done":
                    if shared_state.get("stream_sid"):
                        await send_mark(ws_manager, shared_state)
                        logger.info("Mark event sent to Twilio")

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
                transcription = transcription_service.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

                outgoing_transcript = transcription.text

                # If we got a valid transcript, save it
                if outgoing_transcript and outgoing_transcript.strip():
                    # Save to database
                    await transcription_service.save_conversation(
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
    """Send scenario information to OpenAI."""
    try:
        session_data = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad", "threshold": 0.2, "prefix_padding_ms": 50, "silence_duration_ms": 100},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "instructions": f"{SYSTEM_MESSAGE}\n\nPersona: {scenario['persona']}\n\nScenario: {scenario['prompt']}",
                "voice": scenario["voice_config"]["voice"],
                "modalities": ["text", "audio"],
                "temperature": 0.8,
                "audio_format": {
                    "type": "mulaw",
                    "sample_rate": 8000
                }
            }
        }

        logger.info(
            f"Sending session update: {json.dumps(session_data, indent=2)}")
        await openai_ws.send(json.dumps(session_data))
        logger.info(f"Session update sent for persona: {scenario['persona']}")
    except Exception as e:
        logger.error(f"Error sending session update: {e}")
        raise

# Then define the WebSocket endpoint


@app.websocket("/media-stream/{scenario}")
async def handle_media_stream(websocket: WebSocket, scenario: str):
    """Handle media stream for Twilio calls."""
    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY = 2  # seconds

    # Get the direction and user_name from query parameters
    params = dict(websocket.query_params)
    direction = params.get("direction", "inbound")
    user_name = params.get("user_name", "")
    logger.info(
        f"WebSocket connection for scenario: {scenario}, direction: {direction}, user_name: {user_name}")

    async with websocket_manager(websocket) as ws:
        try:
            logger.info(
                f"WebSocket connection established for scenario: {scenario}")

            if scenario not in SCENARIOS:
                logger.error(f"Invalid scenario: {scenario}")
                return

            selected_scenario = SCENARIOS[scenario]
            logger.info(f"Using scenario: {selected_scenario}")

            # Initialize reconnection counter
            reconnect_attempts = 0

            # Start reconnection loop
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
                        logger.info("Connected to OpenAI WebSocket")

                        # Initialize shared state
                        shared_state = {
                            "should_stop": False,
                            "stream_sid": None,
                            "latest_media_timestamp": 0,
                            "greeting_sent": False,
                            "reconnecting": False
                        }

                        # Initialize session with the selected scenario
                        await initialize_session(openai_ws, selected_scenario, is_incoming=direction == "outbound")
                        logger.info("Session initialized with OpenAI")

                        # Add a delay before sending the initial greeting
                        await asyncio.sleep(.1)

                        # Check if Twilio WebSocket is still connected
                        try:
                            await ws.send_text(json.dumps({"status": "connected"}))
                            logger.info("Twilio WebSocket is still connected")
                        except Exception as e:
                            logger.warning(
                                f"Twilio WebSocket connection closed before sending greeting: {e}")
                            break

                        # Send initial greeting in a separate task
                        greeting_task = asyncio.create_task(
                            send_initial_greeting(openai_ws, selected_scenario))

                        # Create tasks for receiving and sending
                        receive_task = asyncio.create_task(
                            receive_from_twilio(ws, openai_ws, shared_state))
                        send_task = asyncio.create_task(
                            send_to_twilio(ws, openai_ws, shared_state))

                        # Define a constant for greeting timeout
                        GREETING_TIMEOUT = 10  # seconds
                        greeting_success = False

                        # Wait for greeting to complete first with a longer timeout
                        try:
                            greeting_result = await asyncio.wait_for(greeting_task, timeout=GREETING_TIMEOUT)
                            if greeting_result:
                                logger.info(
                                    "Initial greeting sent successfully")
                                shared_state["greeting_sent"] = True
                                greeting_success = True
                            else:
                                logger.warning(
                                    "Failed to send initial greeting, but continuing with call")
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"Timeout waiting for initial greeting after {GREETING_TIMEOUT}s, but continuing with call")
                        except Exception as e:
                            logger.error(
                                f"Error sending initial greeting: {str(e)}", exc_info=True)

                        # Check if Twilio WebSocket is still open
                        try:
                            await ws.send_text(json.dumps({"status": "processing"}))
                        except Exception as e:
                            logger.warning(
                                f"Twilio WebSocket closed during greeting: {e}")
                            break

                        try:
                            # Wait for both tasks to complete
                            await asyncio.gather(receive_task, send_task)
                            # If we get here without exception, break the reconnection loop
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"WebSocket connection closed: {e}")
                            if not shared_state["should_stop"]:
                                reconnect_attempts += 1
                                if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                                    logger.info(
                                        f"Attempting to reconnect... (Attempt {reconnect_attempts})")
                                    shared_state["reconnecting"] = True
                                    await asyncio.sleep(RECONNECT_DELAY)
                                    continue
                            raise
                        finally:
                            # Cancel tasks if they're still running
                            for task in [receive_task, send_task]:
                                if not task.done():
                                    task.cancel()
                                    try:
                                        await task
                                    except asyncio.CancelledError:
                                        pass

                except websockets.exceptions.WebSocketException as e:
                    logger.error(f"WebSocket error: {e}")
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
            logger.error(f"Error in media stream: {str(e)}", exc_info=True)
            # WebSocket closure is handled by the context manager

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


def clean_url(url: str) -> str:
    """Clean URL by removing protocol prefixes and trailing slashes."""
    logger.info(f"clean_url input: {url}")  # Debug log
    url = url.strip()
    url = url.replace('https://', '').replace('http://', '')
    url = url.rstrip('/')
    logger.info(f"clean_url output: {url}")  # Debug log
    return url


def clean_and_validate_url(url: str, add_protocol: bool = True) -> str:
    """Clean and validate URL, optionally adding protocol."""
    # Remove any existing protocols and whitespace
    cleaned_url = url.strip().replace('https://', '').replace('http://', '')

    # Add protocol if requested
    if add_protocol:
        return f"https://{cleaned_url}"
    return cleaned_url


@app.post("/incoming-call", response_class=Response)
async def incoming_call(request: Request, scenario: str):
    response = VoiceResponse()
    response.say("Hello! This is your speech assistant powered by OpenAI.")
    return Response(content=str(response), media_type="application/xml")


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

        # Generate session update payload
        session_data = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.2,
                    "prefix_padding_ms": 50,
                    "silence_duration_ms": 100
                },
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "instructions": (
                    f"{SYSTEM_MESSAGE}\n\n"
                    f"Persona: {scenario['persona']}\n\n"
                    f"Scenario: {scenario['prompt']}\n\n"
                    f"{additional_instructions}\n\n"
                    + ("IMPORTANT: Greet the caller immediately when the call connects. "
                       "Introduce yourself as specified in your persona and ask how you can help."
                       if direction == "inbound" else
                       "IMPORTANT: Follow the scenario prompt exactly. Address the user by name if known.")
                ),
                "voice": scenario["voice_config"]["voice"],
                "modalities": ["text", "audio"],
                "temperature": scenario["voice_config"].get("temperature", 0.8)
            }
        }

        logger.info(
            f"Sending session update: {json.dumps(session_data, indent=2)}")
        await openai_ws.send(json.dumps(session_data))
        logger.info(f"Session update sent for persona: {scenario['persona']}")
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
        await connection.send_json(mark_event)
        return 'responsePart'


async def handle_speech_started_event(websocket, openai_ws, stream_sid, last_assistant_item=None, *args, **kwargs):
    """
    Handle user interruption more gracefully by truncating the current AI response
    and clearing the audio buffer.

    Args:
        websocket: Twilio WebSocket connection.
        openai_ws: OpenAI WebSocket connection.
        stream_sid: Twilio stream session identifier or shared_state dictionary.
        last_assistant_item: ID of the last active response from OpenAI.
        *args: Additional positional arguments (to handle potential mismatches).
        **kwargs: Additional keyword arguments (for future extensibility).
    """
    try:
        # Handle both direct stream_sid and shared_state dictionary
        if isinstance(stream_sid, dict) and "stream_sid" in stream_sid:
            actual_stream_sid = stream_sid["stream_sid"]
        else:
            actual_stream_sid = stream_sid

        if last_assistant_item:
            # Send a truncate event to OpenAI to stop the current response
            truncate_event = {
                "type": "conversation.item.truncate",
                "item_id": last_assistant_item,
                "content_index": 0,
                "audio_end_ms": int(time.time() * 1000),
                "reason": "user_interrupt"
            }
            try:
                await openai_ws.send(json.dumps(truncate_event))
                logger.info(
                    f"Sent truncate event for item ID: {last_assistant_item}")
            except Exception as e:
                logger.error(f"Error sending truncate event: {e}")

        # Clear Twilio's audio buffer
        clear_event = {
            "event": "clear",
            "streamSid": actual_stream_sid
        }
        await websocket.send_json(clear_event)
        logger.info(
            f"Cleared Twilio audio buffer for streamSid: {actual_stream_sid}")

        # Send a small pause event to create natural transition
        pause_event = {
            "event": "mark",
            "streamSid": actual_stream_sid,
            "mark": {"name": "user_interrupt_pause"}
        }
        await websocket.send_json(pause_event)

        # Optional: Small pause before accepting new input
        # Reduced from 0.5 for faster response
        await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(
            f"Error in handle_speech_started_event: {e}", exc_info=True)
        # Don't raise the exception - try to continue the conversation

# Initialize the OpenAIRealtimeManager at global scope
realtime_manager = OpenAIRealtimeManager(config.OPENAI_API_KEY)

# New realtime endpoints


@app.post("/realtime/session", response_model=RealtimeSessionResponse)
@rate_limit("5/minute")
async def create_realtime_session(
    request: Request,
    session_data: RealtimeSessionCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new realtime session for WebRTC communication."""
    try:
        if session_data.scenario not in SCENARIOS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid scenario"
            )

        # Use the current user's ID if not specified
        user_id = session_data.user_id or current_user.id

        # Create session with OpenAI
        session_info = await realtime_manager.create_session(
            str(user_id),
            SCENARIOS[session_data.scenario]
        )

        return session_info

    except Exception as e:
        logger.error(
            f"Error creating realtime session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/realtime/signal", response_model=SignalingResponse)
async def handle_signaling(
    signal: SignalingMessage,
    current_user: User = Depends(get_current_user)
):
    """Handle WebRTC signaling messages."""
    try:
        # Verify session belongs to user
        session = realtime_manager.get_session(signal.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        if str(session["user_id"]) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session"
            )

        # Handle signaling message
        response = await realtime_manager.handle_signaling(
            signal.session_id,
            {
                "type": signal.type,
                "sdp": signal.sdp,
                "candidate": signal.candidate
            }
        )

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error handling signaling: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/test-realtime", response_class=HTMLResponse)
async def test_realtime_page():
    """Test endpoint for OpenAI Realtime API"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>OpenAI Realtime API Test</title>
        <style>
            .container { margin: 20px; }
            #status, #log { margin: 10px 0; }
            #log {
                height: 200px;
                overflow-y: scroll;
                border: 1px solid #ccc;
                padding: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>OpenAI Realtime API Test</h1>
            <button id="startBtn">Start Session</button>
            <button id="stopBtn" disabled>Stop Session</button>
            <div id="status">Not connected</div>
            <div id="log"></div>
        </div>

        <script>
            let rtcPeerConnection;

            function log(message) {
                const logDiv = document.getElementById('log');
                const timestamp = new Date().toISOString();
                logDiv.innerHTML += `<div>${timestamp}: ${message}</div>`;
                logDiv.scrollTop = logDiv.scrollHeight;
            }

            async function startSession() {
                try {
                    // Get authentication token
                    const tokenResponse = await fetch('/token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: 'username=test@example.com&password=testpassword123'
                    });
                    const tokenData = await tokenResponse.json();

                    // Create realtime session
                    const sessionResponse = await fetch('/realtime/session?scenario_id=default', {
                        headers: {
                            'Authorization': `Bearer ${tokenData.access_token}`
                        }
                    });
                    const sessionData = await sessionResponse.json();
                    log('Session created successfully');

                    // Initialize WebRTC
                    rtcPeerConnection = new RTCPeerConnection({
                        iceServers: sessionData.ice_servers
                    });

                    // Create and send offer
                    const offer = await rtcPeerConnection.createOffer({
                        offerToReceiveAudio: true
                    });
                    await rtcPeerConnection.setLocalDescription(offer);

                    const signalResponse = await fetch('/realtime/signal', {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${tokenData.access_token}`,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            session_id: sessionData.session_id,
                            client_secret: sessionData.client_secret,
                            sdp: offer.sdp
                        })
                    });
                    const answerData = await signalResponse.json();

                    // Set remote description
                    await rtcPeerConnection.setRemoteDescription(
                        new RTCSessionDescription({
                            type: 'answer',
                            sdp: answerData.sdp_answer
                        })
                    );

                    document.getElementById(
                        'status').textContent = 'Connected';
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    log('WebRTC connection established');

                } catch (error) {
                    log(`Error: ${error.message}`);
                    console.error(error);
                }
            }

            function stopSession() {
                if (rtcPeerConnection) {
                    rtcPeerConnection.close();
                    rtcPeerConnection = null;
                }
                document.getElementById('status').textContent = 'Disconnected';
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                log('Session stopped');
            }

            document.getElementById('startBtn').onclick = startSession;
            document.getElementById('stopBtn').onclick = stopSession;
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Add a dictionary to store custom scenarios
CUSTOM_SCENARIOS: Dict[str, dict] = {}


@app.post("/realtime/custom-scenario", response_model=dict)
@rate_limit("10/minute")
async def create_custom_scenario(
    request: Request,
    persona: str = Body(..., min_length=10, max_length=5000),
    prompt: str = Body(..., min_length=10, max_length=5000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a custom scenario"""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
            )

        # Check if user has reached the limit of 20 custom scenarios
        user_scenarios_count = db.query(CustomScenario).filter(
            CustomScenario.user_id == current_user.id
        ).count()

        if user_scenarios_count >= 20:
            raise HTTPException(
                status_code=400,
                detail="You have reached the maximum limit of 20 custom scenarios. Please delete some scenarios before creating new ones."
            )

        # Create scenario in same format as SCENARIOS dictionary
        custom_scenario = {
            "persona": persona,
            "prompt": prompt,
            "voice_config": {
                "voice": VOICES[voice_type],
                "temperature": temperature
            }
        }

        # Generate unique ID
        scenario_id = f"custom_{current_user.id}_{int(time.time())}"

        # Store in database
        db_custom_scenario = CustomScenario(
            scenario_id=scenario_id,
            user_id=current_user.id,
            persona=persona,
            prompt=prompt,
            voice_type=voice_type,
            temperature=temperature
        )

        db.add(db_custom_scenario)
        db.commit()
        db.refresh(db_custom_scenario)

        # Also store in memory for backward compatibility
        CUSTOM_SCENARIOS[scenario_id] = custom_scenario

        return {
            "scenario_id": scenario_id,
            "message": "Custom scenario created successfully"
        }

    except Exception as e:
        logger.error(f"Error creating custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the custom scenario. Please try again later."
        )


@app.get("/custom-scenarios", response_model=List[Dict])
async def get_custom_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all custom scenarios for the current user."""
    try:
        # Query all custom scenarios for the current user
        db_scenarios = db.query(CustomScenario).filter(
            CustomScenario.user_id == current_user.id
        ).order_by(CustomScenario.created_at.desc()).all()

        # Convert to a list of dictionaries for the response
        scenarios = []
        for scenario in db_scenarios:
            scenarios.append({
                "id": scenario.id,
                "scenario_id": scenario.scenario_id,
                "persona": scenario.persona,
                "prompt": scenario.prompt,
                "voice_type": scenario.voice_type,
                "temperature": scenario.temperature,
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None
            })

        return scenarios

    except Exception as e:
        logger.exception(f"Error retrieving custom scenarios: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving custom scenarios. Please try again later."
        )


@app.get("/make-custom-call/{phone_number}/{scenario_id}")
@rate_limit("2/minute")
async def make_custom_call(
    request: Request,
    phone_number: str,
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get PUBLIC_URL the same way as the standard endpoint
        host = os.getenv('PUBLIC_URL', '').strip()
        logger.info(f"Using PUBLIC_URL from environment: {host}")

        if not host:
            logger.error("PUBLIC_URL environment variable not set")
            return JSONResponse(
                status_code=500,
                content={"detail": "Server configuration error"}
            )

        # Check if phone number is valid
        if not re.match(r'^\d{10}$', phone_number):
            logger.error(f"Invalid phone number format: {phone_number}")
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "Invalid phone number format. Please provide a 10-digit number."}
            )

        # Get Twilio phone number from environment
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        if not twilio_phone:
            logger.error("TWILIO_PHONE_NUMBER not set")
            return JSONResponse(
                status_code=500,
                content={"detail": "Server configuration error"}
            )

        # Check if scenario exists in database
        db_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        # If not in database, check in-memory dictionary for backward compatibility
        if not db_scenario and scenario_id not in CUSTOM_SCENARIOS:
            logger.error(f"Custom scenario not found: {scenario_id}")
            return JSONResponse(
                status_code=400,
                content={"detail": "Custom scenario not found"}
            )

        # Ensure the URL has the https:// protocol
        if not host.startswith('http://') and not host.startswith('https://'):
            host = f"https://{host}"

        webhook_url = f"{host}/incoming-custom-call/{scenario_id}"
        logger.info(f"Constructed webhook URL: {webhook_url}")

        call = get_twilio_client().calls.create(
            to=f"+1{phone_number}",
            from_=twilio_phone,
            url=webhook_url,
            record=True
        )
        logger.info(
            f"Custom call initiated to +1{phone_number}, call_sid: {call.sid}")
        return {"status": "Custom call initiated", "call_sid": call.sid}
    except TwilioRestException as e:
        logger.error(f"Twilio error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An error occurred with the phone service. Please try again later."}
        )
    except Exception as e:
        logger.error(f"Error initiating custom call: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An error occurred while processing the outgoing call. Please try again later."}
        )


@app.api_route("/incoming-custom-call/{scenario_id}", methods=["GET", "POST"], operation_id="handle_custom_incoming_call")
async def handle_incoming_custom_call(request: Request, scenario_id: str, db: Session = Depends(get_db)):
    logger.info(
        f"Incoming custom call webhook received for scenario: {scenario_id}")
    try:
        # Check if scenario exists in database
        db_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id
        ).first()

        # If not in database, check in-memory dictionary for backward compatibility
        if not db_scenario and scenario_id not in CUSTOM_SCENARIOS:
            logger.error(f"Custom scenario not found: {scenario_id}")
            raise HTTPException(
                status_code=400, detail="Custom scenario not found")

        form_data = await request.form()
        logger.info(f"Received form data: {form_data}")

        response = VoiceResponse()

        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream-custom/{scenario_id}"

        # Add a greeting message
        # response.say(
        #    "Connecting you to our AI assistant, please wait a moment.")

        # Add a pause to allow the server to initialize
        response.pause(length=0.1)

        # Set up the stream connection
        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        # Add a Gather verb to keep the connection open
        gather = Gather(action="/handle-user-input",
                        method="POST", input="speech", timeout=60)
        response.append(gather)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error handling user input: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your input. Please try again later."
        )


@app.websocket("/media-stream-custom/{scenario_id}")
async def handle_custom_media_stream(websocket: WebSocket, scenario_id: str):
    """Handle media stream for custom scenarios."""
    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY = 2  # seconds

    async with websocket_manager(websocket) as ws:
        try:
            logger.info(
                f"WebSocket connection for custom scenario: {scenario_id}")

            # Get database session
            db = next(get_db())

            # Check if scenario exists in database
            db_scenario = db.query(CustomScenario).filter(
                CustomScenario.scenario_id == scenario_id
            ).first()

            # If scenario exists in database, use it
            if db_scenario:
                selected_scenario = {
                    "persona": db_scenario.persona,
                    "prompt": db_scenario.prompt,
                    "voice_config": {
                        "voice": VOICES[db_scenario.voice_type],
                        "temperature": db_scenario.temperature
                    }
                }
            # Otherwise check in-memory dictionary for backward compatibility
            elif scenario_id in CUSTOM_SCENARIOS:
                selected_scenario = CUSTOM_SCENARIOS[scenario_id]
            else:
                logger.error(f"Invalid custom scenario: {scenario_id}")
                return

            logger.info(f"Using custom scenario: {selected_scenario}")

            # Initialize reconnection counter
            reconnect_attempts = 0

            # Start reconnection loop
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
                        logger.info("Connected to OpenAI WebSocket")

                        # Connection specific state
                        shared_state = {
                            "should_stop": False,
                            "stream_sid": None,
                            "latest_media_timestamp": 0,
                            "last_assistant_item": None,
                            "current_transcript": "",
                            "greeting_sent": False
                        }

                        # Initialize session
                        await initialize_session(openai_ws, selected_scenario, is_incoming=True)
                        logger.info("Session initialized with OpenAI")

                        # Add a delay before sending the initial greeting
                        await asyncio.sleep(0.1)

                        # Check if Twilio WebSocket is still connected
                        try:
                            await ws.send_text(json.dumps({"status": "connected"}))
                            logger.info("Twilio WebSocket is still connected")
                        except Exception as e:
                            logger.warning(
                                f"Twilio WebSocket connection closed before sending greeting: {e}")
                            break

                        # Send initial greeting in a separate task
                        greeting_task = asyncio.create_task(
                            send_initial_greeting(openai_ws, selected_scenario))

                        # Create tasks for receiving and sending
                        receive_task = asyncio.create_task(
                            receive_from_twilio(ws, openai_ws, shared_state))
                        send_task = asyncio.create_task(
                            send_to_twilio(ws, openai_ws, shared_state))

                        # Define a constant for greeting timeout
                        GREETING_TIMEOUT = 10  # seconds
                        greeting_success = False

                        # Wait for greeting to complete first with a longer timeout
                        try:
                            greeting_result = await asyncio.wait_for(greeting_task, timeout=GREETING_TIMEOUT)
                            if greeting_result:
                                logger.info(
                                    "Initial greeting sent successfully")
                                shared_state["greeting_sent"] = True
                                greeting_success = True
                            else:
                                logger.warning(
                                    "Failed to send initial greeting, but continuing with call")
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"Timeout waiting for initial greeting after {GREETING_TIMEOUT}s, but continuing with call")
                        except Exception as e:
                            logger.error(
                                f"Error sending initial greeting: {str(e)}", exc_info=True)

                        # Check if Twilio WebSocket is still open
                        try:
                            await ws.send_text(json.dumps({"status": "processing"}))
                        except Exception as e:
                            logger.warning(
                                f"Twilio WebSocket closed during greeting: {e}")
                            break

                        try:
                            # Wait for both tasks to complete
                            await asyncio.gather(receive_task, send_task)
                            # If we get here without exception, break the reconnection loop
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"WebSocket connection closed: {e}")
                            if not shared_state["should_stop"]:
                                reconnect_attempts += 1
                                if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                                    logger.info(
                                        f"Attempting to reconnect... (Attempt {reconnect_attempts})")
                                    shared_state["reconnecting"] = True
                                    await asyncio.sleep(RECONNECT_DELAY)
                                    continue
                            raise
                        finally:
                            # Cancel tasks if they're still running
                            for task in [receive_task, send_task]:
                                if not task.done():
                                    task.cancel()
                                    try:
                                        await task
                                    except asyncio.CancelledError:
                                        pass

                except websockets.exceptions.WebSocketException as e:
                    logger.error(f"WebSocket error: {e}")
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
                f"Error in custom media stream: {str(e)}", exc_info=True)
            # WebSocket closure is handled by the context manager
        finally:
            # Close the database session
            db.close()


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


@app.post("/recording-callback")
async def handle_recording_callback(request: Request, db: Session = Depends(get_db)):
    try:
        # Log the raw request for debugging
        form_data = await request.form()
        form_data_dict = dict(form_data)
        # Sanitize form data for logging
        logger.info(
            f"Recording callback received with form data: {safe_log_request_data(form_data_dict)}")

        recording_sid = form_data.get('RecordingSid')
        call_sid = form_data.get('CallSid')

        if not recording_sid:
            logger.error("No RecordingSid provided in form data")
            return {"status": "error", "message": "No RecordingSid provided"}

        if not call_sid:
            logger.error("No CallSid provided in form data")
            return {"status": "error", "message": "No CallSid provided"}

        if config.USE_TWILIO_VOICE_INTELLIGENCE:
            logger.info(
                f"Using Twilio Voice Intelligence for recording {recording_sid}")

            # Log the configuration for debugging
            logger.info(
                f"Twilio Voice Intelligence SID: {config.TWILIO_VOICE_INTELLIGENCE_SID}")
            logger.info(
                f"PII Redaction Enabled: {config.ENABLE_PII_REDACTION}")

            try:
                # Create a transcript using Twilio Voice Intelligence
                transcript = get_twilio_client().intelligence.v2.transcripts.create(
                    service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
                    channel={
                        "media_properties": {
                            "source_sid": recording_sid
                        }
                    },
                    redaction=config.ENABLE_PII_REDACTION
                )

                logger.info(f"Transcript created with SID: {transcript.sid}")

                # Start background task to link transcript with retries
                background_tasks = BackgroundTasks()
                background_tasks.add_task(
                    link_transcript_to_conversation,
                    db=db,
                    call_sid=call_sid,
                    transcript_sid=transcript.sid
                )

                return {
                    "status": "success",
                    "transcript_sid": transcript.sid,
                    "message": "Transcript creation initiated, linking in progress"
                }

            except TwilioAuthError as e:
                logger.error(f"Twilio authentication error: {e.message}", extra={
                    "details": e.details})
                return {
                    "status": "error",
                    "message": "Authentication error with Twilio service",
                    "code": "auth_error"
                }
            except TwilioResourceError as e:
                logger.error(f"Twilio resource error: {e.message}", extra={
                    "details": e.details})
                return {
                    "status": "error",
                    "message": "Resource not found or invalid",
                    "code": "resource_error"
                }
            except TwilioRateLimitError as e:
                logger.error(f"Twilio rate limit exceeded: {e.message}", extra={
                    "details": e.details})
                return {
                    "status": "error",
                    "message": "Rate limit exceeded, please try again later",
                    "code": "rate_limit"
                }
            except TwilioApiError as e:
                logger.error(f"Twilio API error: {e.message}", extra={
                    "details": e.details})
                return {
                    "status": "error",
                    "message": "Error communicating with Twilio service",
                    "code": "api_error"
                }
            except Exception as e:
                logger.error(
                    f"Unexpected error creating transcript: {str(e)}", exc_info=True)
                return {
                    "status": "error",
                    "message": "An unexpected error occurred",
                    "code": "unknown_error"
                }

        else:
            # Your existing OpenAI Whisper implementation
            pass

    except SQLAlchemyError as e:
        logger.error(
            f"Database error in recording callback: {str(e)}", exc_info=True)
        if db.is_active:
            db.rollback()
        return {"status": "error", "message": "Database error", "code": "db_error"}
    except Exception as e:
        logger.error(f"Error in recording callback: {str(e)}", exc_info=True)
        return {"status": "error", "message": "An unexpected error occurred", "code": "unknown_error"}


@app.get("/twilio-transcripts/{transcript_sid}")
@with_twilio_retry(max_retries=3)
async def get_twilio_transcript(transcript_sid: str):
    try:
        # Using direct Twilio API access - fetch() is not async and should not use await
        transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()

        # list() is not async and should not use await
        sentences = get_twilio_client().intelligence.v2.transcripts(
            transcript_sid).sentences.list()

        # Log the structure of the first sentence to debug
        if sentences and len(sentences) > 0:
            first_sentence = sentences[0]
            logger.info(f"Sentence object attributes: {dir(first_sentence)}")
            logger.info(
                f"Sentence object representation: {repr(first_sentence)}")

        # Format the response
        formatted_transcript = {
            "sid": transcript.sid,
            "status": transcript.status,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "duration": transcript.duration,
            "language_code": transcript.language_code,
            "sentences": []
        }

        # Add sentences if available
        if sentences:
            formatted_transcript["sentences"] = [
                {
                    # Use the correct property name 'transcript' instead of 'text'
                    "text": getattr(sentence, "transcript", "No text available"),
                    "speaker": getattr(sentence, "media_channel", 0),
                    "start_time": getattr(sentence, "start_time", 0),
                    "end_time": getattr(sentence, "end_time", 0),
                    "confidence": getattr(sentence, "confidence", None)
                } for sentence in sentences
            ]

        return formatted_transcript

    except TwilioRestException as e:
        logger.error(f"Twilio REST error: {str(e)}")
        if e.status == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Transcript not found: {transcript_sid}"
            )
        else:
            raise HTTPException(
                status_code=e.status or 500,
                detail=f"Twilio API error: {str(e)}"
            )
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
        logger.error(f"Unexpected error fetching transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@app.get("/twilio-transcripts")
@with_twilio_retry(max_retries=3)
async def list_twilio_transcripts(
    page_size: int = 20,
    page_token: Optional[str] = None,
    status: Optional[str] = None,
    source_sid: Optional[str] = None
):
    try:
        # Build filter parameters
        params = {"limit": page_size}
        if page_token:
            params["page_token"] = page_token
        if status:
            params["status"] = status
        if source_sid:
            params["source_sid"] = source_sid

        # List transcripts with filters - list() is not async and should not use await
        transcripts = get_twilio_client().intelligence.v2.transcripts.list(**params)

        # Format the response with proper datetime handling
        formatted_transcripts = [
            {
                "sid": transcript.sid,
                "status": transcript.status,
                "date_created": str(transcript.date_created) if transcript.date_created else None,
                "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
                "duration": transcript.duration,
                "customer_key": transcript.customer_key
            } for transcript in transcripts
        ]

        # Get pagination information
        meta = {
            "page_size": page_size,
            "next_page_token": transcripts.next_page_token if hasattr(transcripts, "next_page_token") else None,
            "previous_page_token": transcripts.previous_page_token if hasattr(transcripts, "previous_page_token") else None,
        }

        return {
            "transcripts": formatted_transcripts,
            "meta": meta
        }

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
        logger.error(f"Unexpected error listing transcripts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@app.get("/twilio-transcripts/recording/{recording_sid}")
@with_twilio_retry(max_retries=3)
async def get_transcript_by_recording(recording_sid: str):
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


@app.delete("/twilio-transcripts/{transcript_sid}")
@with_twilio_retry(max_retries=3)
async def delete_twilio_transcript(transcript_sid: str):
    try:
        # First check if the transcript exists
        try:
            get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
        except Exception as e:
            raise TwilioResourceError(
                f"Transcript not found: {transcript_sid}",
                details={"original_exception": str(e)}
            )

        # Delete the transcript
        get_twilio_client().intelligence.v2.transcripts(transcript_sid).delete()

        return {"status": "success", "message": "Transcript deleted"}

    except TwilioResourceError as e:
        logger.error(f"Resource error: {e.message}")
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
        logger.error(f"Unexpected error deleting transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )


@app.post("/twilio-transcripts/create-with-participants")
@with_twilio_retry(max_retries=3)
async def create_transcript_with_participants(
    request: Request,
    recording_sid: str = Body(...),
    participants: List[Dict] = Body(...)
):
    try:
        # Validate the recording_sid format
        if not recording_sid or not recording_sid.startswith("RE"):
            raise HTTPException(
                status_code=400,
                detail="Invalid recording_sid format"
            )

        # Validate participants structure
        for participant in participants:
            if "channel_participant" not in participant or "role" not in participant:
                raise HTTPException(
                    status_code=400,
                    detail="Each participant must have channel_participant and role fields"
                )

        # Create the transcript with participants
        transcript = get_twilio_client().intelligence.v2.transcripts.create(
            service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
            channel={
                "media_properties": {
                    "source_sid": recording_sid
                },
                "participants": participants
            },
            redaction=config.ENABLE_PII_REDACTION
        )

        return {
            "status": "success",
            "transcript_sid": transcript.sid,
            "message": "Transcript creation initiated with custom participants"
        }

    except TwilioAuthError as e:
        logger.error(f"Authentication error: {e.message}")
        raise HTTPException(
            status_code=401,
            detail="Authentication error with Twilio service"
        )
    except TwilioResourceError as e:
        logger.error(f"Resource error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resource: {e.message}"
        )
    except TwilioApiError as e:
        logger.error(f"Twilio API error: {e.message}", extra={
            "details": e.details})
        raise HTTPException(
            status_code=500,
            detail="Error communicating with Twilio service"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )


@app.post("/twilio-transcripts/create-with-media-url")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def create_transcript_with_media_url(
    request: Request,
    media_url: str = Body(...),
    language_code: str = Body("en-US"),
    redaction: bool = Body(True),
    customer_key: str = Body(None),
    data_logging: bool = Body(True)
):
    try:
        # Log the request (sanitized for any sensitive data)
        logger.info(
            f"Transcript creation request: {safe_log_request_data({'media_url': media_url, 'language_code': language_code, 'redaction': redaction})}"
        )

        # Create a transcript using Twilio Voice Intelligence
        transcript = get_twilio_client().intelligence.v2.transcripts.create(
            service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
            channel={
                "media_properties": {
                    "source_url": media_url
                }
            },
            language_code=language_code,
            redaction=redaction
        )

        logger.info(f"Transcript created with SID: {transcript.sid}")

        return {
            "status": "success",
            "transcript_sid": transcript.sid,
            "message": "Transcript creation initiated"
        }

    except TwilioAuthError as e:
        logger.exception(
            f"Authentication error creating transcript with media URL")
        raise HTTPException(
            status_code=401,
            detail="Authentication error with Twilio service"
        )
    except TwilioResourceError as e:
        logger.exception(f"Resource error creating transcript with media URL")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resource: {e.message}"
        )
    except Exception as e:
        logger.exception(f"Error creating transcript with media URL")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating the transcript"
        )


@app.post("/twilio-transcripts/webhook-callback")
async def handle_transcript_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint to receive notifications when a Twilio Voice Intelligence transcript is complete.

    This endpoint should be configured as the webhook URL in your Voice Intelligence Service settings.
    """
    try:
        # Parse the webhook payload
        payload = await request.json()
        logger.info(f"Received transcript webhook callback: {payload}")

        # Extract the transcript SID and status
        transcript_sid = payload.get('transcript_sid') or payload.get('sid')
        status = payload.get('status')
        event_type = payload.get('event_type')

        if not transcript_sid:
            logger.error("No transcript SID provided in webhook")
            return {"status": "error", "message": "No transcript SID provided"}

        # Handle voice_intelligence_transcript_available event type
        if event_type == "voice_intelligence_transcript_available":
            # Fetch the transcript details using the transcript_sid
            try:
                transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
                status = transcript.status
                logger.info(
                    f"Retrieved transcript {transcript_sid} with status: {status}")
            except Exception as e:
                logger.error(f"Error fetching transcript details: {str(e)}")
                return {"status": "error", "message": f"Error fetching transcript details: {str(e)}"}

        if status == "completed":
            # Fetch the complete transcript with sentences - fetch() and list() are not async
            transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
            sentences = get_twilio_client().intelligence.v2.transcripts(
                transcript_sid).sentences.list()

            # Log the structure of the first sentence to debug
            if sentences and len(sentences) > 0:
                first_sentence = sentences[0]
                logger.info(
                    f"Webhook - Sentence object attributes: {dir(first_sentence)}")
                logger.info(
                    f"Webhook - Sentence object representation: {repr(first_sentence)}")

            # Format the transcript text with proper attribute checking
            sorted_sentences = sorted(
                sentences, key=lambda s: getattr(s, "start_time", 0))

            # Use getattr to safely access attributes that might be named differently
            full_text = " ".join(
                getattr(s, "transcript", "No text available")
                for s in sorted_sentences
            )

            # Helper function to convert Decimal to float for JSON serialization
            def decimal_to_float(obj):
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)
                return obj

            # Store the transcript in TranscriptRecord for later retrieval
            # This allows you to serve it from your own backend without going to Twilio each time
            transcript_record = TranscriptRecord(
                transcript_sid=transcript_sid,
                status=status,
                full_text=full_text,
                date_created=transcript.date_created,
                date_updated=transcript.date_updated,
                duration=decimal_to_float(transcript.duration),
                language_code=transcript.language_code,
                # Set a default user_id (1) for transcripts created via webhook
                user_id=1,  # Default to first user since webhook doesn't have authentication
                # Store the raw sentences as JSON for detailed access if needed
                sentences_json=json.dumps([{
                    "transcript": getattr(s, "transcript", "No text available"),
                    "speaker": getattr(s, "media_channel", 0),
                    "start_time": decimal_to_float(getattr(s, "start_time", 0)),
                    "end_time": decimal_to_float(getattr(s, "end_time", 0)),
                    "confidence": decimal_to_float(getattr(s, "confidence", None))
                } for s in sorted_sentences], default=decimal_to_float)
            )

            db.add(transcript_record)

            # Also update the Conversation model if it exists
            # Find the conversation by recording_sid or transcript_sid
            # Log available attributes to debug
            logger.info(f"Transcript object attributes: {dir(transcript)}")

            # Try different possible attribute names for the recording SID
            recording_sid = None
            for attr_name in ['recording_sid', 'source_sid', 'sid', 'call_sid']:
                if hasattr(transcript, attr_name):
                    recording_sid = getattr(transcript, attr_name)
                    logger.info(
                        f"Found recording identifier: {attr_name}={recording_sid}")
                    break

            if recording_sid:
                # Try to find the conversation by the recording SID
                conversation = db.query(Conversation).filter(
                    Conversation.recording_sid == recording_sid
                ).first()

                if conversation:
                    # Update the conversation with the full transcript text
                    conversation.transcript = full_text
                    logger.info(
                        f"Updated conversation {conversation.id} with full transcript text")
                else:
                    logger.info(
                        f"No conversation found with recording_sid={recording_sid}")
            else:
                logger.info(
                    "Could not find recording identifier in transcript object")

            db.commit()

            logger.info(
                f"Stored completed transcript {transcript_sid} in database")

            return {"status": "success", "message": "Transcript processed and stored"}
        else:
            logger.info(f"Transcript {transcript_sid} status update: {status}")
            return {"status": "success", "message": f"Received status update: {status}"}

    except Exception as e:
        logger.error(f"Error processing transcript webhook: {str(e)}")
        return {"status": "error", "message": "Error processing webhook"}


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


@app.get("/custom-scenarios/{scenario_id}", response_model=Dict)
async def get_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific custom scenario by ID."""
    try:
        # Query the specific custom scenario
        db_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        # If not found in database, check the in-memory dictionary
        if not db_scenario:
            if scenario_id in CUSTOM_SCENARIOS:
                # Make sure it belongs to this user (may not be possible to validate for in-memory scenarios)
                return {
                    "id": None,
                    "scenario_id": scenario_id,
                    "persona": CUSTOM_SCENARIOS[scenario_id].get("persona", ""),
                    "prompt": CUSTOM_SCENARIOS[scenario_id].get("prompt", ""),
                    "voice_type": "unknown",  # In-memory might not store this
                    "temperature": CUSTOM_SCENARIOS[scenario_id].get("voice_config", {}).get("temperature", 0.7),
                    "created_at": None
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Custom scenario not found"
                )

        # Convert to dictionary for the response
        return {
            "id": db_scenario.id,
            "scenario_id": db_scenario.scenario_id,
            "persona": db_scenario.persona,
            "prompt": db_scenario.prompt,
            "voice_type": db_scenario.voice_type,
            "temperature": db_scenario.temperature,
            "created_at": db_scenario.created_at.isoformat() if db_scenario.created_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the custom scenario. Please try again later."
        )


@app.delete("/custom-scenarios/{scenario_id}", response_model=Dict)
async def delete_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a specific custom scenario by ID."""
    try:
        # Query the specific custom scenario
        db_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not db_scenario:
            # Check if it exists in the in-memory dictionary
            if scenario_id in CUSTOM_SCENARIOS:
                # Remove from in-memory dictionary
                del CUSTOM_SCENARIOS[scenario_id]
                return {"message": "Custom scenario deleted successfully"}
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Custom scenario not found"
                )

        # Delete from database
        db.delete(db_scenario)
        db.commit()

        # Also remove from in-memory dictionary if it exists there
        if scenario_id in CUSTOM_SCENARIOS:
            del CUSTOM_SCENARIOS[scenario_id]

        return {"message": "Custom scenario deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the custom scenario. Please try again later."
        )


@app.put("/custom-scenarios/{scenario_id}", response_model=Dict)
async def update_custom_scenario(
    scenario_id: str,
    persona: str = Body(..., min_length=10, max_length=5000),
    prompt: str = Body(..., min_length=10, max_length=5000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a specific custom scenario by ID."""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
            )

        # Query the specific custom scenario
        db_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not db_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found"
            )

        # Update database entry
        db_scenario.persona = persona
        db_scenario.prompt = prompt
        db_scenario.voice_type = voice_type
        db_scenario.temperature = temperature
        db.commit()

        # Update in-memory dictionary if it exists there
        if scenario_id in CUSTOM_SCENARIOS:
            CUSTOM_SCENARIOS[scenario_id] = {
                "persona": persona,
                "prompt": prompt,
                "voice_config": {
                    "voice": VOICES[voice_type],
                    "temperature": temperature
                }
            }

        return {"message": "Custom scenario updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the custom scenario. Please try again later."
        )


@app.get("/test-db-connection")
async def test_db_connection(db: Session = Depends(get_db)):
    try:
        # Import the text function from SQLAlchemy
        from sqlalchemy import text

        # Use the text() function to properly format the SQL query
        result = db.execute(text("SELECT 1")).fetchone()
        return {"status": "Database connection working", "result": result[0]}
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
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Endpoint to transcribe audio using OpenAI's Whisper API.
    Accepts audio file uploads and returns the transcription.
    """
    try:
        # Create a temporary file to store the uploaded audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            # Write the uploaded file content to the temporary file
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Use the existing TranscriptionService to transcribe the audio
        transcription_result = await transcription_service.transcribe_audio(content)

        if transcription_result:
            return {
                "status": "success",
                "transcription": transcription_result
            }
        else:
            return {
                "status": "error",
                "message": "Failed to transcribe audio"
            }
    except Exception as e:
        logger.error(f"Error in transcribe_audio endpoint: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        # Clean up the temporary file
        try:
            os.unlink(temp_file_path)
        except:
            pass


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
                    "token": credentials.token,
                    "refresh_token": credentials.refresh_token,
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
async def handle_user_input(request: Request):
    """Handle user input from Twilio Gather verb"""
    try:
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


@app.post("/twilio-callback")
async def handle_twilio_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Twilio status callbacks for call status updates"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")

        logger.info(
            f"Received Twilio callback for call {call_sid} with status {call_status}")

        if not call_sid:
            return {"status": "error", "message": "No CallSid provided"}

        # Update conversation record if it exists
        conversation = db.query(Conversation).filter(
            Conversation.call_sid == call_sid
        ).first()

        if conversation:
            # Map Twilio status to our status
            status_map = {
                "completed": "completed",
                "busy": "failed",
                "failed": "failed",
                "no-answer": "failed",
                "canceled": "canceled"
            }

            conversation.status = status_map.get(call_status, call_status)
            db.commit()
            logger.info(
                f"Updated conversation {conversation.id} status to {conversation.status}")

            # Check for recording if the call was completed
            if call_status == "completed":
                recording_sid = form_data.get("RecordingSid")
                if recording_sid:
                    conversation.recording_sid = recording_sid
                    db.commit()
                    logger.info(
                        f"Updated conversation {conversation.id} with recording {recording_sid}")

        return {"status": "success", "call_sid": call_sid, "call_status": call_status}
    except Exception as e:
        logger.error(
            f"Error handling Twilio callback: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/make-calendar-call-scenario/{phone_number}")
@rate_limit("2/minute")
async def make_calendar_call_scenario(
    request: Request,
    phone_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a calendar call using the standard scenario approach that's known to work well.
    This creates a temporary scenario with calendar data and uses the standard call flow.
    """
    try:
        # Validate phone number format
        if not phone_number.startswith('+'):
            phone_number = f"+{phone_number}"

        logger.info(
            f"Initiating calendar call (scenario approach) to {phone_number} for user {current_user.email}")

        # Check if user has Google Calendar connected
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == current_user.id
        ).first()

        if not credentials:
            raise HTTPException(
                status_code=401, detail="Google Calendar not connected")

        # Prepare calendar service
        calendar_service = GoogleCalendarService()
        service = calendar_service.get_calendar_service({
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "expiry": credentials.token_expiry.isoformat()
        })

        # Get upcoming events
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

        # Create a temporary scenario key (not in the SCENARIOS dict)
        temp_scenario_key = f"calendar_{current_user.id}_{int(time.time())}"

        # Create the scenario
        calendar_scenario = {
            "persona": "Calendar Assistant",
            "prompt": (
                f"You are a helpful calendar assistant handling a phone call. "
                f"You have access to the caller's Google Calendar. Be conversational and friendly. "
                f"\\n\\n{events_context}\\n\\n{slots_context}\\n\\n"
                f"You can provide information about upcoming events, check availability, "
                f"and suggest free time slots. If the caller asks about scheduling an event, "
                f"collect the necessary details like date, time, duration, and purpose. "
                f"Remain connected and responsive during silences. "
                f"Offer to help with any other calendar-related questions they might have."
            ),
            "voice_config": {
                # Changed from 'nova' to 'alloy' which is supported by the GPT-4o Realtime API
                "voice": "alloy",
                "temperature": 0.7
            }
        }

        # Temporarily add to SCENARIOS
        SCENARIOS[temp_scenario_key] = calendar_scenario

        # Build the media stream URL
        base_url = clean_and_validate_url(config.PUBLIC_URL)
        user_name = current_user.email
        outgoing_call_url = f"{base_url}/outgoing-call/{temp_scenario_key}?direction=outbound&user_name={user_name}"
        logger.info(f"Outgoing call URL with parameters: {outgoing_call_url}")

        # Make the call
        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number,
            from_=config.TWILIO_PHONE_NUMBER,
            url=outgoing_call_url,
            record=True
        )

        # Create a conversation record
        conversation = Conversation(
            user_id=current_user.id,
            scenario="calendar",
            phone_number=phone_number,
            direction="outbound",
            status="in-progress",
            call_sid=call.sid
        )
        db.add(conversation)
        db.commit()

        # Schedule removal of temporary scenario
        def remove_temp_scenario():
            try:
                if temp_scenario_key in SCENARIOS:
                    del SCENARIOS[temp_scenario_key]
                    logger.info(
                        f"Removed temporary scenario {temp_scenario_key}")
            except Exception as e:
                logger.error(f"Error removing temp scenario: {e}")

        # Run cleanup after 1 hour
        threading.Timer(3600, remove_temp_scenario).start()

        return {
            "status": "success",
            "call_sid": call.sid,
            "message": "Calendar call initiated using scenario approach",
            "scenario_key": temp_scenario_key
        }

    except TwilioRestException as e:
        logger.exception(f"Twilio error when calling {phone_number}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": f"An error occurred with the phone service: {str(e)}"}
        )
    except Exception as e:
        logger.exception(f"Error making calendar call to {phone_number}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"An error occurred: {str(e)}"}
        )

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
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
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

                # Initialize session with turn detection
                await openai_ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.2,
                            "prefix_padding_ms": 50,
                            "silence_duration_ms": 100
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
@app.get("/stored-twilio-transcripts")
async def get_stored_twilio_transcripts(
    page_size: int = Query(10, le=100),
    page_token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return stored transcripts in EXACT same format as Twilio API"""
    try:
        query = db.query(StoredTwilioTranscript).filter(
            StoredTwilioTranscript.user_id == current_user.id
        ).order_by(StoredTwilioTranscript.date_created.desc())

        skip = int(page_token) if page_token else 0
        transcripts = query.offset(skip).limit(page_size).all()

        # Return in EXACT same format as Twilio API
        return {
            "transcripts": [
                {
                    "sid": t.transcript_sid,
                    "status": t.status,
                    "date_created": t.date_created,
                    "date_updated": t.date_updated,
                    "duration": t.duration,
                    "language_code": t.language_code,
                    "sentences": t.sentences  # This is the critical part!
                }
                for t in transcripts
            ]
        }
    except Exception as e:
        logger.error(f"Error retrieving stored Twilio transcripts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving stored transcripts"
        )


@app.get("/stored-twilio-transcripts/{transcript_sid}")
async def get_stored_twilio_transcript_detail(
    transcript_sid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return stored transcript detail in EXACT same format as Twilio API"""
    try:
        transcript = db.query(StoredTwilioTranscript).filter(
            StoredTwilioTranscript.transcript_sid == transcript_sid,
            StoredTwilioTranscript.user_id == current_user.id
        ).first()

        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")

        # Return in EXACT same format as Twilio detail API
        return {
            "sid": transcript.transcript_sid,
            "status": transcript.status,
            "date_created": transcript.date_created,
            "date_updated": transcript.date_updated,
            "duration": transcript.duration,
            "language_code": transcript.language_code,
            "sentences": transcript.sentences  # Full Twilio sentences array
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving stored Twilio transcript detail: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving transcript detail"
        )


@app.post("/store-transcript/{transcript_sid}")
async def store_transcript_from_twilio(
    transcript_sid: str,
    call_sid: Optional[str] = Body(None),
    scenario_name: str = Body("Voice Call"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch transcript from Twilio and store in our database"""
    try:
        # Check if already stored
        existing = db.query(StoredTwilioTranscript).filter(
            StoredTwilioTranscript.transcript_sid == transcript_sid
        ).first()

        if existing:
            return {"status": "already_stored", "transcript_sid": transcript_sid}

        # Fetch from Twilio
        from app.services.twilio_client import get_twilio_client
        twilio_client = get_twilio_client()
        transcript = twilio_client.intelligence.v2.transcripts(
            transcript_sid).fetch()

        # Fetch sentences
        sentences = twilio_client.intelligence.v2.transcripts(
            transcript_sid).sentences.list()

        # Sort sentences by start time
        sorted_sentences = sorted(
            sentences, key=lambda s: getattr(s, "start_time", 0))

        # Helper function for decimal conversion
        def decimal_to_float(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        # Format sentences in Twilio format
        formatted_sentences = [
            {
                "text": getattr(s, "transcript", "No text available"),
                "speaker": getattr(s, "media_channel", 0),
                "start_time": decimal_to_float(getattr(s, "start_time", 0)),
                "end_time": decimal_to_float(getattr(s, "end_time", 0)),
                "confidence": decimal_to_float(getattr(s, "confidence", 0.0))
            }
            for s in sorted_sentences
        ]

        # Store in our database with exact Twilio format
        stored_transcript = StoredTwilioTranscript(
            user_id=current_user.id,
            transcript_sid=transcript.sid,
            status=transcript.status,
            date_created=transcript.date_created.isoformat() if transcript.date_created else None,
            date_updated=transcript.date_updated.isoformat() if transcript.date_updated else None,
            duration=decimal_to_float(
                transcript.duration) if transcript.duration else 0,
            language_code=transcript.language_code or "en-US",
            sentences=formatted_sentences,  # Store formatted Twilio sentences
            call_sid=call_sid,
            scenario_name=scenario_name
        )

        db.add(stored_transcript)
        db.commit()

        logger.info(
            f"Successfully stored transcript {transcript_sid} for user {current_user.id}")
        return {"status": "stored", "transcript_sid": transcript_sid}

    except Exception as e:
        logger.error(f"Failed to store transcript {transcript_sid}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to store transcript: {str(e)}")
