from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from app import config
from app.db import get_db
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.services.twilio_client import get_twilio_client
from app.models import Conversation
import logging
import os

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
    if not config.TWILIO_AUTH_TOKEN and not IS_DEV:
        raise HTTPException(
            status_code=500, detail="Twilio signature validation not configured")

    if config.TWILIO_AUTH_TOKEN:
        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        request_url = str(request.url)
        if not validator.validate(request_url, {}, twilio_signature):
            logger.warning("Invalid Twilio signature on transcript webhook")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    logger.info(
        f"Received transcript webhook callback: {safe_log_request_data(payload)}")
    # Existing logic can be moved here from main.py as needed
    return {"status": "ok"}


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

        return {
            "status": "success",
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "recording_status": recording_status
        }

    except Exception as e:
        logger.error(f"Error handling recording callback: {str(e)}")
        return {"status": "error", "message": str(e)}
