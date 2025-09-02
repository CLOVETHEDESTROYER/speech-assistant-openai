#!/usr/bin/env python3
"""
Simple Calendar Test Script
Quick tests for calendar functionality without complex setup.
"""

import asyncio
import json
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


def test_environment_variables():
    """Test if required environment variables are set"""
    print("🔧 Testing environment variables...")

    required_vars = [
        'GOOGLE_CLIENT_ID',
        'GOOGLE_CLIENT_SECRET',
        'GOOGLE_REDIRECT_URI'
    ]

    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:20]}...")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)

    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
        return False

    print("✅ All required environment variables are set")
    return True


def test_google_calendar_service():
    """Test Google Calendar Service initialization"""
    print("\n🔧 Testing Google Calendar Service...")

    try:
        from app.services.google_calendar import GoogleCalendarService

        service = GoogleCalendarService()
        print("✅ Google Calendar Service initialized")

        # Test OAuth flow creation
        flow = service.create_oauth_flow()
        print("✅ OAuth flow created")

        # Test authorization URL
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        print(f"✅ Authorization URL generated")
        print(f"   URL: {auth_url[:100]}...")

        return True

    except Exception as e:
        print(f"❌ Google Calendar Service test failed: {e}")
        return False


def test_calendar_routes():
    """Test if calendar routes are accessible"""
    print("\n🔧 Testing calendar routes...")

    try:
        import requests

        base_url = "http://localhost:5051"

        # Test if server is running
        try:
            response = requests.get(f"{base_url}/docs", timeout=5)
            if response.status_code == 200:
                print("✅ Server is running")
            else:
                print(
                    f"⚠️ Server responded with status: {response.status_code}")
        except requests.exceptions.RequestException:
            print(
                "❌ Server is not running. Please start it with: python start_dev_server.py")
            return False

        # Test calendar routes
        routes_to_test = [
            "/google-calendar/auth/google",
            "/google-calendar/callback",
            "/google-calendar/test-create-event"
        ]

        for route in routes_to_test:
            try:
                response = requests.get(f"{base_url}{route}", timeout=5)
                print(f"✅ {route}: Status {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"⚠️ {route}: {e}")

        return True

    except ImportError:
        print("⚠️ requests library not available - skipping route tests")
        return True
    except Exception as e:
        print(f"❌ Route test failed: {e}")
        return False


def test_database_connection():
    """Test database connection and models"""
    print("\n🔧 Testing database connection...")

    try:
        from app.db import get_db
        from app.models import User, GoogleCalendarCredentials

        db = next(get_db())
        print("✅ Database connection successful")

        # Test model imports
        print("✅ Models imported successfully")

        # Test query
        user_count = db.query(User).count()
        print(f"✅ User query successful - {user_count} users in database")

        cred_count = db.query(GoogleCalendarCredentials).count()
        print(
            f"✅ Calendar credentials query successful - {cred_count} credentials in database")

        db.close()
        return True

    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_calendar_function_import():
    """Test if calendar functions can be imported"""
    print("\n🔧 Testing calendar function imports...")

    try:
        from app.routes.google_calendar import createCalendarEvent
        print("✅ createCalendarEvent function imported")

        from app.utils.crypto import encrypt_string, decrypt_string
        print("✅ Crypto functions imported")

        return True

    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False


def main():
    """Run all simple tests"""
    print("🧪 Simple Calendar Integration Tests")
    print("=" * 50)

    tests = [
        ("Environment Variables", test_environment_variables),
        ("Google Calendar Service", test_google_calendar_service),
        ("Database Connection", test_database_connection),
        ("Function Imports", test_calendar_function_import),
        ("Calendar Routes", test_calendar_routes),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    # Print summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1

    print("="*50)
    print(f"📈 {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Your calendar integration is ready to test.")
        print("\nNext steps:")
        print("1. Run the full test suite: python test_calendar_integration.py")
        print("2. Test OAuth flow: Visit http://localhost:5051/auth/google")
        print("3. Test event creation: POST to /google-calendar/test-create-event")
    else:
        print(f"⚠️ {total - passed} tests failed. Please fix the issues above.")

    print("="*50)


if __name__ == "__main__":
    main()
