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
from app.limiter import rate_limit
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

# SlowAPIMiddleware removed - using custom rate limiting instead

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


class NameUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("name must be a non-empty string")
        # Trim excessive whitespace
        return v.strip()


# Add this endpoint for updating the user name
@app.post("/update-user-name")
async def update_user_name(
    payload: NameUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        USER_CONFIG["name"] = payload.name
        logger.info(f"Updated user name to: {payload.name}")
        return {"message": f"User name updated to: {payload.name}", "name": payload.name}
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


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
                            # Parse function arguments with better error handling
                            logger.info(
                                f"📋 Raw arguments received: {arguments}")
                            if isinstance(arguments, str):
                                try:
                                    args = json.loads(arguments)
                                except json.JSONDecodeError as json_err:
                                    logger.error(
                                        f"❌ JSON decode error: {json_err}")
                                    logger.error(
                                        f"❌ Malformed JSON: {arguments}")
                                    # Try to fix common JSON issues
                                    # Replace single quotes with double quotes
                                    fixed_args = arguments.replace("'", '"')
                                    try:
                                        args = json.loads(fixed_args)
                                        logger.info(
                                            "✅ Fixed JSON by replacing single quotes")
                                    except:
                                        # If still failing, create a basic structure
                                        args = {"summary": "Calendar Event",
                                                "start_iso": "", "end_iso": ""}
                                        logger.warning(
                                            "⚠️ Using fallback arguments due to JSON parse failure")
                            else:
                                args = arguments

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
                                        f"{os.getenv('PUBLIC_URL', 'https://voice.hyperlabsai.com')}/tools/createCalendarEvent",
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
