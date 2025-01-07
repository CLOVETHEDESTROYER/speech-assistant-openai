import asyncio
import websockets
import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_openai_connection():
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    openai_ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

    try:
        async with websockets.connect(
            openai_ws_url,
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as ws:
            logger.info("Connected to OpenAI WebSocket successfully.")

            # Send a test response.create message
            test_message = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"]
                }
            }
            await ws.send(json.dumps(test_message))
            logger.info(f"Sent test response.create message: {test_message}")

            # Send a test session.update message
            test_session_update = {
                "type": "session.update",
                "session": {
                    "instructions": "Please assist the user.",
                    "voice": "alloy",
                    "input_audio_format": {
                        "type": "mulaw",
                        "sample_rate": 8000
                    },
                    "output_audio_format": {
                        "type": "mulaw",
                        "sample_rate": 8000
                    }
                }
            }
            await ws.send(json.dumps(test_session_update))
            logger.info(
                f"Sent test session.update message: {test_session_update}")

            # Listen for messages for a short duration
            async def listen():
                try:
                    async for message in ws:
                        logger.info(f"Received message from OpenAI: {message}")
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Connection closed by OpenAI.")

            await asyncio.wait_for(listen(), timeout=10)

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(
            f"WebSocket connection failed with status code: {e.status_code}")
        logger.error(f"Response headers: {e.headers}")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_openai_connection())
