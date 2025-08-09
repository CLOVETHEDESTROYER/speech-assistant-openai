import os
import json
import uuid
import logging
import websockets
from datetime import datetime
from typing import Optional, Dict, Any
from app.vad_config import VADConfig  # Import the VAD configuration class

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
        """Create a new realtime session with enhanced VAD configuration."""
        try:
            session_id = str(uuid.uuid4())

            openai_ws = await websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2025-06-03',
                extra_headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "OpenAI-Beta": "realtime=v1"
                },
                ping_interval=20,
                ping_timeout=60,
                close_timeout=60
            )

            # Get optimized VAD configuration for this scenario
            scenario_name = scenario.get("name", "default")
            vad_config = VADConfig.get_scenario_vad_config(scenario_name)

            # Initialize session configuration with enhanced VAD
            session_config = {
                "type": "session.update",
                "session": {
                    "turn_detection": vad_config,
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "instructions": self._get_instructions(scenario),
                    "voice": scenario["voice_config"]["voice"],
                    "temperature": scenario["voice_config"]["temperature"],
                    "modalities": ["text", "audio"]
                }
            }

            self.logger.info(
                f"Creating session with config: {json.dumps(session_config, indent=2)}")
            await openai_ws.send(json.dumps(session_config))
            response = await openai_ws.recv()
            session_response = json.loads(response)

            if session_response.get("type") == "error":
                raise Exception(
                    f"OpenAI session error: {session_response}")

            self.logger.info(
                f"Session response: {json.dumps(session_response, indent=2)}")

            # Store session information
            self.active_sessions[session_id] = {
                "openai_ws": openai_ws,
                "user_id": user_id,
                "scenario": scenario,
                "vad_config": vad_config,  # Store VAD config for reference
                "created_at": datetime.utcnow(),
                "ice_servers": self.ice_servers
            }

            self.logger.info(
                f"Session created with VAD config: {vad_config}")
            self.logger.info(
                f"Session config sent: {json.dumps(session_config, indent=2)}")

            return {
                "session_id": session_id,
                "ice_servers": self.ice_servers,
                "vad_config": vad_config,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(
                f"Error creating session: {str(e)}", exc_info=True)
            raise

    async def create_initial_response(self, session_id: str) -> bool:
        """Create an initial response for outbound calls to start the conversation."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Invalid session ID: {session_id}")

            openai_ws = session["openai_ws"]

            # Send response.create to start the conversation
            await openai_ws.send(json.dumps({
                "type": "response.create"
            }))

            self.logger.info(
                f"Created initial response for session: {session_id}")
            return True

        except Exception as e:
            self.logger.error(
                f"Error creating initial response: {str(e)}", exc_info=True)
            return False

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

            # Debugging logs
            logger.info(
                f"Audio data size received from Twilio: {len(audio_data)} bytes")

            # Send audio to OpenAI
            await openai_ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": audio_data.decode('base64')
            }))

            # Get response from OpenAI
            response = await openai_ws.recv()
            # Add this line explicitly
            logger.info(f"🔍 OpenAI response: {response}")

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
            # For incoming calls, actively gather caller information including name
            instructions = (
                f"{system_message}\n\n"
                f"Persona: {persona}\n\n"
                f"Scenario: {prompt}\n\n"
                f"This is an incoming call where someone is calling you. You do not know who is calling. "
                f"Greet them politely and introduce yourself according to your persona. "
                f"Early in the conversation, ask for their name clearly: 'May I get your name, please?' "
                f"Listen for their response and use their name throughout the rest of the conversation. "
                f"Also gather any other important information that would be relevant to your scenario, "
                f"such as their contact details, reason for calling, or specific needs. "
                f"Be conversational and natural while collecting this information - don't make it feel "
                f"like an interrogation. If they don't provide their name after being asked, "
                f"continue the conversation professionally without pressing the issue."
            )
        return instructions
