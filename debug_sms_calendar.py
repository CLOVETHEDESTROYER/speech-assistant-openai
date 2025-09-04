#!/usr/bin/env python3
import sys
sys.path.append('.')

from app.db import get_db
from app.models import User, UserBusinessConfig, GoogleCalendarCredentials

def check_user_calendar_config():
    db = next(get_db())
    try:
        # Check user 1's configuration
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            print("❌ User 1 not found")
            return
            
        print(f"✅ User found: {user.email}")
        
        # Check business config
        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == 1
        ).first()
        
        if business_config:
            print(f"✅ Business config found:")
            print(f"   - SMS enabled: {business_config.sms_enabled}")
            print(f"   - Calendar integration enabled: {business_config.calendar_integration_enabled}")
            print(f"   - Employee count: {business_config.employee_count}")
            print(f"   - Max concurrent bookings: {business_config.max_concurrent_bookings}")
        else:
            print("❌ No business config found")
            
        # Check calendar credentials
        credentials = db.query(GoogleCalendarCredentials).filter(
            GoogleCalendarCredentials.user_id == 1
        ).first()
        
        if credentials:
            print("✅ Google Calendar credentials found")
        else:
            print("❌ No Google Calendar credentials found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_user_calendar_config()
