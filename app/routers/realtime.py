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
import websockets
import asyncio
import json
import logging

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
        # Validate scenario externally if needed; SCENARIOS is in main, so assume valid here
        user_id = session_data.user_id or current_user.id
        session_info = await realtime_manager.create_session(str(user_id), {})
        return session_info
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/realtime/signal", response_model=SignalingResponse)
async def handle_signaling(
    signal: SignalingMessage,
    current_user: User = Depends(get_current_user)
):
    try:
        session = realtime_manager.get_session(signal.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if str(session["user_id"]) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this session")
        response = await realtime_manager.handle_signaling(signal.session_id, {"type": signal.type, "sdp": signal.sdp, "candidate": signal.candidate})
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/test-realtime", response_class=HTMLResponse)
async def test_realtime_page():
    # Lightweight test page (copied from main to keep endpoint stable)
    return HTMLResponse(content="<html><body>Realtime OK</body></html>")


# WebSocket/media stream endpoints moved from main
@router.websocket("/media-stream/{scenario}")
async def handle_media_stream(websocket: WebSocket, scenario: str):
    MAX_RECONNECT_ATTEMPTS = 3
    params = dict(websocket.query_params)
    direction = params.get("direction", "outbound")
    user_name = params.get("user_name", "")
    logger.info(
        f"WebSocket connection for scenario: {scenario}, direction: {direction}, user_name: {user_name}")

    async with websocket_manager(websocket) as ws:
        try:
            logger.info(
                f"WebSocket connection established for scenario: {scenario}")

            reconnect_attempts = 0
            while reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                try:
                    await asyncio.sleep(0.1)
                    try:
                        await ws.send_text(json.dumps({"status": "connected"}))
                        logger.info("Twilio WebSocket is still connected")
                    except Exception as e:
                        logger.warning(
                            f"Twilio WebSocket connection closed before sending greeting: {e}")
                        break
                    break
                except websockets.exceptions.WebSocketException as e:
                    logger.error(f"WebSocket error: {e}")
                    reconnect_attempts += 1
                    await asyncio.sleep(min(2 ** reconnect_attempts, 8))

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in media stream: {str(e)}", exc_info=True)


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
    MAX_RECONNECT_ATTEMPTS = 3
    async with websocket_manager(websocket) as ws:
        try:
            logger.info(
                f"WebSocket connection for custom scenario: {scenario_id}")
            await ws.send_text(json.dumps({"status": "connected"}))
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in custom media stream: {str(e)}", exc_info=True)


@router.websocket("/calendar-media-stream")
async def handle_calendar_media_stream(websocket: WebSocket):
    caller = websocket.query_params.get("caller", "unknown")
    async with websocket_manager(websocket) as ws:
        try:
            await ws.send_text(json.dumps({"status": "connected", "caller": caller}))
        except Exception:
            pass



