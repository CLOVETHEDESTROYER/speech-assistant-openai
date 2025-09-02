#!/usr/bin/env python3
"""
Test Real Google Calendar Integration
This script will test actual calendar event creation with real Google credentials.
"""

from sqlalchemy.orm import Session
from app.utils.crypto import encrypt_string, decrypt_string
from app.services.google_calendar import GoogleCalendarService
from app.routes.google_calendar import createCalendarEvent
from app.models import User, GoogleCalendarCredentials
from app.db import get_db
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Load environment variables from dev.env file


def load_env_file():
    """Load environment variables from dev.env file"""
    env_file = os.path.join(os.path.dirname(__file__), 'dev.env')
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    os.environ[key] = value


load_env_file()

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))


def exchange_code_for_credentials(auth_code: str, user_id: int = 1):
    """Exchange authorization code for real Google Calendar credentials"""
    print("🔄 Exchanging authorization code for credentials...")

    try:
        # Create OAuth flow
        calendar_service = GoogleCalendarService()
        flow = calendar_service.create_oauth_flow()

        # Exchange code for tokens
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials

        print("✅ Successfully obtained credentials!")
        print(f"   Access Token: {credentials.token[:20]}...")
        print(
            f"   Refresh Token: {credentials.refresh_token[:20] if credentials.refresh_token else 'None'}...")
        print(f"   Expires: {credentials.expiry}")

        # Save to database
        db = next(get_db())

        # Check if credentials already exist
        existing_creds = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == user_id
        ).first()

        if existing_creds:
            # Update existing credentials
            existing_creds.token = encrypt_string(credentials.token)
            existing_creds.refresh_token = encrypt_string(
                credentials.refresh_token)
            existing_creds.token_expiry = credentials.expiry
            print("✅ Updated existing credentials in database")
        else:
            # Create new credentials
            google_creds = GoogleCalendarCredentials(
                user_id=user_id,
                token=encrypt_string(credentials.token),
                refresh_token=encrypt_string(credentials.refresh_token),
                token_expiry=credentials.expiry
            )
            db.add(google_creds)
            print("✅ Created new credentials in database")

        db.commit()
        db.close()

        return True

    except Exception as e:
        print(f"❌ Failed to exchange code for credentials: {e}")
        return False


async def test_real_calendar_creation(user_id: int = 1):
    """Test creating a real calendar event"""
    print("\n📅 Testing real calendar event creation...")

    try:
        # Create test event
        start_time = (datetime.now() + timedelta(hours=1)).isoformat()
        end_time = (datetime.now() +
                    timedelta(hours=1, minutes=30)).isoformat()
        summary = "🧪 Test Event from Calendar Integration"

        print(f"   Event: {summary}")
        print(f"   Start: {start_time}")
        print(f"   End: {end_time}")

        # Get database connection
        db = next(get_db())

        # Create the event
        result = await createCalendarEvent(
            start=start_time,
            end=end_time,
            summary=summary,
            user_id=user_id,
            db=db
        )

        db.close()

        if result.get("success"):
            print("🎉 SUCCESS! Calendar event created!")
            print(f"   Event ID: {result.get('event_id')}")
            print(f"   Google Calendar Link: {result.get('html_link')}")
            print("\n✅ Check your Google Calendar - you should see the new event!")
            return True
        else:
            print(f"❌ Failed to create calendar event: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Error testing calendar creation: {e}")
        return False


def test_voice_agent_simulation(user_id: int = 1):
    """Simulate the voice agent creating a calendar event"""
    print("\n🎤 Simulating voice agent calendar integration...")

    try:
        # Simulate the function call from OpenAI Realtime API
        mock_function_call = {
            "summary": "🎤 Voice Agent Test Appointment",
            "start_iso": (datetime.now() + timedelta(hours=2)).isoformat(),
            "end_iso": (datetime.now() + timedelta(hours=2, minutes=30)).isoformat(),
            "timezone": "America/Denver",
            "customer_name": "Test Customer",
            "customer_phone": "+1234567890",
            "notes": "Created by voice agent during a test call"
        }

        print("🎤 Simulating OpenAI Realtime API function call...")
        print(f"   Function: createCalendarEvent")
        print(f"   Summary: {mock_function_call['summary']}")
        print(f"   Customer: {mock_function_call['customer_name']}")
        print(f"   Phone: {mock_function_call['customer_phone']}")

        # Test the calendar creation
        db = next(get_db())

        result = asyncio.run(createCalendarEvent(
            start=mock_function_call['start_iso'],
            end=mock_function_call['end_iso'],
            summary=mock_function_call['summary'],
            user_id=user_id,
            db=db
        ))

        db.close()

        if result.get("success"):
            print("🎉 SUCCESS! Voice agent calendar integration works!")
            print(f"   Event ID: {result.get('event_id')}")
            print(f"   Google Calendar Link: {result.get('html_link')}")
            print("\n✅ This is exactly what will happen during a real voice call!")
            return True
        else:
            print(f"❌ Voice agent integration failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Error testing voice agent integration: {e}")
        return False


def main():
    """Main test runner"""
    print("🧪 Real Google Calendar Integration Test")
    print("=" * 50)

    # Check if we have an authorization code
    if len(sys.argv) < 2:
        print("❌ Please provide an authorization code")
        print("\nUsage:")
        print("python test_real_calendar.py <authorization_code>")
        print("\nTo get an authorization code:")
        print("1. Run: python -c \"from app.services.google_calendar import GoogleCalendarService; service = GoogleCalendarService(); flow = service.create_oauth_flow(); auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent'); print('Visit:', auth_url)\"")
        print("2. Complete the OAuth flow in your browser")
        print("3. Copy the 'code' parameter from the callback URL")
        sys.exit(1)

    auth_code = sys.argv[1]
    user_id = 1  # Use first user for testing

    print(f"🔑 Using authorization code: {auth_code[:20]}...")
    print(f"👤 Testing with user ID: {user_id}")

    # Step 1: Exchange code for credentials
    if not exchange_code_for_credentials(auth_code, user_id):
        print("❌ Failed to get credentials. Exiting.")
        sys.exit(1)

    # Step 2: Test real calendar creation
    if not asyncio.run(test_real_calendar_creation(user_id)):
        print("❌ Failed to create calendar event. Exiting.")
        sys.exit(1)

    # Step 3: Test voice agent simulation
    if not test_voice_agent_simulation(user_id):
        print("❌ Voice agent integration failed.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("🎉 ALL TESTS PASSED!")
    print("✅ Your calendar integration is working perfectly!")
    print("✅ Real events are being created in your Google Calendar!")
    print("✅ Voice agent integration is ready for live calls!")
    print("=" * 50)


if __name__ == "__main__":
    main()
