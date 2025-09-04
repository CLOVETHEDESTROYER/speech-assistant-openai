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

# Find the line that ends the if parsed_datetime block
# Look for the return statement after the if parsed_datetime block
old_return = '                db.commit()\n                return {"response": response, "calendar_handled": True}'

new_return = '''                db.commit()
                return {"response": response, "calendar_handled": True}
            else:
                # No specific time provided, but scheduling keywords detected
                # Ask for specific time preferences
                response = "I'd be happy to help you schedule something! What time works best for you? (e.g., 'tomorrow 2pm', 'Friday morning', or 'next week Tuesday')"
                return {"response": response, "calendar_handled": True}'''

# Replace the section
if old_return in content:
    content = content.replace(old_return, new_return)
    
    # Write the updated file
    with open('app/services/user_sms_service.py', 'w') as f:
        f.write(content)
    
    print("✅ SMS calendar integration fixed!")
    print("📝 Now SMS will respond to scheduling requests even without specific times")
else:
    print("❌ Could not find the exact return statement to replace")
    print("🔍 Let me check the exact content...")
    
    # Find the line number where the return statement is
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'return {"response": response, "calendar_handled": True}' in line:
            print(f"Found return statement at line {i+1}: {line.strip()}")
            print(f"Context:")
            for j in range(max(0, i-2), min(len(lines), i+3)):
                print(f"{j+1:3d}: {lines[j]}")
            break

