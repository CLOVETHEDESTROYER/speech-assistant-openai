#!/usr/bin/env python3
"""
Test script to verify the webhook fix for Twilio Conversational Intelligence
"""

import requests
import json


def test_webhook():
    """Test the webhook with form data as Twilio sends it"""

    # Test data matching Twilio's Conversational Intelligence webhook format
    test_data = {
        'TranscriptSid': 'GT1234567890abcdef',
        'EventType': 'voice_intelligence_transcript_available',
        'ServiceSid': 'IS1234567890abcdef',
        'CallSid': 'CA1234567890abcdef',
        'Status': 'completed'
    }

    webhook_url = "https://voice.hyperlabsai.com/twilio-transcripts/webhook-callback"

    print("🧪 Testing Twilio Conversational Intelligence Webhook...")
    print(f"📡 URL: {webhook_url}")
    print(f"📦 Data: {test_data}")

    try:
        # Send POST request with form data (as Twilio does)
        response = requests.post(
            webhook_url,
            data=test_data,  # This sends as form-encoded data
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )

        print(f"✅ Response Status: {response.status_code}")
        print(f"📄 Response Body: {response.text}")

        if response.status_code == 200:
            print("🎉 Webhook test successful!")
        else:
            print("❌ Webhook test failed!")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing webhook: {e}")


if __name__ == "__main__":
    test_webhook()
