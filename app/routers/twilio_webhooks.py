from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from app import config
from app.db import get_db
from app.utils.log_helpers import safe_log_request_data, sanitize_text
from app.services.twilio_client import get_twilio_client
from app.models import Conversation
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/twilio-transcripts/webhook-callback")
async def handle_transcript_webhook(request: Request, db: Session = Depends(get_db)):
    if config.TWILIO_AUTH_TOKEN:
        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        request_url = str(request.url)
        if not validator.validate(request_url, {}, twilio_signature):
            logger.warning("Invalid Twilio signature on transcript webhook")
            raise HTTPException(status_code=401, detail="Invalid signature")
    else:
        logger.warning("TWILIO_AUTH_TOKEN not configured; skipping signature validation for transcript webhook")

    payload = await request.json()
    logger.info(f"Received transcript webhook callback: {safe_log_request_data(payload)}")
    # Existing logic can be moved here from main.py as needed
    return {"status": "ok"}


@router.post("/twilio-callback")
async def handle_twilio_callback(request: Request, db: Session = Depends(get_db)):
    request_url = str(request.url)
    form_data = await request.form()
    if config.TWILIO_AUTH_TOKEN:
        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        params = dict(form_data)
        if not validator.validate(request_url, params, twilio_signature):
            logger.warning("Invalid Twilio signature on status callback")
            raise HTTPException(status_code=401, detail="Invalid signature")
    else:
        logger.warning("TWILIO_AUTH_TOKEN not configured; skipping signature validation for status callback")

    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    logger.info(
        f"Received Twilio callback for call {sanitize_text(str(call_sid))} with status {sanitize_text(str(call_status))}")

    if not call_sid:
        return {"status": "error", "message": "No CallSid provided"}
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    if conversation:
        conversation.status = call_status
        db.commit()
    return {"status": "success", "call_sid": call_sid, "call_status": call_status}


