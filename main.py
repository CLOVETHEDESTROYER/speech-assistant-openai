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
from starlette.websockets import WebSocketState  # Add this at the top

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
        "prompt": "We are at the end phase of a real estate deal and I need to get the deal done today.  The price is $5,000,000 and the seller is being difficult.  I need to get the deal done today."
    },
    "sister_emergency": {
        "persona": "I am an experienced hiring manager conducting a job interview.",
        "prompt": "You will act as a sister calling to tell you that your mother has slipped on a banana peel and broken her hip."
    },
    "mother_emergency": {
        "persona": "I your mother and I am calling to tell you that I slipped on a banana peel and broke my hip.",
        "prompt": "I am your mother and I need you to come over and take care of me because I slipped on a banana peel and broke my hip."
    }
}

SYSTEM_MESSAGE = (
    "You are a AI assistant who will adapt to the prompts provided by the user to chat about "
    "the scenarios in depth, you will have an engaging backand forth conversation with. "
    "Your persona is defined by the scenario and prompt provided by the user. "
    "You can change your personality to match the scenario and prompt."
)
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
    try:
        # Get the public URL from environment and ensure it's clean
        public_url = os.getenv('PUBLIC_URL', '').strip()
        logger.info(f"Using PUBLIC_URL from environment: {public_url}")

        # Construct the complete webhook URL with https://
        webhook_url = f"https://{public_url}/incoming-call/{scenario}"
        logger.info(f"Constructed webhook URL: {webhook_url}")

        # Initialize Twilio client
        # twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # Make the call using Twilio
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

        # Get the host from the request
        host = request.headers.get('Host', 'voice.hyperlabsai.com')

        # Construct WebSocket URL with explicit protocol
        ws_url = f"wss://{host}/media-stream/{scenario}"

        # Log the WebSocket URL we're using
        logger.info(f"Setting up WebSocket connection to: {ws_url}")

        # Add Stream connection
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
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": msg["audio"]
                    }
                }))
                logger.info("Sent audio to Twilio")

            elif msg["type"] == "error":
                logger.error(f"Error from OpenAI: {msg}")
                break

            elif msg["type"] in LOG_EVENT_TYPES:
                logger.info(f"OpenAI event: {msg}")

    except WebSocketDisconnect:
        logger.info("OpenAI WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in send_to_twilio: {e}")
        raise


@app.websocket("/media-stream/{scenario}")
async def handle_media_stream(websocket: WebSocket, scenario: str):
    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        selected_scenario = SCENARIOS.get(scenario)
        if not selected_scenario:
            await websocket.close(code=4000)
            return

        # Connect to OpenAI's Realtime API
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }

        async with websockets.connect(url, extra_headers=headers) as openai_ws:
            logger.info("Connected to OpenAI WebSocket")

            # Send initial configuration
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": f"{SYSTEM_MESSAGE}\n\nPersona: {selected_scenario['persona']}\n\nScenario: {selected_scenario['prompt']}",
                    "voice": "alloy",
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.6,
                        "prefix_padding_ms": 1000,
                        "silence_duration_ms": 700
                    },
                    "temperature": 0.8
                }
            }

            await openai_ws.send(json.dumps(session_config))
            logger.info("Session configuration sent")

            # Start the audio handling tasks
            audio_tasks = [
                asyncio.create_task(receive_from_twilio(websocket, openai_ws)),
                asyncio.create_task(send_to_twilio(websocket, openai_ws))
            ]

            # Wait for either task to complete
            done, pending = await asyncio.wait(
                audio_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket handler error: {str(e)}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1011)
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


@app.post("/incoming-call", response_class=Response)
async def incoming_call(request: Request, scenario: str):
    response = VoiceResponse()
    response.say("Hello! This is your speech assistant powered by OpenAI.")
    return Response(content=str(response), media_type="application/xml")


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


@app.websocket("/ws-test")
async def websocket_test(websocket: WebSocket):
    await websocket.accept()
    logger.info("Test WebSocket connection accepted")
    try:
        await websocket.send_text("WebSocket connection test successful")
    except Exception as e:
        logger.error(f"WebSocket test error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
