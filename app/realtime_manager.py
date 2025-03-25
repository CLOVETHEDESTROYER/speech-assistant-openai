import logging
import json
import asyncio
import websockets
from typing import Dict, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import aiohttp

logger = logging.getLogger(__name__)


class OpenAIRealtimeManager:
    def __init__(self, openai_api_key: str, ice_servers: list = None):
        self.openai_api_key = openai_api_key
        self.active_sessions: Dict[str, dict] = {}
        self.ice_servers = ice_servers or [
            {"urls": ["stun:stun.l.google.com:19302"]}
        ]
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    async def create_session(self, user_id: str, scenario: dict) -> dict:
        """Create a new session with OpenAI's Realtime API."""
        try:
            session_id = f"session_{user_id}_{datetime.utcnow().timestamp()}"

            # Connect to OpenAI's Realtime API
            async with websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',

                extra_headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "OpenAI-Beta": "realtime=v1"
                }
            ) as openai_ws:
                # Initialize session configuration
                session_config = {
                    "type": "session.update",
                    "session": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.3,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 750,
                            "create_response": True
                        },
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "sample_rate": 16000,
                        "instructions": self._get_instructions(scenario),
                        "voice": scenario["voice_config"]["voice"],
                        "temperature": scenario["voice_config"]["temperature"],
                        "modalities": ["text", "audio"]
                    }
                }

                await openai_ws.send(json.dumps(session_config))
                response = await openai_ws.recv()
                session_response = json.loads(response)

                if session_response.get("type") == "error":
                    raise Exception(f"OpenAI session error: {
                                    session_response}")

                # Store session information
                self.active_sessions[session_id] = {
                    "openai_ws": openai_ws,
                    "user_id": user_id,
                    "scenario": scenario,
                    "created_at": datetime.utcnow(),
                    "ice_servers": self.ice_servers
                }

                return {
                    "session_id": session_id,
                    "ice_servers": self.ice_servers,
                    "created_at": datetime.utcnow().isoformat()
                }

        except Exception as e:
            self.logger.error(f"Error creating session: {
                              str(e)}", exc_info=True)
            raise

    async def handle_signaling(self, session_id: str, signal_data: dict) -> dict:
        """Handle WebRTC signaling messages."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Invalid session ID: {session_id}")

            signal_type = signal_data.get("type")
            if signal_type == "offer":
                # Handle offer from iOS client
                return {
                    "type": "answer",
                    "sdp": await self._create_answer(session, signal_data),
                    "ice_servers": session["ice_servers"]
                }
            elif signal_type == "ice-candidate":
                # Handle ICE candidate from iOS client
                await self._handle_ice_candidate(session, signal_data)
                return {"type": "ice-candidate-received"}
            else:
                raise ValueError(f"Unsupported signal type: {signal_type}")

        except Exception as e:
            self.logger.error(f"Error handling signal: {
                              str(e)}", exc_info=True)
            raise

    async def _create_answer(self, session: dict, offer: dict) -> str:
        """Create WebRTC answer for the iOS client's offer."""
        try:
            # Here you would implement WebRTC answer creation
            # This is a placeholder for the actual WebRTC implementation
            return "SDP_ANSWER_PLACEHOLDER"
        except Exception as e:
            self.logger.error(f"Error creating answer: {
                              str(e)}", exc_info=True)
            raise

    async def _handle_ice_candidate(self, session: dict, candidate: dict) -> None:
        """Handle ICE candidate from the iOS client."""
        try:
            # Here you would implement ICE candidate handling
            # This is a placeholder for the actual WebRTC implementation
            pass
        except Exception as e:
            self.logger.error(f"Error handling ICE candidate: {
                              str(e)}", exc_info=True)
            raise

    async def close_session(self, session_id: str) -> None:
        """Close and cleanup a session."""
        try:
            session = self.active_sessions.get(session_id)
            if session:
                if session.get("openai_ws"):
                    await session["openai_ws"].close()
                del self.active_sessions[session_id]
                self.logger.info(f"Session closed: {session_id}")
        except Exception as e:
            self.logger.error(f"Error closing session: {
                              str(e)}", exc_info=True)
            raise

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session information."""
        return self.active_sessions.get(session_id)

    async def handle_audio_stream(self, session_id: str, audio_data: bytes) -> bytes:
        """Handle audio streaming between iOS client and OpenAI."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Invalid session ID: {session_id}")

            openai_ws = session["openai_ws"]

            # Send audio to OpenAI
            await openai_ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": audio_data.decode('base64')
            }))

            # Get response from OpenAI
            response = await openai_ws.recv()
            response_data = json.loads(response)

            if response_data.get("type") == "error":
                raise Exception(f"OpenAI stream error: {response_data}")

            return response_data.get("delta", "").encode('utf-8')

        except Exception as e:
            self.logger.error(f"Error handling audio stream: {
                              str(e)}", exc_info=True)
            raise

    def _get_instructions(self, scenario: dict) -> str:
        """Get instructions based on the scenario direction."""
        direction = scenario.get('direction', 'outbound')
        user_name = scenario.get('user_name')

        # Make sure required keys exist
        persona = scenario.get('persona', 'Assistant')
        prompt = scenario.get('prompt', 'You are a helpful assistant.')
        system_message = scenario.get('system_message', '')

        if direction == "outbound":
            # Only include name instructions for outbound calls if name exists
            name_instruction = f"\n\nThe user's name is {user_name}. Address them by name occasionally during the call." if user_name else ""
            instructions = (
                f"{system_message}\n\n"
                f"Persona: {persona}\n\n"
                f"Scenario: {prompt}{name_instruction}\n\n"
                f"This is an outbound call that you initiated. Begin the conversation directly "
                f"according to your persona and scenario without asking how you can help."
            )
        else:
            # For incoming calls, modify to actively ask for and remember caller's name
            instructions = (
                f"{system_message}\n\n"
                f"Persona: {persona}\n\n"
                f"Scenario: {prompt}\n\n"
                f"This is an incoming call where someone is calling you. Greet them politely and "
                f"introduce yourself according to your persona. Early in the conversation, politely ask for "
                f"their name with phrases like 'May I ask who I'm speaking with?' or 'Could I get your name please?'. "
                f"Once they share their name, remember it and use it occasionally throughout the rest of the call to "
                f"make the conversation more personal. If they don't provide their name after asking, proceed with "
                f"the conversation without pressing further."
            )
        return instructions
