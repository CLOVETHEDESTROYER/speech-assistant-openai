# schemas.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

    class Config:
        from_attributes = True


class TokenData(BaseModel):
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

    class Config:
        from_attributes = True


class RealtimeSessionCreate(BaseModel):
    scenario: str
    scenario_id: Optional[str] = None  # For backward compatibility
    user_id: Optional[int] = None


class RealtimeSessionResponse(BaseModel):
    session_id: str
    ice_servers: list
    created_at: str


class SignalingMessage(BaseModel):
    type: str
    sdp: Optional[str] = None
    candidate: Optional[dict] = None
    session_id: str


class SignalingResponse(BaseModel):
    type: str
    sdp: Optional[str] = None
    ice_servers: Optional[list] = None
    error: Optional[str] = None


class ConversationResponse(BaseModel):
    id: int
    call_sid: str
    phone_number: Optional[str]
    direction: str
    scenario: str
    transcript: Optional[str]
    created_at: str
    user_id: Optional[int]

    class Config:
        from_attributes = True


class CallScheduleCreate(BaseModel):
    phone_number: str
    scheduled_time: datetime
    scenario: str

    class Config:
        from_attributes = True  # Updated from orm_mode in newer Pydantic versions


# Validation Schemas
class PhoneNumberValidation(BaseModel):
    """Phone number validation schema."""
    phone_number: str = Field(..., description="Phone number to validate")
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number format."""
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', v)
        
        # Must start with + and have 10-15 digits
        if not re.match(r'^\+\d{10,15}$', cleaned):
            raise ValueError('Phone number must be in international format (+1234567890)')
        
        return cleaned


class EmailValidation(BaseModel):
    """Email validation schema."""
    email: EmailStr = Field(..., description="Email address to validate")
    
    @validator('email')
    def validate_email_domain(cls, v):
        """Additional email domain validation."""
        # Check for common disposable email domains
        disposable_domains = {
            'tempmail.org', '10minutemail.com', 'guerrillamail.com',
            'mailinator.com', 'yopmail.com', 'throwaway.email'
        }
        
        domain = v.split('@')[1].lower()
        if domain in disposable_domains:
            raise ValueError('Disposable email addresses are not allowed')
        
        return v


class PasswordValidation(BaseModel):
    """Password validation schema."""
    password: str = Field(..., min_length=8, max_length=128, description="Password to validate")
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password strength requirements."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        return v


class URLValidation(BaseModel):
    """URL validation schema."""
    url: str = Field(..., description="URL to validate")
    
    @validator('url')
    def validate_url_format(cls, v):
        """Validate URL format and security."""
        # Basic URL format validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError('Invalid URL format')
        
        # Security checks
        if v.startswith('http://') and not v.startswith('http://localhost'):
            raise ValueError('HTTPS is required for production URLs')
        
        return v


class FileValidation(BaseModel):
    """File validation schema."""
    filename: str = Field(..., description="Filename to validate")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    mime_type: str = Field(..., description="MIME type to validate")
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename security."""
        # Check for path traversal attempts
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid filename: path traversal not allowed')
        
        # Check for dangerous extensions
        dangerous_extensions = {'.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js'}
        if any(v.lower().endswith(ext) for ext in dangerous_extensions):
            raise ValueError('Dangerous file type not allowed')
        
        # Check length
        if len(v) > 255:
            raise ValueError('Filename too long')
        
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v):
        """Validate file size limits."""
        max_size = 100 * 1024 * 1024  # 100MB
        if v > max_size:
            raise ValueError(f'File size exceeds maximum limit of {max_size} bytes')
        return v
    
    @validator('mime_type')
    def validate_mime_type(cls, v):
        """Validate MIME type security."""
        allowed_types = {
            'text/plain', 'text/csv', 'application/json', 'application/xml',
            'image/jpeg', 'image/png', 'image/gif', 'application/pdf'
        }
        if v not in allowed_types:
            raise ValueError(f'MIME type {v} not allowed')
        return v


class InputSanitization(BaseModel):
    """Input sanitization schema."""
    text: str = Field(..., description="Text to sanitize")
    max_length: int = Field(1000, ge=1, le=10000, description="Maximum text length")
    allow_html: bool = Field(False, description="Whether to allow HTML tags")
    
    @validator('text')
    def sanitize_text(cls, v, values):
        """Sanitize input text."""
        # Check length
        if len(v) > values.get('max_length', 1000):
            raise ValueError(f'Text exceeds maximum length of {values.get("max_length", 1000)} characters')
        
        # Remove HTML if not allowed
        if not values.get('allow_html', False):
            import html
            v = html.escape(v)
        
        # Remove null bytes and control characters
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\r\t')
        
        return v


class CAPTCHAValidation(BaseModel):
    """CAPTCHA validation schema."""
    captcha_response: str = Field(..., description="CAPTCHA response token")
    user_ip: Optional[str] = Field(None, description="User IP address for verification")
    
    @validator('captcha_response')
    def validate_captcha_response(cls, v):
        """Validate CAPTCHA response format."""
        if not v or len(v) < 10:
            raise ValueError('Invalid CAPTCHA response token')
        
        # Check for common attack patterns
        if any(pattern in v.lower() for pattern in ['script', 'javascript', 'onload', 'onerror']):
            raise ValueError('CAPTCHA response contains potentially malicious content')
        
        return v


class RateLimitValidation(BaseModel):
    """Rate limiting validation schema."""
    endpoint: str = Field(..., description="Endpoint being rate limited")
    user_id: Optional[int] = Field(None, description="User ID for rate limiting")
    ip_address: str = Field(..., description="IP address for rate limiting")
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        """Validate endpoint format."""
        if not v.startswith('/'):
            raise ValueError('Endpoint must start with /')
        if '..' in v or '//' in v:
            raise ValueError('Invalid endpoint path')
        return v


class SecurityHeadersValidation(BaseModel):
    """Security headers validation schema."""
    content_security_policy: Optional[str] = Field(None, description="Content Security Policy")
    x_frame_options: Optional[str] = Field(None, description="X-Frame-Options header")
    x_content_type_options: Optional[str] = Field(None, description="X-Content-Type-Options header")
    x_xss_protection: Optional[str] = Field(None, description="X-XSS-Protection header")
    strict_transport_security: Optional[str] = Field(None, description="Strict-Transport-Security header")
    
    @validator('content_security_policy')
    def validate_csp(cls, v):
        """Validate Content Security Policy."""
        if v and 'unsafe-inline' in v and 'unsafe-eval' in v:
            raise ValueError('CSP should not contain both unsafe-inline and unsafe-eval')
        return v
    
    @validator('x_frame_options')
    def validate_frame_options(cls, v):
        """Validate X-Frame-Options."""
        allowed_values = {'DENY', 'SAMEORIGIN', 'ALLOW-FROM'}
        if v and v not in allowed_values:
            raise ValueError(f'X-Frame-Options must be one of: {allowed_values}')
        return v


class ValidationResponse(BaseModel):
    """Standard validation response schema."""
    valid: bool = Field(..., description="Whether validation passed")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    sanitized_value: Optional[str] = Field(None, description="Sanitized value if applicable")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Validation timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BulkValidationRequest(BaseModel):
    """Bulk validation request schema."""
    validations: List[Dict[str, Any]] = Field(..., description="List of validation requests")
    max_items: int = Field(100, ge=1, le=1000, description="Maximum number of items to validate")
    
    @validator('validations')
    def validate_request_count(cls, v, values):
        """Validate number of validation requests."""
        max_items = values.get('max_items', 100)
        if len(v) > max_items:
            raise ValueError(f'Too many validation requests. Maximum allowed: {max_items}')
        return v


class BulkValidationResponse(BaseModel):
    """Bulk validation response schema."""
    results: List[ValidationResponse] = Field(..., description="Validation results")
    total_valid: int = Field(..., description="Total number of valid items")
    total_invalid: int = Field(..., description="Total number of invalid items")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")


__all__ = [
    "UserCreate", "UserLogin", "TokenSchema", "TokenData", "RealtimeSessionCreate",
    "RealtimeSessionResponse", "SignalingMessage", "SignalingResponse", "ConversationResponse",
    "CallScheduleCreate", "PhoneNumberValidation", "EmailValidation", "PasswordValidation",
    "URLValidation", "FileValidation", "InputSanitization", "CAPTCHAValidation",
    "RateLimitValidation", "SecurityHeadersValidation", "ValidationResponse",
    "BulkValidationRequest", "BulkValidationResponse"
]
