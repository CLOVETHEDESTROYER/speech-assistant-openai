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
        """Create a new anonymous onboarding session"""
        try:
            session_id = self.generate_session_id()
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            session = AnonymousOnboardingSession(
                session_id=session_id,
                expires_at=expires_at,
                is_completed=False
            )
            
            db.add(session)
            db.commit()
            db.refresh(session)
            
            logger.info(f"Created anonymous onboarding session: {session_id}")
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
            logger.error(f"Error getting anonymous onboarding session {session_id}: {e}")
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
            logger.error(f"Error setting user name for session {session_id}: {e}")
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
            logger.error(f"Error selecting scenario for session {session_id}: {e}")
            db.rollback()
            raise
    
    async def complete_onboarding(self, session_id: str, db: Session) -> Dict:
        """Mark onboarding as complete and ready for registration"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                raise ValueError("Invalid or expired session")
            
            if not session.user_name or not session.selected_scenario_id:
                raise ValueError("Onboarding incomplete - missing name or scenario")
            
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
            logger.error(f"Error completing onboarding for session {session_id}: {e}")
            db.rollback()
            raise
    
    async def link_to_user(self, session_id: str, user_id: int, db: Session) -> bool:
        """Link a completed onboarding session to a newly registered user"""
        try:
            session = await self.get_session(session_id, db)
            if not session:
                return False
            
            session.user_id = user_id
            db.commit()
            
            logger.info(f"Linked onboarding session {session_id} to user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error linking session {session_id} to user {user_id}: {e}")
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
