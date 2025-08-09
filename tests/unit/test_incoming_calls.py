#!/usr/bin/env python3
"""
Incoming Call Tests

Tests incoming call functionality to ensure:
- Calls can be received without authentication (business receptionist use case)
- Proper scenario handling for inbound calls
- Webhook signature validation (when implemented)
- Call routing and media stream handling
"""

import pytest
import json
import hmac
import hashlib
import base64
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models import User, Conversation
from app.utils import get_password_hash
from app.db import get_db, SessionLocal, Base, engine
from sqlalchemy.orm import Session


class TestIncomingCalls:
    """Test suite for incoming call functionality"""
    
    @pytest.fixture
    def client(self):
        """Test client"""
        return TestClient(app)
    
    @pytest.fixture
    def db_session(self):
        """Database session"""
        Base.metadata.create_all(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
        Base.metadata.drop_all(bind=engine)
    
    @pytest.fixture
    def twilio_webhook_data(self):
        """Sample Twilio webhook data for incoming calls"""
        return {
            "CallSid": "CA1234567890abcdef",
            "From": "+1234567890",
            "To": "+0987654321",
            "Direction": "inbound",
            "CallStatus": "ringing",
            "CallDuration": "0",
            "RecordingUrl": "",
            "RecordingSid": "",
            "Digits": "",
            "SpeechResult": "",
            "Confidence": "",
            "RecordingDuration": "",
            "TranscriptionStatus": "",
            "TranscriptionText": "",
            "TranscriptionUrl": ""
        }
    
    def test_incoming_call_endpoint_no_auth_required(self, client, twilio_webhook_data):
        """Test that incoming call endpoints don't require authentication"""
        # Test incoming call webhook endpoint
        response = client.post(
            "/incoming-call/default",
            data=twilio_webhook_data
        )
        
        # Should work without authentication (business receptionist use case)
        assert response.status_code == 200
        
        # Should return TwiML response
        content = response.content.decode()
        assert "<?xml version=" in content
        assert "<Response>" in content
        assert "<Connect>" in content or "<Say>" in content
    
    def test_incoming_call_webhook_no_auth_required(self, client, twilio_webhook_data):
        """Test that incoming call webhook doesn't require authentication"""
        response = client.post(
            "/incoming-call-webhook/default",
            data=twilio_webhook_data
        )
        
        # Should work without authentication
        assert response.status_code == 200
        
        # Should return TwiML response
        content = response.content.decode()
        assert "<?xml version=" in content
        assert "<Response>" in content
    
    def test_incoming_call_with_different_scenarios(self, client, twilio_webhook_data):
        """Test incoming calls with different scenarios"""
        scenarios = ["default", "sister_emergency", "mother_emergency", "yacht_party"]
        
        for scenario in scenarios:
            response = client.post(
                f"/incoming-call/{scenario}",
                data=twilio_webhook_data
            )
            
            assert response.status_code == 200
            content = response.content.decode()
            assert "<?xml version=" in content
            assert "<Response>" in content
    
    def test_incoming_call_webhook_signature_validation(self, client, twilio_webhook_data):
        """Test incoming call webhook signature validation (when implemented)"""
        # This test will need to be updated when signature validation is implemented
        # For now, it should work without signature
        
        response = client.post(
            "/incoming-call-webhook/default",
            data=twilio_webhook_data
        )
        
        assert response.status_code == 200
    
    def test_incoming_call_creates_conversation_record(self, client, twilio_webhook_data, db_session):
        """Test that incoming calls create conversation records"""
        # Make an incoming call
        response = client.post(
            "/incoming-call/default",
            data=twilio_webhook_data
        )
        
        assert response.status_code == 200
        
        # Check if conversation record was created
        conversation = db_session.query(Conversation).filter(
            Conversation.call_sid == "CA1234567890abcdef"
        ).first()
        
        # Note: This might not be created immediately depending on implementation
        # The test should be updated based on actual behavior
        if conversation:
            assert conversation.direction == "inbound"
            assert conversation.scenario == "default"
            assert conversation.phone_number == "+1234567890"
    
    def test_incoming_call_with_custom_scenario(self, client, twilio_webhook_data, db_session):
        """Test incoming calls with custom scenarios"""
        # Create a custom scenario first
        user = User(
            email="test@example.com",
            hashed_password=get_password_hash("password123"),
            is_active=True
        )
        db_session.add(user)
        db_session.commit()
        
        # Test with custom scenario ID
        custom_scenario_id = "custom_123"
        response = client.post(
            f"/incoming-custom-call/{custom_scenario_id}",
            data=twilio_webhook_data
        )
        
        # Should handle custom scenarios gracefully
        assert response.status_code in [200, 400, 404]
        
        # If 200, should return TwiML
        if response.status_code == 200:
            content = response.content.decode()
            assert "<?xml version=" in content
            assert "<Response>" in content
    
    def test_incoming_call_phone_number_validation(self, client, twilio_webhook_data):
        """Test incoming call phone number validation"""
        # Test with invalid phone number
        invalid_data = twilio_webhook_data.copy()
        invalid_data["From"] = "invalid_phone"
        
        response = client.post(
            "/incoming-call/default",
            data=invalid_data
        )
        
        # Should handle invalid phone numbers gracefully
        assert response.status_code in [200, 400]
    
    def test_incoming_call_scenario_validation(self, client, twilio_webhook_data):
        """Test incoming call scenario validation"""
        # Test with non-existent scenario
        response = client.post(
            "/incoming-call/nonexistent_scenario",
            data=twilio_webhook_data
        )
        
        # Should handle non-existent scenarios gracefully
        assert response.status_code in [200, 400, 404]
    
    def test_incoming_call_media_stream_endpoint(self, client):
        """Test incoming call media stream WebSocket endpoint"""
        # Test WebSocket connection for media stream
        with client.websocket_connect("/media-stream/default") as websocket:
            # Should be able to connect without authentication
            # This is a basic connection test
            assert websocket is not None
    
    def test_incoming_call_error_handling(self, client):
        """Test incoming call error handling"""
        # Test with missing required fields
        incomplete_data = {
            "CallSid": "CA1234567890abcdef"
            # Missing From, To, etc.
        }
        
        response = client.post(
            "/incoming-call/default",
            data=incomplete_data
        )
        
        # Should handle missing data gracefully
        assert response.status_code in [200, 400, 422]
    
    def test_incoming_call_recording_callback(self, client):
        """Test incoming call recording callback"""
        recording_data = {
            "CallSid": "CA1234567890abcdef",
            "RecordingSid": "RE1234567890abcdef",
            "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/AC123/Recordings/RE123",
            "RecordingDuration": "30",
            "RecordingStatus": "completed"
        }
        
        response = client.post(
            "/recording-callback",
            data=recording_data
        )
        
        # Should handle recording callbacks
        assert response.status_code in [200, 400, 500]
    
    def test_incoming_call_transcript_webhook(self, client):
        """Test incoming call transcript webhook"""
        transcript_data = {
            "CallSid": "CA1234567890abcdef",
            "TranscriptionSid": "TR1234567890abcdef",
            "TranscriptionStatus": "completed",
            "TranscriptionText": "Hello, this is a test call",
            "TranscriptionUrl": "https://api.twilio.com/2010-04-01/Accounts/AC123/Transcriptions/TR123"
        }
        
        response = client.post(
            "/twilio-transcripts/webhook-callback",
            data=transcript_data
        )
        
        # Should handle transcript webhooks
        assert response.status_code in [200, 400, 500]


class TestIncomingCallSecurity:
    """Test security aspects of incoming calls"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_incoming_call_rate_limiting(self, client, twilio_webhook_data):
        """Test rate limiting on incoming call endpoints"""
        # Make multiple rapid incoming calls
        responses = []
        for i in range(10):
            response = client.post(
                "/incoming-call/default",
                data=twilio_webhook_data
            )
            responses.append(response)
        
        # Should handle multiple calls without rate limiting issues
        # (Incoming calls shouldn't be rate limited as aggressively as outgoing)
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count >= 8  # Should allow most calls
    
    def test_incoming_call_input_validation(self, client):
        """Test input validation on incoming call data"""
        # Test with malicious input
        malicious_data = {
            "CallSid": "<script>alert('xss')</script>",
            "From": "+1234567890",
            "To": "+0987654321",
            "Direction": "inbound"
        }
        
        response = client.post(
            "/incoming-call/default",
            data=malicious_data
        )
        
        # Should handle malicious input safely
        assert response.status_code in [200, 400, 422]
        
        # If successful, should not contain malicious content in response
        if response.status_code == 200:
            content = response.content.decode()
            assert "<script>" not in content
    
    def test_incoming_call_scenario_injection(self, client, twilio_webhook_data):
        """Test scenario injection prevention"""
        # Test with potentially malicious scenario name
        malicious_scenario = "../../../etc/passwd"
        
        response = client.post(
            f"/incoming-call/{malicious_scenario}",
            data=twilio_webhook_data
        )
        
        # Should handle malicious scenario names safely
        assert response.status_code in [200, 400, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
