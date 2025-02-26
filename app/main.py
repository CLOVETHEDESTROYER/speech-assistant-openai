import os
import json
import base64
import asyncio
import websockets
import logging
import sys
from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect, Say, Stream
from dotenv import load_dotenv
from twilio.rest import Client
import datetime
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Dict
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pathlib import Path
import sqlalchemy
import threading
import time
from app.auth import router as auth_router, get_current_user
from app.models import User, Token, CallSchedule, Conversation
from app.utils import verify_password, create_access_token
from app.schemas import TokenResponse, RealtimeSessionCreate, RealtimeSessionResponse, SignalingMessage, SignalingResponse
from app.db import engine, get_db, SessionLocal, Base
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.realtime_manager import OpenAIRealtimeManager
from os import getenv
from app.services.conversation_service import ConversationService
from app.services.transcription import TranscriptionService
from app.routers.transcripts import router as transcripts_router
from twilio.request_validator import RequestValidator
import traceback
import openai
from openai import OpenAI
from twilio.base.exceptions import TwilioRestException
import io
import tempfile
import subprocess
import requests
import re

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

# Create database tables (do this only once)
Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(auth_router)
app.include_router(transcripts_router, tags=["transcripts"])

if not OPENAI_API_KEY:
    raise ValueError(
        'Missing the OpenAI API key. Please set it in the .env file.')


# Pydantic Schemas


class UserRead(BaseModel):
    id: int
    email: EmailStr
    is_active: bool

    class Config:
        orm_mode = True


# Password Hashing and JWT Utilities
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration

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
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Basic validation without making API calls
if not TWILIO_ACCOUNT_SID or not TWILIO_ACCOUNT_SID.startswith('AC'):
    logger.error("Invalid or missing TWILIO_ACCOUNT_SID")
if not TWILIO_AUTH_TOKEN or len(TWILIO_AUTH_TOKEN) != 32:
    logger.error("Invalid or missing TWILIO_AUTH_TOKEN")
if not TWILIO_PHONE_NUMBER or not TWILIO_PHONE_NUMBER.startswith('+'):
    logger.error("Invalid or missing TWILIO_PHONE_NUMBER")

# Initialize client without testing connection
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("Twilio client initialized")
except Exception as e:
    logger.error(f"Error initializing Twilio client: {str(e)}")
    twilio_client = None

# User Login Endpoint


@app.post("/token", response_model=TokenResponse)
async def login_for_access_token(
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
def protected_route(current_user: User = Depends(get_current_user)):
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
        orm_mode = True

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

        # Construct the webhook URL with proper protocol
        host = os.environ.get('PUBLIC_URL')
        if not host:
            logger.error("PUBLIC_URL environment variable not set")
            return JSONResponse(
                status_code=500,
                content={"error": "Server configuration error"}
            )

        # Ensure the URL has the https:// protocol
        if not host.startswith('http://') and not host.startswith('https://'):
            host = f"https://{host}"

        # Use the correct route path that matches the defined endpoint
        webhook_url = f"{host}/incoming-call/{scenario}"
        logger.info(f"Using webhook URL: {webhook_url}")

        # Create the call using Twilio
        call = twilio_client.calls.create(
            to=f"+1{phone_number}",
            from_=TWILIO_PHONE_NUMBER,
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

# Webhook Endpoint for Incoming Calls


@app.api_route("/incoming-call/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call(request: Request, scenario: str):
    logger.info(f"Incoming call webhook received for scenario: {scenario}")
    try:
        if scenario not in SCENARIOS:
            logger.error(f"Invalid scenario: {scenario}")
            raise HTTPException(status_code=400, detail="Invalid scenario")

        response = VoiceResponse()
        response.say("what up son, can you talk.")
        response.pause(length=1)
        response.say("y'all ready to talk some shit?")

        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream/{scenario}"

        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(
            f"Error in handle_incoming_call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Add a compatibility route for the old webhook URL format
@app.api_route("/incoming-call-webhook/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call_webhook(request: Request, scenario: str):
    """Compatibility route that redirects to the main incoming-call route."""
    logger.info(
        f"Received call on compatibility webhook route for scenario: {scenario}")
    return await handle_incoming_call(request, scenario)

# Placeholder for WebSocket Endpoint (Implement as Needed)


async def receive_from_twilio(websocket: WebSocket, openai_ws, shared_state):
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            logger.info(f"Received Twilio message: {data['event']}")

            if data["event"] == "media":
                audio_data = base64.b64decode(data["media"]["payload"])
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": data["media"]["payload"]
                }))
                logger.info("Audio buffer appended to OpenAI stream")

            elif data["event"] == "start":
                shared_state["stream_sid"] = data["start"]["streamSid"]
                logger.info(f"Stream started: {shared_state['stream_sid']}")

            elif data["event"] == "stop":
                logger.info("Stop event received from Twilio")
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.commit"
                }))
                await openai_ws.send(json.dumps({
                    "type": "response.create"  # Explicitly request a response
                }))
                logger.info("Requested response from OpenAI")
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in receive_from_twilio: {str(e)}", exc_info=True)


async def send_to_twilio(websocket: WebSocket, openai_ws, shared_state):
    last_assistant_item = None
    response_start_timestamp_twilio = None
    try:
        while True:
            openai_message = await openai_ws.recv()
            response = json.loads(openai_message)
            logger.info(f"OpenAI response: {response}")  # Log full response

            if response.get('type') == 'error':
                logger.error(f"Error from OpenAI: {response}")
                continue

            if response.get('type') == 'response.audio.delta' and 'delta' in response:
                # Log part of the delta
                logger.info(
                    f"Audio delta received: {response['delta'][:50]}...")
                try:
                    # Make sure we have a stream_sid before proceeding
                    if shared_state["stream_sid"] is None:
                        logger.warning(
                            "No stream_sid available, skipping audio delta")
                        continue

                    # Decode and re-encode to verify
                    audio_bytes = base64.b64decode(response['delta'])
                    audio_payload = base64.b64encode(
                        audio_bytes).decode('utf-8')
                    logger.info(
                        f"Re-encoded audio payload sample: {audio_payload[:50]}...")
                    audio_delta = {
                        "event": "media",
                        "streamSid": shared_state["stream_sid"],
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await websocket.send_json(audio_delta)
                    logger.info("Audio delta sent to Twilio")
                except Exception as e:
                    logger.error(f"Audio payload processing error: {str(e)}")

                if response.get('item_id'):
                    last_assistant_item = response['item_id']

                await send_mark(websocket, shared_state["stream_sid"])

            elif response.get('type') == 'input_audio_buffer.speech_started':
                logger.info("Speech started detected")
                if last_assistant_item:
                    await handle_speech_started_event(websocket, openai_ws, shared_state["stream_sid"], last_assistant_item)
                    last_assistant_item = None
                    response_start_timestamp_twilio = None
            elif response.get('type') == 'response.done':
                logger.info("Response completed")

    except WebSocketDisconnect:
        logger.info("OpenAI WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in send_to_twilio: {str(e)}", exc_info=True)


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
    logger.info(f"WebSocket connection attempt for scenario: {scenario}")
    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        # Initialize duration tracking
        start_time = time.time()
        MAX_DURATION = 210  # 3.5 minutes in seconds
        WARNING_TIME = 30   # Warn when 30 seconds remaining

        if scenario not in SCENARIOS:
            await websocket.close(code=4000, reason="Invalid scenario")
            logger.error(f"Invalid scenario: {scenario}")
            return

        selected_scenario = SCENARIOS[scenario]
        logger.info(f"Using scenario: {selected_scenario}")

        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            logger.info("Connected to OpenAI WebSocket")

            # Connection specific state
            # Use a mutable container to share stream_sid between coroutines
            shared_state = {"stream_sid": None}
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None
            current_transcript = ""  # Initialize current_transcript
            db = SessionLocal()

            # Initialize session
            await initialize_session(openai_ws, selected_scenario)

            # Create tasks for all handlers
            duration_task = asyncio.create_task(check_duration(
                openai_ws, start_time, MAX_DURATION, WARNING_TIME))
            receive_task = asyncio.create_task(
                receive_from_twilio(websocket, openai_ws, shared_state))
            send_task = asyncio.create_task(
                send_to_twilio(websocket, openai_ws, shared_state))

            # Wait for all tasks to complete
            await asyncio.gather(duration_task, receive_task, send_task)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        await websocket.close(code=1011)
    finally:
        try:
            db.close()
            await websocket.close()
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True)


async def check_duration(openai_ws, start_time, max_duration, warning_time):
    """Monitor call duration and handle timeouts"""
    try:
        while True:
            current_duration = time.time() - start_time
            remaining_time = max_duration - current_duration

            if remaining_time <= warning_time and remaining_time > warning_time - 1:
                # Send warning message through OpenAI
                warning = {
                    "type": "response.create",
                    "text": "We're approaching the end of our time. Let's wrap up our conversation."
                }
                await openai_ws.send(json.dumps(warning))

            if current_duration >= max_duration:
                logger.info("Call reached maximum duration of 3.5 minutes")
                return

            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Error in check_duration: {str(e)}")

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
            for call in calls:
                try:
                    # Clean the URL first
                    public_url = os.getenv('PUBLIC_URL', '').strip()
                    public_url = public_url.replace(
                        'https://', '').replace('http://', '')

                    # Construct the webhook URL
                    incoming_call_url = f"https://{
                        public_url}/incoming-call/{call.scenario}"

                    twilio_client.calls.create(
                        url=incoming_call_url,
                        to=call.phone_number,
                        from_=TWILIO_PHONE_NUMBER
                    )
                    logger.info(
                        f"Scheduled call initiated to {call.phone_number} with ID: {call.id}")
                    db_local.delete(call)
                except Exception as e:
                    logger.error(f"Failed to initiate scheduled call: {e}")
            db_local.commit()
        except Exception as e:
            logger.error(f"Error in initiate_scheduled_calls: {e}")
        finally:
            db_local.close()
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


async def initialize_session(openai_ws, scenario):
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
                    "threshold": 0.3,  # Lower threshold to detect speech more easily
                    "prefix_padding_ms": 300,  # Reduce padding
                    "silence_duration_ms": 1000,  # Increase silence duration before cutting off
                    "create_response": True
                },
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "instructions": f"{SYSTEM_MESSAGE}\n\nPersona: {scenario['persona']}\n\nScenario: {scenario['prompt']}",
                "voice": scenario["voice_config"]["voice"],
                "modalities": ["text", "audio"],
                "temperature": 0.8
            }
        }

        logger.info(
            f"Sending session update: {json.dumps(session_data, indent=2)}")
        await openai_ws.send(json.dumps(session_data))
        logger.info(f"Session update sent for persona: {scenario['persona']}")
    except Exception as e:
        logger.error(f"Error sending session update: {e}")
        raise


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
                "audio_end_ms": int(time.time() * 1000)
            }
            try:
                await openai_ws.send(json.dumps(truncate_event))
            except Exception as e:
                logger.error(f"Error sending truncate event: {e}")
                logger.info(
                    f"Sent truncate event for item ID: {last_assistant_item}")

        # Clear Twilio's audio buffer
        await websocket.send_json({
            "event": "clear",
            "streamSid": actual_stream_sid
        })
        logger.info(
            f"Cleared Twilio audio buffer for streamSid: {actual_stream_sid}")

        # Optional: Small pause before accepting new input
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Error in handle_speech_started_event: {e}")

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
    persona: str = Body(..., min_length=10, max_length=1000),
    prompt: str = Body(..., min_length=10, max_length=1000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user)
):
    """Create a custom scenario"""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
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

        # Store in custom scenarios
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
    current_user: User = Depends(get_current_user)
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

        if scenario_id not in CUSTOM_SCENARIOS:
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

        call = twilio_client.calls.create(
            to=f"+1{phone_number}",
            from_=TWILIO_PHONE_NUMBER,
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
async def handle_incoming_custom_call(request: Request, scenario_id: str):
    logger.info(
        f"Incoming custom call webhook received for scenario: {scenario_id}")
    try:
        if scenario_id not in CUSTOM_SCENARIOS:
            logger.error(f"Custom scenario not found: {scenario_id}")
            raise HTTPException(
                status_code=400, detail="Custom scenario not found")

        form_data = await request.form()
        logger.info(f"Received form data: {form_data}")

        response = VoiceResponse()
        response.say("Connecting to your custom AI call.")
        response.pause(length=1)

        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream-custom/{scenario_id}"

        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(
            f"Error in handle_incoming_custom_call: {e}", exc_info=True)
        raise


@app.websocket("/media-stream-custom/{scenario_id}")
async def handle_custom_media_stream(websocket: WebSocket, scenario_id: str):
    logger.info(
        f"WebSocket connection attempt for custom scenario: {scenario_id}")
    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        if scenario_id not in CUSTOM_SCENARIOS:
            logger.error(f"Invalid custom scenario: {scenario_id}")
            await websocket.close(code=4000)
            return

        selected_scenario = CUSTOM_SCENARIOS[scenario_id]
        logger.info(f"Using custom scenario: {selected_scenario}")

        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            logger.info("Connected to OpenAI WebSocket")

            # Connection specific state
            stream_sid = None
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None
            current_transcript = ""

            # Initialize session
            await initialize_session(openai_ws, selected_scenario)

            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp, current_transcript
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        if data['event'] == 'media':
                            latest_media_timestamp = int(
                                data['media']['timestamp'])
                            # Forward the audio directly to OpenAI
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))
                            logger.info("Audio forwarded to OpenAI")
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            logger.info(f"Stream started: {stream_sid}")
                except WebSocketDisconnect:
                    logger.info("Twilio WebSocket disconnected")
                    if openai_ws.open:
                        await openai_ws.close()

            async def send_to_twilio():
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        if response.get('type') == 'error':
                            logger.error(f"Error from OpenAI: {response}")
                            continue

                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
                            logger.info("Received audio delta from OpenAI")
                            audio_payload = base64.b64encode(
                                base64.b64decode(response['delta'])).decode('utf-8')
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                            logger.info("Audio sent to Twilio successfully")

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp

                            if response.get('item_id'):
                                last_assistant_item = response['item_id']

                            await send_mark(websocket, stream_sid)

                        elif response.get('type') == 'input_audio_buffer.speech_started':
                            logger.info("Speech started detected")
                            if last_assistant_item:
                                logger.info(
                                    f"Interrupting response: {last_assistant_item}")
                                await handle_speech_started_event(
                                    websocket, openai_ws, stream_sid,
                                    last_assistant_item, response_start_timestamp_twilio,
                                    latest_media_timestamp, mark_queue
                                )
                                last_assistant_item = None
                                response_start_timestamp_twilio = None

                except Exception as e:
                    logger.error(
                        f"Error in send_to_twilio: {e}", exc_info=True)

            # Run both handlers concurrently
            await asyncio.gather(
                receive_from_twilio(),
                send_to_twilio()
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        await websocket.close(code=1011)

# Initialize the transcription service
transcription_service = TranscriptionService()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    await websocket.accept()
    try:
        # Get user from session or token
        # This needs to be implemented based on your authentication strategy
        user_id = None  # Replace with actual user ID from session

        while True:
            # Receive audio data
            audio_data = await websocket.receive_bytes()

            # Transcribe user audio
            user_transcript = await transcription_service.transcribe_audio(audio_data)

            # Save user's part of conversation
            await transcription_service.save_conversation(
                db=db,
                call_sid=session_id,
                phone_number="anonymous",  # or get from session
                direction="inbound",
                scenario="default",  # or get from session
                transcript=user_transcript,
                user_id=user_id  # Use the retrieved user_id
            )

            # Get AI response
            ai_response = await get_ai_response(user_transcript)

            # Save AI's part of conversation
            await transcription_service.save_conversation(
                db=db,
                call_sid=session_id,
                phone_number="AI",
                direction="outbound",
                scenario="default",
                transcript=ai_response,
                user_id=user_id
            )

            await websocket.send_text(json.dumps({
                "type": "text",
                "content": ai_response
            }))

    except WebSocketDisconnect:
        print(f"Client disconnected from session {session_id}")


@app.websocket("/stream")
async def stream_endpoint(websocket: WebSocket):
    logger.info("WebSocket connection attempt")
    shared_state = {"stream_sid": None}
    db = None

    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        # Initialize connection state
        db = SessionLocal()

        # Connect to OpenAI's Realtime API
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
            extra_headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'OpenAI-Beta': 'realtime=v1'
            }
        ) as openai_ws:
            logger.info("Connected to OpenAI Realtime WebSocket")

            # Initialize session with default scenario
            await initialize_session(openai_ws, SCENARIOS['default'])
            logger.info("Session initialized with default scenario")

            # Create tasks for receiving and sending
            receive_task = asyncio.create_task(
                receive_from_twilio(websocket, openai_ws, shared_state))
            send_task = asyncio.create_task(
                send_to_twilio(websocket, openai_ws, shared_state))

            # Wait for both tasks to complete
            await asyncio.gather(receive_task, send_task)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}", exc_info=True)
    finally:
        # Clean up resources
        if db:
            try:
                db.close()
                logger.info("Database connection closed")
            except Exception as db_error:
                logger.error(
                    f"Error closing database: {str(db_error)}", exc_info=True)

        try:
            await websocket.close()
            logger.info("WebSocket connection closed")
        except Exception as ws_error:
            logger.error(
                f"Error closing WebSocket: {str(ws_error)}", exc_info=True)

# Add new endpoint for recording callback


@app.post("/recording-callback")
async def handle_recording_callback(request: Request, db: Session = Depends(get_db)):
    try:
        form_data = await request.form()
        recording_url = form_data.get('RecordingUrl')
        call_sid = form_data.get('CallSid')
        recording_sid = form_data.get('RecordingSid')

        logger.info(f"Recording completed for call {call_sid}")

        if recording_url:
            # Download the recording
            recording_response = requests.get(f"{recording_url}.mp3")
            audio_data = io.BytesIO(recording_response.content)

            # Transcribe using OpenAI Whisper
            transcript = await transcription_service.transcribe_audio(audio_data)

            # Update conversation record with transcript
            conversation = db.query(Conversation).filter(
                Conversation.call_sid == call_sid
            ).first()

            if conversation:
                conversation.transcript = transcript
                db.commit()
                logger.info(f"Transcript saved for call {call_sid}")

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing recording: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
