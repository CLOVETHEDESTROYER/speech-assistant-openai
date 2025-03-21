# Speech Assistant API

A powerful API for creating and managing voice assistants powered by OpenAI's Realtime API and Twilio Voice Services.

## Overview

This application provides a complete solution for creating realistic voice assistants that can:

- Make outbound calls with AI-powered voice interaction
- Process incoming calls with natural language understanding
- Schedule calls for later execution
- Transcribe and store call recordings
- Create and manage custom conversation scenarios
- Stream real-time audio between users and OpenAI's voice models

## Features

- **Authentication**: Secure JWT-based authentication with refresh tokens and CAPTCHA protection
- **Rate Limiting**: Protection against abuse with configurable rate limits
- **Call Scheduling**: Schedule calls for future delivery
- **Voice Customization**: Multiple voice options with adjustable parameters
- **Custom Scenarios**: Create and manage personalized conversation scenarios
- **Transcription**: High-quality transcription services via Twilio Intelligence
- **Realtime Streaming**: WebRTC-based real-time audio streaming
- **Security**: CAPTCHA verification on authentication endpoints to prevent bot attacks

## Getting Started

### Prerequisites

- Python 3.8+
- OpenAI API key with access to the Realtime API
- Twilio account with Voice services
- PostgreSQL (optional, SQLite available for development)

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/speech-assistant-api.git
   cd speech-assistant-api
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:

   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

5. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

## API Documentation

### Authentication

| Endpoint            | Method | Description               | Rate Limit | CAPTCHA |
| ------------------- | ------ | ------------------------- | ---------- | ------- |
| `/auth/register`    | POST   | Register a new user       | None       | Yes     |
| `/auth/login`       | POST   | Login and get tokens      | None       | Yes     |
| `/auth/refresh`     | POST   | Refresh access token      | None       | No      |
| `/token`            | POST   | Get access token (OAuth2) | 5/minute   | No      |
| `/auth/captcha-key` | GET    | Get reCAPTCHA site key    | None       | No      |

### Call Management

| Endpoint                        | Method | Description            | Rate Limit |
| ------------------------------- | ------ | ---------------------- | ---------- |
| `/schedule-call`                | POST   | Schedule a future call | 3/minute   |
| `/make-call/{phone}/{scenario}` | GET    | Make an immediate call | 2/minute   |

### Real-time Sessions

| Endpoint            | Method | Description                | Rate Limit |
| ------------------- | ------ | -------------------------- | ---------- |
| `/realtime/session` | POST   | Create a real-time session | 5/minute   |
| `/realtime/signal`  | POST   | Exchange WebRTC signaling  | None       |

### Custom Scenarios

| Endpoint                         | Method | Description               | Rate Limit |
| -------------------------------- | ------ | ------------------------- | ---------- |
| `/realtime/custom-scenario`      | POST   | Create a custom scenario  | 10/minute  |
| `/realtime/custom-scenarios`     | GET    | List all custom scenarios | None       |
| `/realtime/custom-scenario/{id}` | GET    | Get a specific scenario   | None       |
| `/realtime/custom-scenario/{id}` | PUT    | Update a scenario         | None       |
| `/realtime/custom-scenario/{id}` | DELETE | Delete a scenario         | None       |

### Transcription Services

| Endpoint                                    | Method | Description                | Rate Limit |
| ------------------------------------------- | ------ | -------------------------- | ---------- |
| `/twilio-transcripts/create-with-media-url` | POST   | Create transcript from URL | 10/minute  |
| `/twilio-transcripts/{id}`                  | GET    | Get a specific transcript  | None       |
| `/twilio-transcripts`                       | GET    | List all transcripts       | None       |
| `/twilio-transcripts/{id}`                  | DELETE | Delete a transcript        | None       |

## Rate Limiting

The API implements rate limiting to prevent abuse and ensure fair usage. Rate limits are specified as requests per time period (e.g., "30/minute").

Key endpoints are protected with the following rate limits:

- Authentication: 5 requests per minute
- User info: 20 requests per minute
- Call scheduling: 3 requests per minute
- Immediate calls: 2 requests per minute
- Real-time sessions: 5 requests per minute
- WebRTC signaling: 30 requests per minute
- Custom scenario creation: 10 requests per minute
- Custom scenario retrieval: 30 requests per minute
- Custom scenario modification: 15 requests per minute
- Transcript creation: 10 requests per minute
- Transcript retrieval: 20 requests per minute

Rate limit responses include the following headers:

- `X-RateLimit-Limit`: Maximum requests allowed in the time window
- `X-RateLimit-Remaining`: Number of requests remaining in the current window
- `X-RateLimit-Reset`: Seconds until the rate limit resets

When a rate limit is exceeded, the API responds with:

- Status code: 429 Too Many Requests
- Response body: `{"detail": "Rate limit exceeded: 10 per 1 minute"}`

## Deployment

### Docker

A Dockerfile is included for containerization:

```bash
docker build -t speech-assistant-api .
docker run -p 8000:8000 --env-file .env speech-assistant-api
```

### Production Considerations

For production deployments:

1. Configure a production-ready database (PostgreSQL recommended)
2. Set up a reverse proxy (Nginx, Traefik)
3. Enable HTTPS with proper certificates
4. Configure proper CORS settings
5. Use environment-specific settings

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- OpenAI for the powerful AI models
- Twilio for voice and transcription services
- FastAPI for the excellent API framework

## Security Features

### Rate Limiting

The API includes rate limiting to prevent abuse and ensure fair usage. Rate limits are specified as requests per time period (e.g., "30/minute").

Key endpoints are protected with the following rate limits:

- Authentication: 5 requests per minute
- User info: 20 requests per minute
- Call scheduling: 3 requests per minute
- Immediate calls: 2 requests per minute
- Real-time sessions: 5 requests per minute
- WebRTC signaling: 30 requests per minute
- Custom scenario creation: 10 requests per minute
- Custom scenario retrieval: 30 requests per minute
- Custom scenario modification: 15 requests per minute
- Transcript creation: 10 requests per minute
- Transcript retrieval: 20 requests per minute

Rate limit responses include the following headers:

- `X-RateLimit-Limit`: Maximum requests allowed in the time window
- `X-RateLimit-Remaining`: Number of requests remaining in the current window
- `X-RateLimit-Reset`: Seconds until the rate limit resets

When a rate limit is exceeded, the API responds with:

- Status code: 429 Too Many Requests
- Response body: `{"detail": "Rate limit exceeded: 10 per 1 minute"}`

### CAPTCHA Protection

The API includes CAPTCHA protection on authentication endpoints to prevent automated bot attacks:

- Google reCAPTCHA v2 integration on login and registration endpoints
- Frontend can retrieve the site key through the API
- Configurable through environment variables
- Optional during development (can be disabled)

For detailed integration instructions, see [CAPTCHA Integration Guide](docs/captcha_integration.md).
