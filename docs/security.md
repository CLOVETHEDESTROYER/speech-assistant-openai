# Security Considerations

This document outlines the security measures implemented in the Speech Assistant API.

## Authentication and Authorization

### JWT-Based Authentication

The API uses JSON Web Tokens (JWT) for authentication with the following features:

- Short-lived access tokens (default: 15 minutes)
- Refresh tokens for obtaining new access tokens
- Secure token storage recommendations for clients

### User Management

- Password hashing using bcrypt
- Email verification (planned)
- Account lockout after multiple failed attempts (planned)

## CAPTCHA Protection

All authentication endpoints (`/auth/register` and `/auth/login`) are protected with CAPTCHA verification:

- Using Google reCAPTCHA v2
- Prevents automated bot attacks and credential stuffing
- Configurable through environment variables:
  - `RECAPTCHA_SITE_KEY`: Public key for frontend use
  - `RECAPTCHA_SECRET_KEY`: Private key for backend verification
- Development mode available by leaving `RECAPTCHA_SECRET_KEY` empty

Implementation details:

- Frontend sends `captcha_response` parameter with form submissions
- Backend verifies the CAPTCHA token with Google's API
- Blocks requests without valid CAPTCHA tokens

For frontend integration instructions, see [CAPTCHA Integration Guide](captcha_integration.md).

## Rate Limiting

Rate limiting is implemented on sensitive endpoints to prevent abuse:

- Authentication: 5 requests per minute
- Call scheduling: 3 requests per minute
- Immediate calls: 2 requests per minute
- Real-time sessions: 5 requests per minute
- Custom scenario creation: 10 requests per minute
- Transcript creation: 10 requests per minute

For detailed rate limit configuration, see [Rate Limiting](rate_limiting.md).

## Data Protection

### Sensitive Data

- API keys and secrets are stored in environment variables, not in code
- User passwords are hashed with bcrypt before storage
- Access tokens have limited lifetimes to reduce risk if intercepted

### Call Recording and Transcripts

- Call recordings and transcripts are associated with user accounts
- API endpoints for transcripts are protected with authentication
- Data retention policies will be implemented (planned)

## API Security

### Input Validation

- All API inputs are validated using Pydantic models
- Parameter types and constraints are enforced
- Protection against injection attacks and malformed input

### CORS Configuration

- Cross-Origin Resource Sharing (CORS) headers are properly configured
- Only trusted origins are allowed to access the API
- Preflight requests are handled correctly

### Security Headers

The API implements the following security headers to protect against various attacks:

- **Content-Security-Policy (CSP)**: Restricts the sources from which resources can be loaded, preventing XSS attacks.
- **X-XSS-Protection**: Enables browser's built-in XSS filtering.
- **X-Content-Type-Options**: Prevents MIME type sniffing attacks by forcing browsers to respect the declared content type.
- **X-Frame-Options**: Prevents clickjacking attacks by controlling whether a page can be embedded in iframes.
- **Strict-Transport-Security (HSTS)**: Forces browsers to use HTTPS for all future connections to the site.
- **Permissions-Policy**: Restricts which browser features can be used by the application.
- **Referrer-Policy**: Controls how much referrer information is included with requests.
- **Cache-Control**: Prevents storing sensitive information in browser caches.

These headers are configurable via environment variables and can be enabled or disabled as needed.

For detailed security header configuration, see [Security Headers](security_headers.md).

## Recommendations for Clients

1. **Token Storage**: Store access tokens securely, preferably in HTTP-only cookies or secure local storage
2. **HTTPS**: Always use HTTPS in production environments
3. **Refresh Tokens**: Implement proper token refresh mechanisms
4. **Validation**: Validate all user inputs before sending to the API
5. **Error Handling**: Implement proper error handling for authentication failures

## Future Security Enhancements

1. Two-factor authentication (2FA)
2. Email verification for new accounts
3. Enhanced audit logging
4. Account activity monitoring
5. Data encryption at rest
6. Row-level security (RLS) for database access controls
