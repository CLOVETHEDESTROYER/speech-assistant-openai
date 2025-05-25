#!/usr/bin/env python3
"""
Test script for the enhanced transcript endpoints.
This script tests the new enhanced transcript functionality.
"""

import requests
import json
import sys


def test_enhanced_endpoints():
    """Test the enhanced transcript endpoints"""
    base_url = "http://localhost:5050"

    print("Testing Enhanced Transcript Endpoints")
    print("=" * 50)

    # Test 1: Check if enhanced transcripts endpoint is accessible
    try:
        response = requests.get(f"{base_url}/api/enhanced-transcripts/")
        print(f"✓ Enhanced transcripts list endpoint: {response.status_code}")
        if response.status_code == 401:
            print("  Note: Authentication required (expected)")
        elif response.status_code == 200:
            print(f"  Found {len(response.json())} transcripts")
    except Exception as e:
        print(f"✗ Enhanced transcripts list endpoint failed: {e}")

    # Test 2: Check if fetch and store endpoint is accessible
    try:
        test_data = {"transcript_sid": "test_sid"}
        response = requests.post(
            f"{base_url}/api/enhanced-twilio-transcripts/fetch-and-store",
            json=test_data
        )
        print(f"✓ Fetch and store endpoint: {response.status_code}")
        if response.status_code == 401:
            print("  Note: Authentication required (expected)")
        elif response.status_code == 422:
            print("  Note: Validation error (expected without auth)")
    except Exception as e:
        print(f"✗ Fetch and store endpoint failed: {e}")

    # Test 3: Check application health
    try:
        response = requests.get(f"{base_url}/test")
        print(f"✓ Application health check: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.json()}")
    except Exception as e:
        print(f"✗ Application health check failed: {e}")

    print("\nTest completed!")
    print("\nTo use the enhanced endpoints:")
    print("1. Start the application: python -m uvicorn app.main:app --host 0.0.0.0 --port 5050")
    print("2. Authenticate to get a token")
    print("3. Use the enhanced endpoints with proper authentication")


if __name__ == "__main__":
    test_enhanced_endpoints()
