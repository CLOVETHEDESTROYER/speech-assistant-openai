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
                            "user_speaking": False
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

            scenario_data = {
                "persona": custom_scenario.persona,
                "prompt": custom_scenario.prompt,
                "voice_config": {
                    "voice": mapped_voice,
                    "temperature": custom_scenario.temperature
                }
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


@router.websocket("/calendar-media-stream")
async def handle_calendar_media_stream(websocket: WebSocket):
    caller = websocket.query_params.get("caller", "unknown")
    async with websocket_manager(websocket) as ws:
        try:
            await ws.send_text(json.dumps({"status": "connected", "caller": caller}))
        except Exception:
            pass
