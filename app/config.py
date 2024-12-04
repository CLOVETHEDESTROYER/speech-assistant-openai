from dotenv import load_dotenv
import os

# Load the appropriate .env file based on environment
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
ENV_FILE = '.env.production' if ENVIRONMENT == 'production' else '.env.development'
load_dotenv(ENV_FILE)

# Common configurations
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
SECRET_KEY = SECRET_KEY.encode()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Environment-specific configurations
PUBLIC_URL = os.getenv('PUBLIC_URL')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./local.db' if ENVIRONMENT ==
                         'development' else 'sqlite:///./production.db')

print(f"Current environment: {ENVIRONMENT}")
print(f"Loading from file: {ENV_FILE}")
print(f"PUBLIC_URL loaded as: {PUBLIC_URL}")


def get_webhook_url(path: str) -> str:
    """Generate full webhook URL based on environment"""
    return f"https://{PUBLIC_URL}{path}"
