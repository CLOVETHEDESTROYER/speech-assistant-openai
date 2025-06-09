# Speech Assistant SaaS API

A comprehensive multi-tenant SaaS platform for creating and managing AI voice assistants powered by OpenAI's Realtime API and Twilio Voice Services.

## Overview

This application provides a complete SaaS solution for creating realistic voice assistants with full user onboarding and phone number management:

- **Complete User Onboarding**: Automated setup flow for new users with phone number provisioning and calendar integration.
- **User-Specific Phone Numbers**: Each user gets their own dedicated Twilio phone number for making AI calls.
- **Multi-Tenant Architecture**: Full user isolation for all resources including scenarios, transcripts, and phone numbers.
- **Make outbound calls** with AI-powered voice interaction using various scenarios.
- **Process incoming calls** with natural language understanding.
- **Schedule calls** for later execution.
- **Automatically transcribe** call recordings using Twilio Voice Intelligence.
- **Store and retrieve** call transcripts with enhanced conversation flow analysis.
- **Create and manage** custom conversation scenarios with full user isolation.
- **Stream real-time audio** between users and OpenAI's voice models using WebRTC.
- **Direct audio transcription** via OpenAI Whisper API.
- **Google Calendar integration** for making calendar-aware calls with seamless OAuth flow.

## 🆕 New Features (Latest Update)

### **🎯 Complete User Onboarding System**

- **One-time setup flow** for new users with progress tracking
- **Automatic onboarding initialization** upon registration
- **Step-by-step wizard**: Phone setup → Calendar → Scenarios → Welcome call
- **Progress preservation**: Users can resume onboarding where they left off
- **Smart completion detection**: Automatically detects completed steps

### **📞 User-Specific Phone Number Management**

- **Dedicated phone numbers**: Each user gets their own Twilio phone number
- **Phone number provisioning**: Search and provision numbers via Twilio API
- **Phone number management**: View, release, and manage user phone numbers
- **Development mode support**: Fallback to system phone number for testing
- **Production ready**: Full user isolation for phone numbers

### **🔄 Hybrid Phone Number System**

- **Development Mode** (`DEVELOPMENT_MODE=true`): Uses system phone number for testing
- **Production Mode** (`DEVELOPMENT_MODE=false`): Requires user-specific phone numbers
- **Backward compatibility**: Existing functionality preserved for development

### **⚡ Updated OpenAI Integration**

- **Latest OpenAI Realtime API**: Updated to `gpt-4o-realtime-preview-2025-06-03`
- **Enhanced performance**: Latest model improvements and capabilities

## Core Features

- **Dynamic Voice Interaction**: Engage in natural, real-time conversations powered by OpenAI.
- **Twilio Integration**: Leverages Twilio for PSTN connectivity (making/receiving calls) and call recording.
- **OpenAI Realtime API & Whisper**: Utilizes OpenAI for generating voice responses in real-time and for direct audio file transcription.
- **User Onboarding & Phone Management**:
  - Complete onboarding flow for new users
  - User-specific phone number provisioning and management
  - Progress tracking with step completion detection
  - Clean account setup for multi-tenant SaaS architecture
- **Enhanced Twilio Voice Intelligence**:
  - Automated transcription of call recordings with advanced conversation flow analysis
  - Speaker identification and role assignment (AI agent vs customer)
  - Detailed conversation statistics and participant information
  - Structured conversation flow with timestamps and confidence scores
  - Results stored locally with enhanced metadata for frontend consumption
- **Comprehensive Call Management**:
  - Outbound calls to specified phone numbers using predefined or custom scenarios.
  - Incoming call handling with routing to appropriate scenarios.
  - Call scheduling for future execution.
  - User-specific phone numbers for isolated call management.
- **User-Specific Scenario Management**:
  - Define custom personas, prompts, and voice configurations for varied call interactions.
  - Full CRUD operations for custom scenarios with user isolation.
  - Each user can create up to 20 custom scenarios.
  - Complete multi-tenant SaaS architecture ensuring users only see their own scenarios.
- **Enhanced Transcription Services**:
  - Automatic transcription of recorded Twilio calls with conversation flow analysis
  - Enhanced transcript endpoints with participant identification and conversation structure
  - Webhook for receiving completed transcripts from Twilio with automatic enhancement
  - Local storage of transcripts with enhanced metadata for quick retrieval
  - Endpoints to list and fetch enhanced transcripts with filtering options
  - Detailed sentence-by-sentence data with speaker channels, roles, and conversation flow
  - Direct transcription of uploaded audio files using OpenAI Whisper
  - Import functionality to enhance existing Twilio transcripts
  - User-specific transcript isolation
- **Authentication & Authorization**:
  - Secure JWT-based authentication (access and refresh tokens).
  - OAuth2 compatible token endpoint.
  - CAPTCHA protection on registration and login.
  - Complete user isolation for all resources.
  - Automatic onboarding initialization for new users.
- **Real-time Media Streaming**:
  - WebSocket endpoints for streaming audio data between the client, the server, and OpenAI during a live call.
  - WebRTC signaling support for establishing peer-to-peer connections if needed by a frontend.
- **Database & ORM**:
  - SQLAlchemy for database interaction with enhanced transcript schema.
  - Alembic for database migrations.
  - Supports SQLite for development and PostgreSQL for production.
  - Enhanced schema for user onboarding and phone number management.
- **Configuration & Logging**:
  - Environment variable-based configuration.
  - Detailed logging with rotation and sensitive data filtering.
  - Development mode flag for easy testing.
- **Security**:
  - Rate limiting on sensitive endpoints.
  - Standard security headers (CSP, HSTS, XSS Protection, etc.).
- **Google Calendar Integration**:
  - Complete OAuth2 flow for connecting a user's Google Calendar.
  - Seamless frontend redirect after OAuth authorization.
  - User-specific calendar credentials storage.
  - Endpoints to make calls that can reference calendar events.
  - Calendar-aware AI conversations.

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js and npm/yarn (for Vite React frontend)
- OpenAI API key with access to the Realtime API and Whisper.
- Twilio account with Voice services, and a Voice Intelligence Service configured.
- Google Cloud Console project with Calendar API enabled (for calendar integration).
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
   - Edit `.env` with your API keys and configuration:

   ```bash
   # Core Configuration
   SECRET_KEY=your_secret_key_here
   DATABASE_URL=sqlite:///./sql_app.db  # or PostgreSQL URL for production

   # Development Mode (set to false for production)
   DEVELOPMENT_MODE=true

   # Public URL (your Ngrok URL without https:// for local development)
   PUBLIC_URL=your-ngrok-id.ngrok-free.app

   # Frontend URL (for OAuth redirects)
   FRONTEND_URL=http://localhost:5173

   # OpenAI Configuration
   OPENAI_API_KEY=your_openai_api_key

   # Twilio Configuration
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=+1234567890  # System phone number (for development mode)
   USE_TWILIO_VOICE_INTELLIGENCE=true
   TWILIO_VOICE_INTELLIGENCE_SID=your_voice_intelligence_sid

   # Google Calendar Configuration
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:5050/google-calendar/callback
   ```

5. Set up Twilio Webhooks:

   - **TwiML App/Phone Number Status Callback URL (for Recordings):** Point this to `https://YOUR_NGROK_URL/recording-callback` (HTTP POST). This triggers transcription initiation.
   - **Twilio Voice Intelligence Service Webhook URL (for Transcript Completion):** Point this to `https://YOUR_NGROK_URL/twilio-transcripts/webhook-callback` (HTTP POST). This processes and stores the transcript with enhanced analysis.

6. Set up Google Calendar OAuth:

   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing project
   - Enable the Google Calendar API
   - Create OAuth 2.0 credentials
   - Add `http://localhost:5050/google-calendar/callback` to authorized redirect URIs
   - Copy the client ID and secret to your `.env` file

7. Run database migrations:

   ```bash
   alembic upgrade head
   ```

8. Run the backend application:
   ```bash
   uvicorn app.main:app --reload --port 5050
   ```
   Ensure Ngrok is forwarding to this port, e.g., `ngrok http 5050`.

### Frontend Installation & Running (Vite React)

1. Navigate to the frontend directory:

   ```bash
   cd frontend
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Create frontend environment configuration:

   ```bash
   # Create .env file in frontend directory
   echo "VITE_API_URL=http://localhost:5050" > .env
   ```

4. Start the frontend development server:
   ```bash
   npm run dev
   ```
   The frontend will run on `http://localhost:5173` by default.

## 🎯 User Onboarding Flow

### New User Experience

1. **Registration**: User creates account → Onboarding automatically initialized
2. **Phone Setup**: User searches and provisions their own Twilio phone number
3. **Calendar Connection**: User connects Google Calendar (optional)
4. **First Scenario**: User creates their first AI scenario
5. **Welcome Call**: User makes their first test call
6. **Complete**: User gains full access to the platform

### Onboarding Progress Tracking

The system tracks completion of each step and preserves progress:

- **One-time setup**: Once completed, users never see onboarding again
- **Resumable**: Users can stop and resume onboarding at any step
- **Smart detection**: System automatically detects completed steps
- **Clean experience**: New users get a guided setup flow

### Development vs Production Modes

#### Development Mode (`DEVELOPMENT_MODE=true`)

- Uses system-wide `TWILIO_PHONE_NUMBER` for all calls
- Bypasses user phone number requirements
- Perfect for testing and development
- Maintains backward compatibility

#### Production Mode (`DEVELOPMENT_MODE=false`)

- Requires users to have provisioned phone numbers
- Full user isolation with dedicated phone numbers
- Multi-tenant SaaS ready
- Clean onboarding experience for new users

## API Endpoint Documentation

The API is documented with OpenAPI and can be accessed at `/docs` when the backend is running (e.g., `http://localhost:5050/docs`).

**Base URL for API calls:** `https://YOUR_PUBLIC_URL` (e.g., your Ngrok URL or production domain)

### Authentication

All protected endpoints require a JWT Bearer token in the `Authorization` header.

| Endpoint         | Method | Description                                        | Request Body                          | Response (Success 200/201)                   |
| ---------------- | ------ | -------------------------------------------------- | ------------------------------------- | -------------------------------------------- |
| `/auth/register` | POST   | Register a new user (auto-initializes onboarding). | `UserCreate` schema (email, password) | `UserRead` schema                            |
| `/auth/login`    | POST   | Login to get JWT tokens.                           | `UserLogin` schema (email, password)  | `Token` schema (access_token, refresh_token) |
| `/auth/refresh`  | POST   | Refresh an expired access token.                   | `RefreshToken` schema                 | `Token` schema (access_token)                |
| `/token`         | POST   | OAuth2 compatible token endpoint (form data).      | `username`, `password` (form data)    | `Token` schema (access_token, token_type)    |
| `/users/me`      | GET    | Get current authenticated user's details.          | None                                  | `UserRead` schema                            |

### 🆕 User Onboarding Management

| Endpoint                        | Method | Description                                      | Request Body                     | Response (Success 200)                               |
| ------------------------------- | ------ | ------------------------------------------------ | -------------------------------- | ---------------------------------------------------- |
| `/onboarding/status`            | GET    | Get current user's onboarding progress.          | None                             | Detailed onboarding status with step completion      |
| `/onboarding/next-action`       | GET    | Get recommended next action for user.            | None                             | Next step recommendation with endpoint and priority  |
| `/onboarding/complete-step`     | POST   | Mark a specific onboarding step as completed.    | `{ "step": "phone_setup" }`      | Updated onboarding status                            |
| `/onboarding/initialize`        | POST   | Manually initialize onboarding for current user. | None                             | New onboarding status record                         |
| `/onboarding/check-step/{step}` | GET    | Check if a specific step has been completed.     | `step` (path: phone_setup, etc.) | `{ "completed": true/false, "step": "phone_setup" }` |

### 🆕 Twilio Phone Number Management

| Endpoint                                | Method | Description                                      | Request Body                          | Response (Success 200)                                |
| --------------------------------------- | ------ | ------------------------------------------------ | ------------------------------------- | ----------------------------------------------------- |
| `/twilio/account`                       | GET    | Get Twilio account information and balance.      | None                                  | Account details with balance and capabilities         |
| `/twilio/search-numbers`                | POST   | Search for available phone numbers to provision. | `{ "area_code": "505", "limit": 10 }` | List of available phone numbers with pricing          |
| `/twilio/provision-number`              | POST   | Provision a phone number for the current user.   | `{ "phone_number": "+15059675418" }`  | Provisioned phone number details                      |
| `/twilio/user-numbers`                  | GET    | Get all phone numbers owned by current user.     | None                                  | List of user's phone numbers with status              |
| `/twilio/user-primary-number`           | GET    | Get user's primary phone number.                 | None                                  | Primary phone number details                          |
| `/twilio/release-number/{phone_number}` | DELETE | Release a phone number back to Twilio.           | `phone_number` (path)                 | `{ "message": "Phone number released successfully" }` |

### Call Management

| Endpoint                                      | Method | Description                                                  | Path/Query Params                 | Request Body                                 | Response (Success 200)                                       |
| --------------------------------------------- | ------ | ------------------------------------------------------------ | --------------------------------- | -------------------------------------------- | ------------------------------------------------------------ |
| `/make-call/{phone_number}/{scenario}`        | GET    | Make an immediate call using a predefined scenario.          | `phone_number`, `scenario` (path) | None                                         | `{ "status": "success", "call_sid": "CA..." }`               |
| `/make-custom-call/{phone_number}/{id}`       | GET    | Make an immediate call using a user-defined custom scenario. | `phone_number`, `id` (path)       | None                                         | `{ "status": "Custom call initiated", "call_sid": "CA..." }` |
| `/schedule-call`                              | POST   | Schedule a call for a future time.                           | None                              | `CallScheduleCreate` (phone, scenario, time) | `CallScheduleRead`                                           |
| `/make-calendar-call-scenario/{phone_number}` | GET    | (Experimental) Make a call informed by Google Calendar data. | `phone_number` (path)             | None                                         | `{ "status": "success", "call_sid": "CA..." }`               |

**📝 Note on Phone Number Usage:**

- **Development Mode**: All calls use system `TWILIO_PHONE_NUMBER`
- **Production Mode**: Calls use user's provisioned phone numbers
- **Hybrid Support**: Automatic fallback ensures compatibility

### Google Calendar Integration

Requires user authentication with Google.

| Endpoint                              | Method | Description                                              |
| ------------------------------------- | ------ | -------------------------------------------------------- |
| `/google-calendar/auth`               | GET    | Initiates Google OAuth2 flow.                            |
| `/google-calendar/callback`           | GET    | Google redirects here after user authorization.          |
| `/google-calendar/events`             | GET    | Get upcoming calendar events for the authenticated user. |
| `/google-calendar/check-availability` | POST   | Check free/busy information.                             |
| `/google-calendar/find-slots`         | POST   | Find available time slots.                               |

### Google Calendar OAuth Flow

The application provides a seamless OAuth flow for Google Calendar integration:

1. **Frontend initiates OAuth**: User clicks "Connect Google Calendar" button
2. **Backend provides authorization URL**: `/google-calendar/auth` endpoint returns Google OAuth URL
3. **User authorizes**: User is redirected to Google for authorization
4. **Google redirects to backend**: Google sends authorization code to `/google-calendar/callback`
5. **Backend processes and redirects**: Backend stores credentials and redirects to frontend with success/error parameters
6. **Frontend handles result**: Frontend receives redirect with parameters and shows appropriate message

**Success redirect**: `http://localhost:5173/scheduled-meetings?success=true&connected=calendar`
**Error redirect**: `http://localhost:5173/scheduled-meetings?error=calendar_connection_failed&message=...`

## 🆕 Enhanced Database Schema

### New Models for Onboarding & Phone Management

#### UserPhoneNumber Model

- `user_id`: Foreign key to User
- `phone_number`: User's dedicated Twilio phone number
- `twilio_sid`: Twilio SID for the phone number
- `friendly_name`: Optional custom name for the number
- `is_active`: Whether the number is currently active
- `voice_capable`, `sms_capable`: Twilio capabilities

#### UserOnboardingStatus Model

- `user_id`: Foreign key to User (unique)
- `phone_number_setup`: Boolean - phone number provisioned
- `calendar_connected`: Boolean - Google Calendar connected
- `first_scenario_created`: Boolean - first custom scenario created
- `welcome_call_completed`: Boolean - first test call made
- `started_at`: When onboarding began
- `completed_at`: When onboarding was completed (null if incomplete)
- `current_step`: Current step in onboarding process

## 🎯 SaaS Multi-Tenant Architecture

### User Isolation Features

- **Complete data separation**: All resources isolated by user_id
- **Phone number management**: Each user has their own dedicated numbers
- **Scenario isolation**: Users only see their own custom scenarios
- **Transcript isolation**: Call transcripts separated by user
- **Onboarding tracking**: Individual progress tracking per user
- **Calendar integration**: User-specific Google Calendar connections

### Development vs Production Deployment

#### Development Setup

```bash
# .env configuration for development
DEVELOPMENT_MODE=true
TWILIO_PHONE_NUMBER=+1234567890  # Your system phone number
DATABASE_URL=sqlite:///./sql_app.db
```

#### Production Setup

```bash
# .env configuration for production
DEVELOPMENT_MODE=false
# TWILIO_PHONE_NUMBER not needed - users provision their own
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

## Deployment

### Production Considerations

For production deployments:

1. **Configure production database**: Use PostgreSQL instead of SQLite
2. **Set environment variables**: Configure all required environment variables
3. **Disable development mode**: Set `DEVELOPMENT_MODE=false`
4. **Set up reverse proxy**: Use Nginx or similar for SSL termination
5. **Configure domain**: Update `PUBLIC_URL` and `FRONTEND_URL` for your domain
6. **Enable HTTPS**: Ensure all traffic uses SSL/TLS
7. **Security hardening**: Review security settings and CSP policies
8. **Monitoring setup**: Configure logging and monitoring for production

### Docker Deployment

A `Dockerfile` is included for containerization:

```bash
docker build -t speech-assistant-api .
docker run -p 5050:5050 --env-file .env speech-assistant-api
```

## License

This project is licensed under the MIT License.

## Acknowledgements

- OpenAI for the powerful AI models and Realtime API
- Twilio for voice services and phone number management
- FastAPI for the excellent API framework
- Google for Calendar API integration
