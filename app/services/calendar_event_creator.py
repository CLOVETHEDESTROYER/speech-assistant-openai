import logging
import re
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.services.google_calendar import GoogleCalendarService
from app.models import GoogleCalendarCredentials
from app.utils.crypto import decrypt_string
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os

logger = logging.getLogger(__name__)


class CalendarEventCreator:
    """Service to create calendar events based on AI conversation content"""

    def __init__(self):
        self.calendar_service = GoogleCalendarService()

    async def process_conversation(self, conversation_transcript: str, user_id: int, db_session) -> Optional[Dict[str, Any]]:
        """
        Process entire conversation transcript to detect and create calendar events

        Args:
            conversation_transcript: Full conversation text between AI and client
            user_id: User ID for calendar access
            db_session: Database session

        Returns:
            Dict with event creation results or None
        """
        try:
            # Detect scheduling commitments in the conversation
            scheduling_details = self._analyze_conversation_for_scheduling(
                conversation_transcript)
            if not scheduling_details:
                logger.info(
                    f"No scheduling commitments found in conversation for user {user_id}")
                return None

            logger.info(
                f"Found scheduling commitment for user {user_id}: {scheduling_details}")

            # Get user's calendar credentials
            credentials = db_session.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == user_id
            ).first()

            if not credentials:
                logger.error(
                    f"No calendar credentials found for user {user_id}")
                return None

            # Create the calendar event
            result = await self._create_calendar_event(scheduling_details, credentials, user_id)
            return result

        except Exception as e:
            logger.error(
                f"Error processing conversation for calendar creation: {e}")
            return None

    async def process_ai_response(self, response_text: str, user_id: int, db_session) -> Optional[Dict[str, Any]]:
        """
        Process AI response text to detect and create calendar events

        Args:
            response_text: The AI's response text
            user_id: User ID for calendar access
            db_session: Database session

        Returns:
            Dict with event creation results or None
        """
        try:
            # Detect scheduling intentions
            if not self._contains_scheduling_intent(response_text):
                return None

            logger.info(
                f"Detected scheduling intent in AI response for user {user_id}")

            # Extract event details
            event_details = self._extract_event_details(response_text)
            if not event_details:
                logger.warning(
                    "Could not extract event details from AI response")
                return None

            # Get user's calendar credentials
            credentials = db_session.query(GoogleCalendarCredentials).filter(
                GoogleCalendarCredentials.user_id == user_id
            ).first()

            if not credentials:
                logger.error(
                    f"No calendar credentials found for user {user_id}")
                return None

            # Create the calendar event
            result = await self._create_calendar_event(event_details, credentials)
            return result

        except Exception as e:
            logger.error(
                f"Error processing AI response for calendar creation: {e}")
            return None

    def _analyze_conversation_for_scheduling(self, conversation: str) -> Optional[Dict[str, Any]]:
        """Analyze full conversation to detect scheduling commitments"""
        try:
            conversation_lower = conversation.lower()

            # Look for AI scheduling commitments
            commitment_phrases = [
                "i'll add that to your calendar",
                "i'll schedule that",
                "i'll create that event",
                "adding to your calendar",
                "scheduling that for you",
                "i'll book that",
                "let me schedule",
                "i'll set that up",
                "i've scheduled",
                "appointment is scheduled",
                "i'll put that in your calendar",
                "booking that for you"
            ]

            # Check if AI made a scheduling commitment
            has_commitment = any(
                phrase in conversation_lower for phrase in commitment_phrases)
            if not has_commitment:
                return None

            # Extract details from the conversation
            event_details = self._extract_detailed_event_info(conversation)
            return event_details

        except Exception as e:
            logger.error(f"Error analyzing conversation: {e}")
            return None

    def _extract_detailed_event_info(self, conversation: str) -> Dict[str, Any]:
        """Extract comprehensive event details from conversation"""
        try:
            details = {}

            # Extract client name
            name_patterns = [
                r"my name is ([a-zA-Z\s]+)",
                r"this is ([a-zA-Z\s]+)",
                r"i'm ([a-zA-Z\s]+)",
                r"speaking with ([a-zA-Z\s]+)"
            ]

            for pattern in name_patterns:
                match = re.search(pattern, conversation, re.IGNORECASE)
                if match:
                    details['client_name'] = match.group(1).strip().title()
                    break

            # Extract phone number
            phone_pattern = r'(\+?1?[-.\s]?)?(\()?(\d{3})(\))?[-.\s]?(\d{3})[-.\s]?(\d{4})'
            phone_match = re.search(phone_pattern, conversation)
            if phone_match:
                details['client_phone'] = phone_match.group(0)

            # Extract service type
            service_patterns = [
                r"consultation",
                r"meeting",
                r"appointment",
                r"session",
                r"demo",
                r"call"
            ]

            for service in service_patterns:
                if service in conversation.lower():
                    details['service_type'] = service.title()
                    break

            # Extract date and time with better parsing
            date_time_info = self._parse_scheduling_datetime(conversation)
            if date_time_info:
                details.update(date_time_info)

            # Generate event title
            client_name = details.get('client_name', 'Client')
            service_type = details.get('service_type', 'Consultation')
            details['title'] = f"{service_type} - {client_name}"

            # Generate description
            description_parts = [
                f"Scheduled via AI assistant",
                f"Client: {details.get('client_name', 'Not provided')}",
                f"Phone: {details.get('client_phone', 'Not provided')}",
                f"Service: {details.get('service_type', 'General consultation')}"
            ]
            details['description'] = "\n".join(description_parts)

            return details

        except Exception as e:
            logger.error(f"Error extracting event details: {e}")
            return {}

    def _parse_scheduling_datetime(self, conversation: str) -> Optional[Dict[str, Any]]:
        """Parse date and time from conversation with better accuracy"""
        try:
            from dateutil import parser
            import pytz

            # Look for explicit date/time mentions
            datetime_patterns = [
                r'tomorrow at (\d{1,2}):?(\d{2})?\s*(am|pm)?',
                r'(\w+day) at (\d{1,2}):?(\d{2})?\s*(am|pm)?',
                r'(\d{1,2})/(\d{1,2}) at (\d{1,2}):?(\d{2})?\s*(am|pm)?',
                r'(\w+) (\d{1,2}) at (\d{1,2}):?(\d{2})?\s*(am|pm)?'
            ]

            # For now, use intelligent defaults if we can't parse
            base_time = datetime.now()

            # Look for "tomorrow"
            if "tomorrow" in conversation.lower():
                target_date = base_time + timedelta(days=1)
            else:
                # Default to next business day
                days_ahead = 1
                while (base_time + timedelta(days=days_ahead)).weekday() >= 5:  # Skip weekends
                    days_ahead += 1
                target_date = base_time + timedelta(days=days_ahead)

            # Look for time mentions
            time_patterns = [
                r'(\d{1,2}):?(\d{2})?\s*(am|pm)',
                r'(\d{1,2})\s*(am|pm)'
            ]

            hour = 14  # Default to 2 PM
            minute = 0

            for pattern in time_patterns:
                match = re.search(pattern, conversation.lower())
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0

                    if match.group(3) and "pm" in match.group(3) and hour != 12:
                        hour += 12
                    elif match.group(3) and "am" in match.group(3) and hour == 12:
                        hour = 0
                    break

            # Create the scheduled datetime
            scheduled_datetime = target_date.replace(
                hour=hour, minute=minute, second=0, microsecond=0)

            return {
                'start_time': scheduled_datetime,
                # Default 1 hour duration
                'end_time': scheduled_datetime + timedelta(hours=1),
                'date_source': 'conversation_analysis'
            }

        except Exception as e:
            logger.error(f"Error parsing datetime: {e}")
            return None

    def _contains_scheduling_intent(self, text: str) -> bool:
        """Check if the text contains scheduling-related phrases"""
        scheduling_phrases = [
            "i'll add that to your calendar",
            "i'll schedule that",
            "i'll create that event",
            "adding to your calendar",
            "scheduling that for you",
            "i'll book that",
            "let me schedule",
            "i'll set that up"
        ]

        text_lower = text.lower()
        return any(phrase in text_lower for phrase in scheduling_phrases)

    def _extract_event_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract event details from AI response text"""
        try:
            # This is a simplified extraction - in production you'd want more sophisticated NLP
            details = {}

            # Look for time patterns
            time_patterns = [
                r'(\d{1,2}):(\d{2})\s*(am|pm)?',
                r'(\d{1,2})\s*(am|pm)',
                r'at\s+(\d{1,2}):?(\d{2})?\s*(am|pm)?'
            ]

            # Look for date patterns
            date_patterns = [
                r'tomorrow',
                r'next\s+\w+',
                r'(\w+day)',
                r'(\d{1,2})/(\d{1,2})',
                r'(\w+)\s+(\d{1,2})'
            ]

            # Extract title (look for meeting/appointment/call keywords)
            title_match = re.search(
                r'(meeting|appointment|call|consultation|demo)\s+(?:with\s+)?(.+?)(?:\s+at|\s+on|$)', text.lower())
            if title_match:
                details['title'] = f"{title_match.group(1).capitalize()} {title_match.group(2).strip()}"
            else:
                details['title'] = "Scheduled Event"

            # For now, default to tomorrow at 2 PM if we can't parse specifics
            tomorrow = datetime.now() + timedelta(days=1)
            details['start_time'] = tomorrow.replace(
                hour=14, minute=0, second=0, microsecond=0)
            details['end_time'] = details['start_time'] + timedelta(hours=1)
            details['description'] = f"Event created from AI conversation: {text[:100]}..."

            return details

        except Exception as e:
            logger.error(f"Error extracting event details: {e}")
            return None

    async def _create_calendar_event(self, event_details: Dict[str, Any], credentials, user_id: int) -> Dict[str, Any]:
        """Create the actual calendar event"""
        try:
            # Decrypt credentials
            decrypted_token = decrypt_string(credentials.token)
            decrypted_refresh_token = decrypt_string(
                credentials.refresh_token) if credentials.refresh_token else None

            # Create Google credentials object
            google_creds = Credentials(
                token=decrypted_token,
                refresh_token=decrypted_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=['https://www.googleapis.com/auth/calendar']
            )

            # Build calendar service
            service = build('calendar', 'v3', credentials=google_creds)

            # Create event
            event = {
                'summary': event_details.get('title', 'Client Consultation'),
                'description': event_details.get('description', 'Scheduled via AI assistant'),
                'start': {
                    'dateTime': event_details['start_time'].isoformat(),
                    'timeZone': 'America/New_York',  # You might want to make this configurable
                },
                'end': {
                    'dateTime': event_details['end_time'].isoformat(),
                    'timeZone': 'America/New_York',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        # 15 minutes before
                        {'method': 'popup', 'minutes': 15},
                    ],
                },
            }

            created_event = service.events().insert(
                calendarId='primary', body=event).execute()

            logger.info(f"✅ Calendar event created: {created_event.get('id')}")

            return {
                'success': True,
                'event_id': created_event.get('id'),
                'event_link': created_event.get('htmlLink'),
                'title': event_details['title'],
                'start_time': event_details['start_time']
            }

        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return {
                'success': False,
                'error': str(e)
            }
