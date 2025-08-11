"""
Validation Router

This module provides comprehensive validation endpoints for input validation,
sanitization, and security checks across the application.
"""

import time
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import JSONResponse

from app.schemas import (
    PhoneNumberValidation, EmailValidation, PasswordValidation, URLValidation,
    FileValidation, InputSanitization, CAPTCHAValidation, RateLimitValidation,
    SecurityHeadersValidation, ValidationResponse, BulkValidationRequest,
    BulkValidationResponse
)
from app.auth import get_current_user
from app.models import User
from app.limiter import rate_limit
from app.captcha import verify_captcha

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/validation", tags=["validation"])


@router.post("/phone-number", response_model=ValidationResponse)
@rate_limit("10/minute")
async def validate_phone_number(
    request: Request,
    phone_data: PhoneNumberValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate phone number format and security."""
    try:
        start_time = time.time()

        # Phone number is already validated by Pydantic
        sanitized_value = phone_data.phone_number

        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            sanitized_value=sanitized_value,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Phone number validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/email", response_model=ValidationResponse)
@rate_limit("10/minute")
async def validate_email(
    request: Request,
    email_data: EmailValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate email format and security."""
    try:
        start_time = time.time()

        # Email is already validated by Pydantic
        sanitized_value = email_data.email

        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            sanitized_value=sanitized_value,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Email validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/password", response_model=ValidationResponse)
@rate_limit("5/minute")
async def validate_password(
    request: Request,
    password_data: PasswordValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate password strength and security."""
    try:
        start_time = time.time()

        # Password is already validated by Pydantic
        # Don't return the actual password in response
        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Password validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/url", response_model=ValidationResponse)
@rate_limit("20/minute")
async def validate_url(
    request: Request,
    url_data: URLValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate URL format and security."""
    try:
        start_time = time.time()

        # URL is already validated by Pydantic
        sanitized_value = url_data.url

        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            sanitized_value=sanitized_value,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"URL validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/file", response_model=ValidationResponse)
@rate_limit("20/minute")
async def validate_file(
    request: Request,
    file_data: FileValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate file metadata and security."""
    try:
        start_time = time.time()

        # File data is already validated by Pydantic
        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"File validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/sanitize", response_model=ValidationResponse)
@rate_limit("30/minute")
async def sanitize_input(
    request: Request,
    sanitize_data: InputSanitization,
    current_user: User = Depends(get_current_user)
):
    """Sanitize and validate input text."""
    try:
        start_time = time.time()

        # Text is already sanitized by Pydantic
        sanitized_value = sanitize_data.text

        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            sanitized_value=sanitized_value,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Input sanitization error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/captcha", response_model=ValidationResponse)
@rate_limit("5/minute")
async def validate_captcha(
    request: Request,
    captcha_data: CAPTCHAValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate CAPTCHA response."""
    try:
        start_time = time.time()

        # Verify CAPTCHA using the existing service
        await verify_captcha(request)

        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"CAPTCHA validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/rate-limit", response_model=ValidationResponse)
@rate_limit("10/minute")
async def validate_rate_limit(
    request: Request,
    rate_limit_data: RateLimitValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate rate limiting configuration."""
    try:
        start_time = time.time()

        # Rate limit data is already validated by Pydantic
        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Rate limit validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/security-headers", response_model=ValidationResponse)
@rate_limit("10/minute")
async def validate_security_headers(
    request: Request,
    headers_data: SecurityHeadersValidation,
    current_user: User = Depends(get_current_user)
):
    """Validate security headers configuration."""
    try:
        start_time = time.time()

        # Security headers are already validated by Pydantic
        processing_time = (time.time() - start_time) * 1000

        return ValidationResponse(
            valid=True,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Security headers validation error: {str(e)}")
        return ValidationResponse(
            valid=False,
            errors=[str(e)],
            processing_time_ms=0
        )


@router.post("/bulk", response_model=BulkValidationResponse)
@rate_limit("5/minute")
async def bulk_validate(
    request: Request,
    bulk_data: BulkValidationRequest,
    current_user: User = Depends(get_current_user)
):
    """Perform bulk validation of multiple items."""
    try:
        start_time = time.time()
        results = []
        total_valid = 0
        total_invalid = 0

        for validation_item in bulk_data.validations:
            try:
                # Basic validation - in a real implementation, you'd validate each item
                # based on its type and requirements
                if isinstance(validation_item, dict) and 'type' in validation_item:
                    # Simple type-based validation
                    if validation_item['type'] in ['phone', 'email', 'url', 'text']:
                        result = ValidationResponse(valid=True)
                        total_valid += 1
                    else:
                        result = ValidationResponse(
                            valid=False,
                            errors=[
                                f"Unknown validation type: {validation_item['type']}"]
                        )
                        total_invalid += 1
                else:
                    result = ValidationResponse(
                        valid=False,
                        errors=["Invalid validation item format"]
                    )
                    total_invalid += 1

                results.append(result)

            except Exception as e:
                result = ValidationResponse(
                    valid=False,
                    errors=[f"Validation error: {str(e)}"]
                )
                total_invalid += 1
                results.append(result)

        processing_time = (time.time() - start_time) * 1000

        return BulkValidationResponse(
            results=results,
            total_valid=total_valid,
            total_invalid=total_invalid,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Bulk validation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def validation_health_check():
    """Health check endpoint for validation services."""
    return {
        "status": "healthy",
        "service": "validation",
        "timestamp": time.time(),
        "endpoints": [
            "phone-number", "email", "password", "url", "file",
            "sanitize", "captcha", "rate-limit", "security-headers", "bulk"
        ]
    }


@router.get("/rules", response_model=Dict[str, Any])
async def get_validation_rules():
    """Get validation rules and requirements."""
    return {
        "phone_number": {
            "format": "International format (+1234567890)",
            "min_length": 10,
            "max_length": 15,
            "requirements": ["Must start with +", "Digits only"]
        },
        "email": {
            "format": "Standard email format",
            "requirements": ["Valid domain", "No disposable emails"]
        },
        "password": {
            "min_length": 8,
            "max_length": 128,
            "requirements": [
                "At least one uppercase letter",
                "At least one lowercase letter",
                "At least one digit",
                "At least one special character"
            ]
        },
        "url": {
            "format": "HTTPS required for production",
            "requirements": ["Valid URL format", "HTTPS for non-localhost"]
        },
        "file": {
            "max_size": "100MB",
            "requirements": ["Safe extensions only", "No path traversal"]
        }
    }
