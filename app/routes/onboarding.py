from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, ProviderCredentials
from app.services.onboarding_service import OnboardingService
from pydantic import BaseModel
import logging
from app.utils.crypto import encrypt_string, decrypt_string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Pydantic models


class StepCompletionRequest(BaseModel):
    step: str


# Initialize service
onboarding_service = OnboardingService()


@router.get("/status")
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current onboarding status for the user"""
    try:
        status = await onboarding_service.get_onboarding_status(current_user.id, db)
        return status
    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get onboarding status")


@router.get("/next-action")
async def get_next_action(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the next recommended action for the user"""
    try:
        action = await onboarding_service.get_next_action(current_user.id, db)
        return action
    except Exception as e:
        logger.error(f"Error getting next action: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get next action")


@router.post("/complete-step")
async def complete_step(
    request: StepCompletionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a specific onboarding step as completed"""
    try:
        valid_steps = ["phone_setup", "calendar", "scenarios", "welcome_call"]
        if request.step not in valid_steps:
            raise HTTPException(
                status_code=400, detail=f"Invalid step. Must be one of: {valid_steps}")

        status = await onboarding_service.complete_step(current_user.id, request.step, db)
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing step: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete step")


@router.post("/initialize")
async def initialize_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initialize onboarding for a user (called after registration)"""
    try:
        onboarding = await onboarding_service.initialize_user_onboarding(current_user.id, db)
        status = await onboarding_service.get_onboarding_status(current_user.id, db)
        return status
    except Exception as e:
        logger.error(f"Error initializing onboarding: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to initialize onboarding")


@router.get("/check-step/{step}")
async def check_step_completion(
    step: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if a specific onboarding step has been completed"""
    try:
        valid_steps = ["phone_setup", "calendar", "scenarios", "welcome_call"]
        if step not in valid_steps:
            raise HTTPException(
                status_code=400, detail=f"Invalid step. Must be one of: {valid_steps}")

        is_completed = await onboarding_service.check_step_completion(current_user.id, step, db)
        return {"step": step, "completed": is_completed}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking step completion: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check step completion")


@router.get("/me/providers")
async def get_provider_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    creds = db.query(ProviderCredentials).filter(
        ProviderCredentials.user_id == current_user.id).first()

    def mask(value: str | None):
        if not value:
            return None
        v = decrypt_string(value)
        return f"***{v[-4:]}" if len(v) >= 4 else "***"

    return {
        "openai_api_key": mask(creds.openai_api_key) if creds else None,
        "twilio_account_sid": mask(creds.twilio_account_sid) if creds else None,
        "twilio_auth_token": mask(creds.twilio_auth_token) if creds else None,
        "twilio_phone_number": mask(creds.twilio_phone_number) if creds else None,
        "twilio_vi_sid": mask(creds.twilio_vi_sid) if creds else None,
    }


@router.put("/me/providers")
async def update_provider_credentials(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    creds = db.query(ProviderCredentials).filter(
        ProviderCredentials.user_id == current_user.id).first()
    if not creds:
        creds = ProviderCredentials(user_id=current_user.id)
        db.add(creds)

    for field in [
        "openai_api_key",
        "twilio_account_sid",
        "twilio_auth_token",
        "twilio_phone_number",
        "twilio_vi_sid",
    ]:
        value = payload.get(field)
        if value is not None and value != "":
            setattr(creds, field, encrypt_string(value))

    db.commit()
    return {"status": "ok"}
