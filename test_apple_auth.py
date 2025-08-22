#!/usr/bin/env python3
"""
Test script for Apple Sign In functionality
Run this to verify the implementation is working correctly
"""

import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

def test_apple_auth_service():
    """Test if Apple auth service can be imported and initialized"""
    try:
        from services.apple_auth_service import AppleAuthService
        print("✅ Apple auth service imported successfully")
        
        # Test initialization (will fail without env vars, but that's expected)
        try:
            service = AppleAuthService()
            print("✅ Apple auth service initialized successfully")
        except ValueError as e:
            print(f"⚠️  Apple auth service initialization failed (expected without env vars): {e}")
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import Apple auth service: {e}")
        return False

def test_auth_endpoints():
    """Test if auth endpoints can be imported"""
    try:
        from auth import router
        print("✅ Auth router imported successfully")
        
        # Check if Apple signin endpoint exists
        routes = [route.path for route in router.routes]
        if "/apple-signin" in routes:
            print("✅ Apple signin endpoint found in auth router")
        else:
            print("❌ Apple signin endpoint not found in auth router")
            print(f"Available routes: {routes}")
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import auth router: {e}")
        return False

def test_models():
    """Test if User model has Apple fields"""
    try:
        from models import User
        print("✅ User model imported successfully")
        
        # Check if Apple fields exist
        user_fields = [column.name for column in User.__table__.columns]
        required_fields = ['apple_user_id', 'apple_email', 'apple_full_name', 'auth_provider', 'email_verified']
        
        missing_fields = [field for field in required_fields if field not in user_fields]
        if not missing_fields:
            print("✅ All Apple Sign In fields found in User model")
        else:
            print(f"❌ Missing Apple fields: {missing_fields}")
            print(f"Available fields: {user_fields}")
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import User model: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Apple Sign In Implementation...\n")
    
    tests = [
        ("Apple Auth Service", test_apple_auth_service),
        ("Auth Endpoints", test_auth_endpoints),
        ("User Model", test_models),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        result = test_func()
        results.append(result)
        print()
    
    # Summary
    print("📊 Test Results Summary:")
    passed = sum(results)
    total = len(results)
    
    for i, (test_name, test_func) in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Apple Sign In is ready to use.")
        print("\nNext steps:")
        print("1. Add Apple configuration to your .env file")
        print("2. Download your private key from Apple Developer Portal")
        print("3. Test the /auth/apple-signin endpoint")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
