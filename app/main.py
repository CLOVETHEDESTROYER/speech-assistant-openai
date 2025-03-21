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
from app.models import User, Token, CallSchedule, Conversation, TranscriptRecord, CustomScenario
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

# Load environment variables
load_dotenv('dev.env')  # Load from dev.env explicitly

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Create database tables (do this only once)
Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])

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
async def schedule_call(
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
async def make_call(phone_number: str, scenario: str):
    try:
        # Get PUBLIC_URL from environment
        host = os.getenv('PUBLIC_URL', '').strip()
        logger.info(f"Using PUBLIC_URL from environment: {host}")

        if not host:
            logger.error("PUBLIC_URL environment variable not set")
            return JSONResponse(
                status_code=500,
                content={"error": "Server configuration error"}
            )

        if scenario not in SCENARIOS:
            logger.error(f"Invalid scenario: {scenario}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Invalid scenario. Valid options are: {', '.join(SCENARIOS.keys())}"}
            )

        # Check if phone number is valid
        if not re.match(r'^\d{10}$', phone_number):
            logger.error(f"Invalid phone number format: {phone_number}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid phone number format. Please provide a 10-digit number."}
            )

        # Get Twilio phone number from environment
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        if not twilio_phone:
            logger.error("TWILIO_PHONE_NUMBER not set")
            return JSONResponse(
                status_code=500,
                content={"error": "Twilio phone number not configured"}
            )

        # Ensure the URL has the https:// protocol
        if not host.startswith('http://') and not host.startswith('https://'):
            host = f"https://{host}"

        # Use a different endpoint for outgoing calls
        webhook_url = f"{host}/outgoing-call/{scenario}"
        logger.info(f"Constructed webhook URL: {webhook_url}")

        # Create the call using Twilio
        call = get_twilio_client().calls.create(
            to=f"+1{phone_number}",
            from_=twilio_phone,
            url=webhook_url,
            record=True
        )
        logger.info(
            f"Call initiated to +1{phone_number}, call_sid: {call.sid}")

        return {"status": "Call initiated", "call_sid": call.sid}
    except TwilioRestException as e:
        logger.error(f"Twilio error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Twilio error: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Error making call: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Server error: {str(e)}"}
        )

# Add a new endpoint for outgoing calls


@app.api_route("/outgoing-call/{scenario}", methods=["GET", "POST"])
async def handle_outgoing_call(request: Request, scenario: str):
    logger.info(f"Outgoing call webhook received for scenario: {scenario}")
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

        # Add a brief pause to allow the server to initialize
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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))


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
                            "prefix_padding_ms": 200,
                            "silence_duration_ms": 500
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


async def process_outgoing_audio(audio_data, call_sid, speaker="AI", scenario_name="unknown"):
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
                "turn_detection": {"type": "server_vad"},
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

    async with websocket_manager(websocket) as ws:
        try:
            logger.info(
                f"WebSocket connection established for scenario: {scenario}")

            if scenario not in SCENARIOS:
                logger.error(f"Invalid scenario: {scenario}")
                return

            selected_scenario = SCENARIOS[scenario]
            logger.info(f"Using scenario: {selected_scenario}")

            # Get the request path to determine if this is an outgoing call
            request_path = websocket.url.path
            is_incoming = not request_path.startswith("/outgoing-call")

            # Initialize reconnection counter
            reconnect_attempts = 0

            # Start reconnection loop
            while reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                try:
                    async with websockets.connect(
                        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
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
                        await initialize_session(openai_ws, selected_scenario, is_incoming=is_incoming)
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
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
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
    for session_id in list(realtime_manager.active_sessions.keys()):
        try:
            await realtime_manager.close_session(session_id)
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {str(e)}")


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


async def initialize_session(openai_ws, scenario, is_incoming=True):
    """Initialize session with OpenAI."""
    try:
        # If scenario is a string, get the scenario data from SCENARIOS
        if isinstance(scenario, str):
            if scenario not in SCENARIOS:
                raise ValueError(f"Invalid scenario: {scenario}")
            scenario = SCENARIOS[scenario]

        session_data = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.2,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 500
                },
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "instructions": (
                    f"{SYSTEM_MESSAGE}\n\n"
                    f"Persona: {scenario['persona']}\n\n"
                    f"Scenario: {scenario['prompt']}\n\n"
                    + ("IMPORTANT: Greet the caller immediately when the call connects. "
                       "Introduce yourself as specified in your persona and ask how you can help."
                       if is_incoming else
                       "IMPORTANT: Follow the scenario prompt exactly. Do not ask how you can help.")
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

    # Initialize the OpenAIRealtimeManager
    realtime_manager = OpenAIRealtimeManager(OPENAI_API_KEY)

    # New realtime endpoints


@app.post("/realtime/session", response_model=RealtimeSessionResponse)
async def create_realtime_session(
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
async def create_custom_scenario(
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
            detail=str(e)
        )


@app.get("/make-custom-call/{phone_number}/{scenario_id}")
async def make_custom_call(
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
                content={"error": "Server configuration error"}
            )

        # Check if phone number is valid
        if not re.match(r'^\d{10}$', phone_number):
            logger.error(f"Invalid phone number format: {phone_number}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid phone number format. Please provide a 10-digit number."}
            )

        # Get Twilio phone number from environment
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        if not twilio_phone:
            logger.error("TWILIO_PHONE_NUMBER not set")
            return JSONResponse(
                status_code=500,
                content={"error": "Twilio phone number not configured"}
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
                content={"error": "Custom scenario not found"}
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
            content={"error": f"Twilio error: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Error initiating custom call: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Server error: {str(e)}"}
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
        logger.error(
            f"Error in handle_incoming_custom_call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
                        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
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


@app.post("/recording-callback")
async def handle_recording_callback(request: Request, db: Session = Depends(get_db)):
    try:
        # Log the raw request for debugging
        form_data = await request.form()
        logger.info(
            f"Recording callback received with form data: {dict(form_data)}")

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

                # Store the transcript SID in your database
                conversation = db.query(Conversation).filter(
                    Conversation.call_sid == call_sid
                ).first()

                if conversation:
                    conversation.transcript_sid = transcript.sid
                    conversation.recording_sid = recording_sid
                    db.commit()
                    logger.info(
                        f"Updated conversation with transcript SID: {transcript.sid}")

                    return {
                        "status": "success",
                        "transcript_sid": transcript.sid,
                        "message": "Transcript creation initiated"
                    }
                else:
                    logger.error(
                        f"No conversation found with call_sid: {call_sid}")
                    return {
                        "status": "error",
                        "message": f"No conversation found with call_sid: {call_sid}",
                        "code": "not_found"
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


@app.post("/twilio-transcripts/create-with-media-url", response_model=Dict)
@with_twilio_retry(max_retries=3)
async def create_transcript_with_media_url(
    media_url: str = Body(...),
    language_code: str = Body("en-US"),
    redaction: bool = Body(True),
    customer_key: Optional[str] = Body(None),
    data_logging: bool = Body(False),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new transcript using a media URL instead of a recording SID.

    This endpoint allows creating a transcript by providing a direct media URL
    rather than requiring a Twilio recording SID.
    """
    try:
        # Validate the media_url
        if not media_url or not (media_url.startswith("http://") or media_url.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail="Invalid media_url format. Must be a valid HTTP or HTTPS URL."
            )

        # Create the transcript with the media URL - create() is not async
        transcript = get_twilio_client().intelligence.v2.transcripts.create(
            service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
            channel={
                "media_properties": {
                    "media_url": media_url
                }
            },
            language_code=language_code,
            redaction=redaction,
            customer_key=customer_key,
            data_logging=data_logging
        )

        # Format the response to match the example structure
        formatted_response = {
            "account_sid": transcript.account_sid,
            "service_sid": transcript.service_sid,
            "sid": transcript.sid,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "status": transcript.status,
            "channel": {
                "media_properties": {
                    "media_url": media_url
                }
            },
            "data_logging": transcript.data_logging,
            "language_code": transcript.language_code,
            "media_start_time": transcript.media_start_time,
            "duration": transcript.duration,
            "customer_key": transcript.customer_key,
            "url": transcript.url,
            "redaction": transcript.redaction,
            "links": {
                "sentences": f"https://intelligence.twilio.com/v2/Transcripts/{transcript.sid}/Sentences",
                "media": f"https://intelligence.twilio.com/v2/Transcripts/{transcript.sid}/Media",
                "operator_results": f"https://intelligence.twilio.com/v2/Transcripts/{transcript.sid}/OperatorResults"
            }
        }

        logger.info(
            f"Created transcript with SID: {transcript.sid} using media URL")
        return formatted_response

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
                detail=f"Transcript with SID {transcript_sid} not found"
            )

        # Parse the sentences JSON
        sentences = []
        if transcript.sentences_json:
            try:
                sentences = json.loads(transcript.sentences_json)
            except json.JSONDecodeError:
                logger.error(
                    f"Error parsing sentences JSON for transcript {transcript_sid}")

        # Format the response
        formatted_transcript = {
            "id": transcript.id,
            "transcript_sid": transcript.transcript_sid,
            "status": transcript.status,
            "full_text": transcript.full_text,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "duration": transcript.duration,
            "language_code": transcript.language_code,
            "created_at": str(transcript.created_at) if transcript.created_at else None,
            "sentences": sentences
        }

        return formatted_transcript

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving stored transcript {transcript_sid}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving stored transcript"
        )


@app.get("/realtime/custom-scenarios", response_model=List[dict])
async def get_custom_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all custom scenarios for the current user"""
    try:
        # Get scenarios from database
        db_scenarios = db.query(CustomScenario).filter(
            CustomScenario.user_id == current_user.id
        ).all()

        # Convert to response format
        scenarios = []
        for scenario in db_scenarios:
            scenarios.append({
                "id": scenario.id,
                "scenario_id": scenario.scenario_id,
                "persona": scenario.persona,
                "prompt": scenario.prompt,
                "voice_type": scenario.voice_type,
                "temperature": scenario.temperature,
                "created_at": scenario.created_at
            })

        return scenarios

    except Exception as e:
        logger.error(f"Error getting custom scenarios: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/realtime/custom-scenario/{scenario_id}", response_model=dict)
async def get_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific custom scenario"""
    try:
        # Get scenario from database
        scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found"
            )

        return {
            "id": scenario.id,
            "scenario_id": scenario.scenario_id,
            "persona": scenario.persona,
            "prompt": scenario.prompt,
            "voice_type": scenario.voice_type,
            "temperature": scenario.temperature,
            "created_at": scenario.created_at
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.put("/realtime/custom-scenario/{scenario_id}")
async def update_custom_scenario(
    scenario_id: str,
    persona: str = Body(..., min_length=10, max_length=5000),
    prompt: str = Body(..., min_length=10, max_length=5000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a custom scenario"""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
            )

        # Get scenario from database
        scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found"
            )

        # Update scenario
        scenario.persona = persona
        scenario.prompt = prompt
        scenario.voice_type = voice_type
        scenario.temperature = temperature

        db.commit()
        db.refresh(scenario)

        # Update in-memory dictionary for backward compatibility
        custom_scenario = {
            "persona": persona,
            "prompt": prompt,
            "voice_config": {
                "voice": VOICES[voice_type],
                "temperature": temperature
            }
        }
        CUSTOM_SCENARIOS[scenario_id] = custom_scenario

        return {
            "scenario_id": scenario_id,
            "message": "Custom scenario updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.delete("/realtime/custom-scenario/{scenario_id}", response_model=dict)
async def delete_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a custom scenario"""
    try:
        # Get scenario from database
        scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found"
            )

        # Delete from database
        db.delete(scenario)
        db.commit()

        # Delete from in-memory dictionary
        if scenario_id in CUSTOM_SCENARIOS:
            del CUSTOM_SCENARIOS[scenario_id]

        return {
            "message": "Custom scenario deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting custom scenario: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.api_route("/handle-user-input", methods=["GET", "POST"])
async def handle_user_input(request: Request):
    """Handle user input from the Gather verb."""
    try:
        form_data = await request.form()
        logger.info(f"Received user input: {form_data}")

        # Create a simple response that continues the call
        response = VoiceResponse()
        response.say("Thank you for your input. Continuing the conversation.")

        # Return an empty response to continue the call
        return Response(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"Error handling user input: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
