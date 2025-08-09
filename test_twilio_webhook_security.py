#!/usr/bin/env python3
"""
Twilio Webhook Security Tests

This module tests the Twilio webhook signature validation to ensure
that only legitimate Twilio requests are processed.
"""

import pytest
import hashlib
import hmac
import base64
import urllib.parse
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
import os


class TwilioWebhookSecurityTester:
    """Test Twilio webhook signature validation"""

    def __init__(self):
        self.client = TestClient(app)
        self.test_auth_token = "test_auth_token_123"
        self.test_url = "http://localhost:5051/twilio-callback"

    def generate_twilio_signature(self, url, params, auth_token):
        """Generate a valid Twilio signature"""
        # Sort parameters alphabetically
        sorted_params = sorted(params.items())

        # Create the string to sign
        string_to_sign = url
        for key, value in sorted_params:
            string_to_sign += key + value

        # Create signature using HMAC-SHA1
        signature = base64.b64encode(
            hmac.new(
                auth_token.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha1
            ).digest()
        ).decode('utf-8')

        return signature

    def test_valid_twilio_signature(self):
        """Test that valid Twilio signatures are accepted"""
        print("🔐 Testing Valid Twilio Signature...")

        # Test webhook data
        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321",
            "CallStatus": "ringing",
            "Direction": "inbound"
        }

        # Generate valid signature
        signature = self.generate_twilio_signature(
            self.test_url,
            webhook_data,
            self.test_auth_token
        )

        # Set up mock for Twilio auth token
        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            headers = {
                "X-Twilio-Signature": signature
            }

            response = self.client.post(
                "/twilio-callback",
                data=webhook_data,
                headers=headers
            )

            # Should accept valid signature
            assert response.status_code in [200, 201, 202], \
                f"Valid signature should be accepted, got {response.status_code}"

        print("✅ Valid Twilio signature test passed")

    def test_invalid_twilio_signature(self):
        """Test that invalid Twilio signatures are rejected"""
        print("🚫 Testing Invalid Twilio Signature...")

        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321"
        }

        # Use invalid signature
        invalid_signature = "invalid_signature_123"

        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            headers = {
                "X-Twilio-Signature": invalid_signature
            }

            response = self.client.post(
                "/twilio-callback",
                data=webhook_data,
                headers=headers
            )

            # Should reject invalid signature
            assert response.status_code in [400, 401, 403], \
                f"Invalid signature should be rejected, got {response.status_code}"

        print("✅ Invalid Twilio signature test passed")

    def test_missing_twilio_signature(self):
        """Test that requests without signature are rejected"""
        print("❌ Testing Missing Twilio Signature...")

        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321"
        }

        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            response = self.client.post(
                "/twilio-callback",
                data=webhook_data
                # No signature header
            )

            # Should reject request without signature
            assert response.status_code in [400, 401, 403], \
                f"Request without signature should be rejected, got {response.status_code}"

        print("✅ Missing Twilio signature test passed")

    def test_tampered_webhook_data(self):
        """Test that tampered webhook data is rejected"""
        print("🔒 Testing Tampered Webhook Data...")

        # Original data
        original_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321"
        }

        # Generate signature for original data
        original_signature = self.generate_twilio_signature(
            self.test_url,
            original_data,
            self.test_auth_token
        )

        # Tampered data (different CallSid)
        tampered_data = {
            "CallSid": "CA9999999999tampered",
            "From": "+1234567890",
            "To": "+0987654321"
        }

        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            headers = {
                "X-Twilio-Signature": original_signature  # Signature for original data
            }

            response = self.client.post(
                "/twilio-callback",
                data=tampered_data,
                headers=headers
            )

            # Should reject tampered data
            assert response.status_code in [400, 401, 403], \
                f"Tampered data should be rejected, got {response.status_code}"

        print("✅ Tampered webhook data test passed")

    def test_different_auth_tokens(self):
        """Test that different auth tokens produce different signatures"""
        print("🔑 Testing Different Auth Tokens...")

        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890"
        }

        # Generate signatures with different auth tokens
        signature1 = self.generate_twilio_signature(
            self.test_url,
            webhook_data,
            "auth_token_1"
        )

        signature2 = self.generate_twilio_signature(
            self.test_url,
            webhook_data,
            "auth_token_2"
        )

        # Signatures should be different
        assert signature1 != signature2, "Different auth tokens should produce different signatures"

        print("✅ Different auth tokens test passed")

    def test_url_encoding_handling(self):
        """Test that URL encoding is handled correctly"""
        print("🌐 Testing URL Encoding Handling...")

        # Data with special characters that need URL encoding
        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321",
            "SpeechResult": "Hello, world! How are you?",
            "Confidence": "0.95"
        }

        # Generate signature
        signature = self.generate_twilio_signature(
            self.test_url,
            webhook_data,
            self.test_auth_token
        )

        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            headers = {
                "X-Twilio-Signature": signature
            }

            response = self.client.post(
                "/twilio-callback",
                data=webhook_data,
                headers=headers
            )

            # Should handle URL encoding correctly
            assert response.status_code in [200, 201, 202], \
                f"URL encoding should be handled correctly, got {response.status_code}"

        print("✅ URL encoding handling test passed")

    def test_multiple_webhook_endpoints(self):
        """Test signature validation on multiple webhook endpoints"""
        print("🔗 Testing Multiple Webhook Endpoints...")

        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321"
        }

        # Test different webhook endpoints
        endpoints = [
            "/twilio-callback",
            "/recording-callback",
            "/twilio-transcripts/webhook-callback"
        ]

        with patch('app.config.TWILIO_AUTH_TOKEN', self.test_auth_token):
            for endpoint in endpoints:
                # Generate signature for this specific endpoint
                signature = self.generate_twilio_signature(
                    f"http://localhost:5051{endpoint}",
                    webhook_data,
                    self.test_auth_token
                )

                headers = {
                    "X-Twilio-Signature": signature
                }

                response = self.client.post(
                    endpoint,
                    data=webhook_data,
                    headers=headers
                )

                # Should accept valid signature for each endpoint
                assert response.status_code in [200, 201, 202, 404], \
                    f"Valid signature should be accepted for {endpoint}, got {response.status_code}"

        print("✅ Multiple webhook endpoints test passed")

    def run_all_tests(self):
        """Run all Twilio webhook security tests"""
        print("🚀 Starting Twilio Webhook Security Tests")
        print("=" * 50)

        test_methods = [
            self.test_valid_twilio_signature,
            self.test_invalid_twilio_signature,
            self.test_missing_twilio_signature,
            self.test_tampered_webhook_data,
            self.test_different_auth_tokens,
            self.test_url_encoding_handling,
            self.test_multiple_webhook_endpoints
        ]

        passed_tests = 0
        total_tests = len(test_methods)

        for test_method in test_methods:
            try:
                test_method()
                passed_tests += 1
            except Exception as e:
                print(f"❌ {test_method.__name__} failed: {str(e)}")

        print("\n" + "=" * 50)
        print(
            f"📊 Twilio Webhook Security Test Results: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("🎉 All Twilio webhook security tests passed!")
            return True
        else:
            print("⚠️ Some Twilio webhook security tests failed.")
            return False


def main():
    """Main function to run Twilio webhook security tests"""
    tester = TwilioWebhookSecurityTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
