import os
from dotenv import load_dotenv


load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
SECRET_KEY = SECRET_KEY.encode()  # Ensure it's in bytes format
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
