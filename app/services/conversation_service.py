from sqlalchemy.orm import Session
from app.models import Conversation
from datetime import datetime

class ConversationService:
    @staticmethod
    async def save_conversation(
        db: Session,
        user_id: int,
        scenario: str,
        transcript: str,
        direction: str = "outbound",
        call_sid: str = None,
        phone_number: str = None
    ):
        conversation = Conversation(
            user_id=user_id,
            scenario=scenario,
            transcript=transcript,
            direction=direction,
            call_sid=call_sid or f"chat_{datetime.now().timestamp()}",
            phone_number=phone_number,
            created_at=datetime.now()
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation