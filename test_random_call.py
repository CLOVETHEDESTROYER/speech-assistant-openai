#!/usr/bin/env python3
"""
Test script for the random call endpoint.
This script will generate a random persona and initiate a call immediately.
"""

import requests
import json
import sys
import os

# Configuration
API_BASE_URL = "http://localhost:8000"
PHONE_NUMBER = "+15055535929"  # Change this to your test number

def get_auth_token():
    """Get authentication token"""
    
    # Option 1: Get from environment variable
    token = os.getenv("AUTH_TOKEN")
    if token:
        return token
    
    # Option 2: Login with credentials from environment
    username = os.getenv("TEST_USERNAME") or os.getenv("TEST_EMAIL")
    password = os.getenv("TEST_PASSWORD")
    
    if username and password:
        print(f"🔐 Logging in with {username}...")
        try:
            login_response = requests.post(f"{API_BASE_URL}/auth/login", data={
                "username": username,
                "password": password
            })
            if login_response.status_code == 200:
                token = login_response.json().get("access_token")
                if token:
                    print("✅ Login successful!")
                    return token
            else:
                print(f"❌ Login failed: {login_response.status_code} - {login_response.text}")
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
    
    # Option 3: Interactive login
    if not username or not password:
        print("💡 No credentials found in environment variables.")
        print("Set TEST_USERNAME and TEST_PASSWORD environment variables, or AUTH_TOKEN directly")
        print("Example: export TEST_USERNAME=your_email@example.com")
        print("         export TEST_PASSWORD=your_password")
    
    return None

def test_random_call(phone_number=PHONE_NUMBER, time_context="evening"):
    """Test the random call endpoint"""
    
    print(f"🎯 Testing random call to {phone_number}")
    
    # Get authentication token
    token = get_auth_token()
    if not token:
        print("❌ No authentication token available.")
        print("Please set AUTH_TOKEN environment variable or modify get_auth_token() function")
        return False
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Optional parameters
    params = {}
    if time_context:
        params["time_context"] = time_context
    
    try:
        print("🤖 Generating random persona and initiating call...")
        
        url = f"{API_BASE_URL}/api/random-calls/make-random-call/{phone_number}"
        response = requests.post(url, headers=headers, params=params)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Call initiated successfully!")
            print(f"📞 Call SID: {result.get('call_sid')}")
            print(f"🎭 Scenario ID: {result.get('scenario_id')}")
            print(f"🎨 Persona: {result.get('persona_summary')}")
            print(f"🎵 Voice: {result.get('voice_type')}")
            print(f"🧠 AI Model: {result.get('generation_model')}")
            print(f"💬 Message: {result.get('message')}")
            return True
        else:
            print(f"❌ Call failed with status {response.status_code}")
            print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure the server is running on http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_themes_endpoint():
    """Test the themes endpoint to make sure API is working"""
    try:
        print("🎨 Testing available themes...")
        response = requests.get(f"{API_BASE_URL}/api/random-calls/themes")
        if response.status_code == 200:
            themes = response.json().get("themes", {})
            print(f"✅ Found {len(themes)} available themes:")
            for theme, info in themes.items():
                print(f"  - {theme}: {info.get('description', 'No description')}")
            return True
        else:
            print(f"❌ Themes endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing themes: {str(e)}")
        return False

if __name__ == "__main__":
    print("🎲 Random Call Test Script")
    print("=" * 40)
    
    # Test basic connectivity
    if not test_themes_endpoint():
        print("\n❌ Basic API connectivity failed. Check if server is running.")
        sys.exit(1)
    
    print("\n" + "=" * 40)
    
    # Allow phone number override
    phone_number = sys.argv[1] if len(sys.argv) > 1 else PHONE_NUMBER
    time_context = sys.argv[2] if len(sys.argv) > 2 else "evening"
    
    print(f"📱 Phone: {phone_number}")
    print(f"⏰ Time Context: {time_context}")
    print()
    
    # Test the random call
    success = test_random_call(phone_number, time_context)
    
    if success:
        print("\n🎉 Test completed successfully!")
        print("📞 You should receive a call shortly with a random AI persona.")
    else:
        print("\n❌ Test failed. Check the error messages above.")
        sys.exit(1)
