from sqlalchemy.orm import Session
from app.models import User, UserOnboardingStatus, GoogleCalendarCredentials, UserPhoneNumber, CustomScenario
from app.services.twilio_service import TwilioPhoneService
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OnboardingService:
    def __init__(self):
        self.twilio_service = TwilioPhoneService()

    async def initialize_user_onboarding(self, user_id: int, db: Session) -> UserOnboardingStatus:
        """Initialize onboarding tracking for a new user"""
        try:
            # Check if onboarding already exists
            existing = db.query(UserOnboardingStatus).filter(
                UserOnboardingStatus.user_id == user_id
            ).first()

            if existing:
                return existing

            # Create new onboarding record
            onboarding = UserOnboardingStatus(
                user_id=user_id,
                current_step="phone_setup",
                started_at=datetime.utcnow()
            )

            db.add(onboarding)
            db.commit()
            db.refresh(onboarding)

            logger.info(f"Initialized onboarding for user {user_id}")
            return onboarding

        except Exception as e:
            logger.error(
                f"Error initializing onboarding for user {user_id}: {e}")
            db.rollback()
            raise

    async def get_onboarding_status(self, user_id: int, db: Session) -> Dict:
        """Get comprehensive onboarding status for a user"""
        try:
            # Get or create onboarding record
            onboarding = db.query(UserOnboardingStatus).filter(
                UserOnboardingStatus.user_id == user_id
            ).first()

            if not onboarding:
                onboarding = await self.initialize_user_onboarding(user_id, db)

            # Check actual completion status
            phone_numbers = db.query(UserPhoneNumber).filter(
                UserPhoneNumber.user_id == user_id,
                UserPhoneNumber.is_active == True
            ).count()

            calendar_connected = db.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == user_id
            ).first() is not None

            scenarios_created = db.query(CustomScenario).filter(
                CustomScenario.user_id == user_id
            ).count()

            # Update onboarding record if needed
            if phone_numbers > 0 and not onboarding.phone_number_setup:
                onboarding.phone_number_setup = True

            if calendar_connected and not onboarding.calendar_connected:
                onboarding.calendar_connected = True

            if scenarios_created > 0 and not onboarding.first_scenario_created:
                onboarding.first_scenario_created = True

            # Determine current step
            if not onboarding.phone_number_setup:
                onboarding.current_step = "phone_setup"
            elif not onboarding.calendar_connected:
                onboarding.current_step = "calendar"
            elif not onboarding.first_scenario_created:
                onboarding.current_step = "scenarios"
            elif not onboarding.welcome_call_completed:
                onboarding.current_step = "welcome_call"
            else:
                onboarding.current_step = "complete"
                if not onboarding.completed_at:
                    onboarding.completed_at = datetime.utcnow()

            db.commit()

            # Calculate completion percentage
            steps_completed = sum([
                onboarding.phone_number_setup,
                onboarding.calendar_connected,
                onboarding.first_scenario_created,
                onboarding.welcome_call_completed
            ])

            completion_percentage = (steps_completed / 4) * 100

            return {
                "userId": user_id,
                "currentStep": onboarding.current_step,
                "completionPercentage": completion_percentage,
                "steps": {
                    "phoneSetup": {
                        "completed": onboarding.phone_number_setup,
                        "available": True,
                        "title": "Set Up Phone Number",
                        "description": "Get your dedicated Twilio phone number for making AI calls"
                    },
                    "calendar": {
                        "completed": onboarding.calendar_connected,
                        "available": onboarding.phone_number_setup,
                        "title": "Connect Google Calendar",
                        "description": "Link your calendar to schedule AI calls from events"
                    },
                    "scenarios": {
                        "completed": onboarding.first_scenario_created,
                        "available": onboarding.phone_number_setup,
                        "title": "Create Your First Scenario",
                        "description": "Design an AI persona for your calls"
                    },
                    "welcomeCall": {
                        "completed": onboarding.welcome_call_completed,
                        "available": onboarding.phone_number_setup and scenarios_created > 0,
                        "title": "Make Your First Call",
                        "description": "Test your setup with a practice call"
                    }
                },
                "isComplete": onboarding.current_step == "complete",
                "startedAt": onboarding.started_at.isoformat(),
                "completedAt": onboarding.completed_at.isoformat() if onboarding.completed_at else None
            }

        except Exception as e:
            logger.error(
                f"Error getting onboarding status for user {user_id}: {e}")
            raise

    async def complete_step(self, user_id: int, step: str, db: Session) -> Dict:
        """Mark a specific onboarding step as completed"""
        try:
            onboarding = db.query(UserOnboardingStatus).filter(
                UserOnboardingStatus.user_id == user_id
            ).first()

            if not onboarding:
                onboarding = await self.initialize_user_onboarding(user_id, db)

            # Update the specific step
            if step == "phone_setup":
                onboarding.phone_number_setup = True
            elif step == "calendar":
                onboarding.calendar_connected = True
            elif step == "scenarios":
                onboarding.first_scenario_created = True
            elif step == "welcome_call":
                onboarding.welcome_call_completed = True

            db.commit()

            # Return updated status
            return await self.get_onboarding_status(user_id, db)

        except Exception as e:
            logger.error(
                f"Error completing step {step} for user {user_id}: {e}")
            db.rollback()
            raise

    async def get_next_action(self, user_id: int, db: Session) -> Dict:
        """Get the next recommended action for the user"""
        try:
            status = await self.get_onboarding_status(user_id, db)
            current_step = status["currentStep"]

            actions = {
                "phone_setup": {
                    "title": "Set Up Your Phone Number",
                    "description": "Choose and provision a phone number for your AI assistant",
                    "action": "setup_phone",
                    "endpoint": "/twilio/search-numbers",
                    "priority": "high"
                },
                "calendar": {
                    "title": "Connect Google Calendar",
                    "description": "Link your calendar to automatically schedule AI calls",
                    "action": "connect_calendar",
                    "endpoint": "/google-calendar/auth",
                    "priority": "medium"
                },
                "scenarios": {
                    "title": "Create Your First AI Scenario",
                    "description": "Design how your AI assistant should behave",
                    "action": "create_scenario",
                    "endpoint": "/realtime/custom-scenario",
                    "priority": "high"
                },
                "welcome_call": {
                    "title": "Make Your First Call",
                    "description": "Test your setup with a practice call",
                    "action": "make_call",
                    "endpoint": "/make-custom-call",
                    "priority": "medium"
                },
                "complete": {
                    "title": "Setup Complete!",
                    "description": "Your account is fully configured and ready to use",
                    "action": "explore",
                    "endpoint": "/dashboard",
                    "priority": "low"
                }
            }

            return actions.get(current_step, actions["complete"])

        except Exception as e:
            logger.error(f"Error getting next action for user {user_id}: {e}")
            raise

    async def check_step_completion(self, user_id: int, step: str, db: Session) -> bool:
        """Check if a specific step has been completed"""
        try:
            if step == "phone_setup":
                count = db.query(UserPhoneNumber).filter(
                    UserPhoneNumber.user_id == user_id,
                    UserPhoneNumber.is_active == True
                ).count()
                return count > 0

            elif step == "calendar":
                credentials = db.query(GoogleCalendarCredentials).filter(
                    GoogleCalendarCredentials.user_id == user_id
                ).first()
                return credentials is not None

            elif step == "scenarios":
                count = db.query(CustomScenario).filter(
                    CustomScenario.user_id == user_id
                ).count()
                return count > 0

            elif step == "welcome_call":
                onboarding = db.query(UserOnboardingStatus).filter(
                    UserOnboardingStatus.user_id == user_id
                ).first()
                return onboarding.welcome_call_completed if onboarding else False

            return False

        except Exception as e:
            logger.error(f"Error checking step completion for {step}: {e}")
            return False
