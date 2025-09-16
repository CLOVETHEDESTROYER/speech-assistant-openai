import os
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

# Load .env by default
load_dotenv()

# Load dev.env only when in development mode
if os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true':
    env_path = Path('.') / 'dev.env'
    load_dotenv(env_path, override=True)

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
PORT = int(os.getenv("PORT", "5051"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://localhost:5051")

# JWT Authentication
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")
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

# Logging Configuration
# Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_MAX_SIZE_MB = int(os.getenv("LOG_MAX_SIZE_MB", "10"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
LOG_FORMAT = os.getenv(
    "LOG_FORMAT",
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Session Configuration
MAX_SESSION_DURATION = 3600  # 1 hour in seconds
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes in seconds

# Security Headers Configuration
ENABLE_SECURITY_HEADERS = os.getenv(
    "ENABLE_SECURITY_HEADERS", "true").lower() == "true"
CONTENT_SECURITY_POLICY = os.getenv(
    "CONTENT_SECURITY_POLICY",
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self' wss: https:;"
)
ENABLE_HSTS = os.getenv("ENABLE_HSTS", "true").lower() == "true"
HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", "31536000"))  # 1 year in seconds
XSS_PROTECTION = os.getenv("XSS_PROTECTION", "true").lower() == "true"
CONTENT_TYPE_OPTIONS = os.getenv(
    "CONTENT_TYPE_OPTIONS", "true").lower() == "true"
FRAME_OPTIONS = os.getenv("FRAME_OPTIONS", "DENY")
PERMISSIONS_POLICY = os.getenv(
    "PERMISSIONS_POLICY",
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(self), payment=(), usb=()"
)
REFERRER_POLICY = os.getenv(
    "REFERRER_POLICY", "strict-origin-when-cross-origin")
CACHE_CONTROL = os.getenv("CACHE_CONTROL", "no-store, max-age=0")

# CAPTCHA Configuration (Google reCAPTCHA v2)
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
CAPTCHA_ENABLED = os.getenv("CAPTCHA_ENABLED", "true").lower() == "true"

# Rate Limiting
ENABLE_RATE_LIMITING = os.getenv(
    "ENABLE_RATE_LIMITING", "true").lower() == "true"

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Validate Stripe configuration in production
if os.getenv('DEVELOPMENT_MODE', 'false').lower() != 'true':
    if not STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY environment variable must be set for production")
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET environment variable must be set for production")

# App Store (IAP) Configuration
APP_STORE_SHARED_SECRET = os.getenv("APP_STORE_SHARED_SECRET")
APP_STORE_PRODUCT_ID = os.getenv("APP_STORE_PRODUCT_ID", "com.aifriendchat.premium.weekly.v2")
APP_STORE_SUBSCRIPTION_TITLE = os.getenv("APP_STORE_SUBSCRIPTION_TITLE", "AI Friend Chat Premium Weekly")
APP_STORE_SUBSCRIPTION_DURATION = os.getenv("APP_STORE_SUBSCRIPTION_DURATION", "1 week")
APP_STORE_SUBSCRIPTION_GROUP = os.getenv("APP_STORE_SUBSCRIPTION_GROUP", "Premium Features")
