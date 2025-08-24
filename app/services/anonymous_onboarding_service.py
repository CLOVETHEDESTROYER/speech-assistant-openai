from sqlalchemy.orm import Session
from app.models import AnonymousOnboardingSession
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)


class AnonymousOnboardingService:
    """Service for handling anonymous onboarding sessions before user registration"""

    def __init__(self):
        pass

    def generate_session_id(self) -> str:
        """Generate a unique session ID for anonymous onboarding"""
        return str(uuid.uuid4())

    async def create_session(self, db: Session) -> AnonymousOnboardingSession:
        """Create a new anonymous onboarding session for mobile 4-step flow"""
        try:
            session_id = self.generate_session_id()
            expires_at = datetime.utcnow() + timedelta(hours=24)

            session = AnonymousOnboardingSession(
                session_id=session_id,
                expires_at=expires_at,
                is_completed=False,
                current_step="welcome",
                welcome_completed=False,
                profile_completed=False,
                tutorial_completed=False,
                notifications_enabled=True
            )

            db.add(session)
            db.commit()
            db.refresh(session)

            logger.info(f"Created mobile onboarding session: {session_id}")
            return session

        except Exception as e:
            logger.error(f"Error creating anonymous onboarding session: {e}")
            db.rollback()
            raise

    async def get_session(self, session_id: str, db: Session) -> Optional[AnonymousOnboardingSession]:
        """Get an anonymous onboarding session by ID"""
        try:
            session = db.query(AnonymousOnboardingSession).filter(
                AnonymousOnboardingSession.session_id == session_id,
                AnonymousOnboardingSession.expires_at > datetime.utcnow(),
                AnonymousOnboardingSession.is_completed == False
            ).first()

            return session

        except Exception as e:
            logger.error(
                f"Error getting anonymous onboarding session {session_id}: {e}")
            return None

    async def set_user_name(self, session_id: str, user_name: str, db: Session) -> Dict:
        """Set the user's preferred name in the onboarding session"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")

            session.user_name = user_name
            db.commit()

            return {
                "status": "success",
                "user_name": user_name,
                "next_step": "select_scenario",
                "current_step": 1,
                "total_steps": 3
            }

        except Exception as e:
            logger.error(
                f"Error setting user name for session {session_id}: {e}")
            db.rollback()
            raise

    async def select_scenario(self, session_id: str, scenario_id: str, db: Session) -> Dict:
        """Select the user's preferred scenario in the onboarding session"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")

            session.selected_scenario_id = scenario_id
            db.commit()

            return {
                "status": "success",
                "scenario_id": scenario_id,
                "next_step": "ready_for_registration",
                "current_step": 2,
                "total_steps": 3
            }

        except Exception as e:
            logger.error(
                f"Error selecting scenario for session {session_id}: {e}")
            db.rollback()
            raise

    async def complete_onboarding(self, session_id: str, db: Session) -> Dict:
        """Mark onboarding as complete and ready for registration"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")

            if not session.user_name or not session.selected_scenario_id:
                raise ValueError(
                    "Onboarding incomplete - missing name or scenario")

            session.is_completed = True
            db.commit()

            return {
                "status": "ready_for_registration",
                "user_name": session.user_name,
                "scenario_id": session.selected_scenario_id,
                "current_step": 3,
                "total_steps": 3
            }

        except Exception as e:
            logger.error(
                f"Error completing onboarding for session {session_id}: {e}")
            db.rollback()
            raise

    async def complete_mobile_step(self, session_id: str, step: str, data: Optional[Dict] = None, db: Session = None) -> Dict:
        """Complete a step in the mobile 4-step onboarding flow"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")

            # Define step progression
            step_progression = {
                'welcome': {'next': 'profile', 'step_num': 1},
                'profile': {'next': 'tutorial', 'step_num': 2},
                'tutorial': {'next': 'ready_for_registration', 'step_num': 3}
            }

            if step not in step_progression:
                raise ValueError(f"Invalid step: {step}")

            # Mark current step as completed and store data
            if step == 'welcome':
                session.welcome_completed = True
                session.current_step = 'profile'
                logger.info(f"Session {session_id}: Completed welcome step")

            elif step == 'profile':
                if data:
                    session.user_name = data.get('name')
                    session.phone_number = data.get('phone_number')
                    session.preferred_voice = data.get('preferred_voice')
                    session.notifications_enabled = data.get(
                        'notifications_enabled', True)
                    logger.info(
                        f"Session {session_id}: Stored profile data - name: {session.user_name}, voice: {session.preferred_voice}")

                session.profile_completed = True
                session.current_step = 'tutorial'
                logger.info(f"Session {session_id}: Completed profile step")

            elif step == 'tutorial':
                session.tutorial_completed = True
                session.current_step = 'ready_for_registration'
                logger.info(f"Session {session_id}: Completed tutorial step")

            db.commit()

            # Calculate progress
            completed_steps = sum([
                session.welcome_completed,
                session.profile_completed,
                session.tutorial_completed
            ])

            return {
                "step": step,
                "isCompleted": True,
                "completedAt": datetime.utcnow().isoformat(),
                "nextStep": step_progression[step]['next'] if step_progression[step]['next'] != 'ready_for_registration' else None,
                "currentStep": session.current_step,
                "progress": completed_steps / 3.0,  # 3 anonymous steps
                "readyForRegistration": session.current_step == 'ready_for_registration'
            }

        except Exception as e:
            logger.error(f"Error completing mobile step {step}: {e}")
            db.rollback()
            raise

    async def get_mobile_status(self, session_id: str, db: Session) -> Dict:
        """Get mobile onboarding status"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")

            completed_steps = []
            if session.welcome_completed:
                completed_steps.append('welcome')
            if session.profile_completed:
                completed_steps.append('profile')
            if session.tutorial_completed:
                completed_steps.append('tutorial')

            progress = len(completed_steps) / 3.0

            return {
                "sessionId": session_id,
                "currentStep": session.current_step,
                "completedSteps": completed_steps,
                "progress": progress,
                "readyForRegistration": session.current_step == 'ready_for_registration',
                "profileData": {
                    "name": session.user_name,
                    "phone_number": session.phone_number,
                    "preferred_voice": session.preferred_voice,
                    "notifications_enabled": session.notifications_enabled
                } if session.profile_completed else None
            }

        except Exception as e:
            logger.error(f"Error getting mobile status: {e}")
            raise

    async def link_to_user(self, session_id: str, user_id: int, db: Session) -> bool:
        """Link a completed onboarding session to a newly registered user and transfer profile data"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                return False

            # Link session to user
            session.user_id = user_id

            # Transfer profile data to user account if available
            if session.profile_completed and session.user_name:
                from app.models import User
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.full_name = session.user_name
                    user.preferred_voice = session.preferred_voice
                    user.notifications_enabled = session.notifications_enabled
                    logger.info(
                        f"Transferred profile data from session {session_id} to user {user_id}")

            db.commit()

            logger.info(
                f"Linked onboarding session {session_id} to user {user_id}")
            return True

        except Exception as e:
            logger.error(
                f"Error linking session {session_id} to user {user_id}: {e}")
            db.rollback()
            return False

    async def cleanup_expired_sessions(self, db: Session) -> int:
        """Clean up expired onboarding sessions"""
        try:
            expired_sessions = db.query(AnonymousOnboardingSession).filter(
                AnonymousOnboardingSession.expires_at <= datetime.utcnow()
            ).all()

            count = len(expired_sessions)
            for session in expired_sessions:
                db.delete(session)

            db.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} expired onboarding sessions")

            return count

        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            db.rollback()
            return 0
