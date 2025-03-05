import os
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

# Load from both .env and dev.env
env_path = Path('.') / 'dev.env'
load_dotenv(env_path)
load_dotenv()  # This will load .env as fallback

# API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Twilio Voice Intelligence configuration
TWILIO_VOICE_INTELLIGENCE_SID = os.getenv("TWILIO_VOICE_INTELLIGENCE_SID")
USE_TWILIO_VOICE_INTELLIGENCE = os.getenv(
    "USE_TWILIO_VOICE_INTELLIGENCE", "false").lower() == "true"
ENABLE_PII_REDACTION = os.getenv(
    "ENABLE_PII_REDACTION", "true").lower() == "true"

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")

# Server configuration
PORT = int(os.getenv("PORT", "8000"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")

# JWT Authentication
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-for-development-only")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# WebRTC Configuration
WEBRTC_ICE_SERVERS: List[Dict[str, List[str]]] = [
    {
        "urls": [
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302",
        ]
    }
]

# Add custom TURN servers if configured
TURN_SERVER = os.getenv('TURN_SERVER')
TURN_USERNAME = os.getenv('TURN_USERNAME')
TURN_CREDENTIAL = os.getenv('TURN_CREDENTIAL')

if all([TURN_SERVER, TURN_USERNAME, TURN_CREDENTIAL]):
    WEBRTC_ICE_SERVERS.append({
        "urls": [TURN_SERVER],
        "username": TURN_USERNAME,
        "credential": TURN_CREDENTIAL
    })

# Audio Configuration
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "pcm16"

# Voice settings
VOICE_ID = os.getenv("VOICE_ID", "alloy")
VOICE_MODEL = os.getenv("VOICE_MODEL", "tts-1")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Session Configuration
MAX_SESSION_DURATION = 3600  # 1 hour in seconds
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes in seconds
