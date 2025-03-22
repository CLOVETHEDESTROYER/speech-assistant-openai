# API Rate Limiting

This document provides detailed information about the rate limiting implementation in the Speech Assistant API.

## Overview

Rate limiting is an essential security feature that helps protect our API from abuse and ensures fair usage for all users. It limits the number of requests a client can make to the API within a specific time window.

## Implementation

The Speech Assistant API uses the `slowapi` library for rate limiting, which provides:

- IP-based rate limiting by default
- Configurable limits per endpoint
- Response headers with rate limit information
- Automatic 429 responses when limits are exceeded

## Rate Limit Configuration

Rate limits are specified in the format `"X/Y"` where:

- `X` is the number of allowed requests
- `Y` is the time period (e.g., "second", "minute", "hour", "day")

Example: `"30/minute"` means 30 requests per minute are allowed.

## Protected Endpoints

The following endpoints have rate limits applied:

| Endpoint                                    | Rate Limit | Reason                                       |
| ------------------------------------------- | ---------- | -------------------------------------------- |
| `/token`                                    | 5/minute   | Prevents brute force authentication attempts |
| `/auth/register`                            | 5/minute   | Prevents automated account creation          |
| `/auth/login`                               | 5/minute   | Prevents brute force authentication attempts |
| `/auth/refresh`                             | 10/minute  | Prevents token farming                       |
| `/protected`                                | 5/minute   | Prevents excessive API usage                 |
| `/schedule-call`                            | 3/minute   | Prevents abuse of call scheduling service    |
| `/make-call/{phone}/{scenario}`             | 2/minute   | Limits outgoing calls, which cost money      |
| `/make-custom-call/{phone}/{scenario_id}`   | 2/minute   | Limits outgoing calls, which cost money      |
| `/realtime/session`                         | 5/minute   | Prevents excessive resource consumption      |
| `/realtime/custom-scenario`                 | 10/minute  | Prevents database spam of custom scenarios   |
| `/twilio-transcripts/create-with-media-url` | 10/minute  | Limits expensive transcription API calls     |

## Response Headers

When you make a request to a rate-limited endpoint, the following headers are included in the response:

- `X-RateLimit-Limit`: Maximum number of requests allowed in the current time window
- `X-RateLimit-Remaining`: Number of requests remaining in the current time window
- `X-RateLimit-Reset`: Time in seconds until the rate limit resets

Example:

```
X-RateLimit-Limit: 3
X-RateLimit-Remaining: 2
X-RateLimit-Reset: 58
```

## Rate Limit Exceeded Response

When a rate limit is exceeded, the API responds with:

- HTTP Status Code: `429 Too Many Requests`
- Response Body:
  ```json
  {
    "detail": "Rate limit exceeded: 30 per 1 minute"
  }
  ```

## Best Practices

To avoid hitting rate limits:

1. **Cache responses** when appropriate
2. **Implement retry logic** with exponential backoff
3. **Monitor rate limit headers** and adjust request timing
4. **Batch operations** when possible instead of making multiple requests

## Production Considerations

In production environments with multiple API instances, consider:

1. **Redis backend**: Configure slowapi with Redis to share rate limit counters across instances
2. **User-based limiting**: For authenticated endpoints, consider limiting by user ID instead of IP

## Customizing Rate Limits

If you're hosting your own instance of the API, you can customize rate limits by modifying the `@rate_limit()` decorators in the codebase.

## Rate Limit Exemptions

Administrative users and internal services can be exempted from rate limits by implementing custom key functions that return `None` for these users.

## Troubleshooting

If you're experiencing unexpected rate limiting:

1. Check if you're making requests from multiple processes or threads that share the same IP
2. Verify your application isn't making unnecessary repeated requests
3. Ensure proper handling of 429 responses with backoff and retry logic
