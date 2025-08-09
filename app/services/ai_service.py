import os
import openai
import logging
from app.db import SessionLocal
from app.models import ProviderCredentials
from app.utils.crypto import decrypt_string

logger = logging.getLogger(__name__)

async def get_ai_response(conversation_text: str) -> str:
    try:
        # Resolve API key from user context in future; for now support env only
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            openai.api_key = api_key
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant having a phone conversation."},
                {"role": "user", "content": conversation_text}
            ],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return "I apologize, but I'm having trouble processing that right now."

async def text_to_speech(text: str) -> bytes:
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            openai.api_key = api_key
        response = await openai.Audio.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        return response.content
    except Exception as e:
        logger.error(f"Text-to-speech error: {str(e)}")
        return b""  # Return empty bytes on error 