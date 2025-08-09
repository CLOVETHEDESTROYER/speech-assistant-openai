#!/usr/bin/env python3
"""
Quick Test Script for Speech Assistant

This script provides a quick way to test the basic functionality
and security features of the application.
"""

import requests
import json
import time
import sys
import os
from urllib.parse import urljoin


class QuickTester:
    """Quick test runner for the Speech Assistant"""
    
    def __init__(self, base_url="http://localhost:5051"):
        self.base_url = base_url
        self.session = requests.Session()
        self.auth_token = None
        
    def test_server_running(self):
        """Test if the server is running"""
        print("🔍 Testing server connectivity...")
        
        try:
            response = self.session.get(urljoin(self.base_url, "/test"))
            if response.status_code == 200:
                print("✅ Server is running")
                return True
            else:
                print(f"❌ Server returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to server. Is it running?")
            return False
        except Exception as e:
            print(f"❌ Error connecting to server: {e}")
            return False
            
    def test_security_headers(self):
        """Test security headers"""
        print("🛡️ Testing security headers...")
        
        try:
            response = self.session.get(urljoin(self.base_url, "/test"))
            
            required_headers = [
                "X-XSS-Protection",
                "X-Content-Type-Options",
                "X-Frame-Options"
            ]
            
            missing_headers = []
            for header in required_headers:
                if header not in response.headers:
                    missing_headers.append(header)
                    
            if missing_headers:
                print(f"❌ Missing security headers: {missing_headers}")
                return False
            else:
                print("✅ All required security headers present")
                return True
                
        except Exception as e:
            print(f"❌ Error testing security headers: {e}")
            return False
            
    def test_api_documentation(self):
        """Test if API documentation is accessible"""
        print("📚 Testing API documentation...")
        
        try:
            response = self.session.get(urljoin(self.base_url, "/docs"))
            if response.status_code == 200:
                print("✅ API documentation accessible")
                return True
            else:
                print(f"❌ API documentation returned status {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error accessing API documentation: {e}")
            return False
            
    def test_database_connection(self):
        """Test database connection"""
        print("🗄️ Testing database connection...")
        
        try:
            response = self.session.get(urljoin(self.base_url, "/test-db-connection"))
            if response.status_code == 200:
                print("✅ Database connection working")
                return True
            else:
                print(f"❌ Database connection failed with status {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error testing database connection: {e}")
            return False
            
    def test_rate_limiting(self):
        """Test rate limiting"""
        print("⏱️ Testing rate limiting...")
        
        try:
            # Make multiple rapid requests to trigger rate limiting
            responses = []
            for i in range(10):
                response = self.session.get(urljoin(self.base_url, "/test"))
                responses.append(response.status_code)
                time.sleep(0.1)  # Small delay
                
            # Check if any requests were rate limited (429)
            if 429 in responses:
                print("✅ Rate limiting is working")
                return True
            else:
                print("⚠️ Rate limiting may not be working (no 429 responses)")
                return False
                
        except Exception as e:
            print(f"❌ Error testing rate limiting: {e}")
            return False
            
    def test_cors_configuration(self):
        """Test CORS configuration"""
        print("🌐 Testing CORS configuration...")
        
        try:
            headers = {
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type"
            }
            
            response = self.session.options(urljoin(self.base_url, "/test"), headers=headers)
            
            # Check if CORS headers are present and properly configured
            if "Access-Control-Allow-Origin" in response.headers:
                origin = response.headers["Access-Control-Allow-Origin"]
                if origin == "*":
                    print("⚠️ CORS allows all origins (may be insecure)")
                elif "malicious-site.com" in origin:
                    print("❌ CORS allows malicious origin")
                    return False
                else:
                    print("✅ CORS properly configured")
                    return True
            else:
                print("✅ No CORS headers (secure default)")
                return True
                
        except Exception as e:
            print(f"❌ Error testing CORS: {e}")
            return False
            
    def test_authentication_endpoints(self):
        """Test authentication endpoints"""
        print("🔐 Testing authentication endpoints...")
        
        try:
            # Test login endpoint (should exist but require valid credentials)
            login_data = {
                "username": "test@example.com",
                "password": "wrongpassword"
            }
            
            response = self.session.post(urljoin(self.base_url, "/token"), data=login_data)
            
            # Should return 401 for invalid credentials (not 404)
            if response.status_code == 401:
                print("✅ Authentication endpoint working")
                return True
            elif response.status_code == 404:
                print("❌ Authentication endpoint not found")
                return False
            else:
                print(f"⚠️ Authentication endpoint returned unexpected status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error testing authentication: {e}")
            return False
            
    def test_protected_routes(self):
        """Test protected routes"""
        print("🚪 Testing protected routes...")
        
        try:
            # Try to access protected route without authentication
            response = self.session.get(urljoin(self.base_url, "/users/me"))
            
            if response.status_code == 401:
                print("✅ Protected routes properly secured")
                return True
            else:
                print(f"❌ Protected route accessible without authentication (status: {response.status_code})")
                return False
                
        except Exception as e:
            print(f"❌ Error testing protected routes: {e}")
            return False
            
    def test_error_handling(self):
        """Test error handling"""
        print("⚠️ Testing error handling...")
        
        try:
            # Test non-existent endpoint
            response = self.session.get(urljoin(self.base_url, "/non-existent-endpoint"))
            
            if response.status_code == 404:
                print("✅ 404 errors handled properly")
                return True
            else:
                print(f"⚠️ Unexpected response for non-existent endpoint: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error testing error handling: {e}")
            return False
            
    def run_all_tests(self):
        """Run all quick tests"""
        print("🚀 Starting Quick Test Suite")
        print("=" * 50)
        
        tests = [
            ("Server Running", self.test_server_running),
            ("Security Headers", self.test_security_headers),
            ("API Documentation", self.test_api_documentation),
            ("Database Connection", self.test_database_connection),
            ("Rate Limiting", self.test_rate_limiting),
            ("CORS Configuration", self.test_cors_configuration),
            ("Authentication Endpoints", self.test_authentication_endpoints),
            ("Protected Routes", self.test_protected_routes),
            ("Error Handling", self.test_error_handling)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            print(f"\n{test_name}:")
            try:
                success = test_func()
                results.append((test_name, success))
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                results.append((test_name, False))
                
        # Print summary
        print("\n" + "=" * 50)
        print("📊 Quick Test Results:")
        
        passed = 0
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"  {test_name}: {status}")
            if success:
                passed += 1
                
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All quick tests passed!")
            return True
        else:
            print("⚠️ Some tests failed. Check the details above.")
            return False


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Quick test script for Speech Assistant")
    parser.add_argument("--url", default="http://localhost:5051", 
                       help="Base URL of the application (default: http://localhost:5051)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Verbose output")
    
    args = parser.parse_args()
    
    # Set up logging if verbose
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    tester = QuickTester(args.url)
    success = tester.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
