"""
Twilio Webhook Signature Validation Utility

This module provides centralized validation for Twilio webhook signatures
to ensure security across all webhook endpoints.
"""

import os
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator
from app import config

logger = logging.getLogger(__name__)
IS_DEV = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"


class TwilioWebhookValidator:
    """
    Centralized Twilio webhook signature validator.

    This class provides methods to validate Twilio webhook signatures
    for different types of webhook data (form data, JSON, etc.).
    """

    def __init__(self):
        """Initialize the validator with Twilio auth token."""
        self.auth_token = config.TWILIO_AUTH_TOKEN
        self.validator = RequestValidator(
            self.auth_token) if self.auth_token else None

    async def validate_webhook(
        self,
        request: Request,
        webhook_type: str = "form",
        raise_on_failure: bool = True
    ) -> bool:
        """
        Validate Twilio webhook signature.

        Args:
            request: FastAPI request object
            webhook_type: Type of webhook data ("form", "json", "raw")
            raise_on_failure: Whether to raise HTTPException on validation failure

        Returns:
            True if validation successful, False otherwise

        Raises:
            HTTPException: If validation fails and raise_on_failure is True
        """
        if not self.auth_token:
            if IS_DEV:
                logger.warning(
                    "TWILIO_AUTH_TOKEN not set; skipping validation in development")
                return True
            if raise_on_failure:
                raise HTTPException(
                    status_code=500, detail="Twilio signature validation not configured")
            return False

        signature = request.headers.get("X-Twilio-Signature", "")
        if not signature:
            if raise_on_failure:
                raise HTTPException(
                    status_code=401, detail="Missing Twilio signature header")
            return False

        validator = RequestValidator(self.auth_token)
        request_url = str(request.url)

        try:
            if webhook_type == "form":
                form = await request.form()
                params = dict(form)
                ok = validator.validate(request_url, params, signature)
            elif webhook_type == "json":
                body = await request.body()
                ok = validator.validate(
                    request_url, body.decode() if body else "", signature)
            elif webhook_type == "raw":
                body = await request.body()
                ok = validator.validate(
                    request_url, body.decode() if body else "", signature)
            else:
                logger.error(f"Unknown webhook type: {webhook_type}")
                ok = False

            if not ok and raise_on_failure:
                raise HTTPException(
                    status_code=401, detail="Invalid Twilio signature")

            return ok
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error validating Twilio webhook: {str(e)}")
            if raise_on_failure:
                raise HTTPException(
                    status_code=500, detail="Webhook validation error")
            return False

    def _validate_form_webhook(
        self,
        request: Request,
        request_url: str,
        signature: str,
        raise_on_failure: bool
    ) -> bool:
        """Validate form-based webhook."""
        try:
            # Get form data for validation
            form_data = request.form()
            params = dict(form_data)

            if not self.validator.validate(request_url, params, signature):
                logger.warning("Invalid Twilio signature on form webhook")
                if raise_on_failure:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid Twilio signature"
                    )
                return False
            return True

        except Exception as e:
            logger.error(f"Error validating form webhook: {str(e)}")
            if raise_on_failure:
                raise HTTPException(
                    status_code=500,
                    detail="Form webhook validation error"
                )
            return False

    def _validate_json_webhook(
        self,
        request: Request,
        request_url: str,
        signature: str,
        raise_on_failure: bool
    ) -> bool:
        """Validate JSON-based webhook."""
        try:
            # Get raw body for JSON validation
            body = request.body()
            body_str = body.decode() if body else ""

            if not self.validator.validate(request_url, body_str, signature):
                logger.warning("Invalid Twilio signature on JSON webhook")
                if raise_on_failure:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid Twilio signature"
                    )
                return False
            return True

        except Exception as e:
            logger.error(f"Error validating JSON webhook: {str(e)}")
            if raise_on_failure:
                raise HTTPException(
                    status_code=500,
                    detail="JSON webhook validation error"
                )
            return False

    def _validate_raw_webhook(
        self,
        request: Request,
        request_url: str,
        signature: str,
        raise_on_failure: bool
    ) -> bool:
        """Validate raw body webhook."""
        try:
            # Get raw body for validation
            body = request.body()
            body_str = body.decode() if body else ""

            if not self.validator.validate(request_url, body_str, signature):
                logger.warning("Invalid Twilio signature on raw webhook")
                if raise_on_failure:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid Twilio signature"
                    )
                return False
            return True

        except Exception as e:
            logger.error(f"Error validating raw webhook: {str(e)}")
            if raise_on_failure:
                raise HTTPException(
                    status_code=500,
                    detail="Raw webhook validation error"
                )
            return False


# Global validator instance
twilio_validator = TwilioWebhookValidator()


def validate_twilio_webhook(
    request: Request,
    webhook_type: str = "form",
    raise_on_failure: bool = True
) -> bool:
    """
    Convenience function to validate Twilio webhooks.

    Args:
        request: FastAPI request object
        webhook_type: Type of webhook data ("form", "json", "raw")
        raise_on_failure: Whether to raise HTTPException on validation failure

    Returns:
        True if validation successful, False otherwise
    """
    return twilio_validator.validate_webhook(request, webhook_type, raise_on_failure)


def require_twilio_signature(webhook_type: str = "form"):
    """
    Dependency decorator for requiring Twilio signature validation.

    Args:
        webhook_type: Type of webhook data to validate

    Returns:
        Dependency function that validates Twilio signatures
    """
    def validate_signature(request: Request):
        return validate_twilio_webhook(request, webhook_type, raise_on_failure=True)

    return validate_signature
