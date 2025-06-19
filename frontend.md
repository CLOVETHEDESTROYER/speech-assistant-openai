# Speech Assistant Business Web App - Frontend Documentation

## Overview

Speech Assistant Business Web App is a React-based SaaS application that enables business users to create and manage AI-powered voice calls with custom scenarios. Each user has their own isolated workspace with personalized scenarios, call history, Google Calendar integration, and dedicated phone numbers.

**Note**: This frontend is for the **Business Web App** only. The mobile app has its own iOS implementation documented in `mobileApp.md`.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   External      │
│   (React)       │    │   (FastAPI)     │    │   Services      │
│                 │    │                 │    │                 │
│ • Authentication│◄──►│ • JWT Auth      │    │ • Google OAuth  │
│ • Scenarios     │    │ • User Data     │    │ • OpenAI API    │
│ • Call History  │    │ • Call Logic    │    │ • Twilio        │
│ • Calendar      │    │ • Transcripts   │    │                 │
│ • Onboarding    │    │ • Usage Limits  │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🏗️ Dual-Platform Architecture

### **Single Backend, Multiple Frontends**

This backend serves both platforms:

- **Business Web App** (React) → Standard endpoints (no special headers)
- **Mobile App** (iOS) → `/mobile/*` endpoints with `X-App-Type: mobile` header

### **Platform Detection**

The backend automatically detects platform type:

```python
# Business web app (default)
if request.headers.get("X-App-Type") == "mobile":
    # Mobile logic: 3 trial calls, $4.99/week
    trial_calls = 3
    pricing = "$4.99/week"
else:
    # Business logic: 4 trial calls, $49.99/month
    trial_calls = 4
    pricing = "$49.99/month"
```

---

## ✅ COMPLETED: Stored Transcripts Implementation

### Problem Solved

The frontend was making expensive Twilio API calls for every transcript request. This has been **SOLVED** with the new stored transcripts feature.

### ✅ Implementation Complete

#### Database Model ✅

- **Table**: `stored_twilio_transcripts`
- **Fields**: user_id, transcript_sid, status, date_created, date_updated, duration, language_code, sentences (JSON)
- **User isolation**: All queries filter by current_user.id

#### API Endpoints ✅

- **GET /stored-twilio-transcripts** (list endpoint, paginated) ✅
- **GET /stored-twilio-transcripts/{transcript_sid}** (detail endpoint) ✅
- **POST /store-transcript/{transcript_sid}** (storage endpoint) ✅

#### Twilio API Format Compatibility ✅

- Returns data in **EXACT same format** as Twilio API ✅
- Frontend expects specific JSON structure with "sentences" array ✅
- Each sentence has: text, speaker, start_time, end_time, confidence ✅

#### Frontend Integration ✅

- Frontend components updated to call `/stored-twilio-transcripts` first ✅
- Falls back to Twilio API if no stored data ✅
- No breaking changes - existing functionality preserved ✅

### Usage Instructions

#### For Backend Developers

1. **Store a transcript from Twilio**:

```bash
POST /store-transcript/{transcript_sid}
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "call_sid": "optional_call_sid",
  "scenario_name": "Voice Call"
}
```

2. **List stored transcripts**:

```bash
GET /stored-twilio-transcripts?page_size=10&page_token=0
Authorization: Bearer {jwt_token}
```

3. **Get transcript details**:

```bash
GET /stored-twilio-transcripts/{transcript_sid}
Authorization: Bearer {jwt_token}
```

#### For Frontend Developers

The frontend components automatically:

1. Try `/stored-twilio-transcripts` first
2. Fall back to legacy endpoints if needed
3. Handle both Twilio and legacy formats seamlessly

**No frontend changes needed** - the implementation is backward compatible.

#### Response Format (Exact Twilio API Format)

```json
{
  "transcripts": [
    {
      "sid": "GT1234567890abcdef",
      "status": "completed",
      "date_created": "2024-01-15T10:30:00Z",
      "date_updated": "2024-01-15T10:35:00Z",
      "duration": 120,
      "language_code": "en-US",
      "sentences": [
        {
          "text": "Hello, this is Mike Thompson calling about your property listing.",
          "speaker": 1,
          "start_time": 0.5,
          "end_time": 4.2,
          "confidence": 0.95
        },
        {
          "text": "Hi Mike, thanks for calling. Which property are you interested in?",
          "speaker": 0,
          "start_time": 4.8,
          "end_time": 8.1,
          "confidence": 0.92
        }
      ]
    }
  ]
}
```

### Benefits Achieved

- ✅ **Reduced API Costs**: No more expensive Twilio API calls for stored transcripts
- ✅ **Improved Performance**: Database queries are much faster than API calls
- ✅ **Search Capability**: Can now search and filter stored transcripts
- ✅ **User Notes/Tags**: Ready for future enhancement with user annotations
- ✅ **Offline Access**: Transcripts available even if Twilio API is down

---

## Frontend-Backend Connection

### 1. API Client Configuration

The frontend connects to the backend through a centralized API client:

**File: `src/services/apiClient.ts`**

```typescript
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL, // Backend URL (e.g., http://localhost:5050)
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000,
  withCredentials: false,
});

// Automatic token injection
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### 2. Environment Configuration

**File: `.env`**

```bash
VITE_API_URL=http://localhost:5050  # Backend API URL
```

### 3. Authentication Flow

```typescript
// Login Process (Business web app - no special headers needed)
const loginResponse = await api.auth.login({
  username: email,
  password: password,
});

// Store JWT token
localStorage.setItem("token", loginResponse.token.access_token);

// All subsequent API calls automatically include the token
```

---

## 🎓 User Onboarding System

### Onboarding Flow

The business web app includes a comprehensive onboarding system:

1. **Phone Number Setup**: Provision dedicated Twilio phone number
2. **Calendar Integration**: Connect Google Calendar for scheduling
3. **Scenario Creation**: Create first custom AI scenario
4. **Welcome Call**: Complete first test call

### Onboarding Components

```typescript
// Check onboarding status
const getOnboardingStatus = async () => {
  const response = await apiClient.get("/onboarding/status");
  return response.data;
};

// Complete onboarding step
const completeOnboardingStep = async (step: string, data?: any) => {
  const response = await apiClient.post("/onboarding/complete-step", {
    step,
    ...data,
  });
  return response.data;
};
```

---

## 📞 Phone Number Management

### Business-Specific Features

Business users get dedicated phone numbers (unlike mobile users who share system numbers):

```typescript
// Search available numbers
const searchNumbers = async (areaCode?: string) => {
  const response = await apiClient.post("/twilio/search-numbers", {
    area_code: areaCode,
    limit: 10,
  });
  return response.data;
};

// Provision phone number
const provisionNumber = async (phoneNumber: string) => {
  const response = await apiClient.post("/twilio/provision-number", {
    phone_number: phoneNumber,
  });
  return response.data;
};

// Get user's phone numbers
const getUserNumbers = async () => {
  const response = await apiClient.get("/twilio/user-numbers");
  return response.data;
};
```

---

## 📅 Google Calendar Integration

### Current Implementation Status

- ✅ OAuth flow initiated from frontend
- ✅ Frontend retry logic for token timing
- ✅ Backend redirect to frontend (implemented)
- ✅ Calendar events display
- ✅ Schedule AI calls for meetings

### Required Backend Changes

#### 1. Update OAuth Callback Endpoint

**Backend File: `app/routes/google_calendar.py`**

```python
@router.get("/callback")
async def google_calendar_callback(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # ... existing OAuth logic ...

    # Redirect to frontend with success/error parameters
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')

    if success:
        redirect_url = f"{frontend_url}/dashboard?calendar=connected&success=true"
    else:
        redirect_url = f"{frontend_url}/dashboard?calendar=error&message={error_message}"

    return RedirectResponse(url=redirect_url)
```

#### 2. Frontend Callback Handler

**Frontend File: `src/components/CalendarCallback.tsx`**

```typescript
import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

const CalendarCallback = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const success = searchParams.get("success");
    const calendar = searchParams.get("calendar");
    const message = searchParams.get("message");

    if (calendar === "connected" && success === "true") {
      // Show success message
      showSuccessNotification("Google Calendar connected successfully!");
      navigate("/dashboard");
    } else if (calendar === "error") {
      // Show error message
      showErrorNotification(message || "Failed to connect Google Calendar");
      navigate("/dashboard");
    }
  }, [searchParams, navigate]);

  return <div>Processing calendar connection...</div>;
};
```

---

## 📊 Usage & Analytics

### Business-Specific Usage Tracking

Business users have different usage limits and analytics:

```typescript
// Get usage statistics
const getUsageStats = async () => {
  const response = await apiClient.get('/usage-stats');
  return response.data;
};

// Response format for business users:
{
  "app_type": "web_business",
  "is_trial_active": false,
  "trial_calls_remaining": 0,
  "calls_made_today": 2,
  "calls_made_this_week": 15,
  "calls_made_total": 45,
  "is_subscribed": true,
  "subscription_tier": "business_basic",
  "weekly_call_limit": 20,
  "calls_remaining_this_week": 5,
  "upgrade_recommended": false
}
```

---

## 🎭 Custom Scenario Management

### Business-Specific Features

Business users can create unlimited custom scenarios:

```typescript
// Get user's custom scenarios
const getCustomScenarios = async () => {
  const response = await apiClient.get("/custom-scenarios");
  return response.data;
};

// Create custom scenario
const createCustomScenario = async (scenarioData: any) => {
  const response = await apiClient.post(
    "/realtime/custom-scenario",
    scenarioData
  );
  return response.data;
};
```

---

## 📞 Making Calls

### Business Call Interface

```typescript
// Make standard call
const makeCall = async (phoneNumber: string, scenario: string) => {
  const response = await apiClient.get(`/make-call/${phoneNumber}/${scenario}`);
  return response.data;
};

// Make custom scenario call
const makeCustomCall = async (phoneNumber: string, scenarioId: string) => {
  const response = await apiClient.get(
    `/make-custom-call/${phoneNumber}/${scenarioId}`
  );
  return response.data;
};

// Schedule future call
const scheduleCall = async (callData: any) => {
  const response = await apiClient.post("/schedule-call", callData);
  return response.data;
};
```

---

## 🔧 Error Handling

### Business-Specific Error Handling

```typescript
// Handle payment required errors
const handlePaymentRequired = (error: any) => {
  if (error.response?.status === 402) {
    const detail = error.response.data.detail;

    if (detail.error === "trial_exhausted") {
      showUpgradeModal(detail.pricing);
    } else if (detail.error === "weekly_limit_reached") {
      showLimitReachedModal(detail);
    }
  }
};

// Handle phone number errors
const handlePhoneNumberError = (error: any) => {
  if (
    error.response?.status === 404 &&
    error.response.data.detail.includes("phone number")
  ) {
    navigate("/onboarding?step=phone_setup");
  }
};
```

---

## 🚀 Deployment Configuration

### Environment Variables

```bash
# Frontend (.env)
VITE_API_URL=https://api.speechassistant.com
VITE_GOOGLE_CLIENT_ID=your_google_client_id

# Backend (.env)
FRONTEND_URL=https://business.speechassistant.com
PUBLIC_URL=https://api.speechassistant.com
DEVELOPMENT_MODE=false
```

### Production Build

```bash
# Install dependencies
npm install

# Build for production
npm run build

# Deploy to hosting service (Netlify, Vercel, etc.)
# Configure environment variables in hosting platform
```

---

## 📱 Mobile vs Business Comparison

| Feature           | Business Web App            | Mobile App            |
| ----------------- | --------------------------- | --------------------- |
| **Trial Calls**   | 4 calls                     | 3 calls               |
| **Pricing**       | $49.99-$299/month           | $4.99/week            |
| **Phone Numbers** | Dedicated per user          | Shared system numbers |
| **Scenarios**     | Unlimited custom            | 5 pre-selected        |
| **Onboarding**    | Multi-step wizard           | Instant access        |
| **Calendar**      | Google Calendar integration | Not available         |
| **Transcripts**   | Full analysis               | Basic history         |
| **Endpoints**     | Standard API                | `/mobile/*` endpoints |

---

## 🎯 Key Differences from Mobile App

### **Business Web App Features**

- **Dedicated Phone Numbers**: Each user gets their own Twilio number
- **Custom Scenarios**: Create unlimited personalized AI scenarios
- **Advanced Onboarding**: Step-by-step setup with progress tracking
- **Google Calendar**: Full calendar integration for scheduling
- **Usage Analytics**: Detailed call tracking and insights
- **Professional Pricing**: Multiple tiers with usage limits

### **Mobile App Features**

- **Shared Infrastructure**: Uses system phone numbers
- **Fun Scenarios**: 5 pre-selected entertainment scenarios
- **Simple Onboarding**: Just sign up and start calling
- **App Store Integration**: In-app purchases for subscriptions
- **Quick Access**: Instant calling without complex setup

---

This comprehensive frontend documentation covers the business web app implementation. For mobile app integration, see `mobileApp.md`. Both apps share the same backend with automatic platform detection! 🚀
