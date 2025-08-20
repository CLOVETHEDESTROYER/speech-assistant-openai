# Mobile Custom Call Endpoint Implementation

## Overview

This document summarizes the implementation of a new mobile custom call endpoint that allows mobile app users to make calls using custom scenarios. This is a premium feature that requires a paid subscription.

## Endpoint Details

### URL

```
POST /mobile/make-custom-call
```

### Request Body

```json
{
  "phone_number": "+15551234567",
  "scenario_id": "custom_123_1234567890"
}
```

### Response

```json
{
  "call_sid": "CA1234567890abcdef",
  "status": "initiated",
  "duration_limit": 60,
  "scenario_id": "custom_123_1234567890",
  "scenario_name": "Carl from Hyper Labs AI",
  "usage_stats": {
    "calls_remaining_this_week": 25,
    "calls_remaining_this_month": 25,
    "addon_calls_remaining": 0,
    "upgrade_recommended": false
  }
}
```

## Features

### 1. Premium-Only Access

- Custom scenarios are restricted to users with active premium subscriptions
- Returns 402 Payment Required for non-premium users
- Clear upgrade messaging in error responses

### 2. Security & Validation

- User authentication required
- Custom scenario ownership validation (users can only use their own scenarios)
- Phone number validation
- Rate limiting: 2 requests per minute

### 3. Integration

- Integrates with existing Twilio infrastructure
- Uses the `/incoming-custom-call/{scenario_id}` webhook endpoint
- Tracks calls in the Conversation model
- Updates usage statistics

### 4. Development Mode Support

- Bypasses premium checks when `DEVELOPMENT_MODE=true`
- Useful for testing and development
- Sets longer duration limits (5 minutes) in dev mode

## Implementation Details

### File: `app/routes/mobile_app.py`

- New endpoint: `make_mobile_custom_call()`
- Premium subscription validation
- Custom scenario validation
- Twilio call creation
- Usage tracking integration

### Key Functions

```python
def is_development_mode():
    """Check if we're in development mode at runtime"""
    return os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'

@router.post("/make-custom-call")
@rate_limit("2/minute")
async def make_mobile_custom_call(
    request: Request,
    call_request: MobileCustomCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Make a custom call using a custom scenario - Premium feature only"""
```

## Testing

### Test Suite: `tests/unit/test_mobile_endpoints.py`

Comprehensive test coverage including:

1. **Premium Requirement Test**

   - Verifies non-premium users get 402 error
   - Tests custom scenario access control

2. **Success Test**

   - Tests successful custom call creation
   - Verifies response structure and values
   - Mocks Twilio client to avoid API calls

3. **Validation Tests**

   - Invalid scenario ID handling
   - Unauthorized scenario access
   - Phone number validation
   - Missing authentication headers

4. **Rate Limiting Test**

   - Verifies rate limiting functionality
   - Tests multiple rapid requests

5. **Development Mode Test**
   - Tests development mode behavior
   - Verifies bypass of premium checks

### Test Setup

- Creates test users with proper subscription tiers
- Sets up custom scenarios for testing
- Mocks external dependencies (Twilio)
- Handles rate limiting and authentication

## Usage Examples

### For Mobile App Developers

```javascript
// Make a custom call
const response = await fetch("/mobile/make-custom-call", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${token}`,
    "X-App-Type": "mobile",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    phone_number: "+15551234567",
    scenario_id: "custom_123_1234567890",
  }),
});

if (response.status === 200) {
  const callData = await response.json();
  console.log("Call initiated:", callData.call_sid);
} else if (response.status === 402) {
  console.log("Premium subscription required");
}
```

### For Testing

```bash
# Run all mobile custom call tests
python3 -m pytest tests/unit/test_mobile_endpoints.py::TestMobileCustomCallEndpoint -v

# Run specific test
python3 -m pytest tests/unit/test_mobile_endpoints.py::TestMobileCustomCallEndpoint::test_mobile_custom_call_premium_required -v
```

## Security Considerations

1. **Authentication Required**

   - All requests must include valid JWT token
   - Mobile app type header required

2. **Premium Access Control**

   - Custom scenarios are premium-only features
   - Subscription status validated on each request

3. **User Isolation**

   - Users can only access their own custom scenarios
   - Prevents cross-user scenario access

4. **Rate Limiting**

   - 2 requests per minute per user
   - Prevents abuse and API spam

5. **Input Validation**
   - Phone number format validation
   - Scenario ID validation
   - Request body validation

## Future Enhancements

1. **Enhanced Analytics**

   - Track custom scenario usage patterns
   - Monitor premium feature adoption

2. **Advanced Scenarios**

   - Support for multi-step scenarios
   - Dynamic scenario parameters

3. **Performance Optimization**

   - Caching for frequently used scenarios
   - Async processing for call setup

4. **Monitoring & Alerting**
   - Real-time call status monitoring
   - Error tracking and alerting

## Dependencies

- FastAPI
- SQLAlchemy
- Twilio Python SDK
- Pydantic for validation
- Rate limiting middleware

## Configuration

### Environment Variables

```bash
DEVELOPMENT_MODE=false  # Set to true to bypass premium checks
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
PUBLIC_URL=https://your-domain.com
```

## Conclusion

The mobile custom call endpoint provides a secure, premium-only way for mobile app users to access custom AI scenarios. It integrates seamlessly with the existing infrastructure while maintaining proper security controls and user isolation. The comprehensive test suite ensures reliability and helps catch regressions during development.
