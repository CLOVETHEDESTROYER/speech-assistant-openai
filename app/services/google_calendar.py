import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
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
