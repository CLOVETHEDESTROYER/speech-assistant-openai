from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging
from ..db import get_db
from ..models import Conversation
from ..schemas import ConversationResponse
from ..auth import get_current_user

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()


@router.get("/transcripts/", response_model=List[ConversationResponse])
async def get_transcripts(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get list of transcripts for the current user"""
    logger.info(f"Fetching transcripts for user {current_user.id}")
    transcripts = db.query(Conversation)\
        .filter(Conversation.user_id == current_user.id)\
        .offset(skip)\
        .limit(limit)\
        .all()
    logger.info(f"Found {len(transcripts)} transcripts")

    # Convert datetime objects to strings
    for transcript in transcripts:
        if hasattr(transcript, 'created_at') and transcript.created_at:
            transcript.created_at = str(transcript.created_at)

    return transcripts


@router.get("/transcripts/{sid}", response_model=ConversationResponse)
async def get_transcript(
    sid: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get a specific transcript by SID (supports both Call SID and Recording SID)
    """
    logger.info(f"Fetching transcript for SID {sid}")

    # Try to find by call_sid first
    transcript = db.query(Conversation)\
        .filter(Conversation.call_sid == sid)\
        .filter(Conversation.user_id == current_user.id)\
        .first()

    # If not found by call_sid, try by recording_sid
    if not transcript:
        logger.info(
            f"Transcript not found by call_sid, trying recording_sid {sid}")
        transcript = db.query(Conversation)\
            .filter(Conversation.recording_sid == sid)\
            .filter(Conversation.user_id == current_user.id)\
            .first()

    if not transcript:
        logger.warning(f"Transcript not found for SID {sid}")
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Convert datetime objects to strings
    if hasattr(transcript, 'created_at') and transcript.created_at:
        transcript.created_at = str(transcript.created_at)

    return transcript
