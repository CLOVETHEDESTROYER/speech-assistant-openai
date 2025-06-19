# Business Web App - Backend Integration Guide

## Overview

This guide provides comprehensive integration documentation for the **Speech Assistant Business Web Application**. The backend offers a complete professional SaaS platform with advanced features including user onboarding, usage tracking, subscription management, phone number provisioning, Google Calendar integration, and custom AI scenario creation.

**Note**: This backend serves both mobile and business applications from a single unified API. Platform detection is automatic based on request headers.

## **Professional Business Features**

### **🎯 Target Audience**

- **Business Professionals**: Sales teams, customer service, training departments
- **Content Creators**: Podcasters, interviewers, storytellers
- **Researchers**: Survey teams, data collection, user research
- **Consultants**: Practice sessions, client preparation, role-playing

### **💼 Business-Grade Features**

- **Complete Onboarding**: Phone number provisioning, calendar integration, scenario setup
- **Usage Analytics**: Detailed call tracking and usage insights
- **Custom Scenarios**: Unlimited personalized AI conversation flows
- **Dedicated Phone Numbers**: Individual Twilio phone numbers per user
- **Calendar Integration**: Google Calendar OAuth with smart scheduling
- **Enhanced Transcripts**: Full conversation analysis with speaker identification
- **Subscription Management**: Multiple professional tiers with usage limits

### **🏗️ Architecture Note**

This backend automatically detects platform type:

- **Business Web App**: Uses standard endpoints (no special headers)
- **Mobile App**: Uses `/mobile/*` endpoints with `X-App-Type: mobile` header
- **Shared Infrastructure**: Authentication, database, and core services are shared
- **Platform-Specific Logic**: Usage limits, pricing, and features vary by platform

---

## 🚀 Getting Started

### **1. Authentication Flow**

#### **User Registration**

```javascript
// Register new business user (no special headers needed)
const registerUser = async (email, password) => {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": "Speech-Assistant-Business-Web/1.0",
    },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    throw new Error("Registration failed");
  }

  const data = await response.json();
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);

  return data;
};
```

#### **User Login**

```javascript
const loginUser = async (email, password) => {
  const formData = new FormData();
  formData.append("username", email);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    body: formData,
  });

  return await response.json();
};
```

#### **Token Management**

```javascript
// Auth utility class
class AuthManager {
  constructor() {
    this.token = localStorage.getItem("access_token");
  }

  getAuthHeaders() {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
    };
  }

  async refreshToken() {
    const refresh = localStorage.getItem("refresh_token");
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });

    if (response.ok) {
      const data = await response.json();
      localStorage.setItem("access_token", data.access_token);
      this.token = data.access_token;
      return true;
    }
    return false;
  }
}
```

---

## 🎓 User Onboarding System

### **1. Check Onboarding Status**

```javascript
const getOnboardingStatus = async () => {
  const response = await fetch(`${API_BASE}/onboarding/status`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response example:
{
  "current_step": "phone_setup",
  "steps_completed": {
    "phone_number_setup": false,
    "calendar_connected": false,
    "first_scenario_created": false,
    "welcome_call_completed": false
  },
  "progress_percentage": 0,
  "next_action": {
    "step": "phone_setup",
    "title": "Set up your phone number",
    "description": "Provision a dedicated phone number for your calls",
    "endpoint": "/twilio/search-numbers"
  },
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": null
}
```

### **2. Complete Onboarding Steps**

```javascript
const completeOnboardingStep = async (step, data = {}) => {
  const response = await fetch(`${API_BASE}/onboarding/complete-step`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({ step, ...data }),
  });

  return await response.json();
};

// Usage examples:
await completeOnboardingStep("phone_number_setup", {
  phone_number: "+1234567890",
});
await completeOnboardingStep("calendar_connected");
await completeOnboardingStep("first_scenario_created", {
  scenario_id: "custom_123",
});
await completeOnboardingStep("welcome_call_completed");
```

### **3. Onboarding UI Component Example**

```jsx
import React, { useState, useEffect } from "react";

const OnboardingWizard = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOnboardingStatus();
  }, []);

  const loadOnboardingStatus = async () => {
    try {
      const data = await getOnboardingStatus();
      setStatus(data);
    } catch (error) {
      console.error("Failed to load onboarding status:", error);
    } finally {
      setLoading(false);
    }
  };

  const renderCurrentStep = () => {
    if (!status) return null;

    switch (status.current_step) {
      case "phone_setup":
        return <PhoneNumberSetup onComplete={loadOnboardingStatus} />;
      case "calendar":
        return <CalendarSetup onComplete={loadOnboardingStatus} />;
      case "scenario":
        return <ScenarioSetup onComplete={loadOnboardingStatus} />;
      case "welcome_call":
        return <WelcomeCall onComplete={loadOnboardingStatus} />;
      case "complete":
        return <OnboardingComplete />;
      default:
        return <div>Loading...</div>;
    }
  };

  if (loading) {
    return <div>Loading onboarding status...</div>;
  }

  return (
    <div className="onboarding-wizard">
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${status?.progress_percentage || 0}%` }}
        />
      </div>

      <div className="step-content">{renderCurrentStep()}</div>
    </div>
  );
};
```

---

## 📞 Phone Number Management

### **1. Get Twilio Account Info**

```javascript
const getTwilioAccount = async () => {
  const response = await fetch(`${API_BASE}/twilio/account`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "account_sid": "AC1234567890abcdef",
  "friendly_name": "Speech Assistant Business",
  "status": "active",
  "balance": "$50.00"
}
```

### **2. Search Available Phone Numbers**

```javascript
const searchPhoneNumbers = async (areaCode = null, limit = 10) => {
  const response = await fetch(`${API_BASE}/twilio/search-numbers`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({
      area_code: areaCode,
      limit: limit
    }),
  });

  return await response.json();
};

// Response:
{
  "availableNumbers": [
    {
      "phoneNumber": "+1234567890",
      "friendlyName": "(234) 567-8900",
      "locality": "New York",
      "region": "NY",
      "country": "US"
    }
  ]
}
```

### **3. Provision Phone Number**

```javascript
const provisionPhoneNumber = async (phoneNumber) => {
  const response = await fetch(`${API_BASE}/twilio/provision-number`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({ phone_number: phoneNumber }),
  });

  return await response.json();
};

// Response:
{
  "success": true,
  "phone_number": "+1234567890",
  "twilio_sid": "PN1234567890abcdef",
  "friendly_name": "Business User Phone",
  "is_active": true
}
```

### **4. Get User's Phone Numbers**

```javascript
const getUserPhoneNumbers = async () => {
  const response = await fetch(`${API_BASE}/twilio/user-numbers`, {
    headers: authManager.getAuthHeaders(),
  });

  return await response.json();
};

// Response:
[
  {
    phone_number: "+1234567890",
    twilio_sid: "PN1234567890abcdef",
    friendly_name: "Primary Business Number",
    is_active: true,
    is_primary: true,
  },
];
```

---

## 📅 Google Calendar Integration

### **1. Initiate OAuth Flow**

```javascript
const initiateGoogleAuth = () => {
  const clientId = process.env.REACT_APP_GOOGLE_CLIENT_ID;
  const redirectUri = `${window.location.origin}/auth/callback`;
  const scope = "https://www.googleapis.com/auth/calendar";

  const authUrl =
    `https://accounts.google.com/o/oauth2/v2/auth?` +
    `client_id=${clientId}&` +
    `redirect_uri=${encodeURIComponent(redirectUri)}&` +
    `scope=${encodeURIComponent(scope)}&` +
    `response_type=code&` +
    `access_type=offline&` +
    `prompt=consent`;

  window.location.href = authUrl;
};
```

### **2. Handle OAuth Callback**

```javascript
const handleGoogleCallback = async (code) => {
  const response = await fetch(`${API_BASE}/google-calendar/callback?code=${code}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "success": true,
  "message": "Google Calendar connected successfully",
  "calendar_info": {
    "primary_calendar": "user@gmail.com",
    "timezone": "America/New_York"
  }
}
```

### **3. Find Available Time Slots**

```javascript
const findAvailableSlots = async (startDate, endDate, minDuration = 30) => {
  const params = new URLSearchParams({
    start_date: startDate.toISOString(),
    end_date: endDate.toISOString(),
    min_duration: minDuration,
    max_results: 5
  });

  const response = await fetch(`${API_BASE}/google-calendar/find-slots?${params}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "free_slots": [
    {
      "start": "2024-01-15T10:00:00Z",
      "end": "2024-01-15T10:30:00Z"
    },
    {
      "start": "2024-01-15T14:00:00Z",
      "end": "2024-01-15T14:30:00Z"
    }
  ]
}
```

---

## 🎭 Custom Scenario Management

### **1. Get User's Custom Scenarios**

```javascript
const getCustomScenarios = async () => {
  const response = await fetch(`${API_BASE}/custom-scenarios`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "scenarios": [
    {
      "id": "custom_123",
      "name": "Sales Pitch Practice",
      "description": "Practice sales calls with AI",
      "system_prompt": "You are a sales trainer...",
      "created_at": "2024-01-15T10:30:00Z",
      "is_active": true
    }
  ]
}
```

### **2. Create Custom Scenario**

```javascript
const createCustomScenario = async (scenarioData) => {
  const response = await fetch(`${API_BASE}/realtime/custom-scenario`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify(scenarioData),
  });

  return await response.json();
};

// Request body:
{
  "name": "Customer Service Training",
  "description": "Practice customer service scenarios",
  "system_prompt": "You are a difficult customer...",
  "example_conversation": "Customer: I'm very upset...",
  "tags": ["training", "customer-service"]
}
```

---

## 📞 Making Calls

### **1. Make Standard Call**

```javascript
const makeCall = async (phoneNumber, scenario) => {
  const response = await fetch(`${API_BASE}/make-call/${phoneNumber}/${scenario}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "call_sid": "CA1234567890abcdef",
  "status": "initiated",
  "from_number": "+1234567890",
  "to_number": "+0987654321",
  "scenario": "default",
  "usage_stats": {
    "calls_remaining_this_week": 19,
    "trial_calls_remaining": 0,
    "upgrade_recommended": false
  }
}
```

### **2. Make Custom Scenario Call**

```javascript
const makeCustomCall = async (phoneNumber, scenarioId) => {
  const response = await fetch(
    `${API_BASE}/make-custom-call/${phoneNumber}/${scenarioId}`,
    {
      headers: authManager.getAuthHeaders(),
    }
  );

  return await response.json();
};
```

### **3. Schedule Future Call**

```javascript
const scheduleCall = async (callData) => {
  const response = await fetch(`${API_BASE}/schedule-call`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify(callData),
  });

  return await response.json();
};

// Request body:
{
  "phone_number": "+1234567890",
  "scenario": "custom_123",
  "scheduled_time": "2024-01-15T14:30:00Z",
  "notes": "Follow up call with client"
}
```

---

## 📊 Usage & Analytics

### **1. Get Usage Statistics**

```javascript
const getUsageStats = async () => {
  const response = await fetch(`${API_BASE}/usage-stats`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
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

### **2. Get Call History**

```javascript
const getCallHistory = async (limit = 20, offset = 0) => {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString()
  });

  const response = await fetch(`${API_BASE}/call-history?${params}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "calls": [
    {
      "id": 123,
      "call_sid": "CA1234567890abcdef",
      "phone_number": "+1234567890",
      "scenario": "custom_123",
      "status": "completed",
      "duration": 180,
      "created_at": "2024-01-15T10:30:00Z",
      "transcript_available": true
    }
  ],
  "total": 45,
  "has_more": true
}
```

---

## 📝 Transcript Management

### **1. Get Stored Transcripts**

```javascript
const getStoredTranscripts = async (limit = 10) => {
  const response = await fetch(`${API_BASE}/stored-transcripts?limit=${limit}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response:
{
  "transcripts": [
    {
      "id": 456,
      "call_sid": "CA1234567890abcdef",
      "phone_number": "+1234567890",
      "scenario": "custom_123",
      "transcript_text": "Hello, this is John...",
      "speaker_analysis": {
        "user_speaking_time": 120,
        "ai_speaking_time": 60,
        "conversation_flow": "positive"
      },
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 25
}
```

### **2. Get Specific Transcript**

```javascript
const getTranscript = async (transcriptId) => {
  const response = await fetch(
    `${API_BASE}/stored-transcripts/${transcriptId}`,
    {
      headers: authManager.getAuthHeaders(),
    }
  );

  return await response.json();
};
```

---

## 🔧 Error Handling

### **1. Common Error Responses**

```javascript
// 402 - Payment Required (Trial Exhausted)
{
  "detail": {
    "error": "trial_exhausted",
    "message": "Your 4 free trial calls have been used. Upgrade to Basic ($49.99/month) for 20 calls per week!",
    "upgrade_url": "/pricing",
    "pricing": {
      "basic_plan": {
        "price": "$49.99",
        "billing": "monthly",
        "features": ["20 calls/week", "Custom scenarios", "Dedicated phone number"]
      }
    }
  }
}

// 402 - Weekly Limit Reached
{
  "detail": {
    "error": "weekly_limit_reached",
    "message": "Weekly limit of 20 calls reached. Upgrade to Professional for 50 calls per week.",
    "resets_on": "2024-01-22T00:00:00Z",
    "upgrade_url": "/pricing"
  }
}

// 404 - Phone Number Not Found
{
  "detail": "No phone number available. Please provision a phone number first."
}
```

### **2. Error Handling Utility**

```javascript
class APIErrorHandler {
  static async handleResponse(response) {
    if (response.ok) {
      return await response.json();
    }

    const errorData = await response.json();

    switch (response.status) {
      case 402:
        // Payment required - show upgrade prompt
        this.showUpgradePrompt(errorData.detail);
        break;
      case 404:
        // Resource not found
        this.showNotFoundError(errorData.detail);
        break;
      case 500:
        // Server error
        this.showServerError();
        break;
      default:
        // Generic error
        this.showGenericError(errorData.detail);
    }

    throw new Error(errorData.detail?.message || "API request failed");
  }

  static showUpgradePrompt(detail) {
    // Show upgrade modal with pricing info
    console.log("Show upgrade prompt:", detail);
  }

  static showNotFoundError(message) {
    // Show not found error
    console.log("Not found:", message);
  }

  static showServerError() {
    // Show server error message
    console.log("Server error occurred");
  }

  static showGenericError(message) {
    // Show generic error message
    console.log("Error:", message);
  }
}
```

---

## 🎨 Complete React App Example

```jsx
import React, { useState, useEffect } from "react";
import { AuthManager } from "./utils/AuthManager";
import { OnboardingWizard } from "./components/OnboardingWizard";
import { CallInterface } from "./components/CallInterface";
import { UsageDisplay } from "./components/UsageDisplay";
import { TranscriptList } from "./components/TranscriptList";

const BusinessApp = () => {
  const [user, setUser] = useState(null);
  const [onboardingStatus, setOnboardingStatus] = useState(null);
  const [currentView, setCurrentView] = useState("dashboard");

  const authManager = new AuthManager();

  useEffect(() => {
    initializeApp();
  }, []);

  const initializeApp = async () => {
    try {
      // Check authentication
      const userData = await authManager.getCurrentUser();
      setUser(userData);

      // Check onboarding status
      const onboarding = await getOnboardingStatus();
      setOnboardingStatus(onboarding);
    } catch (error) {
      console.error("App initialization failed:", error);
      // Redirect to login
      window.location.href = "/login";
    }
  };

  const handleOnboardingComplete = () => {
    setOnboardingStatus({ current_step: "complete" });
    setCurrentView("dashboard");
  };

  const renderContent = () => {
    // Show onboarding if not completed
    if (onboardingStatus?.current_step !== "complete") {
      return <OnboardingWizard onComplete={handleOnboardingComplete} />;
    }

    // Show main app
    switch (currentView) {
      case "dashboard":
        return (
          <div className="dashboard">
            <UsageDisplay />
            <CallInterface />
          </div>
        );
      case "transcripts":
        return <TranscriptList />;
      case "scenarios":
        return <ScenarioManager />;
      default:
        return <div>Page not found</div>;
    }
  };

  if (!user) {
    return <div>Loading...</div>;
  }

  return (
    <div className="business-app">
      <header className="app-header">
        <h1>Speech Assistant Business</h1>
        <nav>
          <button
            onClick={() => setCurrentView("dashboard")}
            className={currentView === "dashboard" ? "active" : ""}
          >
            Dashboard
          </button>
          <button
            onClick={() => setCurrentView("transcripts")}
            className={currentView === "transcripts" ? "active" : ""}
          >
            Transcripts
          </button>
          <button
            onClick={() => setCurrentView("scenarios")}
            className={currentView === "scenarios" ? "active" : ""}
          >
            Scenarios
          </button>
        </nav>
        <div className="user-info">
          <span>Welcome, {user.email}</span>
          <button onClick={() => authManager.logout()}>Logout</button>
        </div>
      </header>

      <main className="app-content">{renderContent()}</main>
    </div>
  );
};

export default BusinessApp;
```

---

## 🚀 Deployment Configuration

### **Environment Variables**

```bash
# Frontend (.env)
REACT_APP_API_BASE_URL=https://api.speechassistant.com
REACT_APP_GOOGLE_CLIENT_ID=your_google_client_id
REACT_APP_GOOGLE_CLIENT_SECRET=your_google_client_secret

# Backend (.env)
FRONTEND_URL=https://business.speechassistant.com
PUBLIC_URL=https://api.speechassistant.com
DEVELOPMENT_MODE=false
```

### **Production Build**

```bash
# Build React app
npm run build

# Deploy to hosting service (Netlify, Vercel, etc.)
# Configure environment variables in hosting platform
```

---

This comprehensive integration guide provides everything needed to build a professional business web application that leverages all the advanced features of the Speech Assistant backend! 🚀

**Note**: This backend serves both mobile and business applications. The mobile app uses `/mobile/*` endpoints with `X-App-Type: mobile` headers, while the business web app uses standard endpoints without special headers.
