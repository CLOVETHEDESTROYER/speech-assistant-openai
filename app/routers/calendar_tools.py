from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import logging
from app.db import get_db
from app.models import User, GoogleCalendarCredentials
from app.utils.crypto import decrypt_string
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import pytz

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools")

class CreateCalendarEventRequest(BaseModel):
    summary: str
    start_iso: str  # RFC3339 format
    end_iso: str    # RFC3339 format
    timezone: str = "America/Denver"  # IANA timezone
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    attendee_email: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    user_id: int  # Passed from the Realtime session

@router.post("/createCalendarEvent")
async def create_calendar_event_tool(
    request: CreateCalendarEventRequest,
    db: Session = Depends(get_db)
):
    """Real-time calendar event creation tool called by OpenAI Realtime API"""
    try:
        logger.info(f"📅 Creating calendar event for user {request.user_id}: {request.summary}")
        
        # Get user and validate calendar credentials
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == request.user_id
        ).first()
        
        if not credentials:
            raise HTTPException(status_code=400, detail="No Google Calendar access configured")
        
        # Parse and validate datetime
        try:
            start_dt = datetime.fromisoformat(request.start_iso.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(request.end_iso.replace('Z', '+00:00'))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
        
        if end_dt <= start_dt:
            raise HTTPException(status_code=400, detail="End time must be after start time")
        
        # Validate timezone
        try:
            tz = pytz.timezone(request.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            # Default to America/Denver as specified in requirements
            request.timezone = "America/Denver"
            logger.warning(f"Invalid timezone, defaulting to America/Denver")
        
        # Create Google Calendar service
        google_creds = Credentials(
            token=decrypt_string(credentials.token),
            refresh_token=decrypt_string(credentials.refresh_token) if credentials.refresh_token else None,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=['https://www.googleapis.com/auth/calendar.events']  # Minimal scope as specified
        )
        
        service = build('calendar', 'v3', credentials=google_creds)
        
        # Check for conflicts (optional)
        try:
            conflicts = service.events().list(
                calendarId='primary',
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True
            ).execute()
            
            if conflicts.get('items'):
                logger.warning(f"Potential calendar conflict detected for {request.summary}")
        except Exception as e:
            logger.warning(f"Could not check conflicts: {e}")
        
        # Create event body as per specification
        description = "Set by voice agent."
        if request.customer_name:
            description += f"\\nName: {request.customer_name}"
        if request.customer_phone:
            description += f"\\nPhone: {request.customer_phone}"
        if request.notes:
            description += f"\\nNotes: {request.notes}"
        
        event_body = {
            "summary": request.summary,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": request.timezone
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": request.timezone
            },
            "location": request.location or "",
            "attendees": [{"email": request.attendee_email}] if request.attendee_email else [],
            "reminders": {"useDefault": True}
        }
        
        # Create the event
        created_event = service.events().insert(
            calendarId='primary',
            body=event_body,
            sendUpdates='all' if request.attendee_email else 'none'
        ).execute()
        
        logger.info(f"✅ Calendar event created: {created_event.get('id')}")
        
        # Format response for voice confirmation
        start_formatted = start_dt.strftime("%A, %B %d at %I:%M %p")
        
        return {
            "status": "created",
            "id": created_event.get('id'),
            "htmlLink": created_event.get('htmlLink'),
            "summary": request.summary,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "formatted_time": start_formatted,
            "message": f"Calendar event '{request.summary}' created for {start_formatted}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create calendar event: {str(e)}")


@router.get("/health")
async def calendar_tools_health():
    """Health check for calendar tools"""
    return {"status": "ok", "service": "calendar-tools"}
