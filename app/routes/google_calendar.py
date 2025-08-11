from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
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
from app.utils.crypto import encrypt_string, decrypt_string
from fastapi import status
from uuid import uuid4
from datetime import timedelta
from fastapi import BackgroundTasks
from app.limiter import rate_limit

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

    # Create opaque state with user binding and ttl via server-side store (signed/opaque)
    # For simplicity, include a nonce we can validate later using server session (or Redis); here we encrypt
    nonce = str(uuid4())
    combined = f"{state}:{current_user.id}:{nonce}"
    secure_state = encrypt_string(combined)
    return {"authorization_url": authorization_url.replace(f"state={state}", f"state={secure_state}")}


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """
    Google OAuth callback endpoint that processes the authorization code
    and redirects back to the frontend with success/error status.
    """
    try:
        # Decrypt and validate state
        try:
            decrypted = decrypt_string(state)
        except Exception:
            logger.error("Failed to decrypt state parameter")
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        state_parts = decrypted.split(":")
        if len(state_parts) < 3:
            logger.error(f"Invalid state parameter structure: {decrypted}")
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        user_id = state_parts[1]
        logger.info(
            f"Processing Google Calendar callback for user ID: {user_id}")

        # Get user from database
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user:
            logger.error(f"User not found for ID: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        # Process OAuth callback
        calendar_service = GoogleCalendarService()
        flow = calendar_service.create_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Check if user already has credentials and update them, or create new ones
        existing_creds = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == current_user.id
        ).first()

        if existing_creds:
            # Update existing credentials
            existing_creds.token = encrypt_string(credentials.token)
            existing_creds.refresh_token = encrypt_string(credentials.refresh_token)
            existing_creds.token_expiry = credentials.expiry
            existing_creds.updated_at = datetime.utcnow()
            logger.info(
                f"Updated existing Google Calendar credentials for user {current_user.email}")
        else:
            # Create new credentials
            google_creds = GoogleCalendarCredentials(
                user_id=current_user.id,
                token=encrypt_string(credentials.token),
                refresh_token=encrypt_string(credentials.refresh_token),
                token_expiry=credentials.expiry
            )
            db.add(google_creds)
            logger.info(
                f"Created new Google Calendar credentials for user {current_user.email}")

        db.commit()

        # Get frontend URL from environment variable
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")

        # Return HTML that redirects to frontend with success parameters
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Calendar Connected</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 2rem;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
                }}
                .success-icon {{
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }}
                h1 {{
                    margin: 0 0 1rem 0;
                    font-size: 2rem;
                }}
                p {{
                    margin: 0.5rem 0;
                    opacity: 0.9;
                }}
                .redirect-link {{
                    color: #fff;
                    text-decoration: underline;
                }}
            </style>
            <script>
                // Redirect after 3 seconds
                setTimeout(() => {{
                    window.location.href = '{frontend_url}/scheduled-meetings?success=true&connected=calendar';
                }}, 3000);
                
                // Also allow immediate redirect if user clicks
                function redirectNow() {{
                    window.location.href = '{frontend_url}/scheduled-meetings?success=true&connected=calendar';
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Google Calendar Connected!</h1>
                <p>Your Google Calendar has been successfully connected to your account.</p>
                <p>You can now schedule AI calls directly from your calendar events.</p>
                <br>
                <p>Redirecting you back to the application in 3 seconds...</p>
                <p>If you're not redirected automatically, <a href="javascript:redirectNow()" class="redirect-link">click here</a>.</p>
            </div>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}", exc_info=True)

        # Get frontend URL for error redirect
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")

        # Return error HTML that redirects to frontend with error parameters
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Calendar Connection Failed</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 2rem;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
                }}
                .error-icon {{
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }}
                h1 {{
                    margin: 0 0 1rem 0;
                    font-size: 2rem;
                }}
                p {{
                    margin: 0.5rem 0;
                    opacity: 0.9;
                }}
                .redirect-link {{
                    color: #fff;
                    text-decoration: underline;
                }}
            </style>
            <script>
                // Redirect after 5 seconds for error case
                setTimeout(() => {{
                    window.location.href = '{frontend_url}/scheduled-meetings?error=calendar_connection_failed&message=' + encodeURIComponent('There was an error connecting your Google Calendar. Please try again.');
                }}, 5000);
                
                function redirectNow() {{
                    window.location.href = '{frontend_url}/scheduled-meetings?error=calendar_connection_failed&message=' + encodeURIComponent('There was an error connecting your Google Calendar. Please try again.');
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">❌</div>
                <h1>Calendar Connection Failed</h1>
                <p>There was an error connecting your Google Calendar.</p>
                <p>Please try again or contact support if the problem persists.</p>
                <br>
                <p>Redirecting you back to the application in 5 seconds...</p>
                <p>If you're not redirected automatically, <a href="javascript:redirectNow()" class="redirect-link">click here</a>.</p>
            </div>
        </body>
        </html>
        """

        return HTMLResponse(content=error_html)


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
        "token": decrypt_string(credentials.token),
        "refresh_token": decrypt_string(credentials.refresh_token),
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
        "token": decrypt_string(credentials.token),
        "refresh_token": decrypt_string(credentials.refresh_token),
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
        "token": decrypt_string(credentials.token),
        "refresh_token": decrypt_string(credentials.refresh_token),
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
@rate_limit("1/minute")
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
