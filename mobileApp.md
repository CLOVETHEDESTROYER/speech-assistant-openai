# Mobile Speech Assistant App - Backend Integration Guide

## Overview

This document provides comprehensive integration guidelines for the **Speech Assistant Mobile App** (iOS). The backend provides a complete consumer-focused API with enhanced trial management, usage tracking, duration limits, and subscription handling specifically designed for mobile entertainment users.

**🚀 Production Status: LIVE** - The backend is now deployed and running on a Digital Ocean droplet with PostgreSQL database, ready for production mobile app integration.

## 🚀 Production Deployment Status

### **Current Backend Status**

- **Environment**: Production (Digital Ocean Droplet)
- **Database**: PostgreSQL with full schema migration
- **API Base URL**: `https://your-domain.com` (replace with actual domain)
- **Status**: ✅ Live and operational
- **Security**: Full implementation with rate limiting, CORS protection, and authentication

### **Production Features**

- **Rate Limiting**: Implemented for all endpoints
- **CORS Protection**: Restricted to authorized domains
- **Authentication**: JWT-based with secure token management
- **Database**: PostgreSQL with Alembic migrations
- **Monitoring**: Systemd service with automatic restarts
- **Logging**: Comprehensive logging for debugging and monitoring

### **Mobile App Integration Notes**

- **Development**: Use localhost:5050 for testing
- **Production**: Use your production domain for live app
- **Environment Switching**: Implement environment-based URL switching in your iOS app
- **Testing**: All endpoints tested and working in production

## App Architecture

### **Consumer Mobile App Features**

- **7-Day Free Trial**: 3 free calls to test the service (1-minute duration limit)
- **Enhanced Pricing Tiers**:
  - **Basic Plan**: $4.99/week for 5 calls (1-minute limit per call)
  - **Premium Plan**: $25/month for 30 calls (2-minute limit per call)
  - **Addon Calls**: $4.99 for 5 additional calls (30-day expiry)
- **Duration Tracking**: Real-time call duration monitoring and limits
- **7-Day/30-Day Reset Cycles**: Based on user start date (not calendar weeks)
- **Fun Scenarios**: Pre-selected entertaining call scenarios for pranks and entertainment
- **Easy Setup**: No complex onboarding - just sign up and start calling
- **Shared Infrastructure**: Uses system phone numbers (no individual provisioning needed)
- **App Store Integration**: Complete payment processing through App Store
- **Production Ready**: Full security implementation, rate limiting, and error handling

---

## 📱 Complete API Endpoints Reference

### **Authentication Endpoints**

#### **POST /auth/register**

**Purpose**: Register a new mobile user account
**Headers Required**:

- `Content-Type: application/json`
- `X-App-Type: mobile`
- `User-Agent: Speech-Assistant-Mobile-iOS/1.0`

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response**:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

**What it does**: Creates a new user account with mobile-specific settings (3 trial calls, 7-day trial period). Automatically initializes usage limits for mobile consumers.

---

#### **POST /auth/login**

**Purpose**: Authenticate existing mobile user
**Headers Required**:

- `Content-Type: application/x-www-form-urlencoded`
- `X-App-Type: mobile`

**Request Body** (form data):

```
username=user@example.com&password=securepassword123
```

**Response**: Same as register endpoint
**What it does**: Authenticates user and returns JWT tokens for API access. Automatically detects mobile platform from headers.

---

#### **POST /auth/refresh**

**Purpose**: Refresh expired access token
**Headers Required**:

- `Content-Type: application/json`

**Request Body**:

```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response**: Same as register endpoint
**What it does**: Uses refresh token to get new access token without requiring user to log in again.

---

### **Usage & Trial Management Endpoints**

#### **GET /mobile/usage-stats**

**Purpose**: Get current usage statistics and trial/subscription status
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "app_type": "mobile_consumer",
  "is_trial_active": true,
  "trial_calls_remaining": 2,
  "trial_calls_used": 1,
  "calls_made_today": 1,
  "calls_made_this_week": 1,
  "calls_made_this_month": 1,
  "calls_made_total": 1,
  "is_subscribed": false,
  "subscription_tier": null,
  "upgrade_recommended": false,
  "total_call_duration_this_week": 45,
  "total_call_duration_this_month": 45,
  "addon_calls_remaining": 0,
  "addon_calls_expiry": null,
  "week_start_date": "2024-01-15T10:30:00Z",
  "month_start_date": "2024-01-15T10:30:00Z"
}
```

**What it does**: Returns comprehensive usage statistics including trial status, call counts, duration tracking, subscription info, and reset cycle dates. Automatically initializes usage limits if not found.

---

#### **POST /mobile/check-call-permission**

**Purpose**: Check if user can make a call before initiating
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "can_make_call": true,
  "status": "basic_call_available",
  "details": {
    "calls_remaining_this_week": 4,
    "duration_limit": 60,
    "app_type": "mobile_consumer",
    "message": "You have 4 calls remaining this week"
  }
}
```

**Possible Status Values**:

- `trial_call_available` - User has trial calls remaining
- `basic_call_available` - User has basic subscription calls remaining
- `premium_call_available` - User has premium subscription calls remaining
- `addon_call_available` - User has addon calls remaining
- `trial_exhausted` - Trial calls used up
- `weekly_limit_reached` - Basic plan weekly limit reached
- `monthly_limit_reached` - Premium plan monthly limit reached
- `upgrade_required` - No active trial or subscription

**What it does**: Validates if user has available calls (trial/subscription/addon) and returns duration limits before allowing call initiation. Prevents unnecessary API calls when user can't make calls.

---

#### **GET /mobile/pricing**

**Purpose**: Get enhanced mobile app pricing information
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "plans": [
    {
      "id": "basic",
      "name": "Basic Plan",
      "price": "$4.99",
      "billing": "weekly",
      "calls": "5 calls per week",
      "duration_limit": "1 minute per call",
      "features": ["Unlimited scenarios", "Call history", "Basic support"]
    },
    {
      "id": "premium",
      "name": "Premium Plan",
      "price": "$25.00",
      "billing": "monthly",
      "calls": "30 calls per month",
      "duration_limit": "2 minutes per call",
      "features": [
        "All Basic features",
        "Priority support",
        "Advanced analytics"
      ]
    }
  ],
  "addon": {
    "id": "addon",
    "name": "Additional Calls",
    "price": "$4.99",
    "calls": "5 additional calls",
    "expires": "30 days",
    "description": "Perfect when you need a few more calls"
  }
}
```

**What it does**: Returns comprehensive pricing information including all subscription tiers, duration limits, and addon options for display in upgrade prompts and pricing screens.

---

### **Call Management Endpoints**

#### **GET /mobile/scenarios**

**Purpose**: Get available fun scenarios for mobile users
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "scenarios": [
    {
      "id": "default",
      "name": "Friendly Chat",
      "description": "A casual, friendly conversation",
      "icon": "💬"
    },
    {
      "id": "celebrity",
      "name": "Celebrity Interview",
      "description": "Chat with a virtual celebrity",
      "icon": "🌟"
    },
    {
      "id": "comedian",
      "name": "Stand-up Comedian",
      "description": "Funny jokes and comedy bits",
      "icon": "😂"
    },
    {
      "id": "therapist",
      "name": "Life Coach",
      "description": "Supportive and motivational conversation",
      "icon": "🧠"
    },
    {
      "id": "storyteller",
      "name": "Storyteller",
      "description": "Engaging stories and tales",
      "icon": "📚"
    }
  ]
}
```

**What it does**: Returns the 5 pre-selected fun scenarios available to mobile users. These are simplified, entertainment-focused scenarios.

---

#### **POST /mobile/make-call**

**Purpose**: Initiate a phone call with enhanced usage tracking and duration limits
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`
- `Content-Type: application/json`

**Request Body**:

```json
{
  "phone_number": "+1234567890",
  "scenario": "default"
}
```

**Success Response**:

```json
{
  "call_sid": "CA1234567890abcdef",
  "status": "initiated",
  "duration_limit": 60,
  "usage_stats": {
    "calls_remaining_this_week": 4,
    "calls_remaining_this_month": 29,
    "addon_calls_remaining": 0,
    "upgrade_recommended": false
  }
}
```

**Error Response (402 - Payment Required)**:

```json
{
  "detail": {
    "error": "trial_exhausted",
    "message": "Trial calls exhausted. Upgrade to Basic ($4.99/week) for 5 calls per week!",
    "upgrade_options": [
      {
        "plan": "basic",
        "price": "$4.99",
        "calls": "5/week",
        "product_id": "speech_assistant_basic_weekly"
      },
      {
        "plan": "premium",
        "price": "$25.00",
        "calls": "30/month",
        "product_id": "speech_assistant_premium_monthly"
      }
    ],
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

**What it does**:

1. **Checks and resets limits** based on 7-day/30-day cycles from user start date
2. **Validates user can make calls** (trial/subscription/addon calls)
3. **Applies duration limits** (60s for basic/trial, 120s for premium)
4. **Uses shared system phone number** (no individual provisioning needed)
5. **Initiates Twilio call** with duration tracking and status callback
6. **Records call start** (duration recorded when call ends)
7. **Returns updated usage stats** with remaining calls and limits

---

#### **POST /mobile/schedule-call**

**Purpose**: Schedule a call for future execution
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`
- `Content-Type: application/json`

**Request Body**:

```json
{
  "phone_number": "+1234567890",
  "scenario": "default",
  "scheduled_time": "2024-01-15T14:30:00Z"
}
```

**Response**:

```json
{
  "schedule_id": 123,
  "phone_number": "+1234567890",
  "scenario": "default",
  "scheduled_time": "2024-01-15T14:30:00Z",
  "status": "scheduled"
}
```

**What it does**: Schedules a call to be executed at a specific time. Validates user permissions before scheduling. Defaults to 1 minute from now if no time specified.

---

#### **GET /mobile/call-history**

**Purpose**: Get user's call history
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Query Parameters**:

- `limit` (optional): Number of calls to return (default: 10)

**Response**:

```json
{
  "call_history": [
    {
      "id": 456,
      "phone_number": "+1234567890",
      "scenario": "default",
      "status": "completed",
      "created_at": "2024-01-14T10:30:00Z",
      "call_sid": "CA1234567890abcdef"
    }
  ],
  "total_calls": 1
}
```

**What it does**: Returns recent call history for the authenticated user, including call status and metadata.

---

### **Subscription Management Endpoints**

#### **POST /mobile/purchase-subscription**

**Purpose**: Handle App Store subscription and addon purchases with receipt validation
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`
- `Content-Type: application/json`

**Request Body**:

```json
{
  "receipt_data": "base64_encoded_receipt_from_app_store",
  "is_sandbox": false,
  "product_id": "speech_assistant_basic_weekly"
}
```

**Response**:

```json
{
  "success": true,
  "message": "Purchase processed successfully!",
  "usage_stats": {
    "subscription_tier": "mobile_basic",
    "is_subscribed": true,
    "calls_remaining_this_week": 5,
    "calls_remaining_this_month": 30,
    "addon_calls_remaining": 0
  }
}
```

**Supported Product IDs**:

- `speech_assistant_basic_weekly` - Basic Plan ($4.99/week, 5 calls)
- `speech_assistant_premium_monthly` - Premium Plan ($25/month, 30 calls)
- `speech_assistant_addon_calls` - Addon Calls ($4.99, 5 additional calls)

**What it does**:

1. **Validates App Store receipt** with Apple's servers
2. **Extracts subscription information** from validated receipt
3. **Prevents duplicate processing** of the same transaction
4. **Processes based on product type** (subscription or addon)
5. **Updates user limits** with proper reset cycles and expiration dates
6. **Returns updated usage statistics**

---

#### **POST /mobile/upgrade-subscription** _(Legacy - Use purchase-subscription instead)_

**Purpose**: Handle legacy App Store subscription purchases
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`
- `Content-Type: application/json`

**Request Body**:

```json
{
  "receipt_data": "base64_encoded_receipt_from_app_store",
  "is_sandbox": false,
  "subscription_tier": "mobile_weekly"
}
```

**Response**:

```json
{
  "success": true,
  "message": "Successfully upgraded to weekly subscription!",
  "subscription_tier": "mobile_weekly",
  "usage_stats": {
    "is_subscribed": true,
    "subscription_tier": "mobile_weekly",
    "trial_calls_remaining": 0
  }
}
```

**What it does**:

1. **Validates App Store receipt** with Apple's servers
2. **Extracts subscription information** from validated receipt
3. **Prevents duplicate processing** of the same transaction
4. **Upgrades user to paid subscription** with proper expiration dates
5. **Removes trial limitations** and updates usage statistics

---

#### **POST /mobile/app-store/webhook**

**Purpose**: Handle App Store server notifications for subscription events
**Headers Required**:

- `Content-Type: application/json`
- `x-apple-signature` (optional): For webhook signature verification

**Request Body**:

```json
{
  "signedPayload": "jwt_signed_payload_from_apple",
  "notificationType": "RENEWAL",
  "data": {
    "productId": "speech_assistant_weekly",
    "transactionId": "1000000123456789",
    "originalTransactionId": "1000000123456789",
    "expiresDate": "2024-01-22T10:30:00Z"
  }
}
```

**Response**:

```json
{
  "status": "success",
  "message": "Notification processed successfully"
}
```

**What it does**:

1. **Verifies webhook signature** (if configured)
2. **Processes subscription events** (renewals, cancellations, billing issues)
3. **Updates subscription status** in the database
4. **Handles automatic renewals** and subscription state changes

---

#### **GET /mobile/subscription-status**

**Purpose**: Get detailed subscription status for mobile user
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "subscription_tier": "mobile_weekly",
  "subscription_status": "active",
  "is_subscribed": true,
  "subscription_start_date": "2024-01-15T10:30:00Z",
  "subscription_end_date": "2024-01-22T10:30:00Z",
  "next_payment_date": "2024-01-22T10:30:00Z",
  "billing_cycle": "weekly",
  "app_store_transaction_id": "1000000123456789",
  "app_store_product_id": "speech_assistant_weekly"
}
```

**What it does**: Returns comprehensive subscription information including App Store transaction details and billing cycle information.

---

## Call Duration Tracking & Limits

### **Duration Limits by Plan**

- **Trial**: 60 seconds per call
- **Basic Plan**: 60 seconds per call
- **Premium Plan**: 120 seconds per call
- **Addon Calls**: Follows the user's current plan limit

### **Call End Webhook**

The backend automatically tracks call duration through Twilio's status callback system:

- **Endpoint**: `/call-end-webhook`
- **Trigger**: When a call completes (status: completed)
- **Data**: CallSid and CallDuration from Twilio
- **Action**: Updates user's usage with actual call duration

### **Duration Enforcement**

- **Simple enforcement**: Calls are automatically terminated when duration limit is reached
- **No AI warnings**: Clean termination without interruption messages
- **Real-time tracking**: Duration is monitored during the call
- **Accurate billing**: Actual call duration is recorded for usage tracking

---

## Authentication Flow

### **1. User Registration**

```swift
// Register new user
struct RegisterRequest: Codable {
    let email: String
    let password: String
}

struct AuthResponse: Codable {
    let access_token: String
    let refresh_token: String
    let token_type: String
}

func registerUser(email: String, password: String) async throws -> AuthResponse {
    let url = URL(string: "\(baseURL)/auth/register")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("mobile", forHTTPHeaderField: "X-App-Type") // Important!
    request.setValue("Speech-Assistant-Mobile-iOS/1.0", forHTTPHeaderField: "User-Agent")

    let registerData = RegisterRequest(email: email, password: password)
    request.httpBody = try JSONEncoder().encode(registerData)

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(AuthResponse.self, from: data)
}
```

### **2. User Login**

```swift
func loginUser(email: String, password: String) async throws -> AuthResponse {
    let url = URL(string: "\(baseURL)/auth/login")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    request.setValue("mobile", forHTTPHeaderField: "X-App-Type")

    let body = "username=\(email)&password=\(password)"
    request.httpBody = body.data(using: .utf8)

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(AuthResponse.self, from: data)
}
```

### **3. Token Management**

```swift
class AuthManager: ObservableObject {
    @Published var isAuthenticated = false
    private var accessToken: String?
    private var refreshToken: String?

    func setTokens(_ response: AuthResponse) {
        self.accessToken = response.access_token
        self.refreshToken = response.refresh_token
        self.isAuthenticated = true

        // Store in Keychain
        KeychainHelper.store(response.access_token, forKey: "access_token")
        KeychainHelper.store(response.refresh_token, forKey: "refresh_token")
    }

    func getAuthHeaders() -> [String: String] {
        guard let token = accessToken else { return [:] }
        return [
            "Authorization": "Bearer \(token)",
            "X-App-Type": "mobile",
            "User-Agent": "Speech-Assistant-Mobile-iOS/1.0"
        ]
    }
}
```

---

## Usage & Trial Management

### **1. Check Usage Stats**

```swift
struct UsageStats: Codable {
    let app_type: String
    let is_trial_active: Bool
    let trial_calls_remaining: Int
    let trial_calls_used: Int
    let calls_made_today: Int
    let calls_made_this_week: Int
    let calls_made_this_month: Int
    let calls_made_total: Int
    let is_subscribed: Bool
    let subscription_tier: String?
    let upgrade_recommended: Bool
    let total_call_duration_this_week: Int?
    let total_call_duration_this_month: Int?
    let addon_calls_remaining: Int?
    let addon_calls_expiry: String?
    let week_start_date: String?
    let month_start_date: String?
}

struct PricingInfo: Codable {
    let plans: [PricingPlan]
    let addon: AddonPlan
}

struct PricingPlan: Codable {
    let id: String
    let name: String
    let price: String
    let billing: String
    let calls: String
    let duration_limit: String
    let features: [String]
}

struct AddonPlan: Codable {
    let id: String
    let name: String
    let price: String
    let calls: String
    let expires: String
    let description: String
}

func getUsageStats() async throws -> UsageStats {
    let url = URL(string: "\(baseURL)/mobile/usage-stats")!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"

    // Add auth headers
    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(UsageStats.self, from: data)
}
```

### **2. Check Call Permission Before Making Calls**

```swift
struct CallPermission: Codable {
    let can_make_call: Bool
    let status: String
    let details: CallPermissionDetails
}

struct CallPermissionDetails: Codable {
    let calls_remaining_this_week: Int?
    let calls_remaining_this_month: Int?
    let duration_limit: Int?
    let addon_calls_remaining: Int?
    let trial_ends: String?
    let app_type: String?
    let message: String?
    let upgrade_options: [UpgradeOption]?
}

struct UpgradeOption: Codable {
    let plan: String
    let price: String
    let calls: String
    let product_id: String
}

func checkCallPermission() async throws -> CallPermission {
    let url = URL(string: "\(baseURL)/mobile/check-call-permission")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(CallPermission.self, from: data)
}
```

---

## Making Calls

### **1. Available Scenarios**

The Speech Assistant offers a comprehensive collection of scenarios designed for various use cases, from entertainment to emotional support. All scenarios are available to mobile users, giving you flexibility in your frontend to display and categorize them as needed.

#### **Complete Scenarios List**

```swift
struct Scenario: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let icon: String
    let category: String  // New field for frontend categorization
    let is_family_friendly: Bool  // New field for content filtering
}

struct ScenariosResponse: Codable {
    let scenarios: [Scenario]
}

func getAvailableScenarios() async throws -> [Scenario] {
    let url = URL(string: "\(baseURL)/mobile/scenarios")!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"

    let (data, _) = try await URLSession.shared.data(for: request)
    let response = try JSONDecoder().decode(ScenariosResponse.self, from: data)
    return response.scenarios
}
```

#### **All Available Scenarios by Category**

**🎭 Entertainment & Fun**

- `default` - Friendly Chat (casual conversation) - **Voice**: `alloy` (Female)
- `celebrity` - Celebrity Interview (chat with virtual celebrity) - **Voice**: `alloy` (Female)
- `comedian` - Stand-up Comedian (funny jokes and comedy) - **Voice**: `ash` (Male)
- `storyteller` - Storyteller (engaging stories and tales) - **Voice**: `alloy` (Female)
- `yacht_party` - Yacht Party Host (exclusive party planning) - **Voice**: `ash` (Male)
- `instigator` - Drama Starter (gossip and drama) - **Voice**: `ash` (Male)

**💼 Professional & Business**

- `sales_pitch` - Sales Professional (persuasive sales calls) - **Voice**: `echo` (Male)
- `customer_service` - Customer Service Rep (helpful support) - **Voice**: `coral` (Female)
- `real_estate` - Aggressive Real Estate Agent (pushy property deals) - **Voice**: `echo` (Male)

**🏥 Emergency & Crisis**

- `sister_emergency` - Sister Emergency (family crisis support) - **Voice**: `coral` (Female)
- `mother_emergency` - Mother Emergency (elderly parent care) - **Voice**: `sage` (Female)

**💕 Romantic & Relationships**

- `caring_partner` - Caring Partner (daily relationship check-in) - **Voice**: `alloy` (Female)
- `surprise_date_planner` - Surprise Date Planner (romantic planning) - **Voice**: `ash` (Male)
- `long_distance_love` - Long Distance Love (relationship support) - **Voice**: `coral` (Female)

**👨‍👩‍👧‍👦 Family & Friendship**

- `supportive_bestie` - Supportive Best Friend (emotional support) - **Voice**: `coral` (Female)
- `encouraging_parent` - Encouraging Parent (parental guidance) - **Voice**: `alloy` (Female)
- `caring_sibling` - Caring Sibling (sibling support) - **Voice**: `echo` (Male)

**🚀 Motivational & Wellness**

- `therapist` - Life Coach (supportive conversation) - **Voice**: `coral` (Female)
- `motivational_coach` - Motivational Coach (goal achievement) - **Voice**: `ash` (Male)
- `wellness_checkin` - Wellness Check-in (mental health support) - **Voice**: `sage` (Female)

**🎉 Celebration & Gratitude**

- `celebration_caller` - Celebration Caller (success celebration) - **Voice**: `shimmer` (Female)
- `birthday_wishes` - Birthday Wishes (birthday celebrations) - **Voice**: `shimmer` (Female)
- `gratitude_caller` - Gratitude Caller (appreciation expression) - **Voice**: `verse` (Male)

#### **Frontend Categorization Suggestions**

```swift
enum ScenarioCategory: String, CaseIterable {
    case entertainment = "Entertainment"
    case professional = "Professional"
    case emergency = "Emergency"
    case romantic = "Romantic"
    case family = "Family & Friends"
    case motivational = "Motivational"
    case celebration = "Celebration"

    var icon: String {
        switch self {
        case .entertainment: return "🎭"
        case .professional: return "💼"
        case .emergency: return "🏥"
        case .romantic: return "💕"
        case .family: return "👨‍👩‍👧‍👦"
        case .motivational: return "🚀"
        case .celebration: return "🎉"
        }
    }

    var scenarios: [String] {
        switch self {
        case .entertainment:
            return ["default", "celebrity", "comedian", "storyteller", "yacht_party", "instigator"]
        case .professional:
            return ["sales_pitch", "customer_service", "real_estate"]
        case .emergency:
            return ["sister_emergency", "mother_emergency"]
        case .romantic:
            return ["caring_partner", "surprise_date_planner", "long_distance_love"]
        case .family:
            return ["supportive_bestie", "encouraging_parent", "caring_sibling"]
        case .motivational:
            return ["therapist", "motivational_coach", "wellness_checkin"]
        case .celebration:
            return ["celebration_caller", "birthday_wishes", "gratitude_caller"]
        }
    }
}
```

#### **Family-Friendly Content Filtering**

For App Store compliance and family-friendly content, you can filter scenarios:

```swift
extension Scenario {
    var isFamilyFriendly: Bool {
        // Scenarios that are safe for all audiences
        let familyFriendlyScenarios = [
            "default", "celebrity", "comedian", "storyteller",
            "customer_service", "caring_partner", "surprise_date_planner",
            "long_distance_love", "supportive_bestie", "encouraging_parent",
            "caring_sibling", "therapist", "motivational_coach",
            "wellness_checkin", "celebration_caller", "birthday_wishes",
            "gratitude_caller"
        ]
        return familyFriendlyScenarios.contains(id)
    }

    var isRomantic: Bool {
        let romanticScenarios = [
            "caring_partner", "surprise_date_planner", "long_distance_love"
        ]
        return romanticScenarios.contains(id)
    }

    var isProfessional: Bool {
        let professionalScenarios = [
            "sales_pitch", "customer_service", "real_estate"
        ]
        return professionalScenarios.contains(id)
    }
}
```

### **2. Make a Call**

```swift
struct MakeCallRequest: Codable {
    let phone_number: String
    let scenario: String
}

struct CallResponse: Codable {
    let call_sid: String
    let status: String
    let duration_limit: Int
    let usage_stats: UsageStatsUpdate
}

struct UsageStatsUpdate: Codable {
    let calls_remaining_this_week: Int?
    let calls_remaining_this_month: Int?
    let addon_calls_remaining: Int?
    let upgrade_recommended: Bool
}

func makeCall(phoneNumber: String, scenario: String) async throws -> CallResponse {
    // First check permission
    let permission = try await checkCallPermission()

    if !permission.can_make_call {
        if permission.status == "trial_calls_exhausted" {
            // Show upgrade prompt
            throw CallError.trialExhausted
        } else {
            throw CallError.permissionDenied(permission.details.message ?? "Cannot make call")
        }
    }

    let url = URL(string: "\(baseURL)/mobile/make-call")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let callData = MakeCallRequest(phone_number: phoneNumber, scenario: scenario)
    request.httpBody = try JSONEncoder().encode(callData)

    let (data, response) = try await URLSession.shared.data(for: request)

    // Handle payment required (402) status
    if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 402 {
        let errorData = try JSONDecoder().decode(PaymentRequiredError.self, from: data)
        throw CallError.paymentRequired(errorData)
    }

    return try JSONDecoder().decode(CallResponse.self, from: data)
}
```

### **3. Error Handling**

```swift
enum CallError: Error, LocalizedError {
    case trialExhausted
    case permissionDenied(String)
    case paymentRequired(PaymentRequiredError)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .trialExhausted:
            return "Your 3 free trial calls have been used. Upgrade to Basic ($4.99/week) for 5 calls per week!"
        case .permissionDenied(let message):
            return message
        case .paymentRequired(let error):
            return error.detail.message
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}

struct PaymentRequiredError: Codable {
    let detail: PaymentDetail
}

struct PaymentDetail: Codable {
    let error: String
    let message: String
    let upgrade_options: [UpgradeOption]?
    let timestamp: String?
}
```

---

## Subscription Management

### **1. App Store Integration**

```swift
import StoreKit

class SubscriptionManager: NSObject, ObservableObject {
    @Published var isSubscribed = false

    private let productIDs = [
        "speech_assistant_basic_weekly",
        "speech_assistant_premium_monthly",
        "speech_assistant_addon_calls"
    ]
    private var product: Product?

    override init() {
        super.init()
        Task {
            await loadProducts()
        }
    }

    func loadProducts() async {
        do {
            let products = try await Product.products(for: productIDs)
            // Store all products for different subscription tiers
            self.products = products
        } catch {
            print("Failed to load products: \(error)")
        }
    }

    func purchaseSubscription(productID: String) async throws {
        guard let product = products.first(where: { $0.id == productID }) else {
            throw SubscriptionError.productNotFound
        }

        let result = try await product.purchase()

        switch result {
        case .success(let verification):
            let transaction = try checkVerified(verification)

            // Send to backend
            try await purchaseSubscription(productID: product.id, transaction: transaction)

            await transaction.finish()
            self.isSubscribed = true

        case .pending:
            // Handle pending transaction
            break

        case .userCancelled:
            throw SubscriptionError.userCancelled

        @unknown default:
            break
        }
    }

    func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified:
            throw SubscriptionError.unverifiedTransaction
        case .verified(let safe):
            return safe
        }
    }
}
```

### **2. Send Purchase to Backend**

```swift
struct UpgradeRequest: Codable {
    let receipt_data: String  // Base64 encoded receipt data
    let is_sandbox: Bool      // Whether this is a sandbox receipt
    let subscription_tier: String
}

struct UpgradeResponse: Codable {
    let success: Bool
    let message: String
    let subscription_tier: String
    let usage_stats: UsageStats
}

func purchaseSubscription(productID: String, transaction: Transaction) async throws -> PurchaseResponse {
    let url = URL(string: "\(baseURL)/mobile/purchase-subscription")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    // Get the receipt data from the app
    let receiptData = try await AppStore.receiptData()
    let receiptString = receiptData.base64EncodedString()

    // Determine if this is a sandbox receipt
    let isSandbox = transaction.environment == .sandbox

    let purchaseData = PurchaseRequest(
        receipt_data: receiptString,
        is_sandbox: isSandbox,
        product_id: productID
    )
    request.httpBody = try JSONEncoder().encode(purchaseData)

    let (data, response) = try await URLSession.shared.data(for: request)

    // Handle potential errors
    if let httpResponse = response as? HTTPURLResponse {
        switch httpResponse.statusCode {
        case 400:
            let errorData = try JSONDecoder().decode(UpgradeError.self, from: data)
            throw SubscriptionError.backendError(errorData.detail)
        case 500:
            throw SubscriptionError.serverError
        default:
            break
        }
    }

    return try JSONDecoder().decode(PurchaseResponse.self, from: data)
}

struct PurchaseRequest: Codable {
    let receipt_data: String
    let is_sandbox: Bool
    let product_id: String
}

struct PurchaseResponse: Codable {
    let success: Bool
    let message: String
    let usage_stats: UsageStats
}

// Error handling for subscription purchases
enum SubscriptionError: Error, LocalizedError {
    case productNotFound
    case userCancelled
    case unverifiedTransaction
    case backendError(String)
    case serverError

    var errorDescription: String? {
        switch self {
        case .productNotFound:
            return "Subscription product not found"
        case .userCancelled:
            return "Purchase was cancelled"
        case .unverifiedTransaction:
            return "Transaction could not be verified"
        case .backendError(let message):
            return message
        case .serverError:
            return "Server error occurred"
        }
    }
}

struct PurchaseError: Codable {
    let detail: String
}
```

---

## UI Integration Examples

### **1. Main Call Screen**

```swift
struct CallScreen: View {
    @StateObject private var authManager = AuthManager()
    @StateObject private var subscriptionManager = SubscriptionManager()
    @State private var usageStats: UsageStats?
    @State private var scenarios: [Scenario] = []
    @State private var selectedScenario = "default"
    @State private var phoneNumber = ""
    @State private var showingUpgradeAlert = false

    var body: some View {
        VStack(spacing: 20) {
            // Usage Stats Display
            if let stats = usageStats {
                UsageStatsView(stats: stats)
            }

            // Phone Number Input
            TextField("Phone Number", text: $phoneNumber)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .keyboardType(.phonePad)

            // Scenario Picker
            Picker("Scenario", selection: $selectedScenario) {
                ForEach(scenarios) { scenario in
                    HStack {
                        Text(scenario.icon)
                        Text(scenario.name)
                    }.tag(scenario.id)
                }
            }
            .pickerStyle(MenuPickerStyle())

            // Call Button
            Button(action: makeCall) {
                Text("Make Call")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(canMakeCall ? Color.blue : Color.gray)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
            .disabled(!canMakeCall)

            // Upgrade Buttons (if needed)
            if usageStats?.upgrade_recommended == true {
                VStack(spacing: 10) {
                    Button("Upgrade to Basic ($4.99/week)") {
                        Task {
                            try await subscriptionManager.purchaseSubscription(productID: "speech_assistant_basic_weekly")
                        }
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Upgrade to Premium ($25/month)") {
                        Task {
                            try await subscriptionManager.purchaseSubscription(productID: "speech_assistant_premium_monthly")
                        }
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding()
        .onAppear {
            Task {
                await loadData()
            }
        }
    }

    private var canMakeCall: Bool {
        guard let stats = usageStats else { return false }
        return stats.is_subscribed || stats.trial_calls_remaining > 0 || (stats.addon_calls_remaining ?? 0) > 0
    }

    private func makeCall() {
        Task {
            do {
                let response = try await APIClient.shared.makeCall(
                    phoneNumber: phoneNumber,
                    scenario: selectedScenario
                )
                // Update UI with response
                await loadUsageStats()
            } catch CallError.trialExhausted {
                showingUpgradeAlert = true
            } catch {
                // Handle other errors
                print("Call failed: \(error)")
            }
        }
    }

    private func loadData() async {
        await loadUsageStats()
        await loadScenarios()
    }

    private func loadUsageStats() async {
        do {
            usageStats = try await APIClient.shared.getUsageStats()
        } catch {
            print("Failed to load usage stats: \(error)")
        }
    }

    private func loadScenarios() async {
        do {
            scenarios = try await APIClient.shared.getAvailableScenarios()
        } catch {
            print("Failed to load scenarios: \(error)")
        }
    }
}
```

### **2. Usage Stats Display**

```swift
struct UsageStatsView: View {
    let stats: UsageStats

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Plan Status")
                    .font(.headline)
                Spacer()
                if stats.is_subscribed {
                    Text("\(stats.subscription_tier?.replacingOccurrences(of: "mobile_", with: "").capitalized ?? "Subscribed") ✅")
                        .foregroundColor(.green)
                } else if stats.is_trial_active {
                    Text("Trial Active")
                        .foregroundColor(.blue)
                } else {
                    Text("Trial Ended")
                        .foregroundColor(.red)
                }
            }

            if stats.is_trial_active && !stats.is_subscribed {
                HStack {
                    Text("Trial Calls Remaining:")
                    Spacer()
                    Text("\(stats.trial_calls_remaining)")
                        .fontWeight(.bold)
                        .foregroundColor(stats.trial_calls_remaining > 0 ? .green : .red)
                }
            }

            if stats.is_subscribed {
                if stats.subscription_tier == "mobile_basic" {
                    HStack {
                        Text("Calls This Week:")
                        Spacer()
                        Text("\(stats.calls_made_this_week ?? 0)/5")
                            .fontWeight(.bold)
                    }
                } else if stats.subscription_tier == "mobile_premium" {
                    HStack {
                        Text("Calls This Month:")
                        Spacer()
                        Text("\(stats.calls_made_this_month ?? 0)/30")
                            .fontWeight(.bold)
                    }
                }
            }

            if let addonCalls = stats.addon_calls_remaining, addonCalls > 0 {
                HStack {
                    Text("Addon Calls:")
                    Spacer()
                    Text("\(addonCalls)")
                        .fontWeight(.bold)
                        .foregroundColor(.orange)
                }
            }

            HStack {
                Text("Total Calls Made:")
                Spacer()
                Text("\(stats.calls_made_total)")
            }

            if stats.upgrade_recommended {
                HStack {
                    Text("💡 Ready to upgrade?")
                        .foregroundColor(.orange)
                    Spacer()
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(10)
    }
}
```

---

## Voice Configuration & Options

### **Available Voice Types with Gender & Accent Classification**

The Speech Assistant uses OpenAI's actual text-to-speech voices. Here's the complete classification with gender, accent, and personality characteristics:

#### **Complete Voice Classification System**

```swift
enum VoiceType: String, CaseIterable {
    case alloy = "alloy"
    case ash = "ash"
    case ballad = "ballad"
    case coral = "coral"
    case echo = "echo"
    case sage = "sage"
    case shimmer = "shimmer"
    case verse = "verse"

    var displayName: String {
        switch self {
        case .alloy: return "Alloy"
        case .ash: return "Ash"
        case .ballad: return "Ballad"
        case .coral: return "Coral"
        case .echo: return "Echo"
        case .sage: return "Sage"
        case .shimmer: return "Shimmer"
        case .verse: return "Verse"
        }
    }

    var gender: VoiceGender {
        switch self {
        case .alloy, .coral, .sage, .shimmer:
            return .female
        case .ash, .ballad, .echo, .verse:
            return .male
        }
    }

    var accent: VoiceAccent {
        switch self {
        case .ballad:
            return .british
        case .alloy, .ash, .coral, .echo, .sage, .shimmer, .verse:
            return .american
        }
    }

    var personality: VoicePersonality {
        switch self {
        case .alloy: return .warm_engaging
        case .ash: return .energetic_upbeat
        case .ballad: return .professional_neutral
        case .coral: return .gentle_supportive
        case .echo: return .professional_neutral
        case .sage: return .gentle_supportive
        case .shimmer: return .energetic_upbeat
        case .verse: return .warm_engaging
        }
    }

    var description: String {
        switch self {
        case .alloy: return "Warm and engaging female voice"
        case .ash: return "Energetic and upbeat male voice"
        case .ballad: return "Professional British male voice"
        case .coral: return "Gentle and supportive female voice"
        case .echo: return "Clear and professional male voice"
        case .sage: return "Calm and wise female voice"
        case .shimmer: return "Excited and enthusiastic female voice"
        case .verse: return "Warm and engaging male voice"
        }
    }

    var emoji: String {
        switch self {
        case .alloy: return "😊"
        case .ash: return "🎉"
        case .ballad: return "🇬🇧"
        case .coral: return "🤗"
        case .echo: return "💼"
        case .sage: return "🧘‍♀️"
        case .shimmer: return "✨"
        case .verse: return "😊"
        }
    }
}

enum VoiceGender: String, CaseIterable {
    case male = "male"
    case female = "female"

    var displayName: String {
        switch self {
        case .male: return "Male"
        case .female: return "Female"
        }
    }

    var emoji: String {
        switch self {
        case .male: return "👨"
        case .female: return "👩"
        }
    }
}

enum VoiceAccent: String, CaseIterable {
    case american = "american"
    case british = "british"

    var displayName: String {
        switch self {
        case .american: return "American"
        case .british: return "British"
        }
    }

    var emoji: String {
        switch self {
        case .american: return "🇺🇸"
        case .british: return "🇬🇧"
        }
    }
}

enum VoicePersonality: String, CaseIterable {
    case warm_engaging = "warm_engaging"
    case energetic_upbeat = "energetic_upbeat"
    case gentle_supportive = "gentle_supportive"
    case professional_neutral = "professional_neutral"

    var displayName: String {
        switch self {
        case .warm_engaging: return "Warm & Engaging"
        case .energetic_upbeat: return "Energetic & Upbeat"
        case .gentle_supportive: return "Gentle & Supportive"
        case .professional_neutral: return "Professional & Neutral"
        }
    }
}
```

#### **Voice Configuration Details**

Each scenario includes specific voice configuration with temperature settings that control voice variation:

```swift
struct VoiceConfig: Codable {
    let voice: String
    let temperature: Double

    var temperatureDescription: String {
        switch temperature {
        case 0.0...0.3: return "Very Consistent"
        case 0.4...0.6: return "Consistent"
        case 0.7...0.8: return "Moderate Variation"
        case 0.9...1.0: return "High Variation"
        default: return "Unknown"
        }
    }
}
```

#### **Enhanced Voice Selection UI with Filtering**

```swift
struct EnhancedVoiceSelectionView: View {
    @Binding var selectedVoice: VoiceType
    @State private var selectedGender: VoiceGender?
    @State private var selectedAccent: VoiceAccent?
    @State private var selectedPersonality: VoicePersonality?

    let scenario: Scenario

    var filteredVoices: [VoiceType] {
        var voices = VoiceType.allCases

        if let gender = selectedGender {
            voices = voices.filter { $0.gender == gender }
        }

        if let accent = selectedAccent {
            voices = voices.filter { $0.accent == accent }
        }

        if let personality = selectedPersonality {
            voices = voices.filter { $0.personality == personality }
        }

        return voices
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Voice Selection")
                .font(.headline)

            Text("Scenario: \(scenario.name)")
                .font(.subheadline)
                .foregroundColor(.secondary)

            // Filter Controls
            VStack(spacing: 12) {
                // Gender Filter
                HStack {
                    Text("Gender:")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    HStack(spacing: 8) {
                        ForEach(VoiceGender.allCases, id: \.self) { gender in
                            FilterChip(
                                title: "\(gender.emoji) \(gender.displayName)",
                                isSelected: selectedGender == gender,
                                action: {
                                    if selectedGender == gender {
                                        selectedGender = nil
                                    } else {
                                        selectedGender = gender
                                    }
                                }
                            )
                        }
                    }
                }

                // Accent Filter
                HStack {
                    Text("Accent:")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    HStack(spacing: 8) {
                        ForEach(VoiceAccent.allCases, id: \.self) { accent in
                            FilterChip(
                                title: "\(accent.emoji) \(accent.displayName)",
                                isSelected: selectedAccent == accent,
                                action: {
                                    if selectedAccent == accent {
                                        selectedAccent = nil
                                    } else {
                                        selectedAccent = accent
                                    }
                                }
                            )
                        }
                    }
                }

                // Personality Filter
                HStack {
                    Text("Personality:")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    HStack(spacing: 8) {
                        ForEach(VoicePersonality.allCases, id: \.self) { personality in
                            FilterChip(
                                title: personality.displayName,
                                isSelected: selectedPersonality == personality,
                                action: {
                                    if selectedPersonality == personality {
                                        selectedPersonality = nil
                                    } else {
                                        selectedPersonality = personality
                                    }
                                }
                            )
                        }
                    }
                }
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)

            // Clear Filters Button
            if selectedGender != nil || selectedAccent != nil || selectedPersonality != nil {
                Button("Clear All Filters") {
                    selectedGender = nil
                    selectedAccent = nil
                    selectedPersonality = nil
                }
                .foregroundColor(.blue)
                .font(.caption)
            }

            // Voice Grid
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 2), spacing: 12) {
                ForEach(filteredVoices, id: \.self) { voice in
                    EnhancedVoiceOptionCard(
                        voice: voice,
                        isSelected: selectedVoice == voice,
                        isRecommended: voice == scenario.recommendedVoice
                    ) {
                        selectedVoice = voice
                    }
                }
            }

            if filteredVoices.isEmpty {
                Text("No voices match your current filters")
                    .foregroundColor(.secondary)
                    .padding()
            }
        }
        .padding()
    }
}

struct FilterChip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.blue : Color(.systemGray5))
                .foregroundColor(isSelected ? .white : .primary)
                .cornerRadius(16)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct EnhancedVoiceOptionCard: View {
    let voice: VoiceType
    let isSelected: Bool
    let isRecommended: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Text(voice.emoji)
                    .font(.title)

                Text(voice.displayName)
                    .font(.caption)
                    .fontWeight(.medium)

                // Gender and Accent badges
                HStack(spacing: 4) {
                    Text(voice.gender.emoji)
                        .font(.caption2)

                    Text(voice.accent.emoji)
                        .font(.caption2)
                }

                Text(voice.personality.displayName)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)

                if isRecommended {
                    Text("Recommended")
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(4)
                }
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(isSelected ? Color.blue.opacity(0.1) : Color(.systemGray6))
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isSelected ? Color.blue : Color.clear, lineWidth: 2)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}
```

#### **Voice Filtering Utilities**

```swift
extension VoiceType {
    static func filterByGender(_ gender: VoiceGender) -> [VoiceType] {
        return allCases.filter { $0.gender == gender }
    }

    static func filterByAccent(_ accent: VoiceAccent) -> [VoiceType] {
        return allCases.filter { $0.accent == accent }
    }

    static func filterByPersonality(_ personality: VoicePersonality) -> [VoiceType] {
        return allCases.filter { $0.personality == personality }
    }

    static func getVoicesForScenario(_ scenario: Scenario) -> [VoiceType] {
        // Return voices that match the scenario's recommended characteristics
        switch scenario.category {
        case "romantic", "family":
            return filterByPersonality(.warm_engaging)
        case "entertainment", "celebration":
            return filterByPersonality(.energetic_upbeat)
        case "motivational", "wellness":
            return filterByPersonality(.gentle_supportive)
        case "professional", "business":
            return filterByPersonality(.professional_neutral)
        default:
            return allCases
        }
    }
}
```

### **Voice Customization Options**

#### **Temperature Settings**

The temperature parameter controls how much variation the AI voice has:

- **0.0 - 0.3**: Very consistent, predictable voice (good for professional scenarios)
- **0.4 - 0.6**: Consistent with slight variation (good for family/relationship scenarios)
- **0.7 - 0.8**: Moderate variation (good for entertainment scenarios)
- **0.9 - 1.0**: High variation (good for dramatic/emotional scenarios)

#### **Voice Personality Matching**

```swift
struct VoicePersonalityMatcher {
    static func getOptimalVoice(for emotion: Emotion, context: ScenarioContext) -> VoiceType {
        switch emotion {
        case .excited, .happy:
            return .ash // Energetic male
        case .calm, .supportive:
            return .coral // Gentle female
        case .professional, .business:
            return .echo // Professional male
        case .romantic, .caring:
            return .alloy // Warm female
        case .worried, .concerned:
            return .coral // Gentle female
        case .aggressive, .direct:
            return .echo // Professional male
        case .wise, .experienced:
            return .sage // Wise female
        }
    }

    enum Emotion {
        case excited, happy, calm, supportive, professional, business
        case romantic, caring, worried, concerned, aggressive, direct, wise, experienced
    }

    enum ScenarioContext {
        case entertainment, business, emergency, romantic, family, motivational, celebration
    }
}
```

#### **Custom Scenario Voice Selection**

For custom scenarios, users can now filter voices by:

1. **Gender**: Male or Female voices
2. **Accent**: American or British accents
3. **Personality**: Warm, Energetic, Gentle, or Professional
4. **Combination**: Mix and match filters for perfect voice selection

This enhanced system makes it much easier for users to find the perfect voice for their custom scenarios while maintaining the professional quality of the app.

### **Quick Voice Filtering Reference**

#### **Filter Combinations for Common Use Cases**

```swift
// Get all female voices
let femaleVoices = VoiceType.filterByGender(.female)
// Result: [alloy, coral, sage, shimmer]

// Get all male voices
let maleVoices = VoiceType.filterByGender(.male)
// Result: [ash, ballad, echo, verse]

// Get all British voices
let britishVoices = VoiceType.filterByAccent(.british)
// Result: [ballad]

// Get all American voices
let americanVoices = VoiceType.filterByAccent(.american)
// Result: [alloy, ash, coral, echo, sage, shimmer, verse]

// Get warm and engaging voices
let warmVoices = VoiceType.filterByPersonality(.warm_engaging)
// Result: [alloy, verse]

// Get energetic voices
let energeticVoices = VoiceType.filterByPersonality(.energetic_upbeat)
// Result: [ash, shimmer]

// Get professional voices
let professionalVoices = VoiceType.filterByPersonality(.professional_neutral)
// Result: [ballad, echo]

// Get gentle voices
let gentleVoices = VoiceType.filterByPersonality(.gentle_supportive)
// Result: [coral, sage]
```

#### **Advanced Filtering Examples**

```swift
// Get female American voices
let femaleAmericanVoices = VoiceType.allCases.filter {
    $0.gender == .female && $0.accent == .american
}
// Result: [alloy, coral, sage, shimmer]

// Get male voices with warm personality
let warmMaleVoices = VoiceType.allCases.filter {
    $0.gender == .male && $0.personality == .warm_engaging
}
// Result: [verse]

// Get voices suitable for romantic scenarios
let romanticVoices = VoiceType.allCases.filter { voice in
    voice.personality == .warm_engaging ||
    voice.personality == .gentle_supportive
}
// Result: [alloy, coral, sage, verse]

// Get voices suitable for professional scenarios
let professionalScenarioVoices = VoiceType.allCases.filter { voice in
    voice.personality == .professional_neutral
}
// Result: [ballad, echo]
```

#### **Voice Selection Best Practices**

1. **For Romantic Scenarios**: Use `alloy` (warm female) or `verse` (warm male)
2. **For Professional Calls**: Use `echo` (professional male) or `ballad` (British professional male)
3. **For Entertainment**: Use `ash` (energetic male) or `shimmer` (energetic female)
4. **For Support/Wellness**: Use `coral` (gentle female) or `sage` (wise female)
5. **For Family Scenarios**: Use `alloy` (warm female) or `coral` (gentle female)

## Additional Features

### **1. Call History**

```swift
func getCallHistory(limit: Int = 10) async throws -> [CallHistoryItem] {
    let url = URL(string: "\(baseURL)/mobile/call-history?limit=\(limit)")!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let (data, _) = try await URLSession.shared.data(for: request)
    let response = try JSONDecoder().decode(CallHistoryResponse.self, from: data)
    return response.call_history
}

struct CallHistoryResponse: Codable {
    let call_history: [CallHistoryItem]
    let total_calls: Int
}

struct CallHistoryItem: Codable, Identifiable {
    let id: Int
    let phone_number: String
    let scenario: String
    let status: String
    let created_at: String
    let call_sid: String
}
```

### **2. Schedule Future Calls**

```swift
func scheduleCall(phoneNumber: String, scenario: String, scheduledTime: Date) async throws -> ScheduledCallResponse {
    let url = URL(string: "\(baseURL)/mobile/schedule-call")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let formatter = ISO8601DateFormatter()
    let scheduleData = ScheduleCallRequest(
        phone_number: phoneNumber,
        scenario: scenario,
        scheduled_time: formatter.string(from: scheduledTime)
    )
    request.httpBody = try JSONEncoder().encode(scheduleData)

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(ScheduledCallResponse.self, from: data)
}
```

---

## App Store Compliance & Content Moderation

### **Content Safety Guidelines**

To ensure your app meets App Store guidelines and maintains a family-friendly environment, consider these content moderation strategies:

#### **Scenario Content Filtering**

```swift
struct ContentModerator {
    static let inappropriateKeywords = [
        "hate", "violence", "explicit", "inappropriate", "offensive"
    ]

    static func isScenarioAppropriate(for age: UserAge, scenario: Scenario) -> Bool {
        switch age {
        case .allAges:
            return scenario.isFamilyFriendly
        case .teenPlus:
            return scenario.isFamilyFriendly || scenario.isRomantic
        case .adult:
            return true // All scenarios allowed for adults
        }
    }

    enum UserAge: String, CaseIterable {
        case allAges = "4+"
        case teenPlus = "12+"
        case adult = "17+"

        var displayName: String {
            switch self {
            case .allAges: return "All Ages (4+)"
            case .teenPlus: return "Teen & Up (12+)"
            case .adult: return "Adult (17+)"
            }
        }
    }
}
```

#### **Age-Appropriate Scenario Display**

```swift
struct AgeAppropriateScenarioView: View {
    @State private var selectedAge: ContentModerator.UserAge = .allAges
    @State private var scenarios: [Scenario] = []

    var filteredScenarios: [Scenario] {
        scenarios.filter { scenario in
            ContentModerator.isScenarioAppropriate(for: selectedAge, scenario: scenario)
        }
    }

    var body: some View {
        VStack {
            Picker("Age Rating", selection: $selectedAge) {
                ForEach(ContentModerator.UserAge.allCases, id: \.self) { age in
                    Text(age.displayName).tag(age)
                }
            }
            .pickerStyle(SegmentedPickerStyle())
            .padding()

            List(filteredScenarios) { scenario in
                ScenarioRow(scenario: scenario)
            }
        }
        .navigationTitle("Scenarios")
    }
}
```

#### **Content Warning System**

```swift
struct ContentWarningView: View {
    let scenario: Scenario
    @State private var showingWarning = false

    var body: some View {
        VStack {
            if scenario.requiresContentWarning {
                Button("⚠️ Content Warning") {
                    showingWarning = true
                }
                .foregroundColor(.orange)
            }

            // Scenario content
        }
        .alert("Content Warning", isPresented: $showingWarning) {
            Button("Continue") { }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text(scenario.contentWarningMessage ?? "This scenario may contain content not suitable for all audiences.")
        }
    }
}

extension Scenario {
    var requiresContentWarning: Bool {
        // Scenarios that might need content warnings
        let warningScenarios = [
            "instigator", "real_estate", "sister_emergency", "mother_emergency"
        ]
        return warningScenarios.contains(id)
    }

    var contentWarningMessage: String? {
        switch id {
        case "instigator":
            return "This scenario involves gossip and drama that may not be suitable for all audiences."
        case "real_estate":
            return "This scenario involves aggressive sales tactics that may be intense."
        case "sister_emergency", "mother_emergency":
            return "This scenario involves emergency situations that may be distressing."
        default:
            return nil
        }
    }
}
```

### **App Store Review Guidelines Compliance**

#### **Content Rating Considerations**

- **4+ Rating**: Focus on family-friendly scenarios (default, celebrity, comedian, storyteller, customer_service, caring_partner, supportive_bestie, encouraging_parent, caring_sibling, therapist, motivational_coach, wellness_checkin, celebration_caller, birthday_wishes, gratitude_caller)
- **12+ Rating**: Include romantic scenarios (caring_partner, surprise_date_planner, long_distance_love)
- **17+ Rating**: Include all scenarios including emergency and business scenarios

#### **User-Generated Content Safety**

```swift
struct UserContentSafety {
    static func validateUserInput(_ input: String) -> ValidationResult {
        let inappropriateContent = checkForInappropriateContent(input)
        let spamContent = checkForSpamContent(input)

        if inappropriateContent {
            return .rejected(reason: "Content contains inappropriate material")
        } else if spamContent {
            return .rejected(reason: "Content appears to be spam")
        } else {
            return .approved
        }
    }

    enum ValidationResult {
        case approved
        case rejected(reason: String)
    }

    private static func checkForInappropriateContent(_ input: String) -> Bool {
        // Implement content filtering logic
        return false
    }

    private static func checkForSpamContent(_ input: String) -> Bool {
        // Implement spam detection logic
        return false
    }
}
```

#### **Reporting and Moderation System**

```swift
struct ContentReport {
    let id: UUID
    let scenarioId: String
    let reporterId: String
    let reason: ReportReason
    let description: String
    let timestamp: Date
    let status: ReportStatus

    enum ReportReason: String, CaseIterable {
        case inappropriate = "inappropriate"
        case offensive = "offensive"
        case spam = "spam"
        case other = "other"

        var displayName: String {
            switch self {
            case .inappropriate: return "Inappropriate Content"
            case .offensive: return "Offensive Language"
            case .spam: return "Spam or Misleading"
            case .other: return "Other"
            }
        }
    }

    enum ReportStatus: String {
        case pending = "pending"
        case reviewed = "reviewed"
        case resolved = "resolved"
        case dismissed = "dismissed"
    }
}

struct ReportContentView: View {
    @State private var selectedReason: ContentReport.ReportReason = .inappropriate
    @State private var description = ""
    let scenario: Scenario

    var body: some View {
        NavigationView {
            Form {
                Section("Report Reason") {
                    Picker("Reason", selection: $selectedReason) {
                        ForEach(ContentReport.ReportReason.allCases, id: \.self) { reason in
                            Text(reason.displayName).tag(reason)
                        }
                    }
                }

                Section("Additional Details") {
                    TextField("Describe the issue...", text: $description, axis: .vertical)
                        .lineLimit(3...6)
                }

                Section {
                    Button("Submit Report") {
                        submitReport()
                    }
                    .disabled(description.isEmpty)
                }
            }
            .navigationTitle("Report Content")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func submitReport() {
        // Implement report submission
    }
}
```

## Best Practices

### **1. Error Handling**

- Always check call permissions before making calls
- Handle trial exhaustion gracefully with upgrade prompts
- Provide clear error messages to users
- Implement retry logic for network failures

### **2. User Experience**

- Show trial status prominently in the UI
- Make upgrade process seamless
- Cache usage stats and refresh periodically
- Provide clear call history and status updates

### **3. Security**

- Store tokens securely in Keychain
- Always include proper headers for app identification
- Validate App Store transactions on the backend
- Handle token refresh automatically

### **4. Performance**

- Cache scenarios and pricing data
- Implement proper loading states
- Use background tasks for non-critical API calls
- Minimize API calls during active use

---

## Environment Configuration

### **Development vs Production**

```swift
struct APIConfig {
    static let development = APIConfig(
        baseURL: "http://localhost:5050",
        environment: .development
    )

    static let production = APIConfig(
        baseURL: "https://your-domain.com", // Replace with your actual domain
        environment: .production
    )

    let baseURL: String
    let environment: Environment

    enum Environment {
        case development
        case production
    }
}

// Usage
let config = APIConfig.development // Switch for production
```

### **Environment Switching for Mobile App**

#### **Development Environment**

- **Base URL**: `http://localhost:5050` (when testing with local backend)
- **Features**: Full debugging, testing endpoints available, no rate limits
- **Database**: Local SQLite for development
- **Use Case**: Development, testing, debugging

#### **Production Environment**

- **Base URL**: `https://your-actual-domain.com` (your Digital Ocean droplet)
- **Features**: Rate limiting, production security, PostgreSQL database
- **Database**: Production PostgreSQL with full data
- **Use Case**: Live app, real users, production data

#### **Implementation in iOS App**

```swift
class EnvironmentManager: ObservableObject {
    @Published var currentEnvironment: Environment = .development

    enum Environment: String, CaseIterable {
        case development = "Development"
        case production = "Production"

        var baseURL: String {
            switch self {
            case .development:
                return "http://localhost:5050"
            case .production:
                return "https://your-domain.com" // Replace with actual domain
            }
        }

        var displayName: String {
            return self.rawValue
        }
    }

    func switchEnvironment(_ environment: Environment) {
        currentEnvironment = environment
        // Save to UserDefaults or other persistent storage
        UserDefaults.standard.set(environment.rawValue, forKey: "selected_environment")
    }

    func loadSavedEnvironment() {
        if let saved = UserDefaults.standard.string(forKey: "selected_environment"),
           let environment = Environment(rawValue: saved) {
            currentEnvironment = environment
        }
    }
}

// Usage in your app
@StateObject private var environmentManager = EnvironmentManager()

// In your API calls
let baseURL = environmentManager.currentEnvironment.baseURL
```

#### **Build Configuration**

You can also use Xcode build configurations to automatically switch environments:

```swift
#if DEBUG
let baseURL = "http://localhost:5050"
#else
let baseURL = "https://your-domain.com"
#endif
```

**Important**: Remember to replace `https://your-domain.com` with your actual production domain or IP address.

---

## Testing Endpoints

### **Quick Test Commands**

```bash
# Register mobile user
curl -X POST http://localhost:5050/auth/register \
  -H "Content-Type: application/json" \
  -H "X-App-Type: mobile" \
  -d '{"email":"mobile@test.com","password":"password123"}'

# Get usage stats
curl -X GET http://localhost:5050/mobile/usage-stats \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-App-Type: mobile"

# Get scenarios
curl -X GET http://localhost:5050/mobile/scenarios \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-App-Type: mobile"

# Make a call
curl -X POST http://localhost:5050/mobile/make-call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-App-Type: mobile" \
  -d '{"phone_number":"+1234567890","scenario":"default"}'
```

### **Development Testing Endpoints**

**⚠️ IMPORTANT: These endpoints are for development only and bypass rate limits**

For development and testing purposes, the backend includes special endpoints that bypass normal rate limiting and usage checks:

```bash
# Test endpoint that bypasses rate limits (development only)
curl -X POST http://localhost:5050/test/bypass-rate-limit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"endpoint": "/mobile/make-call", "data": {"phone_number": "+1234567890", "scenario": "default"}}'

# Test endpoint for immediate call testing (development only)
curl -X POST http://localhost:5050/test/test-call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"phone_number": "+1234567890", "scenario": "default"}'
```

**Note**: These testing endpoints are automatically disabled in production mode and should only be used during development.

## 📋 Current Backend Status & Recent Changes

### **✅ What's Working & Ready**

- **Core Mobile API**: All endpoints fully functional
- **Authentication System**: JWT-based auth with mobile app support
- **Usage Tracking**: Complete trial and subscription management
- **Call Management**: Twilio integration working
- **Database**: PostgreSQL with full schema migration
- **Security**: Rate limiting, CORS, authentication implemented
- **Production Deployment**: Live on Digital Ocean droplet

### **❌ What Was Removed**

- **Random Calling Feature**: The AI-generated random call system was removed from this version
- **Background Scheduling**: Automated calling throughout the day feature removed
- **AI Persona Generation**: Dynamic prompt generation for random calls removed

### **🔧 What Was Fixed**

- **Database Migrations**: Resolved Alembic migration issues on production
- **Environment Loading**: Fixed environment variable loading in production
- **Service Management**: Proper systemd service configuration
- **Dependencies**: Resolved Python package compatibility issues

### **📱 Mobile App Impact**

- **No Changes Required**: All mobile app endpoints remain the same
- **Same API Structure**: No breaking changes to existing mobile integration
- **Production Ready**: Backend is now stable and ready for mobile app deployment
- **Testing Available**: Use development endpoints for testing, production for live app

## 🎉 Enhanced Mobile Features Summary

### **New Features Implemented**

✅ **Enhanced Pricing Tiers**

- Basic Plan: $4.99/week (5 calls, 1-minute limit)
- Premium Plan: $25/month (30 calls, 2-minute limit)
- Addon Calls: $4.99 (5 additional calls, 30-day expiry)

✅ **Duration Tracking & Limits**

- Real-time call duration monitoring
- Automatic call termination at limits
- Duration tracking for usage analytics

✅ **7-Day/30-Day Reset Cycles**

- Based on user start date (not calendar weeks)
- Automatic limit resets
- Addon call expiry management

✅ **Enhanced App Store Integration**

- Support for all subscription tiers
- Addon call purchases
- Comprehensive receipt validation

✅ **Improved Error Handling**

- Detailed upgrade options in error responses
- Consistent error format
- Better user guidance

### **Key Benefits**

- **Flexible Pricing**: Multiple tiers to suit different user needs
- **Accurate Tracking**: Real-time duration and usage monitoring
- **User-Friendly**: Clear upgrade paths and error messages
- **Scalable**: Easy to adjust limits and pricing as needed
- **App Store Compliant**: Full integration with Apple's payment system

This comprehensive guide provides everything your iOS development team needs to integrate with the enhanced Speech Assistant backend API. The mobile app now supports a complete entertainment-focused experience with flexible pricing tiers, accurate usage tracking, and seamless App Store integration.

---

## 📋 Complete Scenarios Reference

### **All Available Scenarios with Details**

| ID                      | Name                   | Category      | Voice ID  | Gender | Accent   | Temperature | Family Friendly | Description                   |
| ----------------------- | ---------------------- | ------------- | --------- | ------ | -------- | ----------- | --------------- | ----------------------------- |
| `default`               | Friendly Chat          | Entertainment | `alloy`   | Female | American | 0.7         | ✅              | Casual, friendly conversation |
| `celebrity`             | Celebrity Interview    | Entertainment | `alloy`   | Female | American | 0.7         | ✅              | Chat with a virtual celebrity |
| `comedian`              | Stand-up Comedian      | Entertainment | `ash`     | Male   | American | 0.8         | ✅              | Funny jokes and comedy bits   |
| `storyteller`           | Storyteller            | Entertainment | `alloy`   | Female | American | 0.7         | ✅              | Engaging stories and tales    |
| `yacht_party`           | Yacht Party Host       | Entertainment | `ash`     | Male   | American | 0.8         | ⚠️              | Exclusive party planning      |
| `instigator`            | Drama Starter          | Entertainment | `ash`     | Male   | American | 0.9         | ⚠️              | Gossip and drama creation     |
| `sales_pitch`           | Sales Professional     | Professional  | `echo`    | Male   | American | 0.7         | ✅              | Persuasive sales calls        |
| `customer_service`      | Customer Service Rep   | Professional  | `coral`   | Female | American | 0.6         | ✅              | Helpful support calls         |
| `real_estate`           | Real Estate Agent      | Professional  | `echo`    | Male   | American | 0.7         | ⚠️              | Pushy property deals          |
| `sister_emergency`      | Sister Emergency       | Emergency     | `coral`   | Female | American | 0.8         | ⚠️              | Family crisis support         |
| `mother_emergency`      | Mother Emergency       | Emergency     | `sage`    | Female | American | 0.6         | ⚠️              | Elderly parent care           |
| `caring_partner`        | Caring Partner         | Romantic      | `alloy`   | Female | American | 0.7         | ✅              | Daily relationship check-in   |
| `surprise_date_planner` | Surprise Date Planner  | Romantic      | `ash`     | Male   | American | 0.8         | ✅              | Romantic date planning        |
| `long_distance_love`    | Long Distance Love     | Romantic      | `coral`   | Female | American | 0.6         | ✅              | Relationship support          |
| `supportive_bestie`     | Supportive Best Friend | Family        | `coral`   | Female | American | 0.6         | ✅              | Emotional support             |
| `encouraging_parent`    | Encouraging Parent     | Family        | `alloy`   | Female | American | 0.5         | ✅              | Parental guidance             |
| `caring_sibling`        | Caring Sibling         | Family        | `echo`    | Male   | American | 0.6         | ✅              | Sibling support               |
| `therapist`             | Life Coach             | Motivational  | `coral`   | Female | American | 0.6         | ✅              | Supportive conversation       |
| `motivational_coach`    | Motivational Coach     | Motivational  | `ash`     | Male   | American | 0.8         | ✅              | Goal achievement              |
| `wellness_checkin`      | Wellness Check-in      | Motivational  | `sage`    | Female | American | 0.5         | ✅              | Mental health support         |
| `celebration_caller`    | Celebration Caller     | Celebration   | `shimmer` | Female | American | 0.9         | ✅              | Success celebration           |
| `birthday_wishes`       | Birthday Wishes        | Celebration   | `shimmer` | Female | American | 0.9         | ✅              | Birthday celebrations         |
| `gratitude_caller`      | Gratitude Caller       | Celebration   | `verse`   | Male   | American | 0.6         | ✅              | Appreciation expression       |

### **Voice ID Reference**

| Voice ID  | Gender | Accent   | Personality            | Best For                                 |
| --------- | ------ | -------- | ---------------------- | ---------------------------------------- |
| `alloy`   | Female | American | Warm & Engaging        | Romantic, family, friendly scenarios     |
| `ash`     | Male   | American | Energetic & Upbeat     | Entertainment, celebration, motivational |
| `ballad`  | Male   | British  | Professional & Neutral | Professional, business scenarios         |
| `coral`   | Female | American | Gentle & Supportive    | Support, wellness, caring scenarios      |
| `echo`    | Male   | American | Professional & Neutral | Business, professional, formal scenarios |
| `sage`    | Female | American | Gentle & Supportive    | Wellness, wisdom, calming scenarios      |
| `shimmer` | Female | American | Energetic & Upbeat     | Celebration, excitement, fun scenarios   |
| `verse`   | Male   | American | Warm & Engaging        | Romantic, friendly, warm scenarios       |

### **Legend**

- ✅ **Family Friendly**: Safe for all audiences (4+ rating)
- ⚠️ **Content Warning**: May need age restrictions or warnings
- **Voice ID**: Actual OpenAI voice identifier
- **Gender**: Male or Female voice
- **Accent**: American or British accent
- **Temperature**: Controls voice variation (0.0-1.0 scale)

### **Recommended App Store Ratings**

- **4+ Rating**: Use only family-friendly scenarios
- **12+ Rating**: Include romantic scenarios
- **17+ Rating**: Include all scenarios with appropriate warnings

### **Frontend Implementation Notes**

1. **Category Grouping**: Group scenarios by category for better user experience
2. **Age Filtering**: Implement age-appropriate content filtering
3. **Content Warnings**: Show warnings for scenarios that need them
4. **Voice Selection**: Allow users to customize voices within scenarios using the enhanced voice selection UI
5. **Voice Filtering**: Implement gender, accent, and personality filtering for custom scenarios
6. **Reporting System**: Implement content reporting for moderation

### **Custom Scenario Voice Selection**

When users create custom scenarios, they can now:

- **Filter by Gender**: Choose between male and female voices
- **Filter by Accent**: Select American or British accents
- **Filter by Personality**: Match voice characteristics to scenario mood
- **Combine Filters**: Mix and match for perfect voice selection
- **Preview Voices**: Test different voice combinations before finalizing

This comprehensive scenarios reference gives your iOS development team complete visibility into all available content, helping you build a user-friendly interface that complies with App Store guidelines while maximizing user engagement and providing powerful voice customization options.
