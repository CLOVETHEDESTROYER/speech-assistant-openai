#!/usr/bin/env python3
"""
Fix SMS calendar integration to handle scheduling requests without specific times
"""

import os
import sys
sys.path.append('.')

# Read the current file
with open('app/services/user_sms_service.py', 'r') as f:
    content = f.read()

# Find the problematic section and replace it
old_section = '''            # Try to parse date/time from message
            parsed_datetime = await self.calendar_service.parse_datetime_from_message(message)

            if parsed_datetime:
                # Attempt to schedule
                customer_name = conversation.customer_name or "SMS Customer"
                customer_email = conversation.customer_email

                booking_result = await self.calendar_service.schedule_demo(
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    requested_datetime=parsed_datetime,
                    customer_name=customer_name,
                    user_id=self.user_id,
                    db_session=db
                )

                if booking_result["success"]:
                    if booking_result.get("calendar_created", False):
                        response = f"✅ Perfect! I've scheduled your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. You'll receive a calendar invite shortly!"
                    else:
                        response = f"✅ Great! I've noted your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. Our team will confirm the details with you soon."

                    # Update conversation with scheduling info
                    conversation.customer_interest = "Demo/Appointment Scheduled"
                    conversation.lead_score = min(
                        conversation.lead_score + 20, 100)
                    conversation.conversion_status = "qualified_lead"

                else:
                    # Handle booking conflicts or errors
                    if booking_result.get("error") == "Time slot is not available":
                        response = booking_result.get("message", "That time slot is not available. Let me suggest some alternatives.")
                    else:
                        response = "I'd be happy to help you schedule something! What time works best for you? (e.g., 'tomorrow 2pm' or 'Friday morning')"

                return {"response": response}'''

new_section = '''            # Try to parse date/time from message
            parsed_datetime = await self.calendar_service.parse_datetime_from_message(message)

            if parsed_datetime:
                # Attempt to schedule with specific time
                customer_name = conversation.customer_name or "SMS Customer"
                customer_email = conversation.customer_email

                booking_result = await self.calendar_service.schedule_demo(
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    requested_datetime=parsed_datetime,
                    customer_name=customer_name,
                    user_id=self.user_id,
                    db_session=db
                )

                if booking_result["success"]:
                    if booking_result.get("calendar_created", False):
                        response = f"✅ Perfect! I've scheduled your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. You'll receive a calendar invite shortly!"
                    else:
                        response = f"✅ Great! I've noted your appointment for {parsed_datetime.strftime('%A, %B %d at %I:%M %p')}. Our team will confirm the details with you soon."

                    # Update conversation with scheduling info
                    conversation.customer_interest = "Demo/Appointment Scheduled"
                    conversation.lead_score = min(
                        conversation.lead_score + 20, 100)
                    conversation.conversion_status = "qualified_lead"

                else:
                    # Handle booking conflicts or errors
                    if booking_result.get("error") == "Time slot is not available":
                        response = booking_result.get("message", "That time slot is not available. Let me suggest some alternatives.")
                    else:
                        response = "I'd be happy to help you schedule something! What time works best for you? (e.g., 'tomorrow 2pm' or 'Friday morning')"

                return {"response": response}
            else:
                # No specific time provided, but scheduling keywords detected
                # Ask for specific time preferences
                response = "I'd be happy to help you schedule something! What time works best for you? (e.g., 'tomorrow 2pm', 'Friday morning', or 'next week Tuesday')"
                return {"response": response}'''

# Replace the section
if old_section in content:
    content = content.replace(old_section, new_section)
    
    # Write the updated file
    with open('app/services/user_sms_service.py', 'w') as f:
        f.write(content)
    
    print("✅ SMS calendar integration fixed!")
    print("📝 Now SMS will respond to scheduling requests even without specific times")
else:
    print("❌ Could not find the section to replace")

