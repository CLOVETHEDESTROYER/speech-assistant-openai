from fastapi import APIRouter, Depends, HTTPException, Body, Request
from typing import Optional
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.utils.twilio_helpers import with_twilio_retry
from app.limiter import rate_limit
from app.models import User
from app.services.twilio_client import get_twilio_client

router = APIRouter()


@router.get("/twilio-transcripts/{transcript_sid}")
@with_twilio_retry(max_retries=3)
async def get_twilio_transcript(transcript_sid: str, current_user: User = Depends(get_current_user)):
    try:
        transcript = get_twilio_client().intelligence.v2.transcripts(transcript_sid).fetch()
        sentences = get_twilio_client().intelligence.v2.transcripts(
            transcript_sid).sentences.list()
        formatted_transcript = {
            "sid": transcript.sid,
            "status": transcript.status,
            "date_created": str(transcript.date_created) if transcript.date_created else None,
            "date_updated": str(transcript.date_updated) if transcript.date_updated else None,
            "duration": transcript.duration,
            "language_code": transcript.language_code,
            "sentences": []
        }
        if sentences:
            formatted_transcript["sentences"] = [
                {
                    "text": getattr(sentence, "transcript", "No text available"),
                    "speaker": getattr(sentence, "media_channel", 0),
                    "start_time": getattr(sentence, "start_time", 0),
                    "end_time": getattr(sentence, "end_time", 0),
                    "confidence": getattr(sentence, "confidence", None)
                } for sentence in sentences
            ]
        return formatted_transcript
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twilio-transcripts")
@with_twilio_retry(max_retries=3)
async def list_twilio_transcripts(
    page_size: int = 20,
    page_token: Optional[str] = None,
    status: Optional[str] = None,
    source_sid: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    try:
        params = {"limit": page_size}
        if page_token:
            params["page_token"] = page_token
        if status:
            params["status"] = status
        if source_sid:
            params["source_sid"] = source_sid
        transcripts = get_twilio_client().intelligence.v2.transcripts.list(**params)
        formatted_transcripts = [
            {
                "sid": t.sid,
                "status": t.status,
                "date_created": str(t.date_created) if t.date_created else None,
                "date_updated": str(t.date_updated) if t.date_updated else None,
                "duration": t.duration,
                "language_code": t.language_code
            }
            for t in transcripts
        ]
        return {"transcripts": formatted_transcripts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twilio-transcripts/recording/{recording_sid}")
@with_twilio_retry(max_retries=3)
async def get_transcript_by_recording(recording_sid: str, current_user: User = Depends(get_current_user)):
    try:
        transcript_list = get_twilio_client().intelligence.v2.transcripts.list(
            source_sid=recording_sid, limit=1)
        if not transcript_list:
            raise HTTPException(status_code=404, detail="Transcript not found")
        transcript = transcript_list[0]
        return {"transcript_sid": transcript.sid, "status": transcript.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/twilio-transcripts/create-with-media-url")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def create_transcript_with_media_url(
    request: Request,
    media_url: str = Body(...),
    language_code: str = Body("en-US"),
    redaction: bool = Body(True),
    customer_key: str = Body(None),
    data_logging: bool = Body(True),
    current_user: User = Depends(get_current_user)
):
    try:
        transcript = get_twilio_client().intelligence.v2.transcripts.create(
            service_sid=config.TWILIO_VOICE_INTELLIGENCE_SID,
            channel={"media_properties": {"source_url": media_url}},
            language_code=language_code,
            redaction=redaction
        )
        return {"status": "success", "transcript_sid": transcript.sid, "message": "Transcript creation initiated"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred while creating the transcript")


@router.post("/twilio-transcripts/create-with-participants")
@with_twilio_retry(max_retries=3)
async def create_transcript_with_participants(
    current_user: User = Depends(get_current_user),
):
    # Placeholder to be filled with actual implementation moved from main
    return {"status": "not_implemented"}
