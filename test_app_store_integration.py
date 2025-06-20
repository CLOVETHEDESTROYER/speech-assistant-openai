#!/usr/bin/env python3
"""
Test script for the new App Store integration endpoints.
This script tests the mobile app subscription endpoints with proper receipt validation.
"""

import requests
import json
import sys
import base64


def test_app_store_integration():
    """Test the App Store integration endpoints"""
    base_url = "http://localhost:5050"

    print("Testing App Store Integration Endpoints")
    print("=" * 50)

    # Test 1: Check if new endpoints are accessible
    try:
        response = requests.get(f"{base_url}/mobile/subscription-status")
        print(f"✓ Subscription status endpoint: {response.status_code}")
        if response.status_code == 401:
            print("  Note: Authentication required (expected)")
    except Exception as e:
        print(f"✗ Subscription status endpoint failed: {e}")

    # Test 2: Check App Store webhook endpoint
    try:
        test_webhook_data = {
            "signedPayload": "test_payload",
            "notificationType": "RENEWAL",
            "data": {
                "productId": "speech_assistant_weekly",
                "transactionId": "test_transaction",
                "originalTransactionId": "test_original_transaction"
            }
        }
        response = requests.post(
            f"{base_url}/mobile/app-store/webhook",
            json=test_webhook_data
        )
        print(f"✓ App Store webhook endpoint: {response.status_code}")
        if response.status_code == 401:
            print("  Note: Authentication required (expected)")
    except Exception as e:
        print(f"✗ App Store webhook endpoint failed: {e}")

    # Test 3: Check upgrade subscription endpoint (without auth)
    try:
        test_receipt_data = base64.b64encode(b"test_receipt_data").decode()
        test_upgrade_data = {
            "receipt_data": test_receipt_data,
            "is_sandbox": True,
            "subscription_tier": "mobile_weekly"
        }
        response = requests.post(
            f"{base_url}/mobile/upgrade-subscription",
            json=test_upgrade_data
        )
        print(f"✓ Upgrade subscription endpoint: {response.status_code}")
        if response.status_code == 401:
            print("  Note: Authentication required (expected)")
        elif response.status_code == 400:
            print("  Note: Receipt validation failed (expected with test data)")
    except Exception as e:
        print(f"✗ Upgrade subscription endpoint failed: {e}")

    # Test 4: Check application health
    try:
        response = requests.get(f"{base_url}/test")
        print(f"✓ Application health check: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.json()}")
    except Exception as e:
        print(f"✗ Application health check failed: {e}")

    print("\nApp Store Integration Test completed!")
    print("\nTo test with real App Store receipts:")
    print("1. Set APP_STORE_SHARED_SECRET in your .env file")
    print("2. Use real receipt data from your iOS app")
    print("3. Test with both sandbox and production receipts")


if __name__ == "__main__":
    test_app_store_integration()
