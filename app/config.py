import os
from dotenv import load_dotenv
from typing import List, Dict


load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
SECRET_KEY = SECRET_KEY.encode()  # Ensure it's in bytes format
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

# Session Configuration
MAX_SESSION_DURATION = 3600  # 1 hour in seconds
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes in seconds
