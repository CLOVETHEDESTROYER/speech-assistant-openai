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
    """
    Full OpenAI Bridge Implementation:
    - Receives Twilio μ-law audio frames
    - Forwards audio to OpenAI Realtime API
    - Receives OpenAI audio responses
    - Converts and sends audio back to Twilio
    """
    params = dict(websocket.query_params)
    direction = params.get("direction", "outbound")
    user_name = params.get("user_name", "")
    logger.info(
        f"WebSocket connection for scenario: {scenario}, direction: {direction}, user_name: {user_name}")

    # Validate scenario exists
    if scenario not in SCENARIOS:
        logger.error(f"Invalid scenario: {scenario}")
        await websocket.close(code=4004, reason="Invalid scenario")
        return

    # Get actual scenario data
    scenario_data = SCENARIOS[scenario]
    logger.info(f"Using scenario: {scenario_data}")

    async with websocket_manager(websocket) as ws:
        stream_sid: str | None = None
        openai_ws = None
        session_id = None
        audio_buffer_count = 0
        last_commit_time = time.time()

        try:
            # Create an OpenAI session per call using actual scenario data
            try:
                session_info = await realtime_manager.create_session("twilio", {
                    "name": scenario,
                    "persona": scenario_data["persona"],
                    "prompt": scenario_data["prompt"],
                    "voice_config": scenario_data["voice_config"],
                    "direction": direction,
                    "user_name": user_name,
                })
                session_id = session_info.get("session_id")
                logger.info(f"Created OpenAI session: {session_id}")
            except Exception as e:
                logger.warning(f"OpenAI session unavailable: {e}")
                session_id = None

            # Get the OpenAI WebSocket from the session
            if session_id:
                session = realtime_manager.get_session(session_id)
                if session and "openai_ws" in session:
                    openai_ws = session["openai_ws"]
                    logger.info("Using OpenAI WebSocket from session")

                    # For outbound calls, create initial response to start the conversation
                    if direction == "outbound":
                        try:
                            await openai_ws.send(json.dumps({
                                "type": "response.create"
                            }))
                            logger.info(
                                "Sent initial response.create for outbound call")
                        except Exception as e:
                            logger.warning(
                                f"Failed to create initial response: {e}")
                else:
                    logger.warning("No OpenAI WebSocket found in session")

            await ws.send_text(json.dumps({"status": "connected"}))

            # Main media stream processing loop
            while True:
                msg = await ws.receive_text()
                event = json.loads(msg)
                etype = event.get("event")

                if etype == "start":
                    stream_sid = event.get("start", {}).get("streamSid")
                    logger.info(f"Twilio stream start: {stream_sid}")

                elif etype == "media":
                    # Incoming caller audio (base64 ulaw 8k)
                    media_payload = event.get("media", {}).get("payload")
                    if not stream_sid and event.get("streamSid"):
                        stream_sid = event.get("streamSid")

                    if stream_sid and media_payload and openai_ws:
                        try:
                            # Send audio to OpenAI - Twilio sends μ-law, but we need to convert to base64 properly
                            # The media_payload is already base64 encoded μ-law from Twilio
                            openai_message = {
                                "type": "input_audio_buffer.append",
                                "audio": media_payload  # Already base64 encoded μ-law from Twilio
                            }
                            await openai_ws.send(json.dumps(openai_message))
                            audio_buffer_count += 1

                            # Debug: Log audio data size
                            logger.debug(
                                f"Sent audio to OpenAI: {len(media_payload)} chars base64, buffer count: {audio_buffer_count}")

                            # Commit audio buffer periodically (every 5 frames or 200ms)
                            current_time = time.time()
                            if audio_buffer_count >= 5 or (current_time - last_commit_time) >= 0.2:
                                try:
                                    # Commit the audio buffer
                                    await openai_ws.send(json.dumps({
                                        "type": "input_audio_buffer.commit"
                                    }))

                                    # Create a response
                                    await openai_ws.send(json.dumps({
                                        "type": "response.create"
                                    }))

                                    audio_buffer_count = 0
                                    last_commit_time = current_time
                                    logger.debug(
                                        "Committed audio buffer and created response")
                                except Exception as commit_error:
                                    logger.warning(
                                        f"Failed to commit audio buffer: {commit_error}")

                            # Try to receive response from OpenAI (non-blocking)
                            try:
                                openai_response = await asyncio.wait_for(openai_ws.recv(), timeout=0.05)
                                response_data = json.loads(openai_response)

                                # Debug: Log response type
                                logger.debug(
                                    f"OpenAI response type: {response_data.get('type')}")

                                # Handle both response.audio.delta and response.output_audio.delta
                                if response_data.get("type") in ["response.audio.delta", "response.output_audio.delta"]:
                                    # Extract audio data from OpenAI response
                                    openai_audio = response_data.get("delta")
                                    if openai_audio:
                                        # OpenAI returns base64 encoded audio in the format we specified
                                        # Since we specified mulaw, it should return mulaw format
                                        out_message = {
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {
                                                "payload": openai_audio
                                            }
                                        }
                                        await ws.send_text(json.dumps(out_message))
                                        logger.debug(
                                            f"Sent OpenAI audio back to Twilio (size: {len(openai_audio)})")

                                elif response_data.get("type") == "text":
                                    # Log text responses for debugging
                                    text_content = response_data.get(
                                        "text", {}).get("content", "")
                                    logger.info(
                                        f"OpenAI text response: {text_content}")

                            except asyncio.TimeoutError:
                                # No response from OpenAI, send silence to keep connection alive
                                try:
                                    # 20ms of μ-law silence (0xFF = silence in μ-law)
                                    silence = bytes([0xFF] * 160)
                                    silence_b64 = base64.b64encode(
                                        silence).decode("ascii")
                                    out_message = {
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {
                                            "payload": silence_b64
                                        }
                                    }
                                    await ws.send_text(json.dumps(out_message))
                                except Exception as send_error:
                                    logger.warning(
                                        f"Could not send silence after timeout: {send_error}")
                                    break  # Exit the loop if we can't send

                        except Exception as e:
                            logger.error(f"Error processing audio: {e}")
                            # Try to send silence on error, but don't fail if WebSocket is closed
                            try:
                                silence = bytes([0xFF] * 160)
                                silence_b64 = base64.b64encode(
                                    silence).decode("ascii")
                                out_message = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": silence_b64
                                    }
                                }
                                await ws.send_text(json.dumps(out_message))
                            except Exception as send_error:
                                logger.warning(
                                    f"Could not send silence after audio error: {send_error}")
                                break  # Exit the loop if we can't send

                    elif stream_sid:
                        # No OpenAI connection, send silence
                        silence = bytes([0xFF] * 160)
                        silence_b64 = base64.b64encode(silence).decode("ascii")
                        out_message = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": silence_b64
                            }
                        }
                        await ws.send_text(json.dumps(out_message))

                elif etype == "stop":
                    logger.info(f"Twilio stream stop: {stream_sid}")
                    break
                else:
                    logger.debug(f"Unhandled Twilio media event: {etype}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in media stream: {str(e)}", exc_info=True)
        finally:
            # Cleanup
            if session_id:
                try:
                    await realtime_manager.close_session(session_id)
                except:
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
            # Convert custom scenario to standard format
            scenario_data = {
                "persona": custom_scenario.persona,
                "prompt": custom_scenario.prompt,
                "voice_config": {
                    "voice": custom_scenario.voice_type,
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
