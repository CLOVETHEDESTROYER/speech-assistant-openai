#!/usr/bin/env python3
"""
Debug WebSocket Messages Script
This script helps debug protocol errors by validating JSON messages
"""

import json
import re


def validate_twilio_message(message_dict):
    """Validate a Twilio WebSocket message for protocol compliance"""
    issues = []

    # Check required fields
    if "event" not in message_dict:
        issues.append("Missing 'event' field")

    # Check streamSid validation for events that require it
    events_requiring_stream_sid = ["media", "mark", "clear"]
    if message_dict.get("event") in events_requiring_stream_sid:
        stream_sid = message_dict.get("streamSid")
        if not stream_sid:
            issues.append(
                f"Missing or empty 'streamSid' for {message_dict.get('event')} event")
        elif not isinstance(stream_sid, str):
            issues.append(f"streamSid must be string, got {type(stream_sid)}")
        elif not re.match(r'^[A-Za-z0-9]+$', stream_sid):
            issues.append(
                f"streamSid contains invalid characters: {stream_sid}")

    # Check media event specifics
    if message_dict.get("event") == "media":
        if "media" not in message_dict:
            issues.append("Missing 'media' object for media event")
        elif "payload" not in message_dict.get("media", {}):
            issues.append("Missing 'payload' in media object")

    # Check mark event specifics
    if message_dict.get("event") == "mark":
        if "mark" not in message_dict:
            issues.append("Missing 'mark' object for mark event")
        elif "name" not in message_dict.get("mark", {}):
            issues.append("Missing 'name' in mark object")

    return issues


def test_sample_messages():
    """Test sample messages for validation"""
    print("🧪 Testing WebSocket Message Validation")
    print("=" * 50)

    # Valid media message
    valid_media = {
        "event": "media",
        "streamSid": "MZ123abc456def789",
        "media": {
            "payload": "ulaw audio data here"
        }
    }

    # Invalid media message (no streamSid)
    invalid_media = {
        "event": "media",
        "streamSid": None,
        "media": {
            "payload": "ulaw audio data here"
        }
    }

    # Valid mark message
    valid_mark = {
        "event": "mark",
        "streamSid": "MZ123abc456def789",
        "mark": {
            "name": "responsePart"
        }
    }

    test_cases = [
        ("Valid Media", valid_media),
        ("Invalid Media (null streamSid)", invalid_media),
        ("Valid Mark", valid_mark)
    ]

    for name, message in test_cases:
        print(f"\n📋 {name}:")
        print(f"   Message: {json.dumps(message, indent=2)}")
        issues = validate_twilio_message(message)
        if issues:
            print(f"   ❌ Issues: {', '.join(issues)}")
        else:
            print(f"   ✅ Valid")


if __name__ == "__main__":
    test_sample_messages()
