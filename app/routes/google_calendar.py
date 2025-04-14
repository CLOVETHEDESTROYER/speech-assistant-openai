from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.services.google_calendar import GoogleCalendarService
from app.models import User, GoogleCalendarCredentials
from app.db import get_db
from app.auth import get_current_user
from app.schemas import CallScheduleCreate
import os
from datetime import timedelta

router = APIRouter(prefix="/google-calendar")


@router.get("/auth")
async def google_auth(request: Request, current_user: User = Depends(get_current_user)):
    calendar_service = GoogleCalendarService()
    flow = calendar_service.create_oauth_flow()
    # Include all required parameters and set prompt to consent
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return {"authorization_url": authorization_url}


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calendar_service = GoogleCalendarService()
    flow = calendar_service.create_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Store credentials in database
    google_creds = GoogleCalendarCredentials(
        user_id=current_user.id,
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_expiry=credentials.expiry
    )
    db.add(google_creds)
    db.commit()

    return {"message": "Calendar integration successful"}


@router.post("/schedule")
async def schedule_calendar_event(
    call_schedule: CallScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get user's Google credentials
    credentials = db.query(GoogleCalendarCredentials).filter(
        GoogleCalendarCredentials.user_id == current_user.id
    ).first()

    if not credentials:
        raise HTTPException(
            status_code=401, detail="Google Calendar not connected")

    calendar_service = GoogleCalendarService()
    service = calendar_service.get_calendar_service({
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "expiry": credentials.token_expiry.isoformat()
    })

    # Schedule both the call and calendar event
    event = await calendar_service.schedule_call(service, call_schedule.dict())

    return {"message": "Call scheduled with calendar event", "event_id": event["id"]}
