import os
import time
import threading
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db import get_db
from app.models import User, CustomScenario, Conversation
from app.services.twilio_client import get_twilio_client
from app import config
from app.limiter import rate_limit
from app.utils.url_helpers import clean_and_validate_url
from app.app_config import USER_CONFIG, DEVELOPMENT_MODE, SCENARIOS, VOICES
from app.utils.log_helpers import sanitize_text
from twilio.base.exceptions import TwilioRestException

router = APIRouter()


@router.post("/realtime/custom-scenario", response_model=dict)
@rate_limit("10/minute")
async def create_custom_scenario(
    request: Request,
    persona: str = Body(..., min_length=10, max_length=5000),
    prompt: str = Body(..., min_length=10, max_length=5000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a custom scenario"""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
            )

        # Check if user has reached the limit of 20 custom scenarios
        user_scenarios_count = db.query(CustomScenario).filter(
            CustomScenario.user_id == current_user.id
        ).count()

        if user_scenarios_count >= 20:
            raise HTTPException(
                status_code=400,
                detail="You have reached the maximum limit of 20 custom scenarios. Please delete some scenarios before creating new ones."
            )

        # Create scenario in same format as SCENARIOS dictionary
        custom_scenario = {
            "persona": persona,
            "prompt": prompt,
            "voice_config": {
                "voice": VOICES[voice_type],
                "temperature": temperature
            }
        }

        # Generate unique ID
        scenario_id = f"custom_{current_user.id}_{int(time.time())}"

        # Store in database
        db_custom_scenario = CustomScenario(
            scenario_id=scenario_id,
            user_id=current_user.id,
            persona=persona,
            prompt=prompt,
            voice_type=voice_type,
            temperature=temperature
        )

        db.add(db_custom_scenario)
        db.commit()
        db.refresh(db_custom_scenario)

        # Store in global SCENARIOS for immediate use
        SCENARIOS[scenario_id] = custom_scenario

        return {
            "status": "success",
            "scenario_id": scenario_id,
            "message": "Custom scenario created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create custom scenario: {str(e)}"
        )


@router.get("/custom-scenarios", response_model=List[Dict])
@rate_limit("20/minute")
async def get_custom_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all custom scenarios for the current user"""
    try:
        custom_scenarios = db.query(CustomScenario).filter(
            CustomScenario.user_id == current_user.id
        ).all()

        scenarios_list = []
        for scenario in custom_scenarios:
            scenarios_list.append({
                "id": scenario.id,
                "scenario_id": scenario.scenario_id,
                "persona": scenario.persona,
                "prompt": scenario.prompt,
                "voice_type": scenario.voice_type,
                "temperature": scenario.temperature,
                "created_at": scenario.created_at.isoformat()
            })

        return scenarios_list

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve custom scenarios: {str(e)}"
        )


@router.get("/make-custom-call/{phone_number}/{scenario_id}")
@rate_limit("2/minute")
async def make_custom_call(
    request: Request,
    phone_number: str,
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Make a call using a custom scenario"""
    try:
        # Validate scenario ownership
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not custom_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found or you don't have permission to use it"
            )

        if not phone_number.startswith('+'):
            phone_number = f"+{phone_number}"

        # Ensure scenario is in global SCENARIOS
        if scenario_id not in SCENARIOS:
            SCENARIOS[scenario_id] = {
                "persona": custom_scenario.persona,
                "prompt": custom_scenario.prompt,
                "voice_config": {
                    "voice": VOICES[custom_scenario.voice_type],
                    "temperature": custom_scenario.temperature
                }
            }

        # Use system phone number in development, user's phone number in production
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        if not from_number:
            raise HTTPException(
                status_code=400,
                detail="System phone number not configured. Please set TWILIO_PHONE_NUMBER in your environment."
            )

        base_url = clean_and_validate_url(config.PUBLIC_URL)
        user_name = current_user.email

        # Create webhook URL for the custom call
        webhook_url = f"{base_url}/incoming-custom-call/{scenario_id}?direction=outbound&user_name={user_name}"

        # Make the call using Twilio
        client = get_twilio_client()
        call = client.calls.create(
            to=phone_number,
            from_=from_number,
            url=webhook_url,
            record=True
        )

        # Store conversation record
        conversation = Conversation(
            user_id=current_user.id,
            scenario=scenario_id,
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
            "message": f"Custom call initiated successfully with scenario: {custom_scenario.persona}",
            "scenario_id": scenario_id
        }

    except TwilioRestException as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": f"An error occurred with the phone service: {str(e)}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"An error occurred: {str(e)}"}
        )


@router.api_route("/incoming-custom-call/{scenario_id}", methods=["GET", "POST"])
@rate_limit("10/minute")
async def handle_custom_incoming_call(
    request: Request,
    scenario_id: str,
    db: Session = Depends(get_db)
):
    """Handle incoming custom call webhook from Twilio"""
    try:
        # Get query parameters
        direction = request.query_params.get("direction", "inbound")
        user_name = request.query_params.get("user_name", "")

        # Create TwiML response
        from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

        response = VoiceResponse()

        # Check if scenario exists in database or global SCENARIOS
        if scenario_id not in SCENARIOS:
            # Try to load from database
            custom_scenario = db.query(CustomScenario).filter(
                CustomScenario.scenario_id == scenario_id
            ).first()

            if custom_scenario:
                # Add to global SCENARIOS
                SCENARIOS[scenario_id] = {
                    "persona": custom_scenario.persona,
                    "prompt": custom_scenario.prompt,
                    "voice_config": {
                        "voice": VOICES[custom_scenario.voice_type],
                        "temperature": custom_scenario.temperature
                    }
                }
            else:
                # Use default scenario if custom scenario not found
                response.say(
                    "We're sorry, the requested scenario could not be found. Using default conversation mode.")
                scenario_id = "default"

        # Connect to WebSocket for realtime conversation
        connect = Connect()

        # Use the correct host from the request
        host = request.headers.get('host', 'localhost')
        if 'localhost' in host or '127.0.0.1' in host:
            # Development
            stream_url = f"wss://{host}/ws/{scenario_id}"
        else:
            # Production - ensure secure websocket
            stream_url = f"wss://{host}/ws/{scenario_id}"

        stream = Stream(url=stream_url)
        connect.append(stream)
        response.append(connect)

        return response

    except Exception as e:
        # Return error TwiML
        from twilio.twiml.voice_response import VoiceResponse, Say
        response = VoiceResponse()
        response.say(
            "We're sorry, an application error occurred. Please try again later.")
        return response


@router.get("/custom-scenarios/{scenario_id}", response_model=Dict)
@rate_limit("20/minute")
async def get_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific custom scenario"""
    try:
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not custom_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found or you don't have permission to access it"
            )

        return {
            "id": custom_scenario.id,
            "scenario_id": custom_scenario.scenario_id,
            "persona": custom_scenario.persona,
            "prompt": custom_scenario.prompt,
            "voice_type": custom_scenario.voice_type,
            "temperature": custom_scenario.temperature,
            "created_at": custom_scenario.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve custom scenario: {str(e)}"
        )


@router.delete("/custom-scenarios/{scenario_id}", response_model=Dict)
@rate_limit("10/minute")
async def delete_custom_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a custom scenario"""
    try:
        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not custom_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found or you don't have permission to delete it"
            )

        # Remove from database
        db.delete(custom_scenario)
        db.commit()

        # Remove from global SCENARIOS if it exists
        if scenario_id in SCENARIOS:
            del SCENARIOS[scenario_id]

        return {
            "status": "success",
            "message": "Custom scenario deleted successfully",
            "scenario_id": scenario_id
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete custom scenario: {str(e)}"
        )


@router.put("/custom-scenarios/{scenario_id}", response_model=Dict)
@rate_limit("10/minute")
async def update_custom_scenario(
    request: Request,
    scenario_id: str,
    persona: str = Body(..., min_length=10, max_length=5000),
    prompt: str = Body(..., min_length=10, max_length=5000),
    voice_type: str = Body(...),
    temperature: float = Body(0.7, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a custom scenario"""
    try:
        if voice_type not in VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice type must be one of: {', '.join(VOICES.keys())}"
            )

        custom_scenario = db.query(CustomScenario).filter(
            CustomScenario.scenario_id == scenario_id,
            CustomScenario.user_id == current_user.id
        ).first()

        if not custom_scenario:
            raise HTTPException(
                status_code=404,
                detail="Custom scenario not found or you don't have permission to update it"
            )

        # Update database record
        custom_scenario.persona = persona
        custom_scenario.prompt = prompt
        custom_scenario.voice_type = voice_type
        custom_scenario.temperature = temperature

        db.commit()
        db.refresh(custom_scenario)

        # Update global SCENARIOS
        SCENARIOS[scenario_id] = {
            "persona": persona,
            "prompt": prompt,
            "voice_config": {
                "voice": VOICES[voice_type],
                "temperature": temperature
            }
        }

        return {
            "status": "success",
            "message": "Custom scenario updated successfully",
            "scenario_id": scenario_id,
            "scenario": {
                "id": custom_scenario.id,
                "scenario_id": custom_scenario.scenario_id,
                "persona": custom_scenario.persona,
                "prompt": custom_scenario.prompt,
                "voice_type": custom_scenario.voice_type,
                "temperature": custom_scenario.temperature,
                "created_at": custom_scenario.created_at.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update custom scenario: {str(e)}"
        )
