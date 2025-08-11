from fastapi import FastAPI
import os
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.logging_config import configure_logging
from app.middleware.security_headers import add_security_headers
from app.limiter import limiter
from app import config

# Existing routers
from app.auth import router as auth_router
from app.routes import google_calendar
from app.routes.mobile_app import router as mobile_router
from app.routes.onboarding import router as onboarding_router

# New routers (to be created/filled next)
from app.routers import twilio_transcripts, twilio_webhooks, calls, realtime, transcription
from app.routers.validation import router as validation_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI()

    allowed_origins = [
        o.strip() for o in os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type",
                       "X-Captcha"],  # added X-Captcha
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    if config.ENABLE_SECURITY_HEADERS:
        add_security_headers(
            app,
            content_security_policy=config.CONTENT_SECURITY_POLICY,
            enable_hsts=config.ENABLE_HSTS,
            xss_protection=config.XSS_PROTECTION,
            content_type_options=config.CONTENT_TYPE_OPTIONS,
            frame_options=config.FRAME_OPTIONS,
            permissions_policy=config.PERMISSIONS_POLICY,
            referrer_policy=config.REFERRER_POLICY,
            cache_control=config.CACHE_CONTROL,
        )

    # Include routers
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(google_calendar.router, tags=["google-calendar"])
    app.include_router(mobile_router, tags=["mobile"])
    app.include_router(onboarding_router, tags=["onboarding"])
    app.include_router(twilio_transcripts.router, tags=["twilio"])
    app.include_router(twilio_webhooks.router, tags=["twilio"])
    app.include_router(calls.router, tags=["calls"])
    app.include_router(realtime.router, tags=["realtime"])
    app.include_router(transcription.router, tags=["transcription"])
    app.include_router(validation_router, tags=["validation"])

    return app
