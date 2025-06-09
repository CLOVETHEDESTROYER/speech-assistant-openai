# Business Web App - Backend Integration Guide

## Overview

This guide provides comprehensive integration documentation for the **Speech Assistant Business Web Application**. The backend offers a complete professional SaaS platform with advanced features including user onboarding, usage tracking, subscription management, phone number provisioning, Google Calendar integration, and custom AI scenario creation.

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

---

## 🚀 Getting Started

### **1. Authentication Flow**

#### **User Registration**

```javascript
// Register new business user
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
        return <CalendarConnection onComplete={loadOnboardingStatus} />;
      case "scenarios":
        return <ScenarioCreation onComplete={loadOnboardingStatus} />;
      case "complete":
        return <WelcomeComplete />;
      default:
        return <div>Loading...</div>;
    }
  };

  if (loading) return <div>Loading onboarding status...</div>;

  return (
    <div className="onboarding-wizard">
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${status.progress_percentage}%` }}
        />
      </div>

      <h1>Welcome to Speech Assistant Business</h1>
      <p>Let's get your account set up (Step {status.current_step})</p>

      {renderCurrentStep()}
    </div>
  );
};
```

---

## 📞 Phone Number Management

### **1. Search Available Numbers**

```javascript
const searchPhoneNumbers = async (areaCode = '', country = 'US') => {
  const params = new URLSearchParams({ area_code: areaCode, country });
  const response = await fetch(`${API_BASE}/twilio/search-numbers?${params}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response example:
{
  "available_numbers": [
    {
      "phone_number": "+12025551234",
      "friendly_name": "(202) 555-1234",
      "locality": "Washington",
      "region": "DC",
      "postal_code": "20001",
      "iso_country": "US",
      "capabilities": {
        "voice": true,
        "sms": true,
        "mms": false
      }
    }
  ],
  "search_params": {
    "area_code": "202",
    "country": "US"
  }
}
```

### **2. Provision Phone Number**

```javascript
const provisionPhoneNumber = async (phoneNumber, friendlyName) => {
  const response = await fetch(`${API_BASE}/twilio/provision-number`, {
    method: 'POST',
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({
      phone_number: phoneNumber,
      friendly_name: friendlyName
    })
  });

  return await response.json();
};

// Response example:
{
  "success": true,
  "phone_number": "+12025551234",
  "twilio_sid": "PN1234567890abcdef",
  "friendly_name": "My Business Line",
  "capabilities": {
    "voice": true,
    "sms": true
  },
  "date_provisioned": "2024-01-15T10:30:00Z"
}
```

### **3. Get User's Phone Numbers**

```javascript
const getUserPhoneNumbers = async () => {
  const response = await fetch(`${API_BASE}/twilio/user-numbers`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response example:
{
  "phone_numbers": [
    {
      "id": 1,
      "phone_number": "+12025551234",
      "twilio_sid": "PN1234567890abcdef",
      "friendly_name": "My Business Line",
      "is_active": true,
      "voice_capable": true,
      "sms_capable": true,
      "date_provisioned": "2024-01-15T10:30:00Z"
    }
  ],
  "primary_number": "+12025551234",
  "total_count": 1
}
```

### **4. Phone Number Setup Component**

```jsx
const PhoneNumberSetup = ({ onComplete }) => {
  const [searchResults, setSearchResults] = useState([]);
  const [areaCode, setAreaCode] = useState("");
  const [selectedNumber, setSelectedNumber] = useState(null);
  const [provisioning, setProvisioning] = useState(false);

  const searchNumbers = async () => {
    try {
      const results = await searchPhoneNumbers(areaCode);
      setSearchResults(results.available_numbers);
    } catch (error) {
      console.error("Search failed:", error);
    }
  };

  const handleProvisionNumber = async (number) => {
    setProvisioning(true);
    try {
      await provisionPhoneNumber(number.phone_number, "Business Line");
      await completeOnboardingStep("phone_number_setup", {
        phone_number: number.phone_number,
      });
      onComplete();
    } catch (error) {
      console.error("Provisioning failed:", error);
    } finally {
      setProvisioning(false);
    }
  };

  return (
    <div className="phone-setup">
      <h2>Choose Your Business Phone Number</h2>

      <div className="search-form">
        <input
          type="text"
          placeholder="Area code (optional)"
          value={areaCode}
          onChange={(e) => setAreaCode(e.target.value)}
        />
        <button onClick={searchNumbers}>Search Numbers</button>
      </div>

      <div className="number-results">
        {searchResults.map((number) => (
          <div key={number.phone_number} className="number-option">
            <span className="number">{number.friendly_name}</span>
            <span className="location">
              {number.locality}, {number.region}
            </span>
            <button
              onClick={() => handleProvisionNumber(number)}
              disabled={provisioning}
            >
              {provisioning ? "Provisioning..." : "Select"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
```

---

## 🔄 Usage Tracking & Subscription Management

### **1. Check Usage Statistics**

```javascript
const getUsageStats = async () => {
  const response = await fetch(`${API_BASE}/usage/stats`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response example:
{
  "app_type": "web_business",
  "subscription_tier": "business_free_trial",
  "is_subscribed": false,
  "is_trial_active": true,
  "trial_calls_remaining": 3,
  "trial_calls_used": 1,
  "trial_end_date": "2024-01-22T10:30:00Z",
  "calls_made_today": 1,
  "calls_made_this_week": 1,
  "calls_made_this_month": 1,
  "calls_made_total": 1,
  "weekly_call_limit": null,
  "monthly_call_limit": null,
  "billing_cycle": null,
  "upgrade_recommended": false,
  "pricing": {
    "basic_plan": {
      "price": "$49.99",
      "billing": "monthly",
      "features": ["20 calls per week", "Basic scenarios", "Call transcripts"]
    },
    "professional_plan": {
      "price": "$99.00",
      "billing": "monthly",
      "features": ["50 calls per week", "Custom scenarios", "Calendar integration"]
    },
    "enterprise_plan": {
      "price": "$299.00",
      "billing": "monthly",
      "features": ["Unlimited calls", "Advanced features", "Priority support"]
    }
  }
}
```

### **2. Check Call Permissions**

```javascript
const checkCallPermission = async () => {
  const response = await fetch(`${API_BASE}/usage/check-permission`, {
    method: 'POST',
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response examples:
// Can make call:
{
  "can_make_call": true,
  "status": "trial_call_available",
  "details": {
    "calls_remaining": 3,
    "trial_ends": "2024-01-22T10:30:00Z",
    "app_type": "web_business"
  }
}

// Trial exhausted:
{
  "can_make_call": false,
  "status": "trial_calls_exhausted",
  "details": {
    "message": "Trial calls exhausted. Please upgrade to continue.",
    "pricing": { /* pricing object */ }
  }
}
```

### **3. Usage Display Component**

```jsx
const UsageDisplay = () => {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUsageStats();
  }, []);

  const loadUsageStats = async () => {
    try {
      const data = await getUsageStats();
      setUsage(data);
    } catch (error) {
      console.error("Failed to load usage stats:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading usage stats...</div>;
  if (!usage) return <div>Unable to load usage information</div>;

  return (
    <div className="usage-display">
      <div className="usage-header">
        <h3>Your Usage</h3>
        <span
          className={`status ${usage.is_subscribed ? "subscribed" : "trial"}`}
        >
          {usage.is_subscribed ? "Subscribed" : "Free Trial"}
        </span>
      </div>

      {usage.is_trial_active && !usage.is_subscribed && (
        <div className="trial-info">
          <div className="calls-remaining">
            <span className="number">{usage.trial_calls_remaining}</span>
            <span className="label">Trial calls remaining</span>
          </div>
          <div className="trial-expires">
            Trial expires: {new Date(usage.trial_end_date).toLocaleDateString()}
          </div>
        </div>
      )}

      <div className="usage-stats">
        <div className="stat">
          <span className="number">{usage.calls_made_today}</span>
          <span className="label">Today</span>
        </div>
        <div className="stat">
          <span className="number">{usage.calls_made_this_week}</span>
          <span className="label">This week</span>
        </div>
        <div className="stat">
          <span className="number">{usage.calls_made_total}</span>
          <span className="label">Total</span>
        </div>
      </div>

      {usage.upgrade_recommended && (
        <div className="upgrade-prompt">
          <h4>Ready to upgrade?</h4>
          <p>Continue making unlimited calls with our professional plans</p>
          <button onClick={() => showPricingModal(usage.pricing)}>
            View Plans
          </button>
        </div>
      )}
    </div>
  );
};
```

---

## 📞 Making Calls with Usage Tracking

### **1. Make Standard Call**

```javascript
const makeCall = async (phoneNumber, scenario) => {
  // First check permission
  const permission = await checkCallPermission();

  if (!permission.can_make_call) {
    if (permission.status === "trial_calls_exhausted") {
      throw new Error("TRIAL_EXHAUSTED");
    } else if (permission.status === "weekly_limit_reached") {
      throw new Error("WEEKLY_LIMIT_REACHED");
    } else {
      throw new Error("CALL_NOT_PERMITTED");
    }
  }

  const response = await fetch(
    `${API_BASE}/make-call/${phoneNumber}/${scenario}`,
    {
      method: "GET",
      headers: authManager.getAuthHeaders(),
    }
  );

  if (response.status === 402) {
    // Payment required
    const errorData = await response.json();
    throw new Error(`PAYMENT_REQUIRED: ${errorData.detail}`);
  }

  return await response.json();
};
```

### **2. Make Custom Scenario Call**

```javascript
const makeCustomCall = async (phoneNumber, scenarioId) => {
  const response = await fetch(
    `${API_BASE}/make-custom-call/${phoneNumber}/${scenarioId}`,
    {
      method: "GET",
      headers: authManager.getAuthHeaders(),
    }
  );

  return await response.json();
};
```

### **3. Call Interface Component**

```jsx
const CallInterface = () => {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [selectedScenario, setSelectedScenario] = useState("default");
  const [scenarios, setScenarios] = useState([]);
  const [calling, setCalling] = useState(false);
  const [callPermission, setCallPermission] = useState(null);

  useEffect(() => {
    loadScenarios();
    checkPermissions();
  }, []);

  const checkPermissions = async () => {
    try {
      const permission = await checkCallPermission();
      setCallPermission(permission);
    } catch (error) {
      console.error("Permission check failed:", error);
    }
  };

  const handleMakeCall = async () => {
    if (!callPermission?.can_make_call) {
      alert("Cannot make call. Please check your subscription status.");
      return;
    }

    setCalling(true);
    try {
      await makeCall(phoneNumber, selectedScenario);
      alert("Call initiated successfully!");
      await checkPermissions(); // Refresh permissions
    } catch (error) {
      if (error.message === "TRIAL_EXHAUSTED") {
        alert("Your trial has ended. Please upgrade to continue making calls.");
      } else if (error.message === "WEEKLY_LIMIT_REACHED") {
        alert("You have reached your weekly call limit.");
      } else {
        alert(`Call failed: ${error.message}`);
      }
    } finally {
      setCalling(false);
    }
  };

  return (
    <div className="call-interface">
      <h2>Make a Call</h2>

      <div className="form-group">
        <label>Phone Number</label>
        <input
          type="tel"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          placeholder="+1234567890"
        />
      </div>

      <div className="form-group">
        <label>Scenario</label>
        <select
          value={selectedScenario}
          onChange={(e) => setSelectedScenario(e.target.value)}
        >
          {scenarios.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.name}
            </option>
          ))}
        </select>
      </div>

      <button
        onClick={handleMakeCall}
        disabled={calling || !callPermission?.can_make_call}
        className={`call-button ${calling ? "calling" : ""}`}
      >
        {calling ? "Calling..." : "Make Call"}
      </button>

      {callPermission && !callPermission.can_make_call && (
        <div className="permission-warning">
          <p>{callPermission.details.message}</p>
          {callPermission.status === "trial_calls_exhausted" && (
            <button onClick={() => showUpgradeModal()}>Upgrade Now</button>
          )}
        </div>
      )}
    </div>
  );
};
```

---

## 🎭 Custom Scenario Management

### **1. Create Custom Scenario**

```javascript
const createCustomScenario = async (scenarioData) => {
  const response = await fetch(`${API_BASE}/realtime/custom-scenario`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({
      persona: scenarioData.persona,
      prompt: scenarioData.prompt,
      voice_type: scenarioData.voiceType,
      temperature: scenarioData.temperature || 0.7,
    }),
  });

  return await response.json();
};

// Usage example:
const newScenario = await createCustomScenario({
  persona:
    "You are a professional sales trainer helping someone practice cold calling techniques.",
  prompt:
    "Help the user practice their sales pitch. Provide constructive feedback and simulate realistic customer responses.",
  voiceType: "concerned_female",
  temperature: 0.8,
});
```

### **2. List User's Custom Scenarios**

```javascript
const getCustomScenarios = async () => {
  const response = await fetch(`${API_BASE}/custom-scenarios`, {
    headers: authManager.getAuthHeaders(),
  });

  return await response.json();
};

// Response example:
[
  {
    id: 1,
    scenario_id: "custom_1_1640995200",
    persona: "You are a professional sales trainer...",
    prompt: "Help the user practice their sales pitch...",
    voice_type: "concerned_female",
    temperature: 0.8,
    created_at: "2024-01-15T10:30:00Z",
  },
];
```

### **3. Custom Scenario Editor Component**

```jsx
const ScenarioEditor = ({ scenario, onSave, onCancel }) => {
  const [formData, setFormData] = useState({
    persona: scenario?.persona || "",
    prompt: scenario?.prompt || "",
    voiceType: scenario?.voice_type || "concerned_female",
    temperature: scenario?.temperature || 0.7,
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (scenario) {
        // Update existing scenario
        await updateCustomScenario(scenario.scenario_id, formData);
      } else {
        // Create new scenario
        await createCustomScenario(formData);
      }
      onSave();
    } catch (error) {
      console.error("Save failed:", error);
      alert("Failed to save scenario");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="scenario-editor">
      <h3>{scenario ? "Edit Scenario" : "Create New Scenario"}</h3>

      <div className="form-group">
        <label>Persona</label>
        <textarea
          value={formData.persona}
          onChange={(e) =>
            setFormData({ ...formData, persona: e.target.value })
          }
          placeholder="Describe who the AI should be (e.g., 'You are a friendly customer service representative...')"
          rows="4"
        />
      </div>

      <div className="form-group">
        <label>Prompt</label>
        <textarea
          value={formData.prompt}
          onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
          placeholder="What should the AI do in this conversation?"
          rows="4"
        />
      </div>

      <div className="form-group">
        <label>Voice Type</label>
        <select
          value={formData.voiceType}
          onChange={(e) =>
            setFormData({ ...formData, voiceType: e.target.value })
          }
        >
          <option value="concerned_female">Concerned Female</option>
          <option value="aggressive_male">Aggressive Male</option>
          <option value="friendly_female">Friendly Female</option>
          <option value="professional_male">Professional Male</option>
        </select>
      </div>

      <div className="form-group">
        <label>Temperature: {formData.temperature}</label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={formData.temperature}
          onChange={(e) =>
            setFormData({
              ...formData,
              temperature: parseFloat(e.target.value),
            })
          }
        />
        <small>Lower = more predictable, Higher = more creative</small>
      </div>

      <div className="button-group">
        <button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Scenario"}
        </button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
};
```

---

## 📅 Google Calendar Integration

### **1. Initiate OAuth Flow**

```javascript
const connectCalendar = () => {
  // Redirect user to backend OAuth endpoint
  window.location.href = `${API_BASE}/google-calendar/auth`;
};

// After successful OAuth, user will be redirected to:
// http://localhost:5173/scheduled-meetings?success=true&connected=calendar
```

### **2. Handle OAuth Callback**

```jsx
const CalendarCallback = () => {
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const success = urlParams.get("success");
    const connected = urlParams.get("connected");

    if (success === "true" && connected === "calendar") {
      // Calendar successfully connected
      completeOnboardingStep("calendar_connected");
      showSuccessMessage("Google Calendar connected successfully!");
    } else {
      showErrorMessage("Failed to connect Google Calendar");
    }
  }, []);

  return <div>Processing calendar connection...</div>;
};
```

### **3. Schedule Calendar Events**

```javascript
const scheduleCalendarEvent = async (eventData) => {
  const response = await fetch(`${API_BASE}/google-calendar/schedule`, {
    method: "POST",
    headers: authManager.getAuthHeaders(),
    body: JSON.stringify({
      summary: eventData.title,
      start_time: eventData.startTime,
      end_time: eventData.endTime,
      description: eventData.description,
      attendees: eventData.attendees || [],
    }),
  });

  return await response.json();
};
```

### **4. Get Upcoming Events**

```javascript
const getUpcomingEvents = async (maxResults = 10) => {
  const response = await fetch(
    `${API_BASE}/google-calendar/events?max_results=${maxResults}`,
    {
      headers: authManager.getAuthHeaders(),
    }
  );

  return await response.json();
};
```

---

## 📊 Enhanced Transcripts & Analytics

### **1. Get Call Transcripts**

```javascript
const getTranscripts = async (filters = {}) => {
  const params = new URLSearchParams(filters);
  const response = await fetch(`${API_BASE}/stored-transcripts/?${params}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response example:
{
  "transcripts": [
    {
      "id": 1,
      "transcript_sid": "TR1234567890abcdef",
      "status": "completed",
      "date_created": "2024-01-15T10:30:00Z",
      "duration": 120,
      "language_code": "en-US",
      "scenario_name": "Sales Training",
      "call_direction": "outbound",
      "phone_number": "+1234567890",
      "conversation_summary": {
        "total_words": 450,
        "speaker_turns": 12,
        "sentiment": "positive"
      }
    }
  ],
  "total_count": 1,
  "has_more": false
}
```

### **2. Get Detailed Transcript**

```javascript
const getTranscriptDetails = async (transcriptSid) => {
  const response = await fetch(`${API_BASE}/stored-transcripts/${transcriptSid}`, {
    headers: authManager.getAuthHeaders()
  });

  return await response.json();
};

// Response includes full conversation flow:
{
  "transcript_sid": "TR1234567890abcdef",
  "conversation_flow": [
    {
      "speaker": "AI",
      "text": "Hello! This is your AI sales trainer. Ready to practice?",
      "timestamp": "2024-01-15T10:30:05Z",
      "confidence": 0.98
    },
    {
      "speaker": "User",
      "text": "Yes, I'd like to practice my opening pitch.",
      "timestamp": "2024-01-15T10:30:08Z",
      "confidence": 0.95
    }
  ],
  "summary_data": {
    "key_topics": ["sales", "practice", "pitch"],
    "sentiment_analysis": "positive",
    "speaker_stats": {
      "AI": {"word_count": 200, "speaking_time": 60},
      "User": {"word_count": 250, "speaking_time": 60}
    }
  }
}
```

### **3. Transcript Viewer Component**

```jsx
const TranscriptViewer = ({ transcriptSid }) => {
  const [transcript, setTranscript] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTranscript();
  }, [transcriptSid]);

  const loadTranscript = async () => {
    try {
      const data = await getTranscriptDetails(transcriptSid);
      setTranscript(data);
    } catch (error) {
      console.error("Failed to load transcript:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading transcript...</div>;
  if (!transcript) return <div>Transcript not found</div>;

  return (
    <div className="transcript-viewer">
      <div className="transcript-header">
        <h3>Call Transcript</h3>
        <div className="metadata">
          <span>
            Duration: {Math.floor(transcript.duration / 60)}m{" "}
            {transcript.duration % 60}s
          </span>
          <span>
            Date: {new Date(transcript.date_created).toLocaleDateString()}
          </span>
          <span>Scenario: {transcript.scenario_name}</span>
        </div>
      </div>

      <div className="conversation">
        {transcript.conversation_flow?.map((turn, index) => (
          <div key={index} className={`message ${turn.speaker.toLowerCase()}`}>
            <div className="speaker">{turn.speaker}</div>
            <div className="text">{turn.text}</div>
            <div className="timestamp">
              {new Date(turn.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}
      </div>

      {transcript.summary_data && (
        <div className="summary">
          <h4>Summary</h4>
          <div className="stats">
            <div>
              Key Topics: {transcript.summary_data.key_topics?.join(", ")}
            </div>
            <div>Sentiment: {transcript.summary_data.sentiment_analysis}</div>
          </div>
        </div>
      )}
    </div>
  );
};
```

---

## 🎯 Error Handling & Best Practices

### **1. API Error Handler**

```javascript
class APIError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const handleAPIResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));

    switch (response.status) {
      case 401:
        // Try to refresh token
        const refreshed = await authManager.refreshToken();
        if (!refreshed) {
          // Redirect to login
          window.location.href = "/login";
        }
        throw new APIError("Authentication failed", 401, "AUTH_FAILED");

      case 402:
        // Payment required - trial exhausted or limit reached
        throw new APIError(
          errorData.detail?.message || "Payment required",
          402,
          "PAYMENT_REQUIRED"
        );

      case 429:
        // Rate limited
        throw new APIError("Too many requests", 429, "RATE_LIMITED");

      default:
        throw new APIError(
          errorData.detail || "An error occurred",
          response.status,
          "UNKNOWN_ERROR"
        );
    }
  }

  return await response.json();
};
```

### **2. Usage-Aware Components**

```jsx
const withUsageCheck = (WrappedComponent) => {
  return (props) => {
    const [usageStatus, setUsageStatus] = useState(null);

    useEffect(() => {
      checkUsageStatus();
    }, []);

    const checkUsageStatus = async () => {
      try {
        const permission = await checkCallPermission();
        setUsageStatus(permission);
      } catch (error) {
        console.error("Usage check failed:", error);
      }
    };

    if (!usageStatus) {
      return <div>Checking usage status...</div>;
    }

    if (!usageStatus.can_make_call) {
      return (
        <div className="usage-blocked">
          <h3>Unable to Make Calls</h3>
          <p>{usageStatus.details.message}</p>
          {usageStatus.status === "trial_calls_exhausted" && (
            <button onClick={() => showUpgradeModal()}>
              Upgrade to Continue
            </button>
          )}
        </div>
      );
    }

    return (
      <WrappedComponent
        {...props}
        usageStatus={usageStatus}
        onUsageChange={checkUsageStatus}
      />
    );
  };
};

// Usage:
const CallInterface = withUsageCheck(BaseCallInterface);
```

### **3. Development Environment Configuration**

```javascript
// config.js
const config = {
  API_BASE:
    process.env.NODE_ENV === "development"
      ? "http://localhost:5050"
      : "https://api.yourdomain.com",

  WS_BASE:
    process.env.NODE_ENV === "development"
      ? "ws://localhost:5050"
      : "wss://api.yourdomain.com",

  FEATURES: {
    // Enable/disable features based on environment
    USAGE_TRACKING: process.env.NODE_ENV === "production",
    DEVELOPMENT_MODE: process.env.NODE_ENV === "development",
  },
};

export default config;
```

---

## 🚀 Complete Integration Example

Here's a complete React component that demonstrates the full business app integration:

```jsx
import React, { useState, useEffect } from "react";
import { AuthManager } from "./auth";
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

This comprehensive integration guide provides everything needed to build a professional business web application that leverages all the advanced features of the Speech Assistant backend! 🚀
