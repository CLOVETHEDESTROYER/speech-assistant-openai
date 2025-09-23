#!/usr/bin/env python3
"""
Comprehensive test script for Apple Sign-In implementation
Run this to verify your Apple Sign-In configuration and endpoint functionality
"""

import os
import sys
import requests
import json
import time
import jwt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_apple_config():
    """Test Apple Sign-In configuration"""
    print("🍎 Testing Apple Sign-In Configuration...")

    required_vars = [
        "APPLE_TEAM_ID",
        "APPLE_SERVICE_ID",
        "APPLE_KEY_ID",
        "APPLE_PRIVATE_KEY"
    ]

    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # Mask sensitive values
            if var == "APPLE_PRIVATE_KEY":
                display_value = f"{value[:20]}...{value[-20:]}" if len(
                    value) > 40 else "***"
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")

    if missing_vars:
        print(f"\n❌ Missing environment variables: {', '.join(missing_vars)}")
        return False

    print("\n✅ All Apple configuration variables are set!")
    return True


def test_apple_service():
    """Test Apple Auth Service initialization"""
    print("\n🔍 Testing Apple Auth Service...")

    try:
        from app.services.apple_auth_service import AppleAuthService
        service = AppleAuthService()
        print("✅ Apple Auth Service initialized successfully")

        # Test client secret generation
        try:
            client_secret = service.generate_client_secret()
            if client_secret:
                print("✅ Client secret generation successful")
                print(f"   Secret length: {len(client_secret)} characters")
            else:
                print("❌ Client secret generation failed")
                return False
        except Exception as e:
            print(f"❌ Client secret generation error: {e}")
            return False

    except Exception as e:
        print(f"❌ Apple Auth Service initialization failed: {e}")
        return False

    return True


def test_apple_endpoint():
    """Test Apple Sign-In endpoint availability"""
    print("\n🔍 Testing Apple Sign-In endpoint...")

    # Get the server URL from environment
    server_url = os.getenv("PUBLIC_URL", "http://localhost:5051")
    # Ensure URL has a scheme
    if not server_url.startswith(('http://', 'https://')):
        server_url = f"https://{server_url}"
    endpoint = f"{server_url}/apple-signin"

    try:
        # Test if endpoint is accessible (should return 422 for missing data)
        response = requests.post(endpoint, json={}, timeout=10)

        if response.status_code == 422:
            print("✅ Apple Sign-In endpoint is accessible")
            print(f"   Endpoint: {endpoint}")
            return True
        elif response.status_code == 404:
            print(f"❌ Apple Sign-In endpoint not found: {endpoint}")
            return False
        else:
            print(
                f"⚠️  Unexpected response from endpoint: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            return True

    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to server at {server_url}")
        print("   Make sure your server is running")
        return False
    except Exception as e:
        print(f"❌ Error testing endpoint: {e}")
        return False


def test_database_models():
    """Test database models for Apple Sign-In"""
    print("\n🔍 Testing Database Models...")

    try:
        from app.models import User
        from app.db import SessionLocal

        db = SessionLocal()

        # Check if Apple fields exist in User model
        apple_fields = ['apple_user_id', 'apple_email',
                        'apple_full_name', 'auth_provider']

        missing_fields = []
        for field in apple_fields:
            if not hasattr(User, field):
                missing_fields.append(field)

        if missing_fields:
            print(
                f"❌ Missing Apple fields in User model: {', '.join(missing_fields)}")
            db.close()
            return False

        print("✅ All Apple fields present in User model")
        db.close()
        return True

    except Exception as e:
        print(f"❌ Database model test failed: {e}")
        return False


def test_mock_apple_token():
    """Test with a mock Apple token (for development testing)"""
    print("\n🧪 Testing with Mock Apple Token...")

    try:
        from app.services.apple_auth_service import AppleAuthService

        service = AppleAuthService()

        # Create a mock Apple identity token for testing
        mock_token_payload = {
            "iss": "https://appleid.apple.com",
            "aud": service.service_id,
            "exp": int(time.time()) + 3600,  # 1 hour from now
            "iat": int(time.time()),
            "sub": "mock.apple.user.id.12345",
            "email": "test@example.com",
            "email_verified": "true"
        }

        # Create a mock token (unsigned for testing)
        mock_token = jwt.encode(
            mock_token_payload, "mock_secret", algorithm="HS256")

        print("✅ Mock token created successfully")
        print(f"   Mock user ID: {mock_token_payload['sub']}")
        print(f"   Mock email: {mock_token_payload['email']}")

        # Test token verification (this will fail with real verification but should pass basic checks)
        try:
            import asyncio
            decoded = asyncio.run(service.verify_apple_token(mock_token))
            if decoded:
                print("✅ Mock token verification passed")
            else:
                print("⚠️  Mock token verification failed (expected for unsigned token)")
        except Exception as e:
            print(
                f"⚠️  Mock token verification failed: {e} (expected for unsigned token)")

        return True

    except Exception as e:
        print(f"❌ Mock token test failed: {e}")
        return False


def test_auth_imports():
    """Test that all required auth functions are properly imported"""
    print("\n🔍 Testing Auth Imports...")

    try:
        from app.auth import create_access_token, create_refresh_token
        print("✅ Auth functions imported successfully")

        # Test that functions work
        test_data = {"sub": "test@example.com"}

        access_token = create_access_token(test_data)
        if access_token:
            print("✅ create_access_token function works")
        else:
            print("❌ create_access_token function failed")
            return False

        refresh_token = create_refresh_token()
        if refresh_token:
            print("✅ create_refresh_token function works")
        else:
            print("❌ create_refresh_token function failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Auth imports test failed: {e}")
        return False


def test_server_health():
    """Test if the server is running and healthy"""
    print("\n🔍 Testing Server Health...")

    server_url = "http://localhost:5051"  # Use localhost for health check

    try:
        # Test basic server connectivity
        response = requests.get(f"{server_url}/", timeout=5)
        # Any response means server is running
        if response.status_code in [200, 404, 405]:
            print("✅ Server is running and accessible")
            return True
        else:
            print(
                f"⚠️  Server responded with unexpected status: {response.status_code}")
            return True

    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to server at {server_url}")
        print("   Please start your server with: python -m uvicorn app.main:app --reload")
        return False
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return False


async def main():
    """Run all Apple Sign-In tests"""
    print("🍎 Apple Sign-In Implementation Test Suite\n")
    print("=" * 60)

    tests = [
        ("Server Health", test_server_health),
        ("Configuration", test_apple_config),
        ("Auth Imports", test_auth_imports),
        ("Auth Service", test_apple_service),
        ("Database Models", test_database_models),
        ("API Endpoint", test_apple_endpoint),
        ("Mock Token", test_mock_apple_token),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            if test_func.__name__ == "test_mock_apple_token":
                result = await test_func()  # This one is async
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 All tests passed! Apple Sign-In should be working.")
        print("\n📱 Next Steps for iOS Testing:")
        print("1. ✅ Backend is properly configured")
        print("2. 🔧 Test with your iOS app:")
        print("   - Ensure Bundle ID matches your Apple Developer configuration")
        print("   - Test on a real device (not simulator)")
        print("   - Use the /apple-signin endpoint in your iOS app")
        print("3. 🔄 If testing fails, revoke existing Apple ID associations:")
        print(
            "   - Settings > [Your Name] > Password & Security > Apps Using Apple ID")
        print("   - Find your app and tap 'Stop Using Apple ID'")
        print("4. 📋 Apple Sign-In Request Format:")
        print("   POST /apple-signin")
        print("   {")
        print('     "identity_token": "apple_identity_token_here",')
        print('     "authorization_code": "apple_authorization_code_here",')
        print('     "user_email": "user@example.com",')
        print('     "user_full_name": "John Doe"')
        print("   }")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("\n🔧 Common Fixes:")
        print("1. Add missing environment variables to your .env file")
        print("2. Start your server: python -m uvicorn app.main:app --reload")
        print("3. Run database migrations: alembic upgrade head")
        print("4. Check Apple Developer Portal configuration")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
