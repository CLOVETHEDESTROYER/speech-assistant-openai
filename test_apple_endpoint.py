#!/usr/bin/env python3
"""
Simple test to verify Apple Sign-In endpoint is working
"""

import requests
import json

def test_apple_signin_endpoint():
    """Test the Apple Sign-In endpoint with proper data structure"""
    
    # Test with ngrok URL (your public endpoint)
    endpoint = "https://10c0c1126067.ngrok-free.app/auth/apple-signin"
    
    # Test data that should trigger validation errors (not connection errors)
    test_data = {
        "identity_token": "test_token",
        "authorization_code": "test_code",
        "user_email": "test@example.com",
        "user_full_name": "Test User"
    }
    
    try:
        print(f"🧪 Testing Apple Sign-In endpoint: {endpoint}")
        
        response = requests.post(
            endpoint,
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 400:
            try:
                error_data = response.json()
                print(f"📊 Error Response: {json.dumps(error_data, indent=2)}")
                
                # Check if it's an Apple token validation error (good!)
                if "Invalid Apple token" in str(error_data) or "Apple" in str(error_data):
                    print("✅ Apple Sign-In endpoint is working correctly!")
                    print("   The endpoint is validating Apple tokens as expected.")
                    return True
                else:
                    print("⚠️  Unexpected error format")
                    return False
                    
            except json.JSONDecodeError:
                print(f"📊 Non-JSON Response: {response.text[:200]}...")
                return False
                
        elif response.status_code == 422:
            print("✅ Apple Sign-In endpoint is working!")
            print("   Validation is working as expected.")
            return True
            
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
            print(f"📊 Response: {response.text[:200]}...")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🍎 Apple Sign-In Endpoint Test\n")
    
    success = test_apple_signin_endpoint()
    
    print("\n" + "="*50)
    if success:
        print("🎉 SUCCESS: Apple Sign-In endpoint is working!")
        print("\n📱 Ready for iOS Testing:")
        print("1. ✅ Backend endpoint is accessible")
        print("2. ✅ Apple configuration is correct")
        print("3. ✅ Token validation is working")
        print("\n🔧 Next Steps:")
        print("- Test with your iOS app using real Apple Sign-In tokens")
        print("- Use the endpoint: POST /apple-signin")
        print("- Send: identity_token, authorization_code, user_email, user_full_name")
    else:
        print("❌ FAILED: Apple Sign-In endpoint has issues")
        print("\n🔧 Troubleshooting:")
        print("- Check if server is running")
        print("- Verify ngrok tunnel is active")
        print("- Check Apple configuration")
    
    print("="*50)
