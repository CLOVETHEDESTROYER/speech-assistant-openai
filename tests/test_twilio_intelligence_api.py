import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.db import get_db
from twilio.base.exceptions import TwilioException

client = TestClient(app)


class TestTwilioIntelligenceTranscripts:
    """Test suite for Twilio Intelligence Transcript endpoints."""
    
    def setup_method(self):
        """Set up test data and mocks."""
        self.test_transcript_sid = "GT1234567890abcdef1234567890abcdef"
        self.test_recording_sid = "RE1234567890abcdef1234567890abcdef"
        self.test_user_id = 1
        
        # Mock transcript data
        self.mock_transcript = Mock()
        self.mock_transcript.sid = self.test_transcript_sid
        self.mock_transcript.status = "completed"
        self.mock_transcript.date_created = "2024-01-01T00:00:00Z"
        self.mock_transcript.date_updated = "2024-01-01T00:01:00Z"
        self.mock_transcript.duration = 120
        self.mock_transcript.language_code = "en-US"
        
        # Mock sentence data
        self.mock_sentence = Mock()
        self.mock_sentence.transcript = "Hello, this is a test transcript."
        self.mock_sentence.media_channel = 0
        self.mock_sentence.start_time = 0.0
        self.mock_sentence.end_time = 2.5
        self.mock_sentence.confidence = 0.95
        
        self.mock_sentences = [self.mock_sentence]
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_get_twilio_transcript_success(self, mock_get_client):
        """Test successful transcript retrieval."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.return_value.fetch.return_value = self.mock_transcript
        mock_client.intelligence.v2.transcripts.return_value.sentences.list.return_value = self.mock_sentences
        
        # Make request
        response = client.get(f"/twilio-transcripts/{self.test_transcript_sid}")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["sid"] == self.test_transcript_sid
        assert data["status"] == "completed"
        assert len(data["sentences"]) == 1
        assert data["sentences"][0]["text"] == "Hello, this is a test transcript."
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_get_twilio_transcript_not_found(self, mock_get_client):
        """Test transcript not found error."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.return_value.fetch.side_effect = TwilioException("Not found")
        
        # Make request
        response = client.get(f"/twilio-transcripts/{self.test_transcript_sid}")
        
        # Assertions
        assert response.status_code == 500
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_list_twilio_transcripts_success(self, mock_get_client):
        """Test successful transcript listing."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.list.return_value = [self.mock_transcript]
        
        # Make request
        response = client.get("/twilio-transcripts?page_size=10&status=completed")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "transcripts" in data
        assert len(data["transcripts"]) == 1
        assert data["transcripts"][0]["sid"] == self.test_transcript_sid
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_get_transcript_by_recording_success(self, mock_get_client):
        """Test successful transcript retrieval by recording."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.list.return_value = [self.mock_transcript]
        
        # Make request
        response = client.get(f"/twilio-transcripts/recording/{self.test_recording_sid}")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["transcript_sid"] == self.test_transcript_sid
        assert data["status"] == "completed"
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_get_transcript_by_recording_not_found(self, mock_get_client):
        """Test transcript not found by recording."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.list.return_value = []
        
        # Make request
        response = client.get(f"/twilio-transcripts/recording/{self.test_recording_sid}")
        
        # Assertions
        assert response.status_code == 404
        assert "Transcript not found" in response.json()["detail"]
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_create_transcript_with_media_url_success(self, mock_get_client):
        """Test successful transcript creation with media URL."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.create.return_value = self.mock_transcript
        
        # Test data
        media_url = "https://example.com/audio.wav"
        
        # Make request
        response = client.post(
            "/twilio-transcripts/create-with-media-url",
            json={
                "media_url": media_url,
                "language_code": "en-US",
                "redaction": True
            }
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["transcript_sid"] == self.test_transcript_sid
    
    @patch('app.routers.twilio_transcripts.get_twilio_client')
    def test_create_transcript_with_participants_success(self, mock_get_client):
        """Test successful transcript creation with participants."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.transcripts.create.return_value = self.mock_transcript
        
        # Test data
        participants = [
            {"channel_participant": "agent", "role": "agent"},
            {"channel_participant": "customer", "role": "customer"}
        ]
        
        # Make request
        response = client.post(
            "/twilio-transcripts/create-with-participants",
            json={
                "recording_sid": self.test_recording_sid,
                "participants": participants,
                "language_code": "en-US",
                "redaction": True
            }
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["transcript_sid"] == self.test_transcript_sid
        assert data["participants_count"] == 2
    
    def test_create_transcript_with_participants_invalid_recording_sid(self):
        """Test transcript creation with invalid recording SID."""
        # Test data
        participants = [{"channel_participant": "agent", "role": "agent"}]
        
        # Make request
        response = client.post(
            "/twilio-transcripts/create-with-participants",
            json={
                "recording_sid": "invalid_sid",
                "participants": participants
            }
        )
        
        # Assertions
        assert response.status_code == 400
        assert "Invalid recording_sid format" in response.json()["detail"]
    
    def test_create_transcript_with_participants_invalid_participants(self):
        """Test transcript creation with invalid participants structure."""
        # Test data
        participants = [{"channel_participant": "agent"}]  # Missing 'role'
        
        # Make request
        response = client.post(
            "/twilio-transcripts/create-with-participants",
            json={
                "recording_sid": self.test_recording_sid,
                "participants": participants
            }
        )
        
        # Assertions
        assert response.status_code == 400
        assert "must have 'channel_participant' and 'role' fields" in response.json()["detail"]


class TestTwilioIntelligenceServices:
    """Test suite for Twilio Intelligence Service endpoints."""
    
    def setup_method(self):
        """Set up test data and mocks."""
        self.test_service_sid = "IS1234567890abcdef1234567890abcdef"
        self.test_operator_sid = "LY1234567890abcdef1234567890abcdef"
        
        # Mock service data
        self.mock_service = Mock()
        self.mock_service.sid = self.test_service_sid
        self.mock_service.friendly_name = "Test Intelligence Service"
        self.mock_service.auto_transcribe = True
        self.mock_service.auto_redaction = True
        self.mock_service.data_logging = True
        self.mock_service.webhook_url = "https://example.com/webhook"
        self.mock_service.webhook_http_method = "POST"
        self.mock_service.date_created = "2024-01-01T00:00:00Z"
        self.mock_service.date_updated = "2024-01-01T00:01:00Z"
        
        # Mock operator data
        self.mock_operator = Mock()
        self.mock_operator.sid = self.test_operator_sid
        self.mock_operator.friendly_name = "Sentiment Analysis"
        self.mock_operator.description = "Analyzes sentiment in conversations"
        self.mock_operator.operator_type = "sentiment"
        self.mock_operator.config = {}
        self.mock_operator.date_created = "2024-01-01T00:00:00Z"
        self.mock_operator.date_updated = "2024-01-01T00:01:00Z"
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_list_intelligence_services_success(self, mock_get_client):
        """Test successful intelligence services listing."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.services.list.return_value = [self.mock_service]
        
        # Make request
        response = client.get("/intelligence-services")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert len(data["services"]) == 1
        assert data["services"][0]["sid"] == self.test_service_sid
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_get_intelligence_service_success(self, mock_get_client):
        """Test successful intelligence service retrieval."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.services.return_value.fetch.return_value = self.mock_service
        
        # Make request
        response = client.get(f"/intelligence-services/{self.test_service_sid}")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["sid"] == self.test_service_sid
        assert data["friendly_name"] == "Test Intelligence Service"
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_create_intelligence_service_success(self, mock_get_client):
        """Test successful intelligence service creation."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.services.create.return_value = self.mock_service
        
        # Test data
        service_data = {
            "friendly_name": "Test Service",
            "auto_transcribe": True,
            "auto_redaction": True,
            "data_logging": True
        }
        
        # Make request
        response = client.post("/intelligence-services", json=service_data)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["service_sid"] == self.test_service_sid
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_update_intelligence_service_success(self, mock_get_client):
        """Test successful intelligence service update."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.services.return_value.update.return_value = self.mock_service
        
        # Test data
        update_data = {
            "friendly_name": "Updated Service Name",
            "auto_transcribe": False
        }
        
        # Make request
        response = client.put(f"/intelligence-services/{self.test_service_sid}", json=update_data)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["service_sid"] == self.test_service_sid
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_delete_intelligence_service_success(self, mock_get_client):
        """Test successful intelligence service deletion."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.services.return_value.delete.return_value = None
        
        # Make request
        response = client.delete(f"/intelligence-services/{self.test_service_sid}")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert f"Service {self.test_service_sid} deleted" in data["message"]
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_list_language_operators_success(self, mock_get_client):
        """Test successful language operators listing."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.intelligence.v2.operators.list.return_value = [self.mock_operator]
        
        # Make request
        response = client.get("/intelligence-operators")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "operators" in data
        assert len(data["operators"]) == 1
        assert data["operators"][0]["sid"] == self.test_operator_sid
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_attach_operator_to_service_success(self, mock_get_client):
        """Test successful operator attachment to service."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock service with existing operators
        mock_service = Mock()
        mock_service.read_only_attached_operator_sids = ["existing_operator"]
        mock_client.intelligence.v2.services.return_value.fetch.return_value = mock_service
        mock_client.intelligence.v2.services.return_value.update.return_value = mock_service
        
        # Make request
        response = client.post(
            f"/intelligence-services/{self.test_service_sid}/attach-operator",
            json={"operator_sid": self.test_operator_sid}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["operator_sid"] == self.test_operator_sid
    
    @patch('app.routers.twilio_intelligence_services.get_twilio_client')
    def test_detach_operator_from_service_success(self, mock_get_client):
        """Test successful operator detachment from service."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock service with existing operators
        mock_service = Mock()
        mock_service.read_only_attached_operator_sids = [self.test_operator_sid, "other_operator"]
        mock_client.intelligence.v2.services.return_value.fetch.return_value = mock_service
        mock_client.intelligence.v2.services.return_value.update.return_value = mock_service
        
        # Make request
        response = client.delete(
            f"/intelligence-services/{self.test_service_sid}/detach-operator/{self.test_operator_sid}"
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["operator_sid"] == self.test_operator_sid


class TestTwilioIntelligenceWebhooks:
    """Test suite for Twilio Intelligence webhook endpoints."""
    
    def setup_method(self):
        """Set up test data and mocks."""
        self.test_transcript_sid = "GT1234567890abcdef1234567890abcdef"
        self.test_call_sid = "CA1234567890abcdef1234567890abcdef"
        self.test_recording_sid = "RE1234567890abcdef1234567890abcdef"
    
    @patch('app.routers.twilio_webhooks.get_twilio_client')
    def test_transcript_webhook_success(self, mock_get_client):
        """Test successful transcript webhook processing."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock transcript data
        mock_transcript = Mock()
        mock_transcript.sid = self.test_transcript_sid
        mock_transcript.status = "completed"
        mock_client.intelligence.v2.transcripts.return_value.fetch.return_value = mock_transcript
        
        # Mock sentence data
        mock_sentence = Mock()
        mock_sentence.text = "Hello, this is a test."
        mock_sentence.start_time = 0.0
        mock_client.intelligence.v2.transcripts.return_value.sentences.list.return_value = [mock_sentence]
        
        # Test webhook payload
        webhook_payload = {
            "transcript_sid": self.test_transcript_sid,
            "status": "completed",
            "event_type": "voice_intelligence_transcript_available"
        }
        
        # Make request
        response = client.post("/twilio-transcripts/webhook-callback", json=webhook_payload)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_transcript_webhook_missing_sid(self):
        """Test transcript webhook with missing transcript SID."""
        # Test webhook payload
        webhook_payload = {
            "status": "completed",
            "event_type": "voice_intelligence_transcript_available"
        }
        
        # Make request
        response = client.post("/twilio-transcripts/webhook-callback", json=webhook_payload)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "No transcript SID provided" in data["message"]


if __name__ == "__main__":
    pytest.main([__file__])
