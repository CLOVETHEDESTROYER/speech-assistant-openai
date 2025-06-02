# Backend Integration Guide for Speech Assistant SaaS

## Overview

This guide provides comprehensive documentation for integrating with the Speech Assistant backend API. The backend is a multi-tenant SaaS platform that provides AI-powered voice calling, Google Calendar integration, user-specific scenarios, and enhanced transcript management.

## Architecture

```
Frontend (React/Vite) ←→ Backend (FastAPI) ←→ External Services
     ↓                        ↓                    ↓
- User Interface         - JWT Authentication    - OpenAI Realtime API
- OAuth Handling         - User Isolation        - Twilio Voice/SMS
- API Calls              - Database (SQLite/PG)  - Google Calendar API
- WebSocket Streams      - WebSocket Streams     - Twilio Intelligence
```

## Environment Configuration

### Backend (.env)

```bash
# Core Configuration
SECRET_KEY=your_secret_key_here
DATABASE_URL=sqlite:///./sql_app.db
PUBLIC_URL=your-ngrok-id.ngrok-free.app
FRONTEND_URL=http://localhost:5173

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890
USE_TWILIO_VOICE_INTELLIGENCE=true
TWILIO_VOICE_INTELLIGENCE_SID=your_voice_intelligence_sid

# Google Calendar Configuration
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5050/google-calendar/callback
```

### Frontend (.env)

```bash
VITE_API_URL=http://localhost:5050
```

## Authentication System

### JWT-Based Authentication

All API endpoints require JWT authentication via the `Authorization: Bearer <token>` header.

#### Register User

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password"
}

Response:
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true
}
```

#### Login

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password"
}

Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### Get Current User

```http
GET /users/me
Authorization: Bearer {access_token}

Response:
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_admin": false
}
```

## User-Specific Custom Scenarios

### Overview

Each user can create up to 20 custom scenarios with complete isolation. Users can only see and manage their own scenarios.

### Create Custom Scenario

```http
POST /realtime/custom-scenario
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "persona": "You are a friendly sales representative for a tech company...",
  "prompt": "Your goal is to understand the customer's needs and provide solutions...",
  "voice_type": "aggressive_male",
  "temperature": 0.7
}

Response:
{
  "scenario_id": "custom_1_1640995200",
  "message": "Custom scenario created successfully"
}
```

### List User's Scenarios

```http
GET /custom-scenarios
Authorization: Bearer {access_token}

Response:
[
  {
    "id": 1,
    "scenario_id": "custom_1_1640995200",
    "persona": "You are a friendly sales representative...",
    "prompt": "Your goal is to understand...",
    "voice_type": "aggressive_male",
    "temperature": 0.7,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

### Update Scenario

```http
PUT /custom-scenarios/{scenario_id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "persona": "Updated persona...",
  "prompt": "Updated prompt...",
  "voice_type": "concerned_female",
  "temperature": 0.8
}
```

### Delete Scenario

```http
DELETE /custom-scenarios/{scenario_id}
Authorization: Bearer {access_token}

Response:
{
  "message": "Custom scenario deleted successfully"
}
```

## Google Calendar Integration

### OAuth Flow Implementation

The Google Calendar integration uses a seamless OAuth flow that redirects back to your frontend.

#### Step 1: Initiate OAuth

```http
GET /google-calendar/auth
Authorization: Bearer {access_token}

Response:
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

#### Step 2: Handle OAuth Callback

After user authorization, Google redirects to the backend, which processes the credentials and redirects to your frontend:

**Success**: `http://localhost:5173/scheduled-meetings?success=true&connected=calendar`
**Error**: `http://localhost:5173/scheduled-meetings?error=calendar_connection_failed&message=...`

#### Step 3: Frontend OAuth Handling

```typescript
// Handle OAuth callback parameters
const [searchParams, setSearchParams] = useSearchParams();

useEffect(() => {
  const success = searchParams.get("success");
  const connected = searchParams.get("connected");
  const error = searchParams.get("error");
  const message = searchParams.get("message");

  if (success === "true" && connected === "calendar") {
    toast.success("Google Calendar connected successfully!");
    setSearchParams({}); // Clean up URL
  } else if (error) {
    toast.error(message || "Failed to connect Google Calendar");
    setSearchParams({}); // Clean up URL
  }
}, [searchParams, setSearchParams]);
```

### Calendar API Endpoints

#### Get Calendar Events

```http
GET /google-calendar/events?max_results=10
Authorization: Bearer {access_token}

Response:
[
  {
    "id": "event_id_123",
    "summary": "Team Meeting",
    "start": "2024-01-15T14:00:00Z",
    "end": "2024-01-15T15:00:00Z",
    "location": "Conference Room A",
    "description": "Weekly team sync"
  }
]
```

#### Make Calendar-Aware Call

```http
GET /make-calendar-call-scenario/{phone_number}
Authorization: Bearer {access_token}

Response:
{
  "status": "success",
  "call_sid": "CA1234567890abcdef",
  "message": "Calendar call initiated",
  "phone_number": "+1234567890"
}
```

## Call Management

### Make Standard Call

```http
GET /make-call/{phone_number}/{scenario}
Authorization: Bearer {access_token}

Response:
{
  "status": "success",
  "call_sid": "CA1234567890abcdef"
}
```

### Make Custom Scenario Call

```http
GET /make-custom-call/{phone_number}/{scenario_id}
Authorization: Bearer {access_token}

Response:
{
  "status": "Custom call initiated",
  "call_sid": "CA1234567890abcdef"
}
```

### Schedule Call

```http
POST /schedule-call
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "phone_number": "+1234567890",
  "scenario": "sales",
  "scheduled_time": "2024-01-15T14:00:00Z"
}
```

## Enhanced Transcript System

### Overview

The system provides enhanced transcripts with conversation flow analysis, participant identification, and user-specific isolation.

### List Enhanced Transcripts

```http
GET /api/enhanced-transcripts/?skip=0&limit=10&call_direction=outbound&scenario_name=sales
Authorization: Bearer {access_token}

Response:
[
  {
    "id": 1,
    "transcript_sid": "GT1234567890abcdef",
    "call_date": "2024-01-15T10:30:00Z",
    "duration": 180,
    "call_direction": "outbound",
    "scenario_name": "sales",
    "participant_count": 2,
    "conversation_turns": 27,
    "total_words": 350,
    "summary": {
      "duration_formatted": "3:00",
      "participant_info": {
        "0": {"role": "customer", "name": "Customer"},
        "1": {"role": "agent", "name": "AI Agent"}
      }
    }
  }
]
```

### Get Detailed Transcript

```http
GET /api/enhanced-transcripts/{transcript_sid}
Authorization: Bearer {access_token}

Response:
{
  "transcript_sid": "GT1234567890abcdef",
  "call_date": "2024-01-15T10:30:00Z",
  "duration": 180,
  "call_direction": "outbound",
  "scenario_name": "sales",
  "full_text": "Hello, this is Mike Thompson calling about...",
  "participant_info": {
    "0": {
      "channel": 0,
      "role": "customer",
      "name": "Customer",
      "total_speaking_time": 90,
      "word_count": 150,
      "sentence_count": 12
    },
    "1": {
      "channel": 1,
      "role": "agent",
      "name": "AI Agent",
      "total_speaking_time": 90,
      "word_count": 200,
      "sentence_count": 15
    }
  },
  "conversation_flow": [
    {
      "sequence": 1,
      "speaker": {
        "channel": 1,
        "role": "agent",
        "name": "AI Agent"
      },
      "text": "Hello, this is Mike Thompson calling about...",
      "start_time": 0.5,
      "end_time": 3.2,
      "duration": 2.7,
      "confidence": 0.95,
      "word_count": 8
    }
  ],
  "summary_data": {
    "total_duration_seconds": 180,
    "total_sentences": 27,
    "total_words": 350,
    "participant_count": 2,
    "average_confidence": 0.92
  }
}
```

## Frontend Integration Examples

### API Client Setup

```typescript
// src/services/apiClient.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000,
});

// Automatic token injection
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default apiClient;
```

### Authentication Hook

```typescript
// src/hooks/useAuth.ts
import { useState, useEffect } from "react";
import apiClient from "../services/apiClient";

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const login = async (email: string, password: string) => {
    const response = await apiClient.post("/auth/login", {
      email,
      password,
    });

    localStorage.setItem("token", response.data.access_token);
    setUser(response.data.user);
    setIsAuthenticated(true);

    return response.data;
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    setIsAuthenticated(false);
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      // Verify token and get user info
      apiClient
        .get("/users/me")
        .then((response) => {
          setUser(response.data);
          setIsAuthenticated(true);
        })
        .catch(() => {
          localStorage.removeItem("token");
        });
    }
  }, []);

  return { user, isAuthenticated, login, logout };
};
```

### Custom Scenarios Hook

```typescript
// src/hooks/useScenarios.ts
import { useState, useEffect } from "react";
import apiClient from "../services/apiClient";

export const useScenarios = () => {
  const [scenarios, setScenarios] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadScenarios = async () => {
    try {
      const response = await apiClient.get("/custom-scenarios");
      setScenarios(response.data);
    } catch (error) {
      console.error("Failed to load scenarios:", error);
    } finally {
      setLoading(false);
    }
  };

  const createScenario = async (scenarioData) => {
    const response = await apiClient.post(
      "/realtime/custom-scenario",
      scenarioData
    );
    await loadScenarios(); // Refresh list
    return response.data;
  };

  const updateScenario = async (scenarioId, scenarioData) => {
    const response = await apiClient.put(
      `/custom-scenarios/${scenarioId}`,
      scenarioData
    );
    await loadScenarios(); // Refresh list
    return response.data;
  };

  const deleteScenario = async (scenarioId) => {
    await apiClient.delete(`/custom-scenarios/${scenarioId}`);
    await loadScenarios(); // Refresh list
  };

  useEffect(() => {
    loadScenarios();
  }, []);

  return {
    scenarios,
    loading,
    createScenario,
    updateScenario,
    deleteScenario,
    refreshScenarios: loadScenarios,
  };
};
```

### Google Calendar Hook

```typescript
// src/hooks/useGoogleCalendar.ts
import { useState } from "react";
import apiClient from "../services/apiClient";

export const useGoogleCalendar = () => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  const initiateOAuth = async () => {
    const response = await apiClient.get("/google-calendar/auth");
    window.location.href = response.data.authorization_url;
  };

  const loadEvents = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get("/google-calendar/events");
      setEvents(response.data);
    } catch (error) {
      console.error("Failed to load calendar events:", error);
    } finally {
      setLoading(false);
    }
  };

  const makeCalendarCall = async (phoneNumber) => {
    const response = await apiClient.get(
      `/make-calendar-call-scenario/${phoneNumber}`
    );
    return response.data;
  };

  return {
    events,
    loading,
    initiateOAuth,
    loadEvents,
    makeCalendarCall,
  };
};
```

## Error Handling

### Standard Error Response Format

```json
{
  "detail": "Error message description",
  "status_code": 400
}
```

### Common HTTP Status Codes

- `200`: Success
- `201`: Created
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (invalid/missing token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `422`: Validation Error
- `429`: Rate Limited
- `500`: Internal Server Error

### Frontend Error Handling

```typescript
// Error handling wrapper
const handleApiCall = async (apiCall) => {
  try {
    return await apiCall();
  } catch (error) {
    if (error.response?.status === 401) {
      // Token expired, redirect to login
      logout();
      navigate("/login");
    } else if (error.response?.status === 429) {
      toast.error("Rate limit exceeded. Please try again later.");
    } else {
      toast.error(error.response?.data?.detail || "An error occurred");
    }
    throw error;
  }
};
```

## WebSocket Connections

### Media Streaming

```typescript
// WebSocket for real-time audio streaming
const connectMediaStream = (scenario) => {
  const ws = new WebSocket(`ws://localhost:5050/media-stream/${scenario}`);

  ws.onopen = () => {
    console.log("Media stream connected");
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Handle audio data
  };

  return ws;
};
```

## Rate Limiting

The API implements rate limiting on sensitive endpoints:

- Authentication: 5 requests per minute
- Call initiation: 2 requests per minute
- Scenario creation: 10 requests per minute

## Security Considerations

1. **JWT Tokens**: Store securely, implement refresh logic
2. **HTTPS**: Use HTTPS in production
3. **CORS**: Backend configured for frontend origin
4. **Rate Limiting**: Respect rate limits to avoid blocking
5. **User Isolation**: All data is automatically filtered by user

## Production Deployment

### Environment Variables

```bash
# Production backend
DATABASE_URL=postgresql://user:pass@host:port/db
PUBLIC_URL=api.yourdomain.com
FRONTEND_URL=https://yourdomain.com

# Production frontend
VITE_API_URL=https://api.yourdomain.com
```

### CORS Configuration

Ensure your production frontend domain is added to the backend's CORS middleware configuration.

This comprehensive guide provides all the information needed to integrate with the Speech Assistant backend API, including authentication, user-specific features, Google Calendar integration, and enhanced transcript management.
