# Speech Assistant API

A powerful API for creating and managing voice assistants powered by OpenAI's Realtime API and Twilio Voice Services.

## Overview

This application provides a complete solution for creating realistic voice assistants that can:

- Make outbound calls with AI-powered voice interaction using various scenarios.
- Process incoming calls with natural language understanding.
- Schedule calls for later execution.
- Automatically transcribe call recordings using Twilio Voice Intelligence.
- Store and retrieve call transcripts, including sentence-level details with speaker identification.
- Create and manage custom conversation scenarios.
- Stream real-time audio between users and OpenAI's voice models using WebRTC for interactive sessions.
- Offer direct audio transcription via OpenAI Whisper API.
- Integrate with Google Calendar for making calendar-aware calls (experimental).

## Core Features

- **Dynamic Voice Interaction**: Engage in natural, real-time conversations powered by OpenAI.
- **Twilio Integration**: Leverages Twilio for PSTN connectivity (making/receiving calls) and call recording.
- **OpenAI Realtime API & Whisper**: Utilizes OpenAI for generating voice responses in real-time and for direct audio file transcription.
- **Twilio Voice Intelligence**: Automated transcription of call recordings, with results stored locally.
- **Comprehensive Call Management**:
  - Outbound calls to specified phone numbers using predefined or custom scenarios.
  - Incoming call handling with routing to appropriate scenarios.
  - Call scheduling for future execution.
- **Scenario Management**:
  - Define custom personas, prompts, and voice configurations for varied call interactions.
  - CRUD operations for custom scenarios.
- **Transcription Services**:
  - Automatic transcription of recorded Twilio calls.
  - Webhook for receiving completed transcripts from Twilio.
  - Local storage of transcripts for quick retrieval.
  - Endpoints to list and fetch stored transcripts, including detailed sentence-by-sentence data with speaker channels.
  - Direct transcription of uploaded audio files using OpenAI Whisper.
- **Authentication & Authorization**:
  - Secure JWT-based authentication (access and refresh tokens).
  - OAuth2 compatible token endpoint.
  - CAPTCHA protection on registration and login.
- **Real-time Media Streaming**:
  - WebSocket endpoints for streaming audio data between the client, the server, and OpenAI during a live call.
  - WebRTC signaling support for establishing peer-to-peer connections if needed by a frontend.
- **Database & ORM**:
  - SQLAlchemy for database interaction.
  - Alembic for database migrations.
  - Supports SQLite for development and PostgreSQL for production.
- **Configuration & Logging**:
  - Environment variable-based configuration.
  - Detailed logging with rotation and sensitive data filtering.
- **Security**:
  - Rate limiting on sensitive endpoints.
  - Standard security headers (CSP, HSTS, XSS Protection, etc.).
- **Google Calendar Integration (Experimental)**:
  - OAuth2 flow for connecting a user's Google Calendar.
  - Endpoints to make calls that can reference calendar events.

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js and npm/yarn (if running the frontend module)
- OpenAI API key with access to the Realtime API and Whisper.
- Twilio account with Voice services, a Twilio phone number, and a Voice Intelligence Service configured.
- PostgreSQL (optional, SQLite available for development by default).
- Ngrok or similar tunneling service for local development with Twilio webhooks.

### Backend Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/speech-assistant-api.git
   cd speech-assistant-api
   ```

2. Create and activate a Python virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:

   - Copy `.env.example` to `.env`.
   - Edit `.env` with your API keys (OpenAI, Twilio Account SID, Auth Token, Phone Number, Voice Intelligence Service SID), database URL, secret key, and `PUBLIC_URL` (your Ngrok URL without `https://` for local development, e.g., `your-ngrok-id.ngrok-free.app`).
   - Ensure `USE_TWILIO_VOICE_INTELLIGENCE=true` and your `TWILIO_VOICE_INTELLIGENCE_SID` are correctly set.

5. Set up Twilio Webhooks:

   - **TwiML App/Phone Number Status Callback URL (for Recordings):** Point this to `https://YOUR_NGROK_URL/recording-callback` (HTTP POST). This triggers transcription initiation.
   - **Twilio Voice Intelligence Service Webhook URL (for Transcript Completion):** Point this to `https://YOUR_NGROK_URL/twilio-transcripts/webhook-callback` (HTTP POST). This processes and stores the transcript.

6. Run database migrations:

   ```bash
   alembic upgrade head
   ```

7. Run the backend application:
   ```bash
   uvicorn app.main:app --reload --port YOUR_BACKEND_PORT # Default port is 8000, ensure it matches Ngrok
   ```
   Ensure Ngrok is forwarding to this port, e.g., `ngrok http YOUR_BACKEND_PORT`.

### Frontend Installation & Running (Example for a typical React/Vite setup)

(Instructions to be confirmed once `package.json` location and scripts are verified)

1. Navigate to the frontend directory:
   ```bash
   cd frontend # Or the correct path to your frontend's package.json
   ```
2. Install dependencies:
   ```bash
   npm install # or yarn install
   ```
3. Start the frontend development server:
   ```bash
   npm run dev # or npm start, or yarn dev/start
   ```
   The frontend will likely run on a different port (e.g., `http://localhost:5173` or `http://localhost:3000`). Ensure this origin is added to the `CORSMiddleware` in `app/main.py`.

## API Endpoint Documentation

The API is documented with OpenAPI and can be accessed at `/docs` when the backend is running (e.g., `http://localhost:YOUR_BACKEND_PORT/docs`).

**Base URL for API calls:** `https://YOUR_PUBLIC_URL` (e.g., your Ngrok URL or production domain)

### Authentication

All protected endpoints require a JWT Bearer token in the `Authorization` header.

| Endpoint            | Method | Description                                        | Request Body                          | Response (Success 200/201)                   |
| ------------------- | ------ | -------------------------------------------------- | ------------------------------------- | -------------------------------------------- |
| `/auth/register`    | POST   | Register a new user.                               | `UserCreate` schema (email, password) | `UserRead` schema                            |
| `/auth/login`       | POST   | Login to get JWT tokens.                           | `UserLogin` schema (email, password)  | `Token` schema (access_token, refresh_token) |
| `/auth/refresh`     | POST   | Refresh an expired access token.                   | `RefreshToken` schema                 | `Token` schema (access_token)                |
| `/token`            | POST   | OAuth2 compatible token endpoint (form data).      | `username`, `password` (form data)    | `Token` schema (access_token, token_type)    |
| `/auth/captcha-key` | GET    | Get reCAPTCHA site key (if frontend CAPTCHA used). | None                                  | `{ "captcha_key": "YOUR_SITE_KEY" }`         |
| `/users/me`         | GET    | Get current authenticated user's details.          | None                                  | `UserRead` schema                            |

### Call Management

| Endpoint                                      | Method | Description                                                  | Path/Query Params                 | Request Body                                 | Response (Success 200)                                       |
| --------------------------------------------- | ------ | ------------------------------------------------------------ | --------------------------------- | -------------------------------------------- | ------------------------------------------------------------ |
| `/make-call/{phone_number}/{scenario}`        | GET    | Make an immediate call using a predefined scenario.          | `phone_number`, `scenario` (path) | None                                         | `{ "status": "success", "call_sid": "CA..." }`               |
| `/make-custom-call/{phone_number}/{id}`       | GET    | Make an immediate call using a user-defined custom scenario. | `phone_number`, `id` (path)       | None                                         | `{ "status": "Custom call initiated", "call_sid": "CA..." }` |
| `/schedule-call`                              | POST   | Schedule a call for a future time.                           | None                              | `CallScheduleCreate` (phone, scenario, time) | `CallScheduleRead`                                           |
| `/make-calendar-call-scenario/{phone_number}` | GET    | (Experimental) Make a call informed by Google Calendar data. | `phone_number` (path)             | None                                         | `{ "status": "success", "call_sid": "CA..." }`               |

_Callbacks (primarily for Twilio integration, not direct frontend use):_
| Endpoint | Method | Description |
|----------------------------------|-------------|---------------------------------------------------------------------------|
| `/outgoing-call/{scenario}` | GET, POST | TwiML webhook for handling outgoing call logic (dialing, connecting stream).|
| `/incoming-call/{scenario}` | GET, POST | TwiML webhook for handling incoming call logic. |
| `/incoming-call-webhook/{scenario}`| GET, POST | Compatibility TwiML webhook for incoming calls. |
| `/incoming-custom-call/{scenario_id}`| GET, POST | TwiML webhook for custom scenario incoming calls. |
| `/handle-user-input` | POST | TwiML webhook for `<Gather>` results (speech input during call). |
| `/recording-callback` | POST | Twilio webhook: call recording is ready. Initiates transcription. |
| `/twilio-callback` | POST | Twilio webhook: general call status updates (completed, failed, etc.). |

### Real-time Media Streaming (WebSockets)

Used internally by the call handling TwiML to connect audio to OpenAI.

| Endpoint                             | Protocol  | Description                                                              |
| ------------------------------------ | --------- | ------------------------------------------------------------------------ |
| `/media-stream/{scenario}`           | WebSocket | Streams Twilio call audio to OpenAI and vice-versa for a given scenario. |
| `/media-stream-custom/{scenario_id}` | WebSocket | Streams audio for custom scenarios.                                      |
| `/calendar-media-stream`             | WebSocket | Streams audio for calendar-integrated calls.                             |

### Custom Scenarios

| Endpoint                         | Method | Description                | Request Body                        | Response (Success 200/201/204)      |
| -------------------------------- | ------ | -------------------------- | ----------------------------------- | ----------------------------------- |
| `/realtime/custom-scenario`      | POST   | Create a custom scenario.  | `CustomScenarioCreate` schema       | `CustomScenarioRead` schema         |
| `/realtime/custom-scenarios`     | GET    | List all custom scenarios. | None                                | `List[CustomScenarioRead]`          |
| `/realtime/custom-scenario/{id}` | GET    | Get a specific scenario.   | `id` (path)                         | `CustomScenarioRead` schema         |
| `/realtime/custom-scenario/{id}` | PUT    | Update a scenario.         | `id` (path), `CustomScenarioUpdate` | `CustomScenarioRead` schema         |
| `/realtime/custom-scenario/{id}` | DELETE | Delete a scenario.         | `id` (path)                         | `{ "message": "Scenario deleted" }` |

### Transcription Services

#### Twilio Voice Intelligence Based (Automatic for Recorded Calls)

1.  **Initiation:**

    - Automatic: When a call is recorded, `/recording-callback` is hit, which (if configured) calls Twilio VI to create a transcript.
    - Manual:
      | Endpoint | Method | Description | Request Body | Response (Success 200) |
      |---------------------------------------------------|--------|-------------------------------------------------|----------------------------------------------|-----------------------------------------------------------------|
      | `/twilio-transcripts/create-with-media-url` | POST | Create transcript from a public audio URL. | `media_url`, `language_code`, etc. | `{ "status": "success", "transcript_sid": "GT..." }` |
      | `/twilio-transcripts/create-with-participants` | POST | Create transcript from recording SID & participants. | `recording_sid`, `participants` array | `{ "status": "success", "transcript_sid": "GT..." }` |

2.  **Webhook (from Twilio VI to your app):**
    | Endpoint | Method | Description |
    |-----------------------------------------|--------|--------------------------------------------------------------------------------|
    | `/twilio-transcripts/webhook-callback` | POST | Twilio VI sends notification here when transcript is ready. App stores it. |

3.  **Retrieving Stored Transcripts (Recommended for Frontend):**
    | Endpoint | Method | Description | Path/Query Params | Response (Success 200) |
    |-----------------------------------------|--------|-------------------------------------------------------------------------|--------------------------------|----------------------------------------------------------------------------------------------------------------------|
    | `/stored-transcripts/` | GET | List locally stored transcripts. | `skip`, `limit` (query) | `List[TranscriptRecordRead]` (includes `id`, `transcript_sid`, `status`, `full_text`, `date_created`, `duration`, etc.) |
    | `/stored-transcripts/{transcript_sid}` | GET | Get a specific locally stored transcript by its Twilio Transcript SID. | `transcript_sid` (path) | `TranscriptRecordRead` |
    | `/api/transcripts/{transcript_sid}` | GET | Get detailed locally stored transcript including sentences. | `transcript_sid` (path) | `{ "status": "success", "transcript": { "full_text": "...", "sentences": [...], ...} }` |

4.  **Direct Twilio VI API Access (Less common for frontend, more for admin/debug):**
    | Endpoint | Method | Description | Path/Query Params |
    |---------------------------------------------------|--------|-----------------------------------------------|-----------------------------------|
    | `/twilio-transcripts/{transcript_sid}` | GET | Fetch transcript directly from Twilio. | `transcript_sid` (path) |
    | `/twilio-transcripts` | GET | List transcripts directly from Twilio. | `page_size`, `page_token`, etc. |
    | `/twilio-transcripts/recording/{recording_sid}` | GET | Get transcript from Twilio by recording SID. | `recording_sid` (path) |
    | `/twilio-transcripts/{transcript_sid}` | DELETE | Delete a transcript from Twilio. | `transcript_sid` (path) |

#### OpenAI Whisper Based (Direct File Upload)

| Endpoint              | Method | Description                                      | Request Body (multipart/form-data) | Response (Success 200)                                |
| --------------------- | ------ | ------------------------------------------------ | ---------------------------------- | ----------------------------------------------------- |
| `/whisper/transcribe` | POST   | Transcribe an uploaded audio file using Whisper. | `file` (audio file)                | `{ "status": "success", "transcription": "Text..." }` |

### Google Calendar Integration (Experimental)

Requires user authentication with Google.

| Endpoint                              | Method | Description                                                      |
| ------------------------------------- | ------ | ---------------------------------------------------------------- |
| `/google-calendar/auth`               | GET    | Initiates Google OAuth2 flow.                                    |
| `/google-calendar/callback`           | GET    | Google redirects here after user authorization.                  |
| `/google-calendar/events`             | GET    | Get upcoming calendar events for the authenticated user.         |
| `/google-calendar/free-busy`          | POST   | Check free/busy information.                                     |
| `/google-calendar/revoke`             | POST   | Revoke Google Calendar access for the user.                      |
| `/google-calendar/credentials-status` | GET    | Check if current user has connected Google Calendar credentials. |

_Calendar-aware call endpoint is listed under Call Management._

### Debug Endpoints (For Development/Admin Use)

| Endpoint                            | Method | Description                                                    |
| ----------------------------------- | ------ | -------------------------------------------------------------- |
| `/debug/twilio-intelligence-config` | GET    | Show current Twilio Voice Intelligence config loaded by app.   |
| `/debug/recent-conversations`       | GET    | List recent conversation records from the database.            |
| `/debug/recording-callback-status`  | GET    | (May need implementation) Check status of recording callbacks. |
| `/debug/transcript-records`         | GET    | List all transcript records directly from the database.        |
| `/debug/all-users`                  | GET    | List all users (admin only).                                   |
| `/debug/protected-admin`            | GET    | Example protected admin route.                                 |

## Deployment

### Docker

A `Dockerfile` is included for containerization:

```bash
docker build -t speech-assistant-api .
docker run -p YOUR_CHOSEN_PORT:YOUR_BACKEND_PORT --env-file .env speech-assistant-api
```

(Ensure `YOUR_BACKEND_PORT` inside the container matches what Uvicorn runs on, and `YOUR_CHOSEN_PORT` is what you access it from on your host.)

### Production Considerations

For production deployments:

1.  Configure a production-ready database (PostgreSQL recommended). Update `DATABASE_URL` in `.env`.
2.  Set up a reverse proxy (e.g., Nginx, Traefik) to handle incoming traffic, SSL termination, and potentially serve static files if you integrate the frontend build.
3.  Enable HTTPS with proper SSL certificates.
4.  Configure `PUBLIC_URL` in `.env` to your production domain name (e.g., `api.yourdomain.com`).
5.  Ensure `CORSMiddleware` in `app/main.py` includes your production frontend's origin.
6.  Review and harden security settings (e.g., `SECRET_KEY` should be strong and unique, disable debug mode if Uvicorn runs with it).
7.  Configure logging for production (e.g., appropriate log levels, centralized logging).
8.  Set `ENABLE_SECURITY_HEADERS=true` and review CSP and other security header policies in `app/config.py` for your production domain.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (if one exists, otherwise assume standard MIT).

## Acknowledgements

- OpenAI for the powerful AI models
- Twilio for voice and transcription services
- FastAPI for the excellent API framework
