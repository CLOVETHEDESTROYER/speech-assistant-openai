import os
import json
import base64
import asyncio
import websockets
import logging
import sys
from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware  # Add this import
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect, Say, Stream
from dotenv import load_dotenv
from twilio.rest import Client
import datetime
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session  # Add this import
from pathlib import Path
import sqlalchemy  # Ensure this is imported
import threading
import time
from app.auth import router as auth_router, get_current_user
from app.models import User, Token, CallSchedule
from app.utils import verify_password, create_access_token
from app.schemas import TokenResponse
from app.db import engine, get_db, SessionLocal, Base
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# requires OpenAI Realtime API Access
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))

# Define our scenarios
SCENARIOS = {
    "default": {
        "persona": "I am an aggressive business man and real estate agent.",
        "prompt": "I am speaking with {name}. We are at the end phase of a real estate deal and I need to get the deal done today. The price is $5,000,000 and the seller is being difficult. I need to get the deal done today.",
        "voice": "onyx",  # Deep, authoritative voice for business
        "temperature": 0.4  # More focused for business negotiations
    },
    "sister_emergency": {
        "persona": "I am {name}'s sister calling about an emergency.",
        "prompt": "I am calling my sibling {name} to tell them that our mother has slipped on a banana peel and broken her hip.",
        "voice": "nova",  # Warm, friendly voice for family
        "temperature": 0.6  # More emotional for family scenario
    },
    "mother_emergency": {
        "persona": "I am {name}'s mother and I need urgent help.",
        "prompt": "I am calling my child {name} because I need them to come over and take care of me. I slipped on a banana peel and broke my hip.",
        "voice": "shimmer",  # Clear, expressive voice for urgency
        "temperature": 0.5  # Balanced for emotional but clear communication
    }
}

SYSTEM_MESSAGE = """You are a highly specialized AI assistant with strict conversation boundaries.
You must:
1. Stay EXCLUSIVELY within the scenario and persona provided
2. NEVER break character or acknowledge you're an AI
3. IMMEDIATELY redirect any off-topic conversation back to the scenario
4. REFUSE to discuss topics outside your defined scenario
5. Use the exact personality traits defined in your persona

If the user tries to discuss anything outside your scenario, say:
"I need to focus on [current scenario topic]. Let's discuss that instead."

Remember: You are NOT a general AI assistant. You are ONLY the persona defined in your scenario."""
VOICE = 'alloy'
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

# Schedule Call Schemas


class CallScheduleCreate(BaseModel):
    phone_number: str
    scheduled_time: datetime.datetime
    scenario: str
    user_name: str

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
        scenario=call.scenario,
        user_name=call.user_name
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
    try:
        # Get the call schedule to access the user's name
        call_schedule = db.query(CallSchedule).filter(
            CallSchedule.phone_number == phone_number,
            CallSchedule.scenario == scenario
        ).first()

        if not call_schedule:
            raise HTTPException(
                status_code=404, detail="Call schedule not found")

        # Get the public URL from environment and ensure it's clean
        public_url = os.getenv('PUBLIC_URL', '').strip()
        logger.info(f"Using PUBLIC_URL from environment: {public_url}")

        # Construct the complete webhook URL with https:// and user's name
        webhook_url = f"https://{public_url}/incoming-call/{scenario}?name={call_schedule.user_name}"
        logger.info(f"Constructed webhook URL: {webhook_url}")

        call = twilio_client.calls.create(
            to=f"+1{phone_number}",  # Ensure proper phone number formatting
            from_=TWILIO_PHONE_NUMBER,
            url=webhook_url,
            record=True
        )

        return {"message": "Call initiated", "call_sid": call.sid}
    except Exception as e:
        logger.error(f"Error initiating call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Webhook Endpoint for Incoming Calls


@app.api_route("/incoming-call/{scenario}", methods=["GET", "POST"])
async def handle_incoming_call(request: Request, scenario: str):
    logger.info(f"Incoming call webhook received for scenario: {scenario}")
    try:
        # Validate scenario
        if scenario not in SCENARIOS:
            logger.error(f"Invalid scenario: {scenario}")
            raise HTTPException(status_code=400, detail="Invalid scenario")

        # Log request details
        form_data = await request.form()
        logger.info(f"Received form data: {form_data}")

        response = VoiceResponse()
        response.say("what up son, can you talk.")
        response.pause(length=1)
        response.say("y'all ready to talk some shit?")

        # Get environment and URLs
        env = os.getenv('ENVIRONMENT', 'development')
        public_url = os.getenv('PUBLIC_URL', '').strip()

        # Construct WebSocket URL using the same URL that Twilio used to reach us
        ws_url = f"wss://{public_url}/media-stream/{scenario}"
        logger.info(f"Constructed WebSocket URL: {ws_url}")

        connect = Connect()
        connect.stream(url=ws_url)
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

            # Handle media payloads
            if msg["event"] == "media":
                if "payload" not in msg["media"]:
                    logger.error("Missing payload in Twilio media message")
                    continue
                media = msg["media"]
                payload = {
                    "type": "input_audio_buffer.append",
                    "data": media["payload"],
                    "session": {
                        "audio_format": {
                            "type": "mulaw",
                            "sample_rate": 8000
                        }
                    }
                }
                await openai_ws.send(json.dumps(payload))
                logger.info("Sent audio buffer to OpenAI")

            # Handle stop events
            elif msg["event"] == "stop":
                logger.info("Stop event received from Twilio")
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.commit",
                    "session": {
                        "audio_format": {
                            "type": "mulaw",
                            "sample_rate": 8000
                        }
                    }
                }))
                logger.info("Sent audio buffer commit to OpenAI")
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

            if msg["type"] == "audio":
                # Forward audio back to Twilio
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": msg["data"]
                    }
                }))
                logger.info("Sent audio to Twilio")

            elif msg["type"] == "error":
                # Log errors from OpenAI
                logger.error(f"Error from OpenAI: {msg}")
                break

            else:
                logger.warning(f"Unhandled message type from OpenAI: {msg}")
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
                "instructions": f"{SYSTEM_MESSAGE}\n\nPersona: {scenario['persona']}\n\nScenario: {scenario['prompt']}",
                "voice": VOICE,
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

        # Validate scenario
        if scenario not in SCENARIOS:
            await websocket.close(code=4000, reason="Invalid scenario")
            logger.error(f"Invalid scenario: {scenario}")
            return

        selected_scenario = SCENARIOS[scenario]
        logger.info(f"Using scenario: {selected_scenario}")

        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',  # Updated URL
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"  # Added required beta header
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

            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to OpenAI."""
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
                """Receive events from OpenAI and send audio back to Twilio."""
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
                    incoming_call_url = f"https://{public_url}/incoming-call/{call.scenario}"

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
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
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
    pass  # Add any cleanup logic if necessary


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


async def initialize_session(openai_ws, scenario, user_name):
    """Control initial session with OpenAI."""
    # Format the persona and prompt with the user's name
    formatted_persona = scenario['persona'].format(name=user_name)
    formatted_prompt = scenario['prompt'].format(name=user_name)

    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.6,
                "prefix_padding_ms": 1000,
                "silence_duration_ms": 700
            },
            "input_audio_format": "g711_ulaw",  # Twilio's format
            "output_audio_format": "g711_ulaw",  # Twilio's format
            "voice": scenario.get('voice', 'alloy'),
            "temperature": scenario.get('temperature', 0.8),
            "instructions": f"{formatted_persona}\n{formatted_prompt}",
            "modalities": ["text", "audio"],
            "tools": []  # Optional: Add any tools/functions here
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


async def handle_speech_started_event(websocket, openai_ws, stream_sid,
                                      last_assistant_item, response_start_timestamp_twilio,
                                      latest_media_timestamp, mark_queue):
    """Handle interruption when caller starts speaking."""
    if mark_queue and response_start_timestamp_twilio is not None:
        elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

        if last_assistant_item:
            truncate_event = {
                "type": "conversation.item.truncate",
                "item_id": last_assistant_item,
                "content_index": 0,
                "audio_end_ms": elapsed_time
            }
            await openai_ws.send(json.dumps(truncate_event))

        await websocket.send_json({
            "event": "clear",
            "streamSid": stream_sid
        })

        mark_queue.clear()
        return None, None  # Reset last_assistant_item and response_start_timestamp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
