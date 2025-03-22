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
| `/auth/register`    | POST   | Register a new user       | 5/minute   | Yes     |
| `/auth/login`       | POST   | Login and get tokens      | 5/minute   | Yes     |
| `/auth/refresh`     | POST   | Refresh access token      | 10/minute  | No      |
| `/token`            | POST   | Get access token (OAuth2) | 5/minute   | No      |
| `/auth/captcha-key` | GET    | Get reCAPTCHA site key    | None       | No      |

### Call Management

| Endpoint                         | Method | Description                    | Rate Limit |
| -------------------------------- | ------ | ------------------------------ | ---------- |
| `/schedule-call`                 | POST   | Schedule a future call         | 3/minute   |
| `/make-call/{phone}/{scenario}`  | GET    | Make an immediate call         | 2/minute   |
| `/make-custom-call/{phone}/{id}` | GET    | Make call with custom scenario | 2/minute   |
| `/protected`                     | GET    | Example protected route        | 5/minute   |

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

The API implements several security features to protect against unauthorized access and abuse:

### Rate Limiting

Rate limiting is implemented on sensitive endpoints to prevent abuse:

- Authentication: 5 requests per minute
- Call scheduling: 3 requests per minute
- Immediate calls: 2 requests per minute
- Real-time sessions: 5 requests per minute
- Custom scenario creation: 10 requests per minute
- Transcript creation: 10 requests per minute

For detailed rate limit configuration, see [Rate Limiting](docs/rate_limiting.md).

### Logging and Monitoring

The API includes a comprehensive logging system with the following features:

- **Log rotation**: Automatically rotates log files when they reach a configurable size
- **Sensitive data filtering**: Automatically redacts sensitive information such as API keys and credentials
- **Configurable log levels**: Log levels can be adjusted via environment variables
- **File and console logging**: Logs are written to both the console and log files

For detailed logging documentation, see [Logging Configuration](docs/logging.md).

### Security Headers

The API implements a comprehensive set of security headers to protect against common web vulnerabilities:

- **Content-Security-Policy**: Prevents XSS attacks by controlling resource loading
- **X-XSS-Protection**: Enables browser's built-in XSS filtering
- **X-Content-Type-Options**: Prevents MIME type sniffing attacks
- **X-Frame-Options**: Prevents clickjacking attacks
- **HSTS**: Forces HTTPS connections
- **Permissions-Policy**: Controls browser feature permissions
- **Referrer-Policy**: Controls referrer information in requests
- **Cache-Control**: Prevents sensitive information caching

All security headers are configurable via environment variables.
