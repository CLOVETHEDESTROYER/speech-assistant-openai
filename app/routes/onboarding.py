from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, ProviderCredentials, UserOnboardingStatus
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
    """Start mobile 4-step onboarding for anonymous user (no registration required)"""
    try:
        session = await anonymous_onboarding_service.create_session(db)
        return {
            "session_id": session.session_id,
            "current_step": "welcome",
            # welcome, profile, tutorial, firstCall (after registration)
            "total_steps": 4,
            "expires_at": session.expires_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Error starting mobile onboarding: {e}")
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


@router.post("/mobile/complete-step")
async def complete_mobile_step(
    session_id: str,
    step: str,
    data: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db)
):
    """Complete a step in the mobile 4-step onboarding flow (anonymous)"""
    try:
        result = await anonymous_onboarding_service.complete_mobile_step(session_id, step, data, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing mobile step: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete step")


@router.get("/mobile/status/{session_id}")
async def get_mobile_onboarding_status(session_id: str, db: Session = Depends(get_db)):
    """Get mobile onboarding status (anonymous)"""
    try:
        status = await anonymous_onboarding_service.get_mobile_status(session_id, db)
        return status
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting mobile status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")


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
    """Get onboarding status for authenticated user"""
    try:
        # Check if user needs onboarding (new users after this change)
        needs_onboarding = await check_user_needs_onboarding(current_user.id, db)

        if needs_onboarding:
            # User needs to complete firstCall step (they should have completed anonymous onboarding)
            return {
                "needsOnboarding": True,
                "currentStep": "firstCall",
                "completedSteps": ["welcome", "profile", "tutorial"],
                "isComplete": False,
                # 3 of 4 steps completed (anonymous steps done)
                "progress": 0.75,
                "nextStep": None,  # firstCall is the final step
                "readyForFirstCall": True
            }
        else:
            # Existing user or completed onboarding
            backend_status = await onboarding_service.get_onboarding_status(current_user.id, db)

            return {
                "needsOnboarding": False,
                "isComplete": backend_status.get('isComplete', True),
                "completedSteps": ["welcome", "profile", "tutorial", "firstCall"],
                "progress": 1.0,
                "currentStep": "complete"
            }

    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get onboarding status")


async def check_user_needs_onboarding(user_id: int, db: Session) -> bool:
    """Check if a user needs to complete onboarding (for existing vs new users)"""
    try:
        # Check if user has onboarding status record
        onboarding_status = db.query(UserOnboardingStatus).filter(
            UserOnboardingStatus.user_id == user_id
        ).first()

        if not onboarding_status:
            # New user created after onboarding system implementation
            return True

        # Check if they completed the welcome call (final step)
        return not onboarding_status.welcome_call_completed

    except Exception as e:
        logger.error(
            f"Error checking onboarding needs for user {user_id}: {e}")
        return False  # Default to not needing onboarding to avoid blocking existing users


@router.post("/complete-first-call")
async def complete_first_call(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Complete the firstCall step for authenticated users (final onboarding step)"""
    try:
        # This is the bridge between anonymous onboarding and authenticated onboarding
        # Complete the welcome_call step in the authenticated system
        status = await onboarding_service.complete_step(current_user.id, "welcome_call", db)

        return {
            "step": "firstCall",
            "isCompleted": True,
            "completedAt": status.get("timestamp", ""),
            "nextStep": None,  # Onboarding complete
            "onboardingComplete": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"Error completing first call: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to complete first call")


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
