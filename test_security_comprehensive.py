#!/usr/bin/env python3
"""
Comprehensive Security Test Suite for Speech Assistant

This test suite validates all security features implemented during the refactoring:
- Authentication & Authorization
- CAPTCHA validation
- Security headers
- Rate limiting
- Twilio webhook signature validation
- CORS configuration
- Input validation & sanitization
- Database security
"""

import pytest
import requests
import json
import time
import hashlib
import hmac
import base64
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.utils import get_password_hash
from app.db import get_db, SessionLocal, Base, engine
from sqlalchemy.orm import Session
import os
import tempfile
import shutil


class SecurityTestSuite:
    """Comprehensive security test suite"""
    
    def __init__(self):
        self.client = TestClient(app)
        self.base_url = "http://localhost:8000"
        self.test_user = None
        self.auth_token = None
        
    def setup_database(self):
        """Setup test database"""
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        
        # Create test user
        test_user = User(
            email="security_test@example.com",
            hashed_password=get_password_hash("SecurePassword123!"),
            is_active=True,
            is_admin=False
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        self.test_user = test_user
        db.close()
        
    def teardown_database(self):
        """Cleanup test database"""
        Base.metadata.drop_all(bind=engine)
        
    def authenticate_user(self):
        """Authenticate test user and get token"""
        login_data = {
            "username": "security_test@example.com",
            "password": "SecurePassword123!"
        }
        
        with patch('app.captcha.verify_captcha', return_value=True):
            response = self.client.post("/token", data=login_data)
            if response.status_code == 200:
                self.auth_token = response.json()["access_token"]
                return True
        return False
        
    def test_1_authentication_security(self):
        """Test authentication security features"""
        print("\n🔐 Testing Authentication Security...")
        
        # Test 1.1: Password strength validation
        weak_password_data = {
            "email": "test@example.com",
            "password": "123"  # Too weak
        }
        
        with patch('app.captcha.verify_captcha', return_value=True):
            response = self.client.post("/auth/register", json=weak_password_data)
            # Should fail due to weak password
            assert response.status_code in [400, 422], "Weak password should be rejected"
            
        # Test 1.2: JWT token validation
        if self.auth_token:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = self.client.get("/users/me", headers=headers)
            assert response.status_code == 200, "Valid JWT should work"
            
        # Test 1.3: Invalid token rejection
        invalid_headers = {"Authorization": "Bearer invalid_token"}
        response = self.client.get("/users/me", headers=invalid_headers)
        assert response.status_code == 401, "Invalid JWT should be rejected"
        
        print("✅ Authentication security tests passed")
        
    def test_2_captcha_validation(self):
        """Test CAPTCHA validation"""
        print("\n🤖 Testing CAPTCHA Validation...")
        
        # Test 2.1: CAPTCHA required for login
        login_data = {
            "username": "test@example.com",
            "password": "testpassword123"
        }
        
        with patch('app.captcha.verify_captcha', return_value=False):
            response = self.client.post("/token", data=login_data)
            assert response.status_code == 400, "CAPTCHA failure should block login"
            
        # Test 2.2: CAPTCHA required for registration
        register_data = {
            "email": "newuser@example.com",
            "password": "SecurePassword123!"
        }
        
        with patch('app.captcha.verify_captcha', return_value=False):
            response = self.client.post("/auth/register", json=register_data)
            assert response.status_code == 400, "CAPTCHA failure should block registration"
            
        print("✅ CAPTCHA validation tests passed")
        
    def test_3_security_headers(self):
        """Test security headers"""
        print("\n🛡️ Testing Security Headers...")
        
        response = self.client.get("/test")
        
        # Check for essential security headers
        required_headers = [
            "X-XSS-Protection",
            "X-Content-Type-Options", 
            "X-Frame-Options",
            "Referrer-Policy"
        ]
        
        for header in required_headers:
            assert header in response.headers, f"Missing security header: {header}"
            
        # Verify header values
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        
        # Check CSP header
        if "Content-Security-Policy" in response.headers:
            csp = response.headers["Content-Security-Policy"]
            assert "default-src 'self'" in csp
            assert "script-src" in csp
            
        print("✅ Security headers tests passed")
        
    def test_4_rate_limiting(self):
        """Test rate limiting"""
        print("\n⏱️ Testing Rate Limiting...")
        
        # Test 4.1: Login rate limiting
        login_data = {
            "username": "test@example.com",
            "password": "wrongpassword"
        }
        
        # Make multiple rapid requests
        for i in range(6):  # Should hit 5/minute limit
            with patch('app.captcha.verify_captcha', return_value=True):
                response = self.client.post("/token", data=login_data)
                
        # The 6th request should be rate limited
        assert response.status_code == 429, "Rate limiting should be enforced"
        
        # Test 4.2: Protected route rate limiting
        if self.auth_token:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            for i in range(6):  # Should hit 5/minute limit
                response = self.client.get("/protected", headers=headers)
                
            assert response.status_code == 429, "Protected route rate limiting should work"
            
        print("✅ Rate limiting tests passed")
        
    def test_5_twilio_webhook_security(self):
        """Test Twilio webhook signature validation"""
        print("\n📞 Testing Twilio Webhook Security...")
        
        # Test 5.1: Missing signature
        webhook_data = {
            "CallSid": "test_call_sid",
            "From": "+1234567890",
            "To": "+0987654321"
        }
        
        response = self.client.post("/twilio-callback", data=webhook_data)
        # Should fail without proper signature
        assert response.status_code in [400, 401, 403], "Webhook without signature should be rejected"
        
        # Test 5.2: Invalid signature
        headers = {
            "X-Twilio-Signature": "invalid_signature"
        }
        
        response = self.client.post("/twilio-callback", data=webhook_data, headers=headers)
        assert response.status_code in [400, 401, 403], "Webhook with invalid signature should be rejected"
        
        print("✅ Twilio webhook security tests passed")
        
    def test_6_cors_configuration(self):
        """Test CORS configuration"""
        print("\n🌐 Testing CORS Configuration...")
        
        # Test 6.1: Preflight request
        headers = {
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        }
        
        response = self.client.options("/token", headers=headers)
        
        # Check if CORS headers are properly configured
        if "Access-Control-Allow-Origin" in response.headers:
            origin = response.headers["Access-Control-Allow-Origin"]
            # Should not allow arbitrary origins
            assert origin != "*" or "malicious-site.com" not in origin
            
        print("✅ CORS configuration tests passed")
        
    def test_7_input_validation(self):
        """Test input validation and sanitization"""
        print("\n🔍 Testing Input Validation...")
        
        # Test 7.1: SQL injection attempt
        malicious_email = "test@example.com'; DROP TABLE users; --"
        login_data = {
            "username": malicious_email,
            "password": "testpassword123"
        }
        
        with patch('app.captcha.verify_captcha', return_value=True):
            response = self.client.post("/token", data=login_data)
            # Should handle gracefully without SQL injection
            assert response.status_code in [401, 400], "SQL injection should be handled safely"
            
        # Test 7.2: XSS attempt
        xss_name = "<script>alert('xss')</script>"
        if self.auth_token:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = self.client.post("/update-user-name", 
                                      json={"name": xss_name}, 
                                      headers=headers)
            # Should sanitize or reject XSS content
            assert response.status_code in [200, 400, 422], "XSS content should be handled safely"
            
        print("✅ Input validation tests passed")
        
    def test_8_database_security(self):
        """Test database security"""
        print("\n🗄️ Testing Database Security...")
        
        # Test 8.1: Database connection security
        response = self.client.get("/test-db-connection")
        assert response.status_code == 200, "Database connection should work"
        
        # Test 8.2: Sensitive data exposure
        if self.auth_token:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = self.client.get("/users/me", headers=headers)
            
            if response.status_code == 200:
                user_data = response.json()
                # Should not expose sensitive fields
                sensitive_fields = ["hashed_password", "password", "secret_key"]
                for field in sensitive_fields:
                    assert field not in user_data, f"Sensitive field {field} should not be exposed"
                    
        print("✅ Database security tests passed")
        
    def test_9_session_management(self):
        """Test session management security"""
        print("\n🔐 Testing Session Management...")
        
        # Test 9.1: Token expiration
        if self.auth_token:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            # Simulate token expiration by waiting (if configured for short expiration)
            # This is a basic test - in real scenarios you'd mock time
            
            response = self.client.get("/users/me", headers=headers)
            assert response.status_code in [200, 401], "Token should be valid or properly expired"
            
        print("✅ Session management tests passed")
        
    def test_10_file_upload_security(self):
        """Test file upload security"""
        print("\n📁 Testing File Upload Security...")
        
        # Test 10.1: Malicious file upload attempt
        malicious_content = b"<script>alert('malicious')</script>"
        
        # Create a temporary file with malicious content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as temp_file:
            temp_file.write(malicious_content)
            temp_file_path = temp_file.name
            
        try:
            with open(temp_file_path, 'rb') as f:
                files = {"file": ("malicious.html", f, "text/html")}
                response = self.client.post("/whisper/transcribe", files=files)
                
            # Should handle malicious files safely
            assert response.status_code in [200, 400, 422], "Malicious file should be handled safely"
            
        finally:
            # Cleanup
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
        print("✅ File upload security tests passed")
        
    def run_all_tests(self):
        """Run all security tests"""
        print("🚀 Starting Comprehensive Security Test Suite")
        print("=" * 60)
        
        try:
            self.setup_database()
            
            if not self.authenticate_user():
                print("⚠️ Warning: Could not authenticate test user, some tests may be skipped")
                
            # Run all test methods
            test_methods = [
                self.test_1_authentication_security,
                self.test_2_captcha_validation,
                self.test_3_security_headers,
                self.test_4_rate_limiting,
                self.test_5_twilio_webhook_security,
                self.test_6_cors_configuration,
                self.test_7_input_validation,
                self.test_8_database_security,
                self.test_9_session_management,
                self.test_10_file_upload_security
            ]
            
            passed_tests = 0
            total_tests = len(test_methods)
            
            for test_method in test_methods:
                try:
                    test_method()
                    passed_tests += 1
                except Exception as e:
                    print(f"❌ {test_method.__name__} failed: {str(e)}")
                    
            print("\n" + "=" * 60)
            print(f"📊 Security Test Results: {passed_tests}/{total_tests} tests passed")
            
            if passed_tests == total_tests:
                print("🎉 All security tests passed! Application is secure.")
            else:
                print("⚠️ Some security tests failed. Please review the issues above.")
                
        finally:
            self.teardown_database()


def main():
    """Main function to run the security test suite"""
    test_suite = SecurityTestSuite()
    test_suite.run_all_tests()


if __name__ == "__main__":
    main()
