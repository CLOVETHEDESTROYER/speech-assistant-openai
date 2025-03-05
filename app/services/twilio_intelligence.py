import os
import logging
import time
from typing import Dict, Any, Optional, List, Union

from app import config
from app.services.twilio_client import get_twilio_client
from app.utils.twilio_helpers import with_twilio_retry, safe_twilio_response, TwilioApiError

logger = logging.getLogger(__name__)


class TwilioIntelligenceService:
    """Service for interacting with Twilio Voice Intelligence API for transcriptions with PII redaction."""

    def __init__(self):
        """Initialize the Twilio Intelligence Service."""
        self.voice_intelligence_sid = config.TWILIO_VOICE_INTELLIGENCE_SID

        if not self.voice_intelligence_sid:
            logger.warning(
                "TWILIO_VOICE_INTELLIGENCE_SID is not set. Voice Intelligence features will not work.")

    @with_twilio_retry(max_retries=3)
    async def transcribe_recording(self, recording_sid: str, redact_pii: bool = True) -> Dict[str, Any]:
        """
        Transcribe a Twilio recording using Voice Intelligence API with PII redaction.

        Args:
            recording_sid: The SID of the recording to transcribe
            redact_pii: Whether to redact PII from the transcript

        Returns:
            Dict containing the transcript information

        Raises:
            TwilioApiError: If there's an error with the Twilio API
        """
        try:
            logger.info(
                f"Transcribing recording {recording_sid} with Twilio Voice Intelligence")

            # Get the Twilio client from our singleton service
            client = get_twilio_client()

            # Create a transcript request
            transcript = client.intelligence.v2.transcripts.create(
                service_sid=self.voice_intelligence_sid,
                channel={
                    "media_properties": {
                        "source_sid": recording_sid
                    }
                },
                redaction=redact_pii
            )

            logger.info(
                f"Transcript creation initiated with SID: {transcript.sid}")

            # Poll for the transcript to complete
            completed_transcript = await self._wait_for_transcription(transcript.sid, max_attempts=30, delay_seconds=2)

            return {
                "transcript_sid": completed_transcript.sid,
                "status": completed_transcript.status,
                "recording_sid": recording_sid,
                "redaction": completed_transcript.redaction,
                "language_code": completed_transcript.language_code,
                "duration": completed_transcript.duration,
                "date_created": completed_transcript.date_created,
                "date_updated": completed_transcript.date_updated
            }

        except TwilioApiError as e:
            logger.error(f"Error transcribing recording {recording_sid}: {e.message}",
                         extra={"details": e.details})
            raise
        except Exception as e:
            logger.error(f"Unexpected error transcribing recording {recording_sid}: {str(e)}",
                         exc_info=True)
            raise TwilioApiError(
                f"Failed to transcribe recording: {str(e)}",
                details={"recording_sid": recording_sid}
            )

    @with_twilio_retry(max_retries=3)
    async def _fetch_transcript_with_retry(self, transcript_sid: str) -> Any:
        """
        Fetch a transcript with retry logic.

        Args:
            transcript_sid: The SID of the transcript to fetch

        Returns:
            The transcript object

        Raises:
            TwilioApiError: If there's an error with the Twilio API
        """
        try:
            client = get_twilio_client()
            return client.intelligence.v2.transcripts(transcript_sid).fetch()
        except Exception as e:
            logger.warning(
                f"Error fetching transcript {transcript_sid}: {str(e)}")
            raise TwilioApiError(
                f"Failed to fetch transcript: {str(e)}",
                details={"transcript_sid": transcript_sid}
            )

    async def _wait_for_transcription(
        self,
        transcript_sid: str,
        max_attempts: int = 30,
        delay_seconds: int = 2
    ) -> Any:
        """
        Poll the transcription status until it completes or times out.

        Args:
            transcript_sid: The SID of the transcript to poll
            max_attempts: Maximum number of polling attempts
            delay_seconds: Delay between polling attempts in seconds

        Returns:
            The completed transcript object

        Raises:
            TwilioApiError: If the transcription times out or fails
        """
        logger.info(f"Waiting for transcript {transcript_sid} to complete")

        for attempt in range(max_attempts):
            try:
                transcript = await self._fetch_transcript_with_retry(transcript_sid)

                if transcript.status == "completed":
                    logger.info(
                        f"Transcript {transcript_sid} completed successfully")
                    return transcript
                elif transcript.status == "failed":
                    logger.error(f"Transcript {transcript_sid} failed")
                    raise TwilioApiError(
                        f"Transcription failed with status: {transcript.status}",
                        details={"transcript_sid": transcript_sid}
                    )

                logger.debug(
                    f"Transcript {transcript_sid} status: {transcript.status}, attempt {attempt+1}/{max_attempts}")

            except Exception as e:
                # Log the error but continue polling
                logger.warning(
                    f"Error checking transcript status (attempt {attempt+1}/{max_attempts}): {str(e)}")

            # Wait before the next attempt
            time.sleep(delay_seconds)

        # If we've reached here, we've timed out
        logger.error(
            f"Timed out waiting for transcript {transcript_sid} to complete after {max_attempts} attempts")
        raise TwilioApiError(
            f"Timed out waiting for transcription to complete after {max_attempts * delay_seconds} seconds",
            details={"transcript_sid": transcript_sid,
                     "max_attempts": max_attempts}
        )

    @with_twilio_retry(max_retries=3)
    async def get_transcript_text(self, transcript_sid: str) -> str:
        """
        Get the full text of a transcript.

        Args:
            transcript_sid: The SID of the transcript

        Returns:
            The full text of the transcript

        Raises:
            TwilioApiError: If there's an error with the Twilio API
        """
        try:
            client = get_twilio_client()

            # Fetch all sentences
            sentences = client.intelligence.v2.transcripts(
                transcript_sid).sentences.list()

            # Sort sentences by start_time and join them
            sorted_sentences = sorted(sentences, key=lambda s: s.start_time)
            full_text = " ".join(s.text for s in sorted_sentences)

            return full_text

        except Exception as e:
            logger.error(
                f"Error getting transcript text for {transcript_sid}: {str(e)}")
            raise TwilioApiError(
                f"Failed to get transcript text: {str(e)}",
                details={"transcript_sid": transcript_sid}
            )

    @with_twilio_retry(max_retries=3)
    async def get_transcript_sentences(self, transcript_sid: str) -> List[Dict[str, Any]]:
        """
        Get all sentences from a transcript with speaker information.

        Args:
            transcript_sid: The SID of the transcript

        Returns:
            List of sentence dictionaries with text, speaker, and timing information

        Raises:
            TwilioApiError: If there's an error with the Twilio API
        """
        try:
            client = get_twilio_client()

            # Fetch all sentences
            sentences = client.intelligence.v2.transcripts(
                transcript_sid).sentences.list()

            # Format the sentences
            formatted_sentences = [
                {
                    "text": sentence.text,
                    "speaker": sentence.speaker,
                    "start_time": sentence.start_time,
                    "end_time": sentence.end_time,
                    "confidence": sentence.confidence
                }
                for sentence in sentences
            ]

            # Sort by start_time
            formatted_sentences.sort(key=lambda s: s["start_time"])

            return formatted_sentences

        except Exception as e:
            logger.error(
                f"Error getting transcript sentences for {transcript_sid}: {str(e)}")
            raise TwilioApiError(
                f"Failed to get transcript sentences: {str(e)}",
                details={"transcript_sid": transcript_sid}
            )

    @with_twilio_retry(max_retries=3)
    async def delete_transcript(self, transcript_sid: str) -> bool:
        """
        Delete a transcript.

        Args:
            transcript_sid: The SID of the transcript to delete

        Returns:
            True if deletion was successful

        Raises:
            TwilioApiError: If there's an error with the Twilio API
        """
        try:
            client = get_twilio_client()

            # Delete the transcript
            client.intelligence.v2.transcripts(transcript_sid).delete()

            logger.info(f"Successfully deleted transcript {transcript_sid}")
            return True

        except Exception as e:
            logger.error(
                f"Error deleting transcript {transcript_sid}: {str(e)}")
            raise TwilioApiError(
                f"Failed to delete transcript: {str(e)}",
                details={"transcript_sid": transcript_sid}
            )
