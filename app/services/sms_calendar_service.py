"""
SMS Calendar Integration Service
Handles calendar booking requests from SMS conversations
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta

from app.services.google_calendar import GoogleCalendarService
from app.services.unified_calendar_service import UnifiedCalendarService
from app.business_config import BUSINESS_HOURS
import pytz

logger = logging.getLogger(__name__)


class SMSCalendarService:
    """Calendar integration for SMS bot"""
    
    def __init__(self):
        self.calendar_service = GoogleCalendarService()
        self.business_hours = BUSINESS_HOURS
        
    async def parse_datetime_from_message(self, message: str) -> Optional[datetime]:
        """
        Parse date/time from natural language SMS message
        
        Examples:
        - "tomorrow at 2pm" 
        - "Friday morning"
        - "next week Tuesday 3:30"
        - "December 15th at 10am"
        """
        try:
            message_lower = message.lower()
            now = datetime.now()
            
            # Common patterns
            patterns = [
                # Tomorrow/Today + time
                (r'tomorrow\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lambda m: self._get_tomorrow_at_time(m.group(1))),
                (r'today\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lambda m: self._get_today_at_time(m.group(1))),
                
                # Day of week + time
                (r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', 
                 lambda m: self._get_next_weekday_at_time(m.group(1), m.group(2))),
                
                # Time periods
                (r'tomorrow\s+(morning|afternoon|evening)', lambda m: self._get_tomorrow_period(m.group(1))),
                (r'(monday|tuesday|wednesday|thursday|friday)\s+(morning|afternoon|evening)', 
                 lambda m: self._get_weekday_period(m.group(1), m.group(2))),
                
                # Next week patterns
                (r'next\s+week\s+(monday|tuesday|wednesday|thursday|friday)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))',
                 lambda m: self._get_next_week_day_time(m.group(1), m.group(2))),
            ]
            
            for pattern, parser in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    result = parser(match)
                    if result and self._is_business_hours(result):
                        return result
            
            # Fallback: try dateutil parser on the whole message
            try:
                parsed = parse_date(message, fuzzy=True, default=now)
                if parsed > now and self._is_business_hours(parsed):
                    return parsed
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing datetime from '{message}': {str(e)}")
            return None
    
    def _get_tomorrow_at_time(self, time_str: str) -> datetime:
        """Get tomorrow at specified time"""
        tomorrow = datetime.now() + timedelta(days=1)
        time_obj = self._parse_time(time_str)
        return tomorrow.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
    
    def _get_today_at_time(self, time_str: str) -> datetime:
        """Get today at specified time"""
        today = datetime.now()
        time_obj = self._parse_time(time_str)
        result = today.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
        
        # If time has passed today, assume tomorrow
        if result <= datetime.now():
            result += timedelta(days=1)
        
        return result
    
    def _get_next_weekday_at_time(self, weekday: str, time_str: str) -> datetime:
        """Get next occurrence of weekday at time"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays[weekday]
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        target_date = today + timedelta(days=days_ahead)
        time_obj = self._parse_time(time_str)
        
        return target_date.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
    
    def _get_tomorrow_period(self, period: str) -> datetime:
        """Get tomorrow during specified period"""
        tomorrow = datetime.now() + timedelta(days=1)
        hour = self._period_to_hour(period)
        return tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
    
    def _get_weekday_period(self, weekday: str, period: str) -> datetime:
        """Get next weekday during period"""
        base_dt = self._get_next_weekday_at_time(weekday, "10:00am")  # Default time
        hour = self._period_to_hour(period)
        return base_dt.replace(hour=hour, minute=0)
    
    def _get_next_week_day_time(self, weekday: str, time_str: str) -> datetime:
        """Get specific day next week at time"""
        next_week_day = self._get_next_weekday_at_time(weekday, time_str)
        return next_week_day + timedelta(weeks=1)
    
    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string like '2pm', '10:30am', '14:00'"""
        time_str = time_str.strip().lower()
        
        # Handle PM/AM
        if 'pm' in time_str:
            time_str = time_str.replace('pm', '').strip()
            is_pm = True
        elif 'am' in time_str:
            time_str = time_str.replace('am', '').strip()
            is_pm = False
        else:
            is_pm = False
        
        # Parse hour and minute
        if ':' in time_str:
            hour, minute = map(int, time_str.split(':'))
        else:
            hour = int(time_str)
            minute = 0
        
        # Convert to 24-hour format
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        
        return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def _period_to_hour(self, period: str) -> int:
        """Convert period to default hour"""
        periods = {
            'morning': 10,
            'afternoon': 14,
            'evening': 17
        }
        return periods.get(period, 10)
    
    def _is_business_hours(self, dt: datetime) -> bool:
        """Check if datetime falls within business hours"""
        weekday = dt.strftime('%A').lower()
        
        if weekday not in self.business_hours or self.business_hours[weekday] is None:
            return False
        
        hours = self.business_hours[weekday]
        start_time = datetime.strptime(hours['start'], '%H:%M').time()
        end_time = datetime.strptime(hours['end'], '%H:%M').time()
        
        return start_time <= dt.time() <= end_time
    
    async def check_availability(
        self, 
        requested_datetime: datetime, 
        duration_minutes: int = 30
    ) -> Dict:
        """
        Check if requested time slot is available
        
        Returns:
            Dict with availability status and suggested alternatives
        """
        try:
            # For now, we'll use a simple availability check
            # In production, you'd integrate with your actual calendar system
            
            # Check business hours
            if not self._is_business_hours(requested_datetime):
                return {
                    "available": False,
                    "reason": "outside_business_hours",
                    "suggested_times": self._suggest_business_hours_alternatives(requested_datetime)
                }
            
            # Check if it's too soon (less than 2 hours from now)
            # Handle timezone-aware datetime comparison
            now = datetime.now()
            if requested_datetime.tzinfo is not None:
                # If requested_datetime is timezone-aware, make now timezone-aware too
                import pytz
                now = pytz.utc.localize(now)
            
            if requested_datetime <= now + timedelta(hours=2):
                return {
                    "available": False,
                    "reason": "too_soon",
                    "suggested_times": self._suggest_later_times(requested_datetime)
                }
            
            # TODO: Integrate with actual Google Calendar availability
            # For now, assume availability based on simple rules
            
            # Simulate some unavailable slots (for demonstration)
            unavailable_hours = [12, 13]  # Lunch break
            if requested_datetime.hour in unavailable_hours:
                return {
                    "available": False,
                    "reason": "lunch_break",
                    "suggested_times": self._suggest_alternative_times(requested_datetime)
                }
            
            return {
                "available": True,
                "datetime": requested_datetime,
                "duration": duration_minutes,
                "confirmation_needed": True
            }
            
        except Exception as e:
            logger.error(f"Error checking availability: {str(e)}")
            return {
                "available": False,
                "reason": "error",
                "error": str(e)
            }
    
    async def schedule_demo(
        self, 
        customer_phone: str, 
        customer_email: Optional[str],
        requested_datetime: datetime,
        customer_name: Optional[str] = None,
        user_id: Optional[int] = None,
        db_session = None
    ) -> Dict:
        """
        Schedule a demo call in the calendar
        
        Returns:
            Dict with scheduling results
        """
        try:
            # Check availability first
            availability = await self.check_availability(requested_datetime)
            if not availability["available"]:
                return {
                    "success": False,
                    "reason": availability["reason"],
                    "suggested_times": availability.get("suggested_times", [])
                }
            
            # Create calendar event details
            title = f"Demo Call - SMS Customer"
            if customer_name:
                title = f"Demo Call - {customer_name}"
            
            description = f"""
Demo call scheduled via SMS bot.

Customer Details:
- Phone: {customer_phone}
- Email: {customer_email or 'Not provided'}
- Source: SMS Bot
- Scheduled: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Demo Focus:
- Hyper Labs AI Voice Platform
- Custom AI conversation scenarios
- Real-time voice technology demonstration
"""
            
            # FIXED: Actually create the calendar event using UnifiedCalendarService
            if user_id and db_session:
                try:
                    # Use UnifiedCalendarService for real calendar creation
                    unified_calendar = UnifiedCalendarService(user_id)
                    
                    # Prepare event details
                    event_details = {
                        "summary": title,
                        "description": description,
                        "start_time": requested_datetime,
                        "end_time": requested_datetime + timedelta(minutes=30)  # 30-minute demo
                    }
                    
                    # Create the actual calendar event
                    calendar_result = await unified_calendar.create_event(db_session, event_details)
                    
                    if calendar_result["success"]:
                        logger.info(f"✅ Real calendar event created for SMS demo: {calendar_result.get('event_id', 'Unknown ID')}")
                        
                        return {
                            "success": True,
                            "event_id": calendar_result.get("event_id", ""),
                            "datetime": requested_datetime,
                            "title": title,
                            "description": description,
                            "customer_phone": customer_phone,
                            "customer_email": customer_email,
                            "calendar_link": calendar_result.get("html_link", ""),
                            "google_event_id": calendar_result.get("event_id", ""),
                            "calendar_created": True,
                            "calendar_service": "UnifiedCalendarService"
                        }
                    else:
                        # Check if this is a conflict (time slot not available)
                        if calendar_result.get("error") == "Time slot is not available":
                            logger.warning(f"SMS Calendar conflict detected: {calendar_result.get('message', 'Unknown conflict')}")
                            
                            # Find alternative times
                            suggested_times = await self.find_alternative_times(requested_datetime, db_session)
                            
                            return {
                                "success": False,
                                "error": "Time slot is not available",
                                "conflicting_events": calendar_result.get("conflicting_events", []),
                                "current_bookings": calendar_result.get("current_bookings", 0),
                                "max_concurrent_bookings": calendar_result.get("max_concurrent_bookings", 1),
                                "suggested_times": suggested_times,
                                "message": f"That time is already booked ({calendar_result.get('current_bookings', 0)}/{calendar_result.get('max_concurrent_bookings', 1)} slots filled). How about: {', '.join(suggested_times[:2]) if suggested_times else 'What other times work for you?'}"
                            }
                        else:
                            # Other error - fall back to simulated booking
                            logger.warning(f"Failed to create calendar event: {calendar_result.get('error', 'Unknown error')}")
                            event_id = f"sms_demo_{int(requested_datetime.timestamp())}"
                            return {
                                "success": True,
                                "event_id": event_id,
                                "datetime": requested_datetime,
                                "title": title,
                                "description": description,
                                "customer_phone": customer_phone,
                                "customer_email": customer_email,
                                "calendar_link": f"Demo scheduled for {requested_datetime.strftime('%Y-%m-%d at %I:%M %p')}",
                                "calendar_created": False,
                                "calendar_error": calendar_result.get('error', 'Unknown error'),
                                "fallback": "simulated_booking"
                            }
                        
                except Exception as calendar_error:
                    logger.error(f"Failed to create calendar event via UnifiedCalendarService: {str(calendar_error)}")
                    # Fall back to simulated booking
                    event_id = f"sms_demo_{int(requested_datetime.timestamp())}"
                    return {
                        "success": True,
                        "event_id": event_id,
                        "datetime": requested_datetime,
                        "title": title,
                        "description": description,
                        "customer_phone": customer_phone,
                        "customer_email": customer_email,
                        "calendar_link": f"Demo scheduled for {requested_datetime.strftime('%Y-%m-%d at %I:%M %p')}",
                        "calendar_created": False,
                        "calendar_error": str(calendar_error),
                        "fallback": "simulated_booking"
                    }
            else:
                # No user_id or db_session provided - fall back to simulated booking
                event_id = f"sms_demo_{int(requested_datetime.timestamp())}"
                logger.info(f"Demo scheduled for {customer_phone} at {requested_datetime} (simulated - no user context)")
                
                return {
                    "success": True,
                    "event_id": event_id,
                    "datetime": requested_datetime,
                    "title": title,
                    "description": description,
                    "customer_phone": customer_phone,
                    "customer_email": customer_email,
                    "calendar_link": f"Demo scheduled for {requested_datetime.strftime('%Y-%m-%d at %I:%M %p')}",
                    "calendar_created": False,
                    "note": "No user context provided for calendar creation",
                    "fallback": "simulated_booking"
                }
            
        except Exception as e:
            logger.error(f"Error scheduling demo: {str(e)}")
            return {
                "success": False,
                "reason": "error",
                "error": str(e)
            }
    
    def _suggest_business_hours_alternatives(self, requested_dt: datetime) -> List[str]:
        """Suggest alternative times within business hours"""
        suggestions = []
        base_date = requested_dt.date()
        
        # Try same day during business hours
        for hour in [9, 10, 11, 14, 15, 16]:
            alt_dt = datetime.combine(base_date, datetime.min.time().replace(hour=hour))
            if self._is_business_hours(alt_dt) and alt_dt > datetime.now():
                suggestions.append(alt_dt.strftime('%I:%M %p today'))
        
        # Try next business day
        next_day = base_date + timedelta(days=1)
        for hour in [9, 10, 11, 14, 15]:
            alt_dt = datetime.combine(next_day, datetime.min.time().replace(hour=hour))
            if self._is_business_hours(alt_dt):
                suggestions.append(alt_dt.strftime('%I:%M %p tomorrow'))
                
        return suggestions[:3]  # Return top 3 suggestions
    
    def _suggest_later_times(self, requested_dt: datetime) -> List[str]:
        """Suggest times at least 2 hours later"""
        suggestions = []
        min_time = datetime.now() + timedelta(hours=2)
        
        # Round up to next business hour
        if min_time.minute > 0:
            min_time = min_time.replace(minute=0) + timedelta(hours=1)
        
        for i in range(3):
            alt_dt = min_time + timedelta(hours=i)
            if self._is_business_hours(alt_dt):
                if alt_dt.date() == datetime.now().date():
                    suggestions.append(alt_dt.strftime('%I:%M %p today'))
                elif alt_dt.date() == (datetime.now() + timedelta(days=1)).date():
                    suggestions.append(alt_dt.strftime('%I:%M %p tomorrow'))
                else:
                    suggestions.append(alt_dt.strftime('%I:%M %p on %B %d'))
        
        return suggestions
    
    def _suggest_alternative_times(self, requested_dt: datetime) -> List[str]:
        """Suggest alternative times around the requested time"""
        suggestions = []
        base_hour = requested_dt.hour
        
        # Suggest times before and after
        for offset in [-2, -1, 1, 2]:
            alt_hour = base_hour + offset
            if 9 <= alt_hour <= 17:  # Business hours
                alt_dt = requested_dt.replace(hour=alt_hour)
                if alt_dt > datetime.now():
                    suggestions.append(alt_dt.strftime('%I:%M %p'))
        
        return suggestions[:3]
    
    def format_availability_response(self, availability: Dict, requested_time_str: str) -> str:
        """Format availability check result for SMS response"""
        if availability["available"]:
            return f"Great! {requested_time_str} is available. Shall I book the 30-min demo for you?"
        
        reason = availability.get("reason", "unavailable")
        suggestions = availability.get("suggested_times", [])
        
        if reason == "outside_business_hours":
            response = f"Sorry, {requested_time_str} is outside business hours. "
        elif reason == "too_soon":
            response = f"I need at least 2 hours notice. "
        elif reason == "lunch_break":
            response = f"That's during lunch break. "
        else:
            response = f"Sorry, {requested_time_str} isn't available. "
        
        if suggestions:
            response += f"How about: {', '.join(suggestions[:2])}?"
        else:
            response += "When else works for you?"
        
        return response
    
    def format_booking_confirmation(self, booking_result: Dict) -> str:
        """Format booking confirmation for SMS response"""
        if booking_result["success"]:
            dt = booking_result["datetime"]
            return f"✓ Demo booked for {dt.strftime('%A, %B %d at %I:%M %p')}! What email should I send the invite to?"
        
        reason = booking_result.get("reason", "error")
        if reason == "error":
            return "Sorry, I had trouble booking that time. Can you try a different time?"
        
        suggestions = booking_result.get("suggested_times", [])
        if suggestions:
            return f"That time isn't available. How about: {', '.join(suggestions[:2])}?"
        
        return "I couldn't book that time. When else works for you?"
    
    async def find_alternative_times(self, requested_datetime: datetime, db_session) -> List[str]:
        """Find alternative available times near the requested time"""
        try:
            # For now, use basic business hours suggestions to avoid timezone issues
            # TODO: Implement proper free slot finding with timezone handling
            return self._suggest_business_hours_alternatives(requested_datetime)
            
        except Exception as e:
            logger.error(f"Error finding alternative times: {str(e)}")
            # Fall back to basic suggestions
            return self._suggest_business_hours_alternatives(requested_datetime)
