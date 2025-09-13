from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from app import config
from app.db import get_db
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.services.twilio_client import get_twilio_client
from app.models import Conversation, GoogleCalendarCredentials, TranscriptRecord
import logging
import os
import json
from typing import Optional
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"


def safe_log_twilio_sid(sid: str) -> str:
    """Safely log Twilio SIDs - show first/last 4 chars only"""
    if not sid or len(sid) < 8:
        return sid or "None"
    return f"{sid[:4]}...{sid[-4:]}"


@router.post("/twilio-transcripts/webhook-callback")
async def handle_transcript_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Enhanced webhook to handle Twilio Conversational Intelligence transcripts
    and process them for automatic calendar creation
    """
    try:
        # Validate Twilio signature
        if not IS_DEV and not config.TWILIO_AUTH_TOKEN:
            raise HTTPException(
                status_code=500, detail="Twilio signature validation not configured")

        if config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            body = await request.body()
            if not validator.validate(request_url, body.decode(), twilio_signature):
                logger.warning(
                    "Invalid Twilio signature on transcript webhook")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")

        # Parse webhook payload (Twilio sends form-encoded data, not JSON)
        form_data = await request.form()
        payload = dict(form_data)
        logger.info(
            f"📝 Conversational Intelligence webhook received: {safe_log_request_data(payload)}")

        # Extract transcript information using correct field names
        transcript_sid = payload.get(
            'TranscriptSid') or payload.get('transcript_sid')
        event_type = payload.get('EventType') or payload.get('event_type')
        service_sid = payload.get('ServiceSid') or payload.get('service_sid')
        call_sid = payload.get('CallSid') or payload.get('call_sid')

        if not transcript_sid:
            logger.error("No transcript SID provided in webhook")
            return {"status": "error", "message": "No transcript SID provided"}

        # Handle different event types
        if event_type == 'voice_intelligence_transcript_available':
            logger.info(
                f"📋 Processing completed transcript: {safe_log_twilio_sid(transcript_sid)}")

            # Fetch the complete transcript from Twilio
            try:
                client = get_twilio_client()
                transcript = client.intelligence.v2.transcripts(
                    transcript_sid).fetch()
                sentences = client.intelligence.v2.transcripts(
                    transcript_sid).sentences.list()

                # Format the full conversation text
                sorted_sentences = sorted(
                    sentences, key=lambda s: getattr(s, "start_time", 0))
                full_conversation = " ".join(
                    getattr(s, "text", "").strip()
                    for s in sorted_sentences
                    if getattr(s, "text", "").strip()
                )

                if not full_conversation:
                    logger.warning(
                        f"No conversation text found in transcript {transcript_sid}")
                    return {"status": "success", "message": "No conversation text to process"}

                logger.info(
                    f"📄 Extracted conversation text: {len(full_conversation)} characters")

                # Find the associated conversation record
                conversation = await find_conversation_for_transcript(db, transcript_sid, transcript, call_sid)

                if not conversation:
                    logger.warning(
                        f"No conversation record found for transcript {transcript_sid}")
                    return {"status": "success", "message": "No associated conversation found"}

                # 🚀 CALENDAR PROCESSING: Check if this is a calendar-enabled scenario
                if await should_process_for_calendar(db, conversation):
                    logger.info(
                        f"🗓️ Processing calendar for conversation {conversation.id}")

                    # Import and use the post-call processor
                    from app.services.post_call_processor import PostCallProcessor

                    processor = PostCallProcessor()
                    calendar_result = await processor.process_call_end(
                        call_sid=conversation.call_sid or call_sid or "unknown",
                        user_id=conversation.user_id,
                        scenario_id=conversation.scenario or "default",
                        conversation_content=full_conversation
                    )

                    if calendar_result and calendar_result.get("calendar_event_created"):
                        logger.info(
                            f"✅ Calendar events created: {calendar_result['calendar_event_created']}")

                        # Update conversation with transcript and calendar processing status
                        conversation.transcript = full_conversation
                        db.commit()

                        return {
                            "status": "success",
                            "transcript_processed": True,
                            "calendar_events_created": calendar_result["calendar_event_created"],
                            "message": "Transcript processed and calendar events created"
                        }
                    else:
                        logger.info(
                            f"ℹ️ No calendar events created for conversation {conversation.id}")
                else:
                    logger.info(
                        f"📞 Standard conversation processing for {conversation.id}")

                # Update conversation with transcript even if no calendar events
                conversation.transcript = full_conversation
                db.commit()

                return {
                    "status": "success",
                    "transcript_processed": True,
                    "message": "Transcript processed successfully"
                }

            except Exception as e:
                logger.error(
                    f"Error processing transcript {transcript_sid}: {e}")
                return {"status": "error", "message": f"Error processing transcript: {str(e)}"}

        elif event_type == 'voice_intelligence_transcript_failed':
            logger.warning(
                f"❌ Transcript failed: {safe_log_twilio_sid(transcript_sid)}")
            return {"status": "error", "message": "Transcript processing failed"}

        else:
            logger.info(f"Event type {event_type} - not processing")
            return {"status": "success", "message": f"Event processed: {event_type}"}

    except Exception as e:
        logger.error(f"Error in transcript webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/twilio-callback")
async def handle_twilio_callback(request: Request, db: Session = Depends(get_db)):
    if not config.TWILIO_AUTH_TOKEN and not IS_DEV:
        raise HTTPException(
            status_code=500, detail="Twilio signature validation not configured")

    request_url = str(request.url)
    form_data = await request.form()
    if config.TWILIO_AUTH_TOKEN:
        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        params = dict(form_data)
        if not validator.validate(request_url, params, twilio_signature):
            logger.warning("Invalid Twilio signature on status callback")
            raise HTTPException(status_code=401, detail="Invalid signature")

    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    logger.info(
        f"Received Twilio callback for call {safe_log_twilio_sid(call_sid)} with status {sanitize_text(str(call_status))}")

    if not call_sid:
        return {"status": "error", "message": "No CallSid provided"}
    conversation = db.query(Conversation).filter(
        Conversation.call_sid == call_sid).first()
    if conversation:
        conversation.status = call_status
        db.commit()
    return {"status": "success", "call_sid": call_sid, "call_status": call_status}


@router.post("/recording-callback")
async def handle_recording_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Twilio recording callback"""
    try:
        # Validate Twilio signature if not in development
        if not IS_DEV and config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            form_data = await request.form()
            params = dict(form_data)

            if not validator.validate(request_url, params, twilio_signature):
                logger.warning(
                    "Invalid Twilio signature on recording callback")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")
        else:
            form_data = await request.form()

        # Get form data
        call_sid = form_data.get("CallSid")
        recording_sid = form_data.get("RecordingSid")
        recording_url = form_data.get("RecordingUrl")
        recording_status = form_data.get("RecordingStatus")

        # Safe logging with Twilio SID-specific logging (don't use sanitize_text for SIDs)
        logger.info(f"Recording callback: CallSid={safe_log_twilio_sid(call_sid)}, "
                    f"RecordingSid={safe_log_twilio_sid(recording_sid)}, "
                    f"Status={recording_status or 'None'}")

        # Update conversation with recording info if found
        if call_sid:
            conversation = db.query(Conversation).filter(
                Conversation.call_sid == call_sid
            ).first()

            if conversation:
                conversation.recording_sid = recording_sid
                db.commit()
                logger.info(
                    f"✅ Updated conversation with recording SID: {safe_log_twilio_sid(recording_sid)}")
            else:
                logger.warning(
                    f"⚠️ No conversation found for CallSid: {safe_log_twilio_sid(call_sid)}")
        else:
            logger.warning("⚠️ Recording callback received without CallSid")

        if conversation and recording_status == "completed":
            # Check if this should be transcribed for calendar processing
            if await should_process_for_calendar(db, conversation):
                logger.info(
                    f"🎙️ Auto-triggering transcription for calendar call")

                # Create background task to transcribe
                asyncio.create_task(auto_transcribe_recording(
                    recording_sid, conversation.id))

        return {
            "status": "success",
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "recording_status": recording_status
        }

    except Exception as e:
        logger.error(f"Error handling recording callback: {str(e)}")
        return {"status": "error", "message": str(e)}


async def find_conversation_for_transcript(db: Session, transcript_sid: str, transcript_data, call_sid: str = None) -> Optional[Conversation]:
    """
    Find the conversation record associated with this transcript
    """
    try:
        # First try to find by call_sid if provided
        if call_sid:
            conversation = db.query(Conversation).filter(
                Conversation.call_sid == call_sid
            ).first()
            if conversation:
                logger.info(
                    f"Found conversation {conversation.id} by call_sid: {safe_log_twilio_sid(call_sid)}")
                return conversation

        # Fallback: Look for the most recent completed conversation that doesn't have a transcript yet
        conversation = db.query(Conversation).filter(
            Conversation.transcript.is_(None),
            Conversation.status.in_(["completed", "in-progress"])
        ).order_by(Conversation.created_at.desc()).first()

        if conversation:
            logger.info(
                f"Found conversation {conversation.id} for transcript {safe_log_twilio_sid(transcript_sid)}")

        return conversation

    except Exception as e:
        logger.error(
            f"Error finding conversation for transcript {transcript_sid}: {e}")
        return None


async def should_process_for_calendar(db: Session, conversation: Conversation) -> bool:
    """
    Determine if this conversation should be processed for calendar events
    """
    try:
        # Check if user has calendar credentials
        if conversation.user_id:
            credentials = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == conversation.user_id
            ).first()

            if credentials:
                logger.info(
                    f"User {conversation.user_id} has calendar credentials - enabling calendar processing")
                return True
            else:
                logger.info(
                    f"User {conversation.user_id} has no calendar credentials - skipping calendar processing")

        return False

    except Exception as e:
        logger.error(f"Error checking calendar processing eligibility: {e}")
        return False


async def auto_transcribe_recording(recording_sid: str, conversation_id: int):
    """Auto-trigger transcription using Twilio Voice Intelligence"""
    try:
        from app.services.twilio_intelligence import TwilioIntelligenceService

        intelligence_service = TwilioIntelligenceService()

        # This will automatically trigger the webhook when complete
        await intelligence_service.transcribe_recording(recording_sid)

        logger.info(
            f"✅ Transcription initiated for recording: {recording_sid}")

    except Exception as e:
        logger.error(
            f"Failed to auto-transcribe recording {recording_sid}: {e}")


@router.post("/call-status")
async def handle_twilio_call_status(request: Request, db: Session = Depends(get_db)):
    """Handle Twilio call status webhooks for both inbound and outbound calls"""
    try:
        # Validate Twilio signature
        if not IS_DEV and not config.TWILIO_AUTH_TOKEN:
            raise HTTPException(
                status_code=500, detail="Twilio signature validation not configured")

        if config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            body = await request.body()
            if not validator.validate(request_url, body.decode(), twilio_signature):
                logger.warning(
                    "Invalid Twilio signature on call status webhook")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")

        form_data = await request.form()

        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        # "inbound" or "outbound-api"
        call_direction = form_data.get("Direction")
        from_number = form_data.get("From")
        to_number = form_data.get("To")

        logger.info(
            f"📞 Call status webhook: {safe_log_twilio_sid(call_sid)} - Status: {call_status}, Direction: {call_direction}")

        if call_status == "completed":
            # Trigger transcript creation for completed calls
            await create_transcript_for_call(call_sid, call_direction, from_number, to_number, db)

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error in call status webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/transcript-ready")
async def handle_transcript_ready(request: Request, db: Session = Depends(get_db)):
    """Handle when Twilio Intelligence finishes processing transcript"""
    try:
        # Validate Twilio signature
        if not IS_DEV and not config.TWILIO_AUTH_TOKEN:
            raise HTTPException(
                status_code=500, detail="Twilio signature validation not configured")

        if config.TWILIO_AUTH_TOKEN:
            validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
            twilio_signature = request.headers.get("X-Twilio-Signature", "")
            request_url = str(request.url)
            body = await request.body()
            if not validator.validate(request_url, body.decode(), twilio_signature):
                logger.warning(
                    "Invalid Twilio signature on transcript ready webhook")
                raise HTTPException(
                    status_code=401, detail="Invalid signature")

        form_data = await request.form()

        transcript_sid = form_data.get("TranscriptSid")
        call_sid = form_data.get("CallSid")
        status = form_data.get("Status")

        logger.info(
            f"📋 Transcript ready webhook: {safe_log_twilio_sid(transcript_sid)} - Status: {status}")

        if status == "completed":
            # Fetch and store the completed transcript
            await fetch_and_store_transcript_webhook(transcript_sid, call_sid, db)

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error in transcript ready webhook: {e}")
        return {"status": "error", "message": str(e)}


async def create_transcript_for_call(call_sid: str, call_direction: str, from_number: str, to_number: str, db: Session):
    """Create transcript request for a completed call"""
    try:
        from app.services.twilio_intelligence import TwilioIntelligenceService

        # Normalize direction for storage
        normalized_direction = "inbound" if call_direction == "inbound" else "outbound"

        logger.info(
            f"🎯 Creating transcript for {normalized_direction} call {safe_log_twilio_sid(call_sid)}")

        # Try to find existing conversation record
        conversation = db.query(Conversation).filter(
            Conversation.call_sid == call_sid
        ).first()

        if not conversation:
            # Create conversation record for inbound calls that don't have one yet
            scenario_name = "Inbound Call" if normalized_direction == "inbound" else "Unknown"

            conversation = Conversation(
                call_sid=call_sid,
                phone_number=from_number if normalized_direction == "inbound" else to_number,
                direction=normalized_direction,
                scenario=scenario_name,
                status="completed"
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

            logger.info(
                f"📝 Created conversation record for {normalized_direction} call")

        # Check if we have a recording to transcribe
        # Note: This assumes recordings are enabled for the call
        # You may need to fetch the recording SID from Twilio if not stored
        if conversation.recording_sid:
            intelligence_service = TwilioIntelligenceService()
            await intelligence_service.transcribe_recording(conversation.recording_sid)

            logger.info(
                f"✅ Transcript request initiated for recording {conversation.recording_sid}")
        else:
            logger.warning(
                f"⚠️ No recording SID found for call {safe_log_twilio_sid(call_sid)}")

    except Exception as e:
        logger.error(
            f"Error creating transcript for call {safe_log_twilio_sid(call_sid)}: {e}")


async def fetch_and_store_transcript_webhook(transcript_sid: str, call_sid: str, db: Session):
    """Fetch completed transcript from Twilio and store with proper call direction"""
    try:
        # Check if transcript already exists
        existing_transcript = db.query(TranscriptRecord).filter(
            TranscriptRecord.transcript_sid == transcript_sid
        ).first()

        if existing_transcript:
            logger.info(
                f"📋 Transcript {safe_log_twilio_sid(transcript_sid)} already stored")
            return existing_transcript

        # Fetch transcript from Twilio
        client = get_twilio_client()
        transcript = client.intelligence.v2.transcripts(transcript_sid).fetch()
        sentences = client.intelligence.v2.transcripts(
            transcript_sid).sentences.list()

        # Sort sentences by start time
        sorted_sentences = sorted(
            sentences, key=lambda s: getattr(s, "start_time", 0))

        # Create full text from sentences
        full_text = " ".join(
            getattr(s, "transcript", "No text available")
            for s in sorted_sentences
        )

        # Helper function for decimal conversion
        def decimal_to_float(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        # Find associated conversation to get call direction
        conversation = db.query(Conversation).filter(
            Conversation.call_sid == call_sid
        ).first()

        call_direction = "outbound"  # default
        scenario_name = "Voice Call"  # default
        user_id = None

        if conversation:
            call_direction = conversation.direction or "outbound"
            scenario_name = conversation.scenario or (
                "Inbound Call" if call_direction == "inbound" else "Voice Call")
            user_id = conversation.user_id

            # Update conversation with transcript
            conversation.transcript = full_text

        # Create new TranscriptRecord with proper call direction
        new_transcript = TranscriptRecord(
            transcript_sid=transcript_sid,
            status=transcript.status,
            full_text=full_text,
            date_created=transcript.date_created,
            date_updated=transcript.date_updated,
            duration=decimal_to_float(transcript.duration),
            language_code=transcript.language_code,
            user_id=user_id,
            call_direction=call_direction,  # Ensure call_direction is properly stored
            scenario_name=scenario_name,
            source_type="TwilioIntelligence",
            sentences_json=json.dumps([{
                "transcript": getattr(s, "transcript", "No text available"),
                "speaker": getattr(s, "media_channel", 0),
                "start_time": decimal_to_float(getattr(s, "start_time", 0)),
                "end_time": decimal_to_float(getattr(s, "end_time", 0)),
                "confidence": decimal_to_float(getattr(s, "confidence", None))
            } for s in sorted_sentences], default=decimal_to_float)
        )

        db.add(new_transcript)
        db.commit()
        db.refresh(new_transcript)

        logger.info(
            f"✅ Stored transcript {safe_log_twilio_sid(transcript_sid)} with direction: {call_direction}")

        return new_transcript

    except Exception as e:
        logger.error(
            f"Error fetching and storing transcript {safe_log_twilio_sid(transcript_sid)}: {e}")
        raise
