"""
Post-Call Processing Service
Handles conversation analysis and calendar event creation after calls end
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import ConversationTranscript, CustomScenario, User
from app.services.calendar_event_creator import CalendarEventCreator
from app.db import SessionLocal

logger = logging.getLogger(__name__)


class PostCallProcessor:
    """Service to process calls after they end for calendar creation"""

    def __init__(self):
        self.calendar_creator = CalendarEventCreator()

    async def process_call_end(
        self,
        call_sid: str,
        user_id: int,
        scenario_id: str,
        conversation_content: str
    ) -> Dict[str, Any]:
        """
        Process a call after it ends to detect and create calendar events

        Args:
            call_sid: Twilio call SID
            user_id: User who owns the scenario
            scenario_id: The scenario that was used
            conversation_content: Full conversation transcript

        Returns:
            Dict with processing results
        """
        db = SessionLocal()
        try:
            # Store conversation transcript
            transcript_record = await self._store_conversation_transcript(
                db, call_sid, user_id, scenario_id, conversation_content
            )

            # Check if this scenario has calendar integration
            if not await self._scenario_has_calendar_integration(db, scenario_id, user_id):
                logger.info(
                    f"Scenario {scenario_id} does not have calendar integration")
                return {"calendar_processing": False, "reason": "no_calendar_integration"}

            # Process for calendar events
            calendar_result = await self.calendar_creator.process_conversation(
                conversation_content, user_id, db
            )

            # Update transcript record with results
            if calendar_result:
                transcript_record.calendar_processed = True
                transcript_record.calendar_event_created = calendar_result.get(
                    'success', False)
                transcript_record.calendar_event_id = calendar_result.get(
                    'event_id')
                db.commit()

                logger.info(
                    f"✅ Calendar event created for call {call_sid}: {calendar_result.get('event_id')}")

                return {
                    "calendar_processing": True,
                    "calendar_event_created": True,
                    "event_details": calendar_result
                }
            else:
                transcript_record.calendar_processed = True
                transcript_record.calendar_event_created = False
                db.commit()

                logger.info(f"No calendar events needed for call {call_sid}")

                return {
                    "calendar_processing": True,
                    "calendar_event_created": False,
                    "reason": "no_scheduling_detected"
                }

        except Exception as e:
            logger.error(f"Error processing call {call_sid}: {e}")
            db.rollback()
            return {
                "calendar_processing": False,
                "error": str(e)
            }
        finally:
            db.close()

    async def _store_conversation_transcript(
        self,
        db: Session,
        call_sid: str,
        user_id: int,
        scenario_id: str,
        conversation_content: str
    ) -> ConversationTranscript:
        """Store conversation transcript in database"""
        try:
            # Check if transcript already exists
            existing = db.query(ConversationTranscript).filter(
                ConversationTranscript.call_sid == call_sid
            ).first()

            if existing:
                # Update existing transcript
                existing.transcript = conversation_content
                db.commit()
                return existing

            # Create new transcript record
            transcript = ConversationTranscript(
                user_id=user_id,
                call_sid=call_sid,
                scenario_id=scenario_id,
                transcript=conversation_content,
                calendar_processed=False
            )

            db.add(transcript)
            db.commit()
            db.refresh(transcript)

            logger.info(f"Stored conversation transcript for call {call_sid}")
            return transcript

        except Exception as e:
            logger.error(f"Error storing transcript for call {call_sid}: {e}")
            db.rollback()
            raise

    async def _scenario_has_calendar_integration(
        self,
        db: Session,
        scenario_id: str,
        user_id: int
    ) -> bool:
        """Check if a scenario should have calendar integration"""
        try:
            # For custom scenarios, check if user has calendar credentials
            if scenario_id.startswith("custom_") or scenario_id.startswith("cal_"):
                from app.models import GoogleCalendarCredentials
                credentials = db.query(GoogleCalendarCredentials).filter(
                    GoogleCalendarCredentials.user_id == user_id
                ).first()
                return bool(credentials)

            # Default scenarios don't have calendar integration by default
            return False

        except Exception as e:
            logger.error(
                f"Error checking calendar integration for scenario {scenario_id}: {e}")
            return False

    async def reprocess_pending_transcripts(self) -> Dict[str, Any]:
        """
        Reprocess any transcripts that haven't been processed for calendar events
        Useful for batch processing or fixing failed processing
        """
        db = SessionLocal()
        try:
            # Get unprocessed transcripts
            pending_transcripts = db.query(ConversationTranscript).filter(
                ConversationTranscript.calendar_processed == False
            ).limit(50).all()  # Process in batches

            results = {
                "processed_count": 0,
                "events_created": 0,
                "errors": []
            }

            for transcript in pending_transcripts:
                try:
                    if await self._scenario_has_calendar_integration(
                        db, transcript.scenario_id, transcript.user_id
                    ):
                        calendar_result = await self.calendar_creator.process_conversation(
                            transcript.transcript, transcript.user_id, db
                        )

                        transcript.calendar_processed = True
                        if calendar_result and calendar_result.get('success'):
                            transcript.calendar_event_created = True
                            transcript.calendar_event_id = calendar_result.get(
                                'event_id')
                            results["events_created"] += 1
                        else:
                            transcript.calendar_event_created = False

                        results["processed_count"] += 1
                    else:
                        # Mark as processed even if no calendar integration
                        transcript.calendar_processed = True
                        transcript.calendar_event_created = False
                        results["processed_count"] += 1

                except Exception as e:
                    error_msg = f"Error processing transcript {transcript.id}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            db.commit()
            logger.info(
                f"Reprocessed {results['processed_count']} transcripts, created {results['events_created']} events")
            return results

        except Exception as e:
            logger.error(f"Error in batch reprocessing: {e}")
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()


# Global instance for use across the app
post_call_processor = PostCallProcessor()
