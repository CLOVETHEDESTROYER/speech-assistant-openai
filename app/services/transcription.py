import os
import io
import tempfile
from typing import Optional, BinaryIO
import base64
from openai import OpenAI
import logging
from app.models import Conversation

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    async def transcribe_base64_audio(self, base64_audio: str, format: str = "wav") -> Optional[str]:
        """
        Transcribe base64 encoded audio using OpenAI's Whisper API
        """
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(base64_audio)

            # Create a temporary file to store the audio
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name

            # Transcribe the audio file
            with open(temp_file_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

            # Clean up the temporary file
            os.unlink(temp_file_path)

            return transcription.text
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return None

    async def transcribe_audio(self, audio_data) -> Optional[str]:
        """
        Simple transcription using OpenAI's Whisper API
        Accepts either a bytes object or a file-like object
        """
        temp_file_path = None
        try:
            # If audio_data is bytes, create a temporary file
            if isinstance(audio_data, bytes):
                # Create a temporary file to store the audio
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name

                # Transcribe the audio file
                with open(temp_file_path, "rb") as audio_file:
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )

                # Clean up the temporary file
                os.unlink(temp_file_path)
            else:
                # If audio_data is already a file-like object, use it directly
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_data
                )

            return transcription.text
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")

            # Clean up temporary file if it exists and an error occurred
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to remove temporary file {temp_file_path}: {str(cleanup_error)}")

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
