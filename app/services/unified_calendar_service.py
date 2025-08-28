"""
Unified Calendar Service
Provides calendar read/write functionality for all interaction methods (SMS, Voice, etc.)
Handles user authentication, calendar operations, and error handling uniformly.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.services.google_calendar import GoogleCalendarService
from app.models import GoogleCalendarCredentials
from app.utils.crypto import decrypt_string
import os

logger = logging.getLogger(__name__)


class UnifiedCalendarService:
    """
    Unified calendar service for all interaction methods (SMS, Voice, etc.)
    Provides consistent calendar read/write functionality across the app.
    """
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.google_calendar_service = GoogleCalendarService()
    
    async def get_user_calendar_service(self, db: Session):
        """Get authenticated Google Calendar service for the user"""
        if not self.user_id:
            raise ValueError("User ID required for calendar operations")
            
        # Get user's Google credentials
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == self.user_id
        ).first()
        
        if not credentials:
            raise HTTPException(
                status_code=401, 
                detail="Google Calendar not connected for this user"
            )
        
        # Create authenticated service
        service = self.google_calendar_service.get_calendar_service({
            "token": decrypt_string(credentials.token),
            "refresh_token": decrypt_string(credentials.refresh_token),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "expiry": credentials.token_expiry.isoformat()
        })
        
        return service
    
    async def read_upcoming_events(self, db: Session, max_results: int = 10, days_ahead: int = 7) -> List[Dict]:
        """Read user's upcoming calendar events"""
        try:
            service = await self.get_user_calendar_service(db)
            
            # Get events for next week
            time_min = datetime.now(timezone.utc)
            time_max = time_min + timedelta(days=days_ahead)
            
            events = await self.google_calendar_service.get_upcoming_events(
                service, 
                max_results=max_results, 
                time_min=time_min
            )
            
            # Format events for consistent usage
            formatted_events = []
            for event in events:
                formatted_events.append({
                    "id": event.get("id", ""),
                    "summary": event.get("summary", "No title"),
                    "start": event.get("start", {}),
                    "end": event.get("end", {}),
                    "description": event.get("description", ""),
                    "location": event.get("location", "")
                })
            
            logger.info(f"Retrieved {len(formatted_events)} events for user {self.user_id}")
            return formatted_events
            
        except Exception as e:
            logger.error(f"Failed to read calendar events for user {self.user_id}: {str(e)}")
            return []
    
    async def check_availability(self, db: Session, start_time: datetime, duration_minutes: int = 30) -> Dict:
        """Check if a specific time slot is available"""
        try:
            service = await self.get_user_calendar_service(db)
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            # Check availability using the existing method
            available = await self.google_calendar_service.check_availability(
                service, start_time, end_time
            )
            
            return {
                "available": available,
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration_minutes
            }
            
        except Exception as e:
            logger.error(f"Failed to check availability for user {self.user_id}: {str(e)}")
            return {
                "available": False,
                "error": str(e),
                "start_time": start_time,
                "end_time": start_time + timedelta(minutes=duration_minutes)
            }
    
    async def create_event(self, db: Session, event_details: Dict) -> Dict:
        """Create a calendar event"""
        try:
            service = await self.get_user_calendar_service(db)
            
            # Ensure required fields exist
            if "summary" not in event_details:
                event_details["summary"] = "New Event"
            
            if "start_time" not in event_details:
                event_details["start_time"] = datetime.now() + timedelta(hours=1)
            
            if "end_time" not in event_details:
                event_details["end_time"] = event_details["start_time"] + timedelta(minutes=30)
            
            # Create the event
            result = await self.google_calendar_service.create_calendar_event(
                service, event_details
            )
            
            logger.info(f"✅ Created calendar event for user {self.user_id}: {result.get('id', 'Unknown ID')}")
            
            return {
                "success": True,
                "event_id": result.get("id", ""),
                "summary": result.get("summary", ""),
                "start": result.get("start", {}),
                "end": result.get("end", {}),
                "html_link": result.get("htmlLink", ""),
                "created": True
            }
            
        except Exception as e:
            logger.error(f"Failed to create calendar event for user {self.user_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "created": False
            }
    
    async def find_free_slots(self, db: Session, days_ahead: int = 7, max_results: int = 5, 
                             working_hours: tuple = (9, 17), min_duration_minutes: int = 30) -> List[Dict]:
        """Find available time slots in the user's calendar"""
        try:
            service = await self.get_user_calendar_service(db)
            
            start_date = datetime.now(timezone.utc)
            end_date = start_date + timedelta(days=days_ahead)
            
            # Use the existing find_free_slots method
            free_slots = await self.google_calendar_service.find_free_slots(
                service,
                start_date,
                end_date,
                min_duration_minutes=min_duration_minutes,
                max_results=max_results,
                working_hours=working_hours
            )
            
            # Format slots for consistent usage
            formatted_slots = []
            for start, end in free_slots:
                formatted_slots.append({
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_minutes": int((end - start).total_seconds() / 60),
                    "formatted_start": start.strftime('%A, %B %d at %I:%M %p'),
                    "formatted_end": end.strftime('%I:%M %p')
                })
            
            logger.info(f"Found {len(formatted_slots)} free slots for user {self.user_id}")
            return formatted_slots
            
        except Exception as e:
            logger.error(f"Failed to find free slots for user {self.user_id}: {str(e)}")
            return []
    
    async def parse_natural_language_time(self, message: str, timezone_str: str = "UTC") -> Optional[datetime]:
        """Parse date/time from natural language text"""
        try:
            from dateutil import parser
            import re
            
            message_lower = message.lower()
            
            # Handle common natural language patterns
            now = datetime.now()
            
            # "tomorrow at 2pm"
            if "tomorrow" in message_lower:
                tomorrow = now + timedelta(days=1)
                time_match = re.search(r'(\d{1,2})\s*(?::|at)?\s*(\d{0,2})\s*(am|pm)', message_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    if time_match.group(3) == "pm" and hour != 12:
                        hour += 12
                    elif time_match.group(3) == "am" and hour == 12:
                        hour = 0
                    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # "next week", "next monday", etc.
            if "next week" in message_lower:
                next_week = now + timedelta(days=7)
                return next_week.replace(hour=14, minute=0, second=0, microsecond=0)  # Default 2 PM
            
            # "friday at 3:30"
            weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for i, day in enumerate(weekdays):
                if day in message_lower:
                    # Find next occurrence of this weekday
                    days_ahead = (i - now.weekday()) % 7
                    if days_ahead == 0:  # Today
                        days_ahead = 7  # Next week
                    target_day = now + timedelta(days=days_ahead)
                    
                    # Look for time
                    time_match = re.search(r'(\d{1,2})\s*:?\s*(\d{0,2})\s*(am|pm)?', message_lower)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2)) if time_match.group(2) else 0
                        if time_match.group(3) == "pm" and hour != 12:
                            hour += 12
                        elif time_match.group(3) == "am" and hour == 12:
                            hour = 0
                        return target_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        return target_day.replace(hour=14, minute=0, second=0, microsecond=0)  # Default 2 PM
            
            # Try dateutil parser for more complex patterns
            try:
                parsed_time = parser.parse(message, fuzzy=True)
                # If parsed time is in the past, move to future
                if parsed_time < now:
                    parsed_time = parsed_time.replace(year=now.year + 1)
                return parsed_time
            except:
                pass
            
            # Default fallback
            return None
            
        except Exception as e:
            logger.error(f"Failed to parse time from message '{message}': {str(e)}")
            return None

    async def get_calendar_context_for_ai(self, db: Session) -> str:
        """Get calendar context formatted for AI responses"""
        try:
            events = await self.read_upcoming_events(db, max_results=5)
            
            if not events:
                return "The user has no upcoming events on their calendar."
            
            context = "Here are the user's upcoming calendar events:\n"
            for event in events:
                start_info = event.get("start", {})
                end_info = event.get("end", {})
                
                if "dateTime" in start_info:
                    start_time = start_info["dateTime"]
                    end_time = end_info.get("dateTime", "")
                else:
                    start_time = start_info.get("date", "")
                    end_time = end_info.get("date", "")
                
                context += f"- {event['summary']} from {start_time} to {end_time}\n"
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to get calendar context for user {self.user_id}: {str(e)}")
            return "Unable to access calendar information at this time."


# Helper function for easy usage across the app
async def get_calendar_service_for_user(user_id: int) -> UnifiedCalendarService:
    """Factory function to create calendar service for a user"""
    return UnifiedCalendarService(user_id=user_id)
