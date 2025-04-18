from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.services.google_calendar import GoogleCalendarService
from app.models import User, GoogleCalendarCredentials, Conversation
from app.db import get_db
from app.auth import get_current_user
from app.schemas import CallScheduleCreate
import os
import json
import logging
from datetime import timedelta, datetime
from typing import List, Optional
from pydantic import BaseModel
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect
from app.services.twilio_client import get_twilio_client
from app.config import PUBLIC_URL

logger = logging.getLogger(__name__)

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

    # Store user ID in state by appending it to the URL
    # We'll extract this in the callback
    state_data = f"{state}:{current_user.id}"

    return {"authorization_url": authorization_url.replace(f"state={state}", f"state={state_data}")}


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    # Extract user ID from state
    state_parts = state.split(":")
    if len(state_parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    user_id = state_parts[1]

    # Get user from database
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

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


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class AvailabilityResponse(BaseModel):
    is_available: bool


class TimeSlotList(BaseModel):
    free_slots: List[TimeSlot]


@router.get("/events", response_model=List[dict])
async def get_upcoming_events(
    max_results: int = 10,
    days_ahead: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get upcoming events from the user's calendar"""
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

    # Get events for the specified time range
    time_min = datetime.utcnow()
    events = await calendar_service.get_upcoming_events(
        service,
        max_results=max_results,
        time_min=time_min
    )

    # Format events for response
    formatted_events = []
    for event in events:
        if 'dateTime' in event.get('start', {}):
            start_time = event['start']['dateTime']
            end_time = event['end']['dateTime']
        else:
            # All-day event
            start_time = event.get('start', {}).get('date', '')
            end_time = event.get('end', {}).get('date', '')

        formatted_events.append({
            'id': event.get('id', ''),
            'summary': event.get('summary', 'No title'),
            'start': start_time,
            'end': end_time,
            'location': event.get('location', ''),
            'description': event.get('description', '')
        })

    return formatted_events


@router.get("/check-availability", response_model=AvailabilityResponse)
async def check_time_availability(
    start_time: datetime,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check if a specific time is available in the calendar"""
    if not end_time:
        # Default to 30 minutes if no end time provided
        end_time = start_time + timedelta(minutes=30)

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

    # Check availability
    is_available = await calendar_service.check_availability(service, start_time, end_time)

    return {"is_available": is_available}


@router.get("/find-slots", response_model=TimeSlotList)
async def find_available_slots(
    start_date: datetime,
    end_date: Optional[datetime] = None,
    min_duration: int = 30,
    max_results: int = 5,
    start_hour: int = 9,
    end_hour: int = 17,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Find available time slots in the calendar"""
    if not end_date:
        # Default to 7 days if no end date provided
        end_date = start_date + timedelta(days=7)

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

    # Find free slots
    free_slots = await calendar_service.find_free_slots(
        service,
        start_date,
        end_date,
        min_duration_minutes=min_duration,
        max_results=max_results,
        working_hours=(start_hour, end_hour)
    )

    # Format slots for response
    formatted_slots = [TimeSlot(start=start, end=end)
                       for start, end in free_slots]

    return {"free_slots": formatted_slots}


@router.api_route("/incoming-calendar-call", methods=["GET", "POST"])
async def handle_incoming_calendar_call(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle incoming calls requesting calendar information"""
    logger.info("Incoming calendar call webhook received")
    try:
        # Get form data (to identify caller)
        form_data = await request.form()
        caller = form_data.get("From", "unknown")
        call_sid = form_data.get("CallSid", "unknown")
        logger.info(
            f"Incoming calendar call from: {caller}, CallSid: {call_sid}")

        # Get the base URL from PUBLIC_URL env var and validate it
        base_url = PUBLIC_URL
        if not base_url:
            raise ValueError("PUBLIC_URL environment variable is not set")

        # Ensure base URL has the correct protocol
        if not base_url.startswith('http://') and not base_url.startswith('https://'):
            base_url = f"https://{base_url}"

        # Clean up the URL (remove trailing slashes)
        base_url = base_url.rstrip('/')

        # Replace http with ws for WebSocket protocol
        ws_base_url = base_url.replace(
            'http://', 'ws://').replace('https://', 'wss://')

        # Build the WebSocket URL
        ws_url = f"{ws_base_url}/calendar-media-stream?caller={caller}"
        logger.info(f"Setting up WebSocket connection at: {ws_url}")

        # Create TwiML response
        response = VoiceResponse()

        # Add a greeting message
        response.say(
            "Connecting you to your calendar assistant. One moment please.",
            voice="alloy",
            language="en-US"
        )

        # Add a pause to allow the server to initialize
        response.pause(length=1)

        # Set up the stream connection
        connect = Connect()
        connect.stream(url=ws_url)
        response.append(connect)

        # Create conversation record for tracking
        try:
            # Find the user by phone number
            normalized_phone = caller.replace('+', '').replace(' ', '')
            existing_conversation = db.query(Conversation).filter(
                Conversation.phone_number.like(f"%{normalized_phone}%")
            ).order_by(Conversation.created_at.desc()).first()

            user_id = None
            if existing_conversation and existing_conversation.user_id:
                user_id = existing_conversation.user_id
            else:
                # Try to find a user with calendar credentials as fallback
                credentials = db.query(GoogleCalendarCredentials).first()
                if credentials:
                    user_id = credentials.user_id

            if user_id:
                conversation = Conversation(
                    user_id=user_id,
                    scenario="calendar",
                    phone_number=caller,
                    direction="inbound",
                    status="in-progress",
                    call_sid=call_sid
                )
                db.add(conversation)
                db.commit()
                logger.info(
                    f"Created conversation record for calendar call: {call_sid}")
        except Exception as e:
            logger.error(f"Error creating conversation record: {e}")
            # Continue anyway - this shouldn't block the call

        twiml = str(response)
        logger.info(f"Generated TwiML response: {twiml}")

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(
            f"Error in handle_incoming_calendar_call: {e}", exc_info=True)
        # Create a fallback TwiML response in case of error
        response = VoiceResponse()
        response.say(
            "I'm sorry, there was an error connecting to the calendar service. Please try again later.",
            voice="alloy",
            language="en-US"
        )
        return Response(content=str(response), media_type="application/xml")


@router.get("/make-calendar-call/{phone_number}")
async def make_calendar_call(
    request: Request,
    phone_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate an outbound call to discuss calendar events"""
    try:
        # Validate phone number format
        if not phone_number.startswith('+'):
            phone_number = f"+{phone_number}"

        logger.info(
            f"Initiating calendar call to {phone_number} for user {current_user.email}")

        # Check if user has Google Calendar connected
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == current_user.id
        ).first()

        if not credentials:
            raise HTTPException(
                status_code=401, detail="Google Calendar not connected")

        # Build the webhook URL for the calendar call
        base_url = os.getenv("PUBLIC_URL", "").strip()
        if not base_url:
            raise HTTPException(
                status_code=500, detail="PUBLIC_URL not configured")

        # Ensure the URL has the https:// protocol and no trailing slash
        if not base_url.startswith('http://') and not base_url.startswith('https://'):
            base_url = f"https://{base_url}"
        base_url = base_url.rstrip('/')

        webhook_url = f"{base_url}/google-calendar/incoming-calendar-call"
        logger.info(f"Using webhook URL: {webhook_url}")

        # Check that Twilio phone number is configured
        twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        if not twilio_phone:
            raise HTTPException(
                status_code=500, detail="TWILIO_PHONE_NUMBER not configured")

        # Make the call
        try:
            client = get_twilio_client()
            call = client.calls.create(
                to=phone_number,
                from_=twilio_phone,
                url=webhook_url,
                record=True,
                timeout=30,  # 30 seconds timeout to prevent long waits
                status_callback=f"{base_url}/twilio-callback",
                status_callback_event=["completed", "failed"],
                status_callback_method="POST"
            )
            logger.info(
                f"Twilio call initiated successfully with SID: {call.sid}")

            # Create a conversation record
            conversation = Conversation(
                user_id=current_user.id,
                scenario="calendar",
                phone_number=phone_number,
                direction="outbound",
                status="in-progress",
                call_sid=call.sid
            )
            db.add(conversation)
            db.commit()

            return {
                "status": "success",
                "call_sid": call.sid,
                "message": "Calendar call initiated",
                "phone_number": phone_number
            }
        except Exception as twilio_error:
            logger.error(f"Twilio error: {str(twilio_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error from Twilio: {str(twilio_error)}"
            )

    except HTTPException:
        # Pass through HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error making calendar call: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while initiating the calendar call. Please try again later."
        )
