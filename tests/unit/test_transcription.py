import pytest
from app.models import TranscriptRecord, Conversation
from datetime import datetime
import json
import base64


@pytest.mark.asyncio
async def test_transcribe_base64_audio(client, test_user, auth_headers, mock_openai):
    """Test transcribing base64 audio."""
    audio_data = base64.b64encode(b"test audio data").decode()

    response = client.post(
        "/transcribe",
        json={"audio_data": audio_data},
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Test transcription"
    mock_openai.return_value.audio.transcriptions.create.assert_called_once()


@pytest.mark.asyncio
async def test_get_twilio_transcript(client, test_user, auth_headers, mock_twilio, db_session):
    """Test getting a Twilio transcript."""
    # Create a test transcript record
    transcript = TranscriptRecord(
        transcript_sid="test_transcript_sid",
        recording_sid="test_recording_sid",
        status="completed",
        content="Test transcript content",
        user_id=test_user.id
    )
    db_session.add(transcript)
    db_session.commit()

    response = client.get(
        "/twilio-transcripts/test_transcript_sid",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Test transcript content"


@pytest.mark.asyncio
async def test_list_stored_transcripts(client, test_user, auth_headers, db_session):
    """Test listing stored transcripts."""
    # Create test transcripts
    for i in range(3):
        transcript = TranscriptRecord(
            transcript_sid=f"test_transcript_{i}",
            recording_sid=f"test_recording_{i}",
            status="completed",
            content=f"Test content {i}",
            user_id=test_user.id
        )
        db_session.add(transcript)
    db_session.commit()

    response = client.get(
        "/stored-transcripts/",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(t["status"] == "completed" for t in data)


@pytest.mark.asyncio
async def test_webhook_callback_transcript_completed(client, test_user, db_session, mock_twilio):
    """Test handling a completed transcript webhook."""
    # Create a test conversation
    conversation = Conversation(
        call_sid="test_call_sid",
        recording_sid="test_recording_sid",
        direction="outbound",
        scenario="test_scenario",
        transcript=None,
        user_id=test_user.id
    )
    db_session.add(conversation)
    db_session.commit()

    # Mock Twilio transcript response
    mock_transcript = type(
        "TranscriptResponse",
        (),
        {
            "data": "Test transcript content",
            "status": "completed",
            "date_created": datetime.utcnow(),
            "date_updated": datetime.utcnow(),
            "duration": 60,
            "language_code": "en-US",
            "recording_sid": "test_recording_sid",
            "sid": "test_transcript_sid"
        }
    )
    mock_sentence = type(
        "SentenceResponse",
        (),
        {
            "transcript": "Test sentence",
            "media_channel": 0,
            "start_time": 0,
            "end_time": 10,
            "confidence": 0.9
        }
    )

    # Set up the mock chain
    mock_transcripts = mock_twilio.return_value.intelligence.v2.transcripts
    mock_transcripts.return_value.fetch.return_value = mock_transcript
    mock_transcripts.return_value.sentences.list.return_value = [mock_sentence]

    webhook_data = {
        "transcript_sid": "test_transcript_sid",
        "status": "completed",
        "event_type": "voice_intelligence_transcript_available"
    }

    response = client.post(
        "/twilio-transcripts/webhook-callback",
        json=webhook_data
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Verify conversation was updated
    updated_conversation = db_session.query(Conversation).filter(
        Conversation.recording_sid == "test_recording_sid"
    ).first()
    assert updated_conversation is not None
    assert "Test sentence" in updated_conversation.transcript


@pytest.mark.asyncio
async def test_create_transcript_with_media_url(client, test_user, auth_headers, mock_twilio):
    """Test creating a transcript with a media URL."""
    transcript_data = {
        "media_url": "https://example.com/audio.mp3",
        "recording_sid": "test_recording_sid"
    }

    response = client.post(
        "/twilio-transcripts/create-with-media-url",
        json=transcript_data,
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "transcript_sid" in data


@pytest.mark.asyncio
async def test_delete_transcript(client, test_user, auth_headers, db_session):
    """Test deleting a transcript."""
    # Create a test transcript
    transcript = TranscriptRecord(
        transcript_sid="test_transcript_sid",
        recording_sid="test_recording_sid",
        status="completed",
        content="Test content",
        user_id=test_user.id
    )
    db_session.add(transcript)
    db_session.commit()

    response = client.delete(
        "/twilio-transcripts/test_transcript_sid",
        headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Transcript deleted"

    # Verify transcript was deleted
    deleted_transcript = db_session.query(TranscriptRecord).first()
    assert deleted_transcript is None
