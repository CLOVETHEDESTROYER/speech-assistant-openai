import os
import time
import threading
import datetime
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, JSONResponse, status
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db import get_db
from app.models import User, Conversation, UserPhoneNumber, GoogleCalendarCredentials
from app.services.twilio_client import get_twilio_client
from app.services.google_calendar import GoogleCalendarService
from app import config
from app.limiter import rate_limit
from app.utils.crypto import decrypt_string
from app.utils.url_helpers import clean_and_validate_url
from app.main import USER_CONFIG, DEVELOPMENT_MODE, SCENARIOS
from app.utils.log_helpers import sanitize_text
from twilio.base.exceptions import TwilioRestException

router = APIRouter()


@router.get("/make-call/{phone_number}/{scenario}")
@rate_limit("2/minute")
async def make_call(
    request: Request,
    phone_number: str,
    scenario: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if not DEVELOPMENT_MODE:
            from app.services.usage_service import UsageService
            from app.models import AppType, UsageLimits

            usage_limits = db.query(UsageLimits).filter(
                UsageLimits.user_id == current_user.id).first()
            if not usage_limits:
                app_type = UsageService.detect_app_type_from_request(request)
                usage_limits = UsageService.initialize_user_usage(
                    current_user.id, app_type, db)

            if usage_limits.app_type == AppType.WEB_BUSINESS:
                can_call, status_code, details = UsageService.can_make_call(
                    current_user.id, db)
                if not can_call:
                    if status_code == "trial_calls_exhausted":
                        raise HTTPException(
                            status_code=402,
                            detail={
                                "error": "trial_exhausted",
                                "message": "Your 4 free trial calls have been used. Upgrade to Basic ($49.99/month) for 20 calls per week!",
                                "upgrade_url": "/pricing",
                                "pricing": details.get("pricing")
                            }
                        )
                    elif status_code == "weekly_limit_reached":
                        raise HTTPException(
                            status_code=402,
                            detail={
                                "error": "weekly_limit_reached",
                                "message": details.get("message"),
                                "resets_on": details.get("resets_on"),
                                "upgrade_url": "/pricing"
                            }
                        )
                    else:
                        raise HTTPException(status_code=400, detail=details.get(
                            "message", "Cannot make call"))

        from_number = None
        if DEVELOPMENT_MODE:
            from_number = os.getenv('TWILIO_PHONE_NUMBER')
            if not from_number:
                raise HTTPException(
                    status_code=400,
                    detail="System phone number not configured for development mode. Please set TWILIO_PHONE_NUMBER in your environment."
                )
        else:
            user_phone_numbers = db.query(UserPhoneNumber).filter(
                UserPhoneNumber.user_id == current_user.id,
                UserPhoneNumber.is_active == True,
                UserPhoneNumber.voice_capable == True
            ).all()

            if user_phone_numbers:
                from_number = user_phone_numbers[0].phone_number
            else:
                from_number = os.getenv('TWILIO_PHONE_NUMBER')
                if not from_number:
                    raise HTTPException(
                        status_code=400,
                        detail="No phone number available. Please provision a phone number in Settings or configure TWILIO_PHONE_NUMBER."
                    )

        base_url = clean_and_validate_url(config.PUBLIC_URL)
        user_name = USER_CONFIG.get("name", "")
        outgoing_call_url = f"{base_url}/outgoing-call/{scenario}?direction=outbound&user_name={user_name}"

        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number,
            from_=from_number,
            url=outgoing_call_url,
            record=True
        )

        conversation = Conversation(
            user_id=current_user.id,
            scenario=scenario,
            phone_number=phone_number,
            direction="outbound",
            status="in-progress",
            call_sid=call.sid
        )
        db.add(conversation)
        db.commit()

        return {"status": "success", "call_sid": call.sid, "message": "Call initiated"}
    except TwilioRestException as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": f"An error occurred with the phone service: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": f"An error occurred: {str(e)}"})


@router.get("/make-calendar-call-scenario/{phone_number}")
@rate_limit("2/minute")
async def make_calendar_call_scenario(
    request: Request,
    phone_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if not phone_number.startswith('+'):
            phone_number = f"+{phone_number}"

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

        time_min = datetime.datetime.utcnow()
        events = await calendar_service.get_upcoming_events(service, max_results=5, time_min=time_min)

        events_context = ""
        if events:
            events_context = "Here are the user's upcoming calendar events:\n"
            for event in events:
                if 'dateTime' in event.get('start', {}):
                    start_time = event['start']['dateTime']
                    end_time = event['end']['dateTime']
                else:
                    start_time = event.get('start', {}).get('date', '')
                    end_time = event.get('end', {}).get('date', '')
                events_context += f"- {event.get('summary', 'No title')} from {start_time} to {end_time}\n"
        else:
            events_context = "The user has no upcoming events on their calendar."

        start_date = datetime.datetime.utcnow()
        end_date = start_date + timedelta(days=7)
        free_slots = await calendar_service.find_free_slots(service, start_date, end_date, min_duration_minutes=30, max_results=3, working_hours=(9, 17))

        slots_context = ""
        if free_slots:
            slots_context = "Here are some available time slots in the user's calendar:\n"
            for start, end in free_slots:
                slots_context += f"- {start.strftime('%A, %B %d at %I:%M %p')} to {end.strftime('%I:%M %p')}\n"
        else:
            slots_context = "The user has no free time slots in the next week."

        temp_scenario_key = f"calendar_{current_user.id}_{int(time.time())}"
        calendar_scenario = {
            "persona": "Calendar Assistant",
            "prompt": (
                f"You are a helpful calendar assistant handling a phone call. "
                f"You have access to the caller's Google Calendar. Be conversational and friendly. "
                f"\n\n{events_context}\n\n{slots_context}\n\n"
                f"You can provide information about upcoming events, check availability, "
                f"and suggest free time slots. If the caller asks about scheduling an event, "
                f"collect the necessary details like date, time, duration, and purpose. "
                f"Remain connected and responsive during silences. "
                f"Offer to help with any other calendar-related questions they might have."
            ),
            "voice_config": {"voice": "alloy", "temperature": 0.7}
        }
        SCENARIOS[temp_scenario_key] = calendar_scenario

        base_url = clean_and_validate_url(config.PUBLIC_URL)
        user_name = current_user.email
        outgoing_call_url = f"{base_url}/outgoing-call/{temp_scenario_key}?direction=outbound&user_name={user_name}"

        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number, from_=config.TWILIO_PHONE_NUMBER, url=outgoing_call_url, record=True)

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

        def remove_temp_scenario():
            try:
                if temp_scenario_key in SCENARIOS:
                    del SCENARIOS[temp_scenario_key]
            except Exception:
                pass

        threading.Timer(3600, remove_temp_scenario).start()
        return {"status": "success", "call_sid": call.sid, "message": "Calendar call initiated using scenario approach", "scenario_key": temp_scenario_key}
    except TwilioRestException as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": f"An error occurred with the phone service: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": f"An error occurred: {str(e)}"})
