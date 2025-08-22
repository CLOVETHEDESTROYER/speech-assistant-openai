from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, ProviderCredentials
from app.services.onboarding_service import OnboardingService
from app.services.anonymous_onboarding_service import AnonymousOnboardingService
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from app.utils.crypto import encrypt_string, decrypt_string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Pydantic models


class StepCompletionRequest(BaseModel):
    step: str
    data: Optional[Dict[str, Any]] = None


class AnonymousOnboardingRequest(BaseModel):
    user_name: str


class ScenarioSelectionRequest(BaseModel):
    scenario_id: str


class RegistrationWithOnboardingRequest(BaseModel):
    session_id: str
    email: str
    password: str


# Initialize services
onboarding_service = OnboardingService()
anonymous_onboarding_service = AnonymousOnboardingService()


# Onboarding step mappings and constants
MOBILE_STEP_MAPPING = {
    'welcome': 'phone_setup',
    'profile': 'calendar',
    'tutorial': 'scenarios',
    'firstCall': 'welcome_call'
}

BACKEND_TO_MOBILE_MAPPING = {
    'phone_setup': 'welcome',
    'calendar': 'profile',
    'scenarios': 'tutorial',
    'welcome_call': 'firstCall',
    'complete': 'complete'
}

MOBILE_STEP_PROGRESSION = {
    'welcome': 'profile',
    'profile': 'tutorial',
    'tutorial': 'firstCall',
    'firstCall': None  # No next step, onboarding complete
}


def get_next_mobile_step(current_step: str) -> Optional[str]:
    """Get the next step in mobile app onboarding flow"""
    return MOBILE_STEP_PROGRESSION.get(current_step)


# ============================================================================
# ANONYMOUS ONBOARDING ENDPOINTS (No authentication required)
# ============================================================================

@router.post("/start")
async def start_onboarding(db: Session = Depends(get_db)):
    """Start onboarding for anonymous user (no registration required)"""
    try:
        session = await anonymous_onboarding_service.create_session(db)
        return {
            "session_id": session.session_id,
            "current_step": 1,
            "total_steps": 3,
            "expires_at": session.expires_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Error starting anonymous onboarding: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to start onboarding")


@router.post("/set-name")
async def set_user_name(
    session_id: str,
    request: AnonymousOnboardingRequest,
    db: Session = Depends(get_db)
):
    """Set user's preferred name during onboarding"""
    try:
        result = await anonymous_onboarding_service.set_user_name(
            session_id, request.user_name, db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting user name: {e}")
        raise HTTPException(status_code=500, detail="Failed to set user name")


@router.post("/select-scenario")
async def select_scenario(
    session_id: str,
    request: ScenarioSelectionRequest,
    db: Session = Depends(get_db)
):
    """Select user's preferred scenario during onboarding"""
    try:
        result = await anonymous_onboarding_service.select_scenario(
            session_id, request.scenario_id, db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error selecting scenario: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to select scenario")


@router.post("/complete")
async def complete_onboarding(session_id: str, db: Session = Depends(get_db)):
    """Complete onboarding and mark as ready for registration"""
    try:
        result = await anonymous_onboarding_service.complete_onboarding(session_id, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to complete onboarding")


@router.get("/session/{session_id}")
async def get_onboarding_session(session_id: str, db: Session = Depends(get_db)):
    """Get current onboarding session status"""
    try:
        session = await anonymous_onboarding_service.get_session(session_id, db)
        if not session:
            raise HTTPException(
                status_code=404, detail="Session not found or expired")

        return {
            "session_id": session.session_id,
            "user_name": session.user_name,
            "selected_scenario_id": session.selected_scenario_id,
            "is_completed": session.is_completed,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting onboarding session: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session")


# ============================================================================
# EXISTING ONBOARDING ENDPOINTS (Require authentication)
# ============================================================================

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
        # Support both mobile app step names and backend step names
        mobile_steps = list(MOBILE_STEP_MAPPING.keys())
        backend_steps = list(MOBILE_STEP_MAPPING.values())
        valid_steps = mobile_steps + backend_steps

        if request.step not in valid_steps:
            raise HTTPException(
                status_code=400, detail=f"Invalid step. Must be one of: {valid_steps}")

        # Map mobile step to backend step if needed
        internal_step = MOBILE_STEP_MAPPING.get(request.step, request.step)

        # Process the step with any provided data
        profile_data = None
        if request.data:
            logger.info(
                f"Processing step {request.step} with data: {request.data}")
            # Handle profile data from mobile app
            if request.step == 'profile' and request.data:
                profile_data = request.data
                logger.info(
                    f"User profile data: name={request.data.get('name')}, phone={request.data.get('phone_number')}, voice={request.data.get('preferred_voice')}")

        status = await onboarding_service.complete_step(current_user.id, internal_step, db, profile_data)

        # Return response in mobile app format
        return {
            "step": request.step,
            "isCompleted": True,
            "completedAt": status.get("timestamp", ""),
            "nextStep": get_next_mobile_step(request.step),
            "status": status
        }
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


@router.get("/status")
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get onboarding status in mobile app format"""
    try:
        # Get backend onboarding status
        backend_status = await onboarding_service.get_onboarding_status(current_user.id, db)

        current_mobile_step = BACKEND_TO_MOBILE_MAPPING.get(
            backend_status.get('currentStep'), 'welcome')

        # Determine completed steps in mobile format
        completed_steps = []
        step_completion = {
            'welcome': backend_status.get('phoneNumberSetup', False),
            'profile': backend_status.get('calendarConnected', False),
            'tutorial': backend_status.get('firstScenarioCreated', False),
            'firstCall': backend_status.get('welcomeCallCompleted', False)
        }

        for step, is_completed in step_completion.items():
            if is_completed:
                completed_steps.append(step)

        return {
            "currentStep": current_mobile_step,
            "completedSteps": completed_steps,
            "isComplete": backend_status.get('isComplete', False),
            "progress": len(completed_steps) / 4.0,  # 4 total steps
            "nextStep": get_next_mobile_step(current_mobile_step) if not backend_status.get('isComplete') else None
        }
    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get onboarding status")


@router.get("/check-step/{step}")
async def check_step_completion(
    step: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if a specific onboarding step is completed"""
    try:
        # Support both mobile app step names and backend step names
        mobile_steps = list(MOBILE_STEP_MAPPING.keys())
        backend_steps = list(MOBILE_STEP_MAPPING.values())
        valid_steps = mobile_steps + backend_steps

        if step not in valid_steps:
            raise HTTPException(
                status_code=400, detail=f"Invalid step. Must be one of: {valid_steps}")

        # Map mobile step to backend step if needed
        internal_step = MOBILE_STEP_MAPPING.get(step, step)

        is_completed = await onboarding_service.check_step_completion(current_user.id, internal_step, db)
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
    """Get user's connected provider credentials"""
    try:
        credentials = db.query(ProviderCredentials).filter(
            ProviderCredentials.user_id == current_user.id
        ).all()

        return {
            "credentials": [
                {
                    "id": cred.id,
                    "provider": cred.provider,
                    "is_connected": cred.is_connected,
                    "connected_at": cred.connected_at.isoformat() if cred.connected_at else None
                }
                for cred in credentials
            ]
        }
    except Exception as e:
        logger.error(f"Error getting provider credentials: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get provider credentials")
