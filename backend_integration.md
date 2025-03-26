# Backend Integration Guide for Speech Assistant

## Overview

This guide explains how to integrate the Speech Assistant backend with a React + Tailwind frontend. The backend provides real-time speech processing capabilities using OpenAI's API, WebRTC for audio streaming, and includes user authentication.

## Prerequisites

- Python 3.8+
- PostgreSQL or SQLite
- OpenAI API key with Realtime API access
- Twilio account (for phone call features)
- Node.js and npm/yarn

## Environment Setup

Create a `.env` file in your project root with the following variables:

```env
# API Keys
OPENAI_API_KEY=your_openai_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

# Security
SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///./app.db  # or your PostgreSQL URL

# WebRTC Configuration (Optional)
TURN_SERVER=your_turn_server
TURN_USERNAME=your_turn_username
TURN_CREDENTIAL=your_turn_credential

# Server Configuration
PORT=5050
PUBLIC_URL=your_public_url
```

## API Endpoints

### Authentication

#### Register User

```http
POST /register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password"
}
```

#### Login

```http
POST /token
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=secure_password
```

#### Get Current User

```http
GET /users/me
Authorization: Bearer {access_token}
```

### Real-time Speech Features

#### Create Real-time Session

```http
GET /realtime/session?scenario_id=default
Authorization: Bearer {access_token}
```

#### WebSocket Connections

- Media Stream: `ws://your-domain/media-stream/{scenario}`
- Scenario Updates: `ws://your-domain/update-scenario/{scenario}`

## Frontend Integration

### 1. Install Dependencies

Add these dependencies to your React project:

```bash
npm install @microsoft/fetch-event-source socket.io-client webrtc-adapter
```

### 2. Authentication Setup

```typescript
// src/services/auth.ts
export const login = async (email: string, password: string) => {
  const response = await fetch("/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: `username=${email}&password=${password}`,
  });
  return response.json();
};

export const getCurrentUser = async (token: string) => {
  const response = await fetch("/users/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return response.json();
};
```

### 3. WebRTC Integration

```typescript
// src/services/realtime.ts
export class RealtimeService {
  private rtcPeerConnection: RTCPeerConnection | null = null;
  private sessionId: string | null = null;

  async startSession(token: string, scenario: string = "default") {
    // Create session
    const sessionResponse = await fetch(
      `/realtime/session?scenario_id=${scenario}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );
    const sessionData = await sessionResponse.json();
    this.sessionId = sessionData.session_id;

    // Initialize WebRTC
    this.rtcPeerConnection = new RTCPeerConnection({
      iceServers: sessionData.ice_servers,
    });

    // Create and send offer
    const offer = await this.rtcPeerConnection.createOffer({
      offerToReceiveAudio: true,
    });
    await this.rtcPeerConnection.setLocalDescription(offer);

    // Signal the offer
    const signalResponse = await fetch("/realtime/signal", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: this.sessionId,
        client_secret: sessionData.client_secret,
        sdp: offer.sdp,
      }),
    });
    const answerData = await signalResponse.json();

    // Set remote description
    await this.rtcPeerConnection.setRemoteDescription(
      new RTCSessionDescription({
        type: "answer",
        sdp: answerData.sdp_answer,
      })
    );
  }

  stopSession() {
    if (this.rtcPeerConnection) {
      this.rtcPeerConnection.close();
      this.rtcPeerConnection = null;
      this.sessionId = null;
    }
  }
}
```

### 4. React Component Example

```typescript
// src/components/SpeechAssistant.tsx
import React, { useEffect, useState } from "react";
import { RealtimeService } from "../services/realtime";

export const SpeechAssistant: React.FC = () => {
  const [isConnected, setIsConnected] = useState(false);
  const realtimeService = new RealtimeService();

  const handleStart = async () => {
    try {
      const token = localStorage.getItem("access_token");
      if (!token) return;

      await realtimeService.startSession(token);
      setIsConnected(true);
    } catch (error) {
      console.error("Failed to start session:", error);
    }
  };

  const handleStop = () => {
    realtimeService.stopSession();
    setIsConnected(false);
  };

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-4">Speech Assistant</h2>
      <div className="space-x-4">
        <button
          className={`px-4 py-2 rounded ${
            isConnected ? "bg-gray-300" : "bg-blue-500 text-white"
          }`}
          onClick={handleStart}
          disabled={isConnected}
        >
          Start Session
        </button>
        <button
          className={`px-4 py-2 rounded ${
            !isConnected ? "bg-gray-300" : "bg-red-500 text-white"
          }`}
          onClick={handleStop}
          disabled={!isConnected}
        >
          Stop Session
        </button>
      </div>
      <div className="mt-4">
        Status: {isConnected ? "Connected" : "Disconnected"}
      </div>
    </div>
  );
};
```

## Available Scenarios

The backend supports various conversation scenarios:

1. Default Assistant
2. Customer Service
3. Gameshow Host
4. Custom scenarios (can be configured)

## Security Considerations

1. Store sensitive tokens securely (use HTTP-only cookies or secure storage)
2. Implement proper CORS configuration
3. Use HTTPS in production
4. Implement rate limiting
5. Validate all user inputs
6. Keep dependencies updated

## Error Handling

Implement proper error handling for:

- WebSocket disconnections
- Authentication failures
- API rate limits
- Network issues
- Invalid audio input

## Testing

1. Unit test authentication flows
2. Test WebRTC connection establishment
3. Verify audio streaming
4. Test scenario switching
5. Validate error handling

## Deployment Considerations

1. Use HTTPS
2. Configure proper CORS settings
3. Set up proper environment variables
4. Configure database connections
5. Set up proper logging
6. Monitor API usage and rate limits

## Troubleshooting

Common issues and solutions:

1. WebRTC Connection Issues

   - Check ICE server configuration
   - Verify network connectivity
   - Check browser compatibility

2. Authentication Problems

   - Verify token expiration
   - Check credentials
   - Validate request headers

3. Audio Issues
   - Check microphone permissions
   - Verify audio format
   - Check WebRTC configuration

## Support

For additional support:

1. Check the API documentation
2. Review the error logs
3. Contact the development team
4. Check the GitHub repository for updates
