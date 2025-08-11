import os
import requests
from fastapi import HTTPException, Request
from dotenv import load_dotenv
from app.config import CAPTCHA_ENABLED, RECAPTCHA_SECRET_KEY, RECAPTCHA_SITE_KEY

# Load environment variables
load_dotenv()

# Environment variables - now imported from config
# RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
# RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")

if not RECAPTCHA_SECRET_KEY or RECAPTCHA_SECRET_KEY.strip() == "":
    import logging
    logging.warning(
        "RECAPTCHA_SECRET_KEY not set in environment variables. CAPTCHA validation will not work correctly.")

if not CAPTCHA_ENABLED:
    import logging
    logging.info(
        "CAPTCHA is disabled via configuration. All CAPTCHA checks will be bypassed.")


async def verify_captcha(request: Request):
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
    # Skip verification entirely if disabled
    if not CAPTCHA_ENABLED:
        return True

    # Secret is required in production
    if not RECAPTCHA_SECRET_KEY or RECAPTCHA_SECRET_KEY.strip() == "":
        if IS_DEV:
            return True
        raise HTTPException(status_code=500, detail="CAPTCHA misconfigured")

    # Accept token from header or query string
    captcha_response = (
        request.headers.get("X-Captcha")
        or request.query_params.get("captcha_response")
    )

    if not captcha_response:
        raise HTTPException(
            status_code=400, detail="CAPTCHA verification required")

    payload = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": captcha_response,
        "remoteip": request.client.host if request else None,
    }

    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data=payload,
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
