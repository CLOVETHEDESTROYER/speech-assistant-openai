import os
import requests
from fastapi import HTTPException, Form, Depends, Request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")

if not RECAPTCHA_SECRET_KEY:
    import logging
    logging.warning(
        "RECAPTCHA_SECRET_KEY not set in environment variables. CAPTCHA validation will not work correctly.")


async def verify_captcha(captcha_response: str = Form(None), request: Request = None):
    """
    Verify Google reCAPTCHA v2.

    This function should be used as a dependency in protected routes:

    @app.post("/protected-route")
    def protected_route(captcha: bool = Depends(verify_captcha)):
        # Your code here

    Args:
        request: The FastAPI request object

    Returns:
        True if verification successful

    Raises:
        HTTPException if verification fails
    """
    # Skip verification if RECAPTCHA_SECRET_KEY is not set (for development/testing)
    if not RECAPTCHA_SECRET_KEY:
        return True

    # Support fallback to query parameter if not provided as form field
    if not captcha_response and request is not None:
        captcha_response = request.query_params.get("captcha_response")

    if not captcha_response:
        raise HTTPException(
            status_code=400, detail="CAPTCHA verification required")

    # Prepare verification data
    payload = {
        'secret': RECAPTCHA_SECRET_KEY,
        'response': captcha_response,
        'remoteip': request.client.host if request else None
    }

    # Send verification request to Google
    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data=payload
        )
        result = response.json()

        if not result.get("success", False):
            raise HTTPException(
                status_code=400, detail="CAPTCHA verification failed")

        return True
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"CAPTCHA verification error: {str(e)}")


def get_recaptcha_site_key():
    """
    Get the reCAPTCHA site key for frontend use.
    """
    return RECAPTCHA_SITE_KEY
