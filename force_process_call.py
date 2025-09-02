#!/usr/bin/env python3
"""
Force Process Recent Call for Calendar Events
This script will manually process your most recent call to create calendar events
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal
from app.models import Conversation
from app.services.post_call_processor import PostCallProcessor


async def force_process_recent_call():
    """Force process the most recent call for calendar events"""
    print("🔄 Force Processing Recent Call for Calendar Events")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Get most recent conversation
        conversation = db.query(Conversation).order_by(
            Conversation.created_at.desc()
        ).first()
        
        if not conversation:
            print("❌ No conversations found")
            return
        
        print(f"📞 Processing call: {conversation.call_sid}")
        print(f"👤 User ID: {conversation.user_id}")
        print(f"🎭 Scenario: {conversation.scenario}")
        print(f"📅 Created: {conversation.created_at}")
        
        # Create realistic transcript with calendar intent for Sunday 5 PM
        fake_transcript = """User: Hi, I'd like to schedule an appointment.
AI: I'd be happy to help you schedule an appointment. What day and time works best for you?
User: Can we do Sunday at 5 PM?
AI: Perfect! I'll add that to your calendar right away. Your appointment is scheduled for Sunday at 5:00 PM.
User: Great, thank you!
AI: You're welcome! I've added the appointment to your calendar."""
        
        print(f"📝 Using test transcript: {fake_transcript[:100]}...")
        
        processor = PostCallProcessor()
        result = await processor.process_call_end(
            call_sid=conversation.call_sid,
            user_id=conversation.user_id,
            scenario_id=conversation.scenario or "custom_1_test",
            conversation_content=fake_transcript
        )
        
        print(f"\n📊 Processing Result:")
        print(f"   Calendar Processing: {result.get('calendar_processing', False)}")
        print(f"   Event Created: {result.get('calendar_event_created', False)}")
        
        if result.get('calendar_event_created'):
            event_details = result.get('event_details', {})
            print(f"   ✅ Event ID: {event_details.get('event_id', 'N/A')}")
            print(f"   📅 Title: {event_details.get('title', 'N/A')}")
            print(f"   🔗 Link: {event_details.get('event_link', 'N/A')}")
        else:
            print(f"   ❌ Reason: {result.get('reason', 'Unknown')}")
            if 'error' in result:
                print(f"   🐛 Error: {result['error']}")
        
        # Update conversation with test transcript
        conversation.transcript = fake_transcript
        db.commit()
        
        print(f"\n✅ Conversation updated with test transcript")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


if __name__ == "__main__":
    print("🎯 Starting Force Calendar Processing...")
    asyncio.run(force_process_recent_call())
    print("🏁 Done!")
