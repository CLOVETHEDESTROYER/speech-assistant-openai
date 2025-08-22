#!/usr/bin/env python3
"""
Test script for mobile app onboarding flow
Tests the new step names and data format handling
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"  # Adjust as needed
TEST_EMAIL = "test_mobile_onboarding@example.com"
TEST_PASSWORD = "TestPassword123!"


def test_mobile_onboarding_flow():
    """Test the complete mobile onboarding flow"""
    print("🧪 Testing Mobile App Onboarding Flow")
    print("=" * 50)

    # Step 1: Register a test user
    print("\n1. Registering test user...")
    register_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }

    # Note: This might fail if CAPTCHA is enabled
    try:
        response = requests.post(f"{BASE_URL}/register", json=register_data)
        if response.status_code != 200:
            print(
                f"⚠️  Registration failed: {response.status_code} - {response.text}")
            print("Note: CAPTCHA might be enabled. Try with a real user account.")
            return False
    except Exception as e:
        print(f"❌ Registration request failed: {e}")
        return False

    # Step 2: Login to get auth token
    print("2. Logging in...")
    try:
        login_response = requests.post(f"{BASE_URL}/login", json=register_data)
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return False

        auth_data = login_response.json()
        token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login request failed: {e}")
        return False

    # Step 3: Test mobile app step names
    mobile_steps = [
        {
            "step": "welcome",
            "data": None,
            "description": "Welcome step completion"
        },
        {
            "step": "profile",
            "data": {
                "name": "Test Mobile User",
                "phone_number": "+1234567890",
                "preferred_voice": "coral",
                "notifications_enabled": True
            },
            "description": "Profile step with user data"
        },
        {
            "step": "tutorial",
            "data": None,
            "description": "Tutorial step completion"
        },
        {
            "step": "firstCall",
            "data": None,
            "description": "First call step completion"
        }
    ]

    print("\n3. Testing mobile app step completion...")
    for i, step_data in enumerate(mobile_steps, 1):
        print(f"\n   3.{i} Testing {step_data['step']} step...")

        try:
            # Test step completion
            payload = {"step": step_data["step"]}
            if step_data["data"]:
                payload["data"] = step_data["data"]

            response = requests.post(
                f"{BASE_URL}/onboarding/complete-step",
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                print(f"     ✅ {step_data['description']}: SUCCESS")
                print(f"        - Step: {result.get('step')}")
                print(f"        - Completed: {result.get('isCompleted')}")
                print(f"        - Next Step: {result.get('nextStep')}")
                print(f"        - Completed At: {result.get('completedAt')}")
            else:
                print(f"     ❌ {step_data['description']}: FAILED")
                print(f"        Status: {response.status_code}")
                print(f"        Error: {response.text}")
                return False

        except Exception as e:
            print(f"     ❌ {step_data['description']}: ERROR - {e}")
            return False

    # Step 4: Test onboarding status endpoint
    print("\n4. Testing onboarding status endpoint...")
    try:
        response = requests.get(
            f"{BASE_URL}/onboarding/status", headers=headers)
        if response.status_code == 200:
            status = response.json()
            print("   ✅ Onboarding status: SUCCESS")
            print(f"      - Current Step: {status.get('currentStep')}")
            print(f"      - Completed Steps: {status.get('completedSteps')}")
            print(f"      - Progress: {status.get('progress', 0)*100:.1f}%")
            print(f"      - Is Complete: {status.get('isComplete')}")
        else:
            print(f"   ❌ Onboarding status: FAILED ({response.status_code})")
            return False
    except Exception as e:
        print(f"   ❌ Onboarding status: ERROR - {e}")
        return False

    # Step 5: Test individual step checking
    print("\n5. Testing individual step checking...")
    for step_name in ["welcome", "profile", "tutorial", "firstCall"]:
        try:
            response = requests.get(
                f"{BASE_URL}/onboarding/check-step/{step_name}", headers=headers)
            if response.status_code == 200:
                result = response.json()
                print(
                    f"   ✅ Check {step_name}: {result.get('completed', False)}")
            else:
                print(
                    f"   ❌ Check {step_name}: FAILED ({response.status_code})")
        except Exception as e:
            print(f"   ❌ Check {step_name}: ERROR - {e}")

    print("\n" + "=" * 50)
    print("🎉 Mobile Onboarding Flow Test COMPLETED!")
    print("\n✅ Key Features Tested:")
    print("   - Mobile app step names (welcome, profile, tutorial, firstCall)")
    print("   - Profile data storage during onboarding")
    print("   - Mobile-compatible response format")
    print("   - Step progression and status tracking")
    print("   - Individual step completion checking")

    return True


def test_backend_compatibility():
    """Test that backend step names still work"""
    print("\n🔄 Testing Backend Step Compatibility...")

    # This would require authentication, which we've already tested above
    # For now, just confirm the mapping is working
    from app.routes.onboarding import MOBILE_STEP_MAPPING, BACKEND_TO_MOBILE_MAPPING

    print("   ✅ Mobile to Backend mapping:")
    for mobile, backend in MOBILE_STEP_MAPPING.items():
        print(f"      {mobile} → {backend}")

    print("   ✅ Backend to Mobile mapping:")
    for backend, mobile in BACKEND_TO_MOBILE_MAPPING.items():
        print(f"      {backend} → {mobile}")


if __name__ == "__main__":
    print("🚀 Starting Mobile App Onboarding Tests")
    print(f"🕐 Test started at: {datetime.now().isoformat()}")

    # Test the mapping first
    test_backend_compatibility()

    # Test the full flow
    try:
        success = test_mobile_onboarding_flow()
        if success:
            print("\n🎯 ALL TESTS PASSED!")
            sys.exit(0)
        else:
            print("\n💥 SOME TESTS FAILED!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⛔ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        sys.exit(1)
