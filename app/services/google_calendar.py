import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from fastapi import HTTPException


class GoogleCalendarService:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/calendar.events']
        self.api_version = 'v3'

        # Validate environment variables
        if not all([
            os.getenv("GOOGLE_CLIENT_ID"),
            os.getenv("GOOGLE_CLIENT_SECRET"),
            os.getenv("GOOGLE_REDIRECT_URI")
        ]):
            raise ValueError(
                "Missing required Google Calendar environment variables")

    def create_oauth_flow(self) -> Flow:
        try:
            redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
            if not redirect_uri:
                raise ValueError(
                    "GOOGLE_REDIRECT_URI environment variable is not set")

            return Flow.from_client_config(
                {
                    "web": {
                        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                        "redirect_uris": [redirect_uri],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=self.scopes,
                redirect_uri=redirect_uri  # Explicitly set the redirect_uri
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create OAuth flow: {str(e)}"
            )

    def get_calendar_service(self, credentials: Dict[str, Any]):
        try:
            creds = Credentials.from_authorized_user_info(
                credentials, self.scopes)
            return build('calendar', self.api_version, credentials=creds)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create calendar service: {str(e)}"
            )

    async def schedule_call(self, service, call_details: Dict[str, Any]):
        try:
            event = {
                'summary': f'Scheduled Call: {call_details["scenario"]}',
                'description': f'Phone call to {call_details["phone_number"]}',
                'start': {
                    'dateTime': call_details["scheduled_time"].isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (call_details["scheduled_time"] + timedelta(minutes=30)).isoformat(),
                    'timeZone': 'UTC',
                },
            }
            return service.events().insert(calendarId='primary', body=event).execute()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to schedule calendar event: {str(e)}"
            )

    async def get_upcoming_events(self, service, max_results=10, time_min=None):
        """Get upcoming events from the user's primary calendar"""
        try:
            # If no start time provided, use current time
            if not time_min:
                # Use timezone-aware datetime
                time_min = datetime.now(timezone.utc)
            elif time_min.tzinfo is None:
                # Make naive datetime timezone-aware
                time_min = time_min.replace(tzinfo=timezone.utc)

            # Format time as RFC3339 timestamp
            # 'Z' no longer needed as we use timezone-aware objects
            time_min_rfc = time_min.isoformat()

            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min_rfc,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve calendar events: {str(e)}"
            )

    async def check_availability(self, service, start_time, end_time):
        """Check if a specific time slot is available"""
        try:
            # Ensure datetimes are timezone-aware
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)

            # Format times as RFC3339 timestamp
            start_rfc = start_time.isoformat()
            end_rfc = end_time.isoformat()

            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_rfc,
                timeMax=end_rfc,
                singleEvents=True
            ).execute()

            events = events_result.get('items', [])

            # Return True if no events during this time
            return len(events) == 0
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to check availability: {str(e)}"
            )

    async def find_free_slots(self, service, start_date, end_date,
                              min_duration_minutes=30, max_results=5,
                              working_hours=(9, 17)):
        """Find available time slots in a date range

        Args:
            service: The Google Calendar service instance
            start_date: Beginning date to search from (datetime)
            end_date: End date to search to (datetime)
            min_duration_minutes: Minimum duration of free slot in minutes
            max_results: Maximum number of free slots to return
            working_hours: Tuple of (start_hour, end_hour) in 24h format

        Returns:
            List of available time slots as (start_time, end_time) tuples
        """
        try:
            # Ensure datetimes are timezone-aware
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            # Format times as RFC3339 timestamp
            start_rfc = start_date.replace(
                hour=0, minute=0, second=0).isoformat()
            end_rfc = end_date.replace(
                hour=23, minute=59, second=59).isoformat()

            # Get all events in the date range
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_rfc,
                timeMax=end_rfc,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Convert events to busy periods
            busy_periods = []
            for event in events:
                # Skip events that are declined or have no start/end time
                if 'dateTime' not in event.get('start', {}) or 'dateTime' not in event.get('end', {}):
                    continue

                # Parse start and end times, ensuring timezone awareness
                start = datetime.fromisoformat(
                    event['start']['dateTime'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(
                    event['end']['dateTime'].replace('Z', '+00:00'))

                # Ensure timezone-aware
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)

                busy_periods.append((start, end))

            # Find free slots
            free_slots = []
            current_day = start_date

            # Analyze each day in the range
            while current_day <= end_date and len(free_slots) < max_results:
                day_start = current_day.replace(
                    hour=working_hours[0], minute=0, second=0)
                day_end = current_day.replace(
                    hour=working_hours[1], minute=0, second=0)

                # Skip if current day is already past
                # Use timezone-aware datetime
                current_time = datetime.now(timezone.utc)
                if day_end < current_time:
                    current_day += timedelta(days=1)
                    continue

                # Adjust day_start if it's in the past
                if day_start < current_time:
                    day_start = current_time.replace(
                        minute=(current_time.minute // 30) * 30,
                        second=0, microsecond=0,
                        tzinfo=timezone.utc  # Ensure timezone awareness
                    ) + timedelta(minutes=30)  # Round up to next half hour

                # Find free slots for this day
                slots = self._find_free_slots_in_day(
                    day_start, day_end, busy_periods, min_duration_minutes)

                free_slots.extend(slots[:max_results - len(free_slots)])

                # Move to next day
                current_day += timedelta(days=1)

            return free_slots[:max_results]
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to find free slots: {str(e)}"
            )

    def _find_free_slots_in_day(self, day_start, day_end, busy_periods, min_duration_minutes):
        """Helper method to find free slots in a single day"""
        slots = []
        current_time = day_start

        # Ensure day boundaries are timezone-aware
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=timezone.utc)
        if day_end.tzinfo is None:
            day_end = day_end.replace(tzinfo=timezone.utc)

        # Filter busy periods that overlap with this day
        day_busy_periods = []
        for bp in busy_periods:
            bp_start, bp_end = bp
            # Ensure timezone awareness for comparison
            if bp_start.tzinfo is None:
                bp_start = bp_start.replace(tzinfo=timezone.utc)
            if bp_end.tzinfo is None:
                bp_end = bp_end.replace(tzinfo=timezone.utc)

            if bp_start < day_end and bp_end > day_start:
                day_busy_periods.append(
                    (max(bp_start, day_start), min(bp_end, day_end)))

        # Sort by start time
        day_busy_periods.sort(key=lambda x: x[0])

        # Find gaps between meetings
        for busy_start, busy_end in day_busy_periods:
            # If there's a gap before this meeting
            if (busy_start - current_time).total_seconds() >= min_duration_minutes * 60:
                slots.append((current_time, busy_start))

            # Move current time to end of this meeting
            current_time = max(current_time, busy_end)

        # Check if there's time after the last meeting
        if (day_end - current_time).total_seconds() >= min_duration_minutes * 60:
            slots.append((current_time, day_end))

        return slots
