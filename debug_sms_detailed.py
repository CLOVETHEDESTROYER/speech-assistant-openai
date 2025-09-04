#!/usr/bin/env python3
import sys
sys.path.append('.')

from app.db import get_db
from app.models import User, UserBusinessConfig, GoogleCalendarCredentials
from app.services.user_sms_service import UserSMSService
from app.services.sms_calendar_service import SMSCalendarService
import asyncio
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_sms_calendar_integration():
    db = next(get_db())
    try:
        print("🧪 Testing SMS Calendar Integration...")
        
        # Test 1: Check if UserSMSService can be initialized
        print("\n1️⃣ Testing UserSMSService initialization...")
        try:
            sms_service = UserSMSService(user_id=1)
            print("✅ UserSMSService initialized successfully")
        except Exception as e:
            print(f"❌ UserSMSService initialization failed: {e}")
            return
        
        # Test 2: Check calendar service
        print("\n2️⃣ Testing SMSCalendarService...")
        try:
            calendar_service = SMSCalendarService()
            print("✅ SMSCalendarService initialized successfully")
        except Exception as e:
            print(f"❌ SMSCalendarService initialization failed: {e}")
            return
        
        # Test 3: Test datetime parsing
        print("\n3️⃣ Testing datetime parsing...")
        test_messages = [
            "I want to schedule a demo for tomorrow at 2pm",
            "Can I book an appointment?",
            "demo tomorrow 2pm",
            "schedule meeting next week"
        ]
        
        for message in test_messages:
            print(f"\n�� Testing: '{message}'")
            try:
                parsed_datetime = await calendar_service.parse_datetime_from_message(message)
                if parsed_datetime:
                    print(f"✅ Parsed: {parsed_datetime}")
                else:
                    print("❌ Could not parse datetime")
            except Exception as e:
                print(f"❌ Parsing error: {e}")
        
        # Test 4: Test keyword detection
        print("\n4️⃣ Testing keyword detection...")
        scheduling_keywords = [
            "schedule", "book", "appointment", "meeting", "demo",
            "call", "available", "free", "calendar", "time"
        ]
        
        for message in test_messages:
            message_lower = message.lower()
            detected_keywords = [kw for kw in scheduling_keywords if kw in message_lower]
            print(f"📝 '{message}' -> Keywords: {detected_keywords}")
        
        # Test 5: Test business config
        print("\n5️⃣ Testing business config...")
        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == 1
        ).first()
        
        if business_config:
            print(f"✅ Business config found:")
            print(f"   - SMS enabled: {business_config.sms_enabled}")
            print(f"   - Calendar integration enabled: {business_config.calendar_integration_enabled}")
        else:
            print("❌ No business config found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_sms_calendar_integration())
