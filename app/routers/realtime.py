import time
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Body, status, WebSocket
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db import get_db
from app import config
from app.limiter import rate_limit
from app.models import User, CustomScenario
from app.schemas import RealtimeSessionCreate, RealtimeSessionResponse, SignalingMessage, SignalingResponse
from app.realtime_manager import OpenAIRealtimeManager
from app.utils.websocket import websocket_manager
from app.app_config import SCENARIOS, USER_CONFIG
import websockets
import asyncio
import json
import logging
import base64
import struct
from datetime import datetime
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

router = APIRouter()

realtime_manager = OpenAIRealtimeManager(config.OPENAI_API_KEY)


@router.post("/realtime/session", response_model=RealtimeSessionResponse)
@rate_limit("5/minute")
async def create_realtime_session(
    request: Request,
    session_data: RealtimeSessionCreate,
    current_user: User = Depends(get_current_user)
):
    try:
        # Handle both scenario and scenario_id for backward compatibility
        scenario_key = session_data.scenario or session_data.scenario_id

        if not scenario_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either scenario or scenario_id must be provided"
            )

        # Validate scenario exists
        if scenario_key not in SCENARIOS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scenario: {scenario_key}"
            )

        user_id = session_data.user_id or current_user.id
        session_info = await realtime_manager.create_session(str(user_id), SCENARIOS[scenario_key])
        return session_info
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/realtime/signal", response_model=SignalingResponse)
async def handle_signaling(
    signal: SignalingMessage,
    current_user: User = Depends(get_current_user)
):
    try:
        session = realtime_manager.get_session(signal.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if str(session["user_id"]) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Not authorized to access this session")
        response = await realtime_manager.handle_signaling(signal.session_id, {"type": signal.type, "sdp": signal.sdp, "candidate": signal.candidate})
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/test-realtime", response_class=HTMLResponse)
async def test_realtime_page():
    # Lightweight test page (copied from main to keep endpoint stable)
    return HTMLResponse(content="<html><body>Realtime OK</body></html>")


# WebSocket/media stream endpoints moved from main
@router.websocket("/media-stream/{scenario}")
async def handle_media_stream(websocket: WebSocket, scenario: str):
    """Handle media stream for Twilio calls with enhanced interruption handling."""
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
                            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
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
                            "reconnecting": False,
                            "ai_speaking": False,
                            "user_speaking": False,
                            "scenario": selected_scenario  # Add scenario for function calling
                        }

                        # Initialize conversation state for enhanced interruption handling
                        from app.main import ConversationState
                        conversation_state = ConversationState()
                        shared_state["conversation_state"] = conversation_state

                        # Initialize session with the selected scenario
                        from app.main import initialize_session
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
                        from app.main import send_initial_greeting
                        greeting_task = asyncio.create_task(
                            send_initial_greeting(openai_ws, selected_scenario))

                        # Create tasks for receiving and sending with enhanced state management
                        from app.main import receive_from_twilio, send_to_twilio

                        # ✅ DEBUG: Log that we're starting WebSocket tasks
                        logger.info(
                            f"🚀 Starting WebSocket tasks for scenario: {scenario}")

                        receive_task = asyncio.create_task(
                            receive_from_twilio(ws, openai_ws, shared_state))
                        send_task = asyncio.create_task(
                            send_to_twilio(ws, openai_ws, shared_state, conversation_state))

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
                                f"Greeting timeout after {GREETING_TIMEOUT} seconds, continuing with call")
                        except Exception as e:
                            logger.error(f"Error during greeting: {e}")

                        # Wait for both tasks to complete
                        try:
                            await asyncio.gather(receive_task, send_task, return_exceptions=True)
                        except Exception as e:
                            logger.error(f"Error in main tasks: {e}")

                        # Check if we should reconnect
                        if shared_state.get("should_stop"):
                            logger.info(
                                "Call ended normally, not reconnecting")
                            break

                        # If we get here, we need to reconnect
                        reconnect_attempts += 1
                        if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                            logger.warning(
                                f"Connection lost, attempting reconnect {reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS}")
                            shared_state["reconnecting"] = True
                            await asyncio.sleep(RECONNECT_DELAY)
                        else:
                            logger.error("Max reconnection attempts reached")
                            break

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("OpenAI WebSocket connection closed")
                    reconnect_attempts += 1
                    if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                        await asyncio.sleep(RECONNECT_DELAY)
                    else:
                        break
                except Exception as e:
                    logger.error(f"Error in reconnection loop: {e}")
                    reconnect_attempts += 1
                    if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                        await asyncio.sleep(RECONNECT_DELAY)
                    else:
                        break

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in media stream: {str(e)}", exc_info=True)
        finally:
            # Cleanup
            pass


@router.websocket("/update-scenario/{scenario}")
async def handle_scenario_update(websocket: WebSocket, scenario: str):
    await websocket.accept()
    try:
        await websocket.send_text(json.dumps({"status": "ok"}))
    except Exception:
        pass
    finally:
        await websocket.close()


@router.websocket("/media-stream-custom/{scenario_id}")
async def handle_custom_media_stream(websocket: WebSocket, scenario_id: str):
    """Handle custom scenarios by resolving scenario_id to scenario and reusing main logic"""
    MAX_RECONNECT_ATTEMPTS = 3

    # Try to resolve scenario_id to a scenario
    # First check if it's a custom scenario in the database
    try:
        db = next(get_db())
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id
        ).first()

        if custom_scenario:
            # Check if scenario already exists in SCENARIOS (with calendar info)
            if scenario_id in SCENARIOS:
                # Use existing scenario with calendar information
                await handle_media_stream(websocket, scenario_id)
            else:
                # Convert custom scenario to standard format with proper voice mapping
                from app.constants import VOICES

                # Map voice_type to actual OpenAI voice, with fallback to alloy
                mapped_voice = VOICES.get(
                    custom_scenario.voice_type, custom_scenario.voice_type)
                # If still not a valid OpenAI voice, fallback to alloy
                valid_voices = ["alloy", "ash", "ballad",
                                "coral", "echo", "sage", "shimmer", "verse"]
                if mapped_voice not in valid_voices:
                    mapped_voice = "alloy"

                # Check if user has calendar credentials
                calendar_enabled = False
                user_id = custom_scenario.user_id
                try:
                    from app.models import GoogleCalendarCredentials
                    credentials = db.query(GoogleCalendarCredentials).filter(
                        GoogleCalendarCredentials.user_id == custom_scenario.user_id
                    ).first()
                    calendar_enabled = bool(credentials)
                    if calendar_enabled:
                        logger.info(
                            f"📅 Calendar integration enabled for user {user_id}")
                except Exception as e:
                    logger.warning(
                        f"Could not check calendar credentials: {e}")

                scenario_data = {
                    "persona": custom_scenario.persona,
                    "prompt": custom_scenario.prompt,
                    "voice_config": {
                        "voice": mapped_voice,
                        "temperature": custom_scenario.temperature
                    },
                    "calendar_enabled": calendar_enabled,
                    "user_id": user_id
                }

                # Add to SCENARIOS temporarily for this call
                temp_scenario_key = f"temp_{scenario_id}"
                SCENARIOS[temp_scenario_key] = scenario_data

                # Reuse the main media stream logic
                await handle_media_stream(websocket, temp_scenario_key)

                # Clean up temporary scenario
                if temp_scenario_key in SCENARIOS:
                    del SCENARIOS[temp_scenario_key]
        else:
            # If not found in database, try to use as direct scenario name
            if scenario_id in SCENARIOS:
                await handle_media_stream(websocket, scenario_id)
            else:
                logger.error(f"Custom scenario not found: {scenario_id}")
                await websocket.close(code=4004, reason="Scenario not found")
    except Exception as e:
        logger.error(f"Error in custom media stream: {str(e)}", exc_info=True)
        await websocket.close(code=1011, reason="Internal error")
    finally:
        if 'db' in locals():
            db.close()


@router.websocket("/media-stream-custom-calendar/{scenario_id}")
async def handle_custom_calendar_media_stream(websocket: WebSocket, scenario_id: str):
    """Handle custom scenarios WITH Google Calendar integration"""
    try:
        # Get database session
        db = next(get_db())

        # Find the custom scenario and its owner
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id
        ).first()

        if not custom_scenario:
            logger.error(f"Custom scenario not found: {scenario_id}")
            await websocket.close(code=4004, reason="Scenario not found")
            return

        # Get the user who owns this scenario
        from app.models import User
        user = db.query(User).filter(
            User.id == custom_scenario.user_id).first()
        if not user:
            logger.error(f"User not found for scenario: {scenario_id}")
            await websocket.close(code=4004, reason="User not found")
            return

        # Check if user has Google Calendar credentials
        from app.models import GoogleCalendarCredentials
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == user.id
        ).first()

        if not credentials:
            logger.warning(
                f"No Google Calendar credentials for user {user.id} - falling back to regular custom scenario")
            # Fall back to regular custom scenario handling WITHOUT accepting websocket
            await handle_custom_media_stream(websocket, scenario_id)
            return

        # Get calendar context using GoogleCalendarService
        from app.services.google_calendar import GoogleCalendarService
        from app.utils.crypto import decrypt_string
        import json

        calendar_service = GoogleCalendarService()
        calendar_context = "No calendar information available."
        slots_context = "No free time slots available."

        try:
            # Decrypt the stored credentials
            decrypted_token = decrypt_string(credentials.token)
            decrypted_refresh_token = decrypt_string(
                credentials.refresh_token) if credentials.refresh_token else None

            # Create Google credentials object
            google_creds = Credentials(
                token=decrypted_token,
                refresh_token=decrypted_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=['https://www.googleapis.com/auth/calendar']
            )

            # Build the calendar service
            service = build('calendar', 'v3', credentials=google_creds)

            # Get upcoming events
            events = await calendar_service.get_upcoming_events(service, max_results=5)

            # Format calendar context
            if events:
                calendar_context = "Upcoming events:\\n"
                for event in events:
                    start = event.get('start', {}).get(
                        'dateTime', event.get('start', {}).get('date', 'Unknown time'))
                    summary = event.get('summary', 'No title')
                    calendar_context += f"- {summary} at {start}\\n"
            else:
                calendar_context = "No upcoming events found."

            # Get basic free time info (simplified)
            from datetime import datetime, timedelta
            now = datetime.now()
            tomorrow = now + timedelta(days=1)

            # Check availability for next day, 9 AM - 5 PM slots
            available_slots = []
            for hour in [9, 11, 14, 16]:  # 9 AM, 11 AM, 2 PM, 4 PM
                slot_start = tomorrow.replace(
                    hour=hour, minute=0, second=0, microsecond=0)
                slot_end = slot_start + timedelta(hours=1)

                is_available = await calendar_service.check_availability(service, slot_start, slot_end)
                if is_available:
                    available_slots.append(
                        f"{slot_start.strftime('%Y-%m-%d at %I:%M %p')}")

            if available_slots:
                slots_context = "Available time slots tomorrow:\\n"
                for slot in available_slots[:3]:  # Limit to 3 slots
                    slots_context += f"- {slot}\\n"
            else:
                slots_context = "No free time slots found tomorrow."

        except Exception as e:
            logger.error(f"Error getting calendar data: {e}")
            calendar_context = "Unable to access calendar information."
            slots_context = "Calendar temporarily unavailable."

        # Enhanced prompt with calendar integration
        enhanced_prompt = f"""
{custom_scenario.prompt}

CALENDAR INTEGRATION:
You now have access to this user's Google Calendar. Here's their calendar information:

{calendar_context}

{slots_context}

CALENDAR CAPABILITIES:
- You can check the user's availability 
- You can suggest free time slots
- When the user asks to schedule something, collect all details (title, date, time, duration) and confirm you'll add it to their calendar
- Our system will automatically create calendar events when you mention scheduling something

IMPORTANT: If someone asks to schedule a meeting or event:
1. Get all the details (what, when, how long)
2. Check if that time appears available based on the calendar info above
3. Confirm the details and say "I'll add that to your calendar right away"
4. The system will handle the actual calendar creation

Remember to be helpful with calendar-related questions while maintaining your original persona and purpose.
"""

        # Create enhanced scenario data
        from app.constants import VOICES
        mapped_voice = VOICES.get(custom_scenario.voice_type, "alloy")
        valid_voices = ["alloy", "ash", "ballad",
                        "coral", "echo", "sage", "shimmer", "verse"]
        if mapped_voice not in valid_voices:
            mapped_voice = "alloy"

        # Create enhanced scenario with function calling
        enhanced_scenario = {
            "persona": custom_scenario.persona,
            "prompt": enhanced_prompt,
            "voice_config": {
                "voice": mapped_voice,
                "temperature": custom_scenario.temperature
            },
            "calendar_enabled": True,
            "user_id": user.id,
            "tools": [
                {
                    "type": "function",
                    "name": "create_calendar_event",
                    "description": "Create a new calendar event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "The title/summary of the event"
                            },
                            "date": {
                                "type": "string",
                                "description": "The date in YYYY-MM-DD format"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "Start time in HH:MM format (24-hour)"
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration in minutes (default 60)",
                                "default": 60
                            },
                            "description": {
                                "type": "string",
                                "description": "Additional details about the event"
                            }
                        },
                        "required": ["title", "date", "start_time"]
                    }
                }
            ]
        }

        # Add to SCENARIOS temporarily
        enhanced_scenario_key = f"cal_{scenario_id}"
        SCENARIOS[enhanced_scenario_key] = enhanced_scenario

        logger.info(
            f"📅 Calendar-enhanced custom scenario started: {scenario_id} for user {user.email}")

        # Use the main media stream logic with enhanced scenario (this will accept the websocket)
        await handle_media_stream(websocket, enhanced_scenario_key)

        # Clean up
        if enhanced_scenario_key in SCENARIOS:
            del SCENARIOS[enhanced_scenario_key]

    except Exception as e:
        logger.error(
            f"Error in calendar-enhanced custom media stream: {str(e)}", exc_info=True)
        await websocket.close(code=1011, reason="Internal error")
    finally:
        if 'db' in locals():
            db.close()


@router.websocket("/calendar-media-stream")
async def handle_calendar_media_stream(websocket: WebSocket):
    caller = websocket.query_params.get("caller", "unknown")
    async with websocket_manager(websocket) as ws:
        try:
            await ws.send_text(json.dumps({"status": "connected", "caller": caller}))
        except Exception:
            pass
