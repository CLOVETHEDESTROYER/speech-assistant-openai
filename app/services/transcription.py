import os
from typing import Optional
from openai import OpenAI
import logging
from app.models import Conversation

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    async def transcribe_audio(self, audio_data: bytes) -> Optional[str]:
        """
        Simple transcription using OpenAI's Whisper API
        """
        try:
            # Basic transcription
            transcription = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_data
            )
            return transcription.text
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return None

    async def save_conversation(self, db, call_sid, phone_number, direction, scenario, transcript, user_id=None):
        """Save conversation to database"""
        try:
            conversation = Conversation(
                call_sid=call_sid,
                phone_number=phone_number,
                direction=direction,
                scenario=scenario,
                transcript=transcript,
                user_id=user_id
            )
            db.add(conversation)
            db.commit()
            logger.info(f"Saved conversation for call {call_sid}")
        except Exception as e:
            logger.error(f"Error saving conversation: {str(e)}")
            db.rollback()
            raise 