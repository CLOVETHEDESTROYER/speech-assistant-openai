# MAIN.PY

import os
import json
import base64
import asyncio
import websockets
import logging
import sys
from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware # Add this import
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
from sqlalchemy.orm import Session # Add this import
from pathlib import Path
import sqlalchemy # Ensure this is imported
import threading
import time
from app.auth import router as auth_router, get_current_user
from app.models import User, Token, CallSchedule, UserPhoneNumber
from app.utils import verify_password, create_access_token
from app.schemas import TokenResponse, RealtimeSessionCreate, RealtimeSessionResponse,SignalingMessage, SignalingResponse
from app.db import engine, get_db, SessionLocal, Base
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.realtime_manager import OpenAIRealtimeManager
from os import getenv

# Configure logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

load_dotenv()

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
"aggressive_male": "ash", # Deep, authoritative male voice
"concerned_female": "coral", # Warm, empathetic female voice
"elderly_female": "shimmer", # Gentle, mature female voice
"professional_neutral": "alloy", # Neutral, professional voice
"gentle_supportive": "echo", # Soft-spoken, gentle voice # Warm, engaging storyteller voice (replacing "fable")
"warm_engaging": "ballad", # Deep, commanding voice (replacing "onyx")
"deep_authoritative": "sage", # Lively, energetic voice (replacing "nova")
"energetic_upbeat": "verse",
"clear_optimistic": "shimmer", # Clear, optimistic voice
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
"temperature": 0.8 # More variation for emotional state
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
"temperature": 0.6 # More consistent for maturity
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
"temperature": 0.8 # Higher temperature for more dynamic expression
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
"temperature": 0.7 # Balanced temperature for controlled aggression
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
"temperature": 0.9 # High temperature for maximum expressiveness
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

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
raise ValueError(
"Twilio credentials are not set in the environment variables.")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

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
name: str = Body(...), # Get name from request body
current_user: User = Depends(get_current_user), # Keep authentication
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
async def make_call(
phone_number: str,
scenario: str,
current_user: User = Depends(get_current_user),
db: Session = Depends(get_db)
):
try: # Get user's first available phone number as the caller ID
user_number = db.query(UserPhoneNumber).filter(
UserPhoneNumber.user_id == current_user.id,
UserPhoneNumber.is_active == True,
UserPhoneNumber.voice_capable == True
).first()

        if not user_number:
            raise HTTPException(
                status_code=400,
                detail="No phone number available. Please provision a phone number in Settings first."
            )

        # Use user's phone number as the caller ID
        from_number = user_number.phone_number

        # Rest of the existing logic...
        public_url = os.getenv('PUBLIC_URL', '').strip()
        webhook_url = f"https://{public_url}/incoming-call/{scenario}"

        call = twilio_client.calls.create(
            to=f"+1{phone_number}",
            from_=from_number,  # Use user's number
            url=webhook_url,
            record=True,
            time_limit=90
        )

        return {"message": "Call initiated", "call_sid": call.sid, "from_number": from_number}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Webhook Endpoint for Incoming Calls

@app.api_route("/incoming-call/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call(request: Request, scenario: str):
logger.info(f"Incoming call webhook received for scenario: {scenario}")
try:
form_data = await request.form()
logger.info(f"Received form data: {form_data}")

        response = VoiceResponse()
        response.say("Thanks for calling Hyper labs, How may I help you?")
        response.pause(length=1)

        # Get the host from the request
        host = request.url.hostname
        ws_url = f"wss://{host}/media-stream/{scenario}"

        # Create Connect verb with stream
        connect = Connect()
        stream = Stream(url=ws_url)
        # Add parameters as attributes to the Stream
        stream.parameter("maxDuration", "210")
        connect.append(stream)
        response.append(connect)

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in handle_incoming_call: {e}", exc_info=True)
        raise

# Placeholder for WebSocket Endpoint (Implement as Needed)

async def receive_from_twilio(websocket: WebSocket, openai_ws):
"""Handle incoming audio from Twilio."""
try:
while True:
msg = await websocket.receive_json()
logger.info(f"Received message from Twilio: {msg['event']}")

            if msg["event"] == "media":
                if "payload" not in msg["media"]:
                    logger.error("Missing payload in Twilio media message")
                    continue
                payload = {
                    "type": "input_audio_buffer.append",
                    "audio": msg["media"]["payload"]
                }
                await openai_ws.send(json.dumps(payload))
                logger.info("Sent audio buffer to OpenAI")

            elif msg["event"] == "stop":
                logger.info("Stop event received from Twilio")
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.commit"
                }))
                # Create response after committing audio
                await openai_ws.send(json.dumps({
                    "type": "response.create"
                }))
                logger.info("Requested response from OpenAI")
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in receive_from_twilio: {e}")
        raise

async def send_to_twilio(websocket: WebSocket, openai_ws):
"""Handle outgoing audio to Twilio."""
try:
while True:
message = await openai_ws.recv()
msg = json.loads(message)
logger.info(f"Received message from OpenAI: {msg['type']}")

            if msg["type"] == "response.audio.delta":
                # Forward audio back to Twilio
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": msg["delta"]
                    }
                }))
                logger.info("Sent audio to Twilio")

            elif msg["type"] == "input_audio_buffer.speech_started":
                logger.info("Speech started detected")
                # Handle interruption if needed

            elif msg["type"] == "error":
                logger.error(f"Error from OpenAI: {msg}")
                break

    except WebSocketDisconnect:
        logger.info("OpenAI WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in send_to_twilio: {e}")
        raise

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
"voice": VOICE,
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
            stream_sid = None
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None

            # Initialize session
            await initialize_session(openai_ws, selected_scenario)

            async def check_duration():
                """Monitor call duration and handle timeouts"""
                while True:
                    current_duration = time.time() - start_time
                    remaining_time = MAX_DURATION - current_duration

                    if remaining_time <= WARNING_TIME and remaining_time > WARNING_TIME - 1:
                        # Send warning message through OpenAI
                        warning = {
                            "type": "response.create",
                            "text": "We're approaching the end of our time. Let's wrap up our conversation."
                        }
                        await openai_ws.send(json.dumps(warning))

                    if current_duration >= MAX_DURATION:
                        logger.info("Call reached maximum duration of 3.5 minutes")
                        return

                    await asyncio.sleep(1)

            async def receive_from_twilio():
                """Handle incoming audio from Twilio"""
                nonlocal stream_sid, latest_media_timestamp
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.open:
                            latest_media_timestamp = int(data['media']['timestamp'])
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            logger.info(f"Stream started: {stream_sid}")
                            response_start_timestamp_twilio = None
                            latest_media_timestamp = 0
                            last_assistant_item = None
                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
                except WebSocketDisconnect:
                    logger.info("Twilio WebSocket disconnected")
                    if openai_ws.open:
                        await openai_ws.close()

            async def send_to_twilio():
                """Handle outgoing audio to Twilio"""
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        if response.get('type') == 'error':
                            logger.error(f"Error from OpenAI: {response}")
                            continue

                        if response.get('type') == 'response.audio.delta' and 'delta' in response:
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

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp

                            if response.get('item_id'):
                                last_assistant_item = response['item_id']

                            await send_mark(websocket, stream_sid)

                        elif response.get('type') == 'input_audio_buffer.speech_started':
                            logger.info("Speech started detected")
                            if last_assistant_item:
                                logger.info(f"Interrupting response: {last_assistant_item}")
                                await handle_speech_started_event(
                                    websocket, openai_ws, stream_sid,
                                    last_assistant_item, response_start_timestamp_twilio,
                                    latest_media_timestamp, mark_queue
                                )
                                last_assistant_item = None
                                response_start_timestamp_twilio = None

                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}", exc_info=True)

            # Run all handlers concurrently
            await asyncio.gather(
                check_duration(),
                receive_from_twilio(),
                send_to_twilio()
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        await websocket.close(code=1011)

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
try: # Clean the URL first
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
logger.info(f"clean_url input: {url}") # Debug log
url = url.strip()
url = url.replace('https://', '').replace('http://', '')
url = url.rstrip('/')
logger.info(f"clean_url output: {url}") # Debug log
return url

def clean_and_validate_url(url: str, add_protocol: bool = True) -> str:
"""Clean and validate URL, optionally adding protocol.""" # Remove any existing protocols and whitespace
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
"""Initialize session with OpenAI's new Realtime API."""
user_instruction = (
f"\nUser's name is {USER_CONFIG['name']}. {
USER_CONFIG['instructions']}"
if USER_CONFIG['name']
else ""
)
session_update = {
"type": "session.update",
"session": {
"turn_detection": {
"type": "server_vad",
"threshold": 0.5,
"prefix_padding_ms": 500,
"silence_duration_ms": 500,
"create_response": True
},
"input_audio_format": "g711_ulaw", # Use a valid string
"output_audio_format": "g711_ulaw", # Use a valid string
"instructions": f"{SYSTEM_MESSAGE}{user_instruction}\n\nPersona: {scenario['persona']}\n\nScenario: {scenario['prompt']}",
"voice": scenario["voice_config"]["voice"],
"temperature": scenario["voice_config"]["temperature"],
"modalities": ["text", "audio"]

        }
    }
    logger.info(f'Sending session update: {json.dumps(session_update)}')
    await openai_ws.send(json.dumps(session_update))

async def send_mark(connection, stream_sid):
"""Send mark event to Twilio."""
if stream_sid:
mark_event = {
"event": "mark",
"streamSid": stream_sid,
"mark": {"name": "responsePart"}
}
await connection.send_json(mark_event)
return 'responsePart'

async def handle_speech_started_event(websocket, openai_ws, stream_sid, last_assistant_item=None, \*args, \*\*kwargs):
"""
Handle user interruption more gracefully by truncating the current AI response
and clearing the audio buffer.

    Args:
        websocket: Twilio WebSocket connection.
        openai_ws: OpenAI WebSocket connection.
        stream_sid: Twilio stream session identifier.
        last_assistant_item: ID of the last active response from OpenAI.
        *args: Additional positional arguments (to handle potential mismatches).
        **kwargs: Additional keyword arguments (for future extensibility).
    """
    try:
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
            "streamSid": stream_sid
        })
        logger.info(f"Cleared Twilio audio buffer for streamSid: {stream_sid}")

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
        logger.error(f"Error creating realtime session: {
                     str(e)}", exc_info=True)
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
try: # Verify session belongs to user
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

                    document.getElementById('status').textContent = 'Connected';
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
try: # Get PUBLIC_URL the same way as the standard endpoint
public_url = os.getenv('PUBLIC_URL', '').strip()
logger.info(f"Using PUBLIC_URL from environment: {public_url}")

        if scenario_id not in CUSTOM_SCENARIOS:
            raise HTTPException(
                status_code=400, detail="Custom scenario not found")

        webhook_url = f"https://{public_url}/incoming-custom-call/{scenario_id}"
        logger.info(f"Constructed webhook URL: {webhook_url}")

        call = twilio_client.calls.create(
            to=f"+1{phone_number}",
            from_=TWILIO_PHONE_NUMBER,
            url=webhook_url,
            record=True
        )
        return {"message": "Custom call initiated", "call_sid": call.sid}
    except Exception as e:
        logger.error(f"Error initiating custom call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

        # Connect to OpenAI's WebSocket
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',  # Updated URL
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

            # Initialize session
            await initialize_session(openai_ws, selected_scenario)

            # Use the same receive_from_twilio and send_to_twilio functions
            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.open:
                            latest_media_timestamp = int(
                                data['media']['timestamp'])
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            logger.info(f"Stream started: {stream_sid}")
                            response_start_timestamp_twilio = None
                            latest_media_timestamp = 0
                            last_assistant_item = None
                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
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

# ==============================================================

# URGENT BACKEND IMPLEMENTATION TASK

# ==============================================================

# Backend Implementation: Twilio Account Management & User Phone Number Provisioning

## Context & Overview

The frontend has been updated with a complete Twilio account management system. Users can now access a Settings page (`/settings`) with a "Phone Numbers" tab that allows them to:

- View their Twilio account status and balance
- Provision new phone numbers (with optional area code)
- Manage and release their phone numbers
- See their current phone number inventory

**Frontend API Client Expectations**: The frontend is making calls to these new endpoints:

- `GET /twilio/account` - Get account info
- `POST /twilio/provision-number` - Provision new number
- `DELETE /twilio/release-number/{phone_number}` - Release number
- `GET /twilio/user-numbers` - Get user's numbers

## Required Implementation

### 1. Database Schema Addition

Create a new table to associate users with their phone numbers:

```python
# Add to your models file (app/models.py)

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

# Add to User model:
class User(Base):
    # ... existing fields ...
    phone_numbers = relationship("UserPhoneNumber", back_populates="user")
```

### 2. API Endpoints Implementation

Add these endpoints to your FastAPI main.py:

```python
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import or_
from fastapi import Query

# Pydantic models
class PhoneNumberProvisionRequest(BaseModel):
    area_code: Optional[str] = None

class PhoneNumberResponse(BaseModel):
    sid: str
    phoneNumber: str
    friendlyName: Optional[str]
    capabilities: dict
    dateCreated: str

class TwilioAccountResponse(BaseModel):
    accountSid: str
    balance: str
    status: str

# Endpoints
@app.get("/twilio/account", response_model=TwilioAccountResponse)
async def get_twilio_account(current_user: User = Depends(get_current_user)):
    """Get Twilio account information"""
    try:
        # Fetch account balance from Twilio
        balance = twilio_client.balance.fetch()
        account = twilio_client.api.accounts(TWILIO_ACCOUNT_SID).fetch()

        return TwilioAccountResponse(
            accountSid=TWILIO_ACCOUNT_SID,
            balance=balance.balance,
            status=account.status
        )
    except Exception as e:
        logger.error(f"Error fetching Twilio account: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch account information")

@app.post("/twilio/provision-number")
async def provision_phone_number(
    request: PhoneNumberProvisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Provision a new phone number for the user"""
    try:
        # Search for available numbers
        search_params = {
            'limit': 10,
            'voice_enabled': True,
            'sms_enabled': True
        }

        if request.area_code:
            search_params['area_code'] = request.area_code

        available_numbers = twilio_client.available_phone_numbers('US').local.list(**search_params)

        if not available_numbers:
            raise HTTPException(status_code=404, detail="No available phone numbers found")

        # Purchase the first available number
        selected_number = available_numbers[0]
        purchased_number = twilio_client.incoming_phone_numbers.create(
            phone_number=selected_number.phone_number,
            voice_url=f"https://{os.getenv('PUBLIC_URL')}/incoming-call/default",  # Default webhook
            voice_method='POST'
        )

        # Store in database
        user_phone = UserPhoneNumber(
            user_id=current_user.id,
            phone_number=purchased_number.phone_number,
            twilio_sid=purchased_number.sid,
            friendly_name=purchased_number.friendly_name,
            voice_capable=purchased_number.capabilities.get('voice', False),
            sms_capable=purchased_number.capabilities.get('sms', False)
        )

        db.add(user_phone)
        db.commit()
        db.refresh(user_phone)

        return {
            "phoneNumber": purchased_number.phone_number,
            "sid": purchased_number.sid,
            "message": f"Phone number {purchased_number.phone_number} provisioned successfully"
        }

    except Exception as e:
        logger.error(f"Error provisioning phone number: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to provision phone number: {str(e)}")

@app.get("/twilio/user-numbers")
async def get_user_phone_numbers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get phone numbers assigned to the current user"""
    try:
        user_numbers = db.query(UserPhoneNumber).filter(
            UserPhoneNumber.user_id == current_user.id,
            UserPhoneNumber.is_active == True
        ).all()

        # Enrich with current Twilio data
        enriched_numbers = []
        for user_number in user_numbers:
            try:
                # Fetch current data from Twilio
                twilio_number = twilio_client.incoming_phone_numbers(user_number.twilio_sid).fetch()

                enriched_numbers.append({
                    "sid": twilio_number.sid,
                    "phoneNumber": twilio_number.phone_number,
                    "friendlyName": twilio_number.friendly_name or "No name set",
                    "capabilities": {
                        "voice": twilio_number.capabilities.get('voice', False),
                        "sms": twilio_number.capabilities.get('sms', False)
                    },
                    "dateCreated": user_number.date_provisioned.isoformat()
                })
            except Exception as e:
                logger.warning(f"Could not fetch Twilio data for {user_number.phone_number}: {e}")
                # Fallback to database data
                enriched_numbers.append({
                    "sid": user_number.twilio_sid,
                    "phoneNumber": user_number.phone_number,
                    "friendlyName": user_number.friendly_name or "No name set",
                    "capabilities": {
                        "voice": user_number.voice_capable,
                        "sms": user_number.sms_capable
                    },
                    "dateCreated": user_number.date_provisioned.isoformat()
                })

        return enriched_numbers

    except Exception as e:
        logger.error(f"Error fetching user phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch phone numbers")

@app.delete("/twilio/release-number/{phone_number}")
async def release_phone_number(
    phone_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Release a phone number"""
    try:
        # Verify user owns this number
        user_number = db.query(UserPhoneNumber).filter(
            UserPhoneNumber.user_id == current_user.id,
            UserPhoneNumber.phone_number == phone_number,
            UserPhoneNumber.is_active == True
        ).first()

        if not user_number:
            raise HTTPException(status_code=404, detail="Phone number not found or not owned by user")

        # Release from Twilio
        twilio_client.incoming_phone_numbers(user_number.twilio_sid).delete()

        # Mark as inactive in database (keep for history)
        user_number.is_active = False
        db.commit()

        return {"message": f"Phone number {phone_number} released successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing phone number {phone_number}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to release phone number: {str(e)}")

# ==============================================================
# END OF URGENT BACKEND IMPLEMENTATION TASK
# ==============================================================

if **name** == "**main**":
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=PORT)

# schemas.py

from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
email: EmailStr
password: str

class UserLogin(BaseModel):
email: EmailStr
password: str

class TokenSchema(BaseModel):
access_token: str
refresh_token: str
token_type: str

    class Config:
        orm_mode = True

class TokenData(BaseModel):
email: Optional[str] = None

class TokenResponse(BaseModel):
access_token: str
token_type: str

    class Config:
        orm_mode = True

class RealtimeSessionCreate(BaseModel):
scenario: str
user_id: Optional[int] = None

class RealtimeSessionResponse(BaseModel):
session_id: str
ice_servers: list
created_at: str

class SignalingMessage(BaseModel):
type: str
sdp: Optional[str] = None
candidate: Optional[dict] = None
session_id: str

class SignalingResponse(BaseModel):
type: str
sdp: Optional[str] = None
ice_servers: Optional[list] = None
error: Optional[str] = None

**all** = ["UserCreate", "UserLogin", "TokenSchema", "TokenData", "RealtimeSessionCreate",
"RealtimeSessionResponse", "SignalingMessage", "SignalingResponse"]

# config

import os
from dotenv import load_dotenv
from typing import List, Dict
from typing import List, Dict

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
raise ValueError("SECRET_KEY environment variable is not set")
SECRET_KEY = SECRET_KEY.encode() # Ensure it's in bytes format
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# WebRTC Configuration

WEBRTC_ICE_SERVERS: List[Dict[str, List[str]]] = [
{
"urls": [
"stun:stun.l.google.com:19302",
"stun:stun1.l.google.com:19302",
]
}
]

# Add custom TURN servers if configured

TURN_SERVER = os.getenv('TURN_SERVER')
TURN_USERNAME = os.getenv('TURN_USERNAME')
TURN_CREDENTIAL = os.getenv('TURN_CREDENTIAL')

if all([TURN_SERVER, TURN_USERNAME, TURN_CREDENTIAL]):
WEBRTC_ICE_SERVERS.append({
"urls": [TURN_SERVER],
"username": TURN_USERNAME,
"credential": TURN_CREDENTIAL
})

# Audio Configuration

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "pcm16"

# OpenAI Configuration

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
raise ValueError("OPENAI_API_KEY environment variable is not set")

# Session Configuration

MAX_SESSION_DURATION = 3600 # 1 hour in seconds
SESSION_CLEANUP_INTERVAL = 300 # 5 minutes in seconds
```
