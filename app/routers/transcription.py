import tempfile
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User
from app.services.transcription import TranscriptionService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/transcribe-audio")
async def transcribe_audio_api(
    request: Request,
    audio_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Transcribe an uploaded audio file and save conversation if applicable."""
    transcription_service = TranscriptionService()
    try:
        # Read file content
        content = await audio_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Transcribe
        transcription_result = await transcription_service.transcribe_audio(content)
        if not transcription_result:
            raise HTTPException(status_code=500, detail="Transcription failed")

        # This endpoint just returns text; saving flows in other endpoints
        return {"transcript": transcription_result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in transcribe_audio_api: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


