# Mobile Speech Assistant App - Backend Integration Guide

## Overview

This document provides comprehensive integration guidelines for the **Speech Assistant Mobile App** (iOS). The backend provides a complete consumer-focused API with trial management, usage tracking, and subscription handling specifically designed for mobile users.

## App Architecture

### **Consumer Mobile App Features**

- **7-Day Free Trial**: 3 free calls to test the service
- **Simple Pricing**: $4.99/week for unlimited calls
- **Fun Scenarios**: 5 pre-selected entertaining call scenarios
- **Easy Setup**: No complex onboarding - just sign up and start calling
- **Shared Infrastructure**: Uses system phone numbers (no individual provisioning needed)

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
  "calls_made_total": 1,
  "is_subscribed": false,
  "subscription_tier": null,
  "upgrade_recommended": false,
  "pricing": {
    "weekly_plan": {
      "price": "$4.99",
      "billing": "weekly",
      "features": ["Unlimited calls", "Fun scenarios", "Call friends"]
    }
  }
}
```

**What it does**: Returns comprehensive usage statistics including trial status, call counts, subscription info, and pricing details. Automatically initializes usage limits if not found.

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
  "status": "trial_active",
  "details": {
    "calls_remaining": 2,
    "trial_ends": "2024-01-15T10:30:00Z",
    "app_type": "mobile_consumer",
    "message": "You have 2 trial calls remaining"
  }
}
```

**What it does**: Validates if user has available trial calls or active subscription before allowing call initiation. Prevents unnecessary API calls when user can't make calls.

---

#### **GET /mobile/pricing**

**Purpose**: Get mobile app pricing information
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`

**Response**:

```json
{
  "weekly_plan": {
    "price": "$4.99",
    "billing": "weekly",
    "features": ["Unlimited calls", "Fun scenarios", "Call friends"]
  }
}
```

**What it does**: Returns mobile-specific pricing information for display in upgrade prompts and pricing screens.

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

**Purpose**: Initiate a phone call with usage tracking
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
  "usage_stats": {
    "trial_calls_remaining": 1,
    "calls_made_total": 2,
    "upgrade_recommended": false
  }
}
```

**Error Response (402 - Payment Required)**:

```json
{
  "detail": {
    "error": "trial_exhausted",
    "message": "Your 3 free trial calls have been used. Upgrade to $4.99/week for unlimited calls!",
    "upgrade_url": "/mobile/upgrade"
  }
}
```

**What it does**:

1. Validates user can make calls (trial/subscription)
2. Uses shared system phone number (no individual provisioning needed)
3. Initiates Twilio call with selected scenario
4. Records call in usage statistics
5. Returns updated usage stats

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

#### **POST /mobile/upgrade-subscription**

**Purpose**: Handle App Store subscription purchases
**Headers Required**:

- `Authorization: Bearer <token>`
- `X-App-Type: mobile`
- `Content-Type: application/json`

**Request Body**:

```json
{
  "app_store_transaction_id": "1000000123456789",
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

1. Validates App Store transaction ID
2. Upgrades user to paid subscription
3. Removes trial limitations
4. Returns updated usage statistics

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
    let calls_made_total: Int
    let is_subscribed: Bool
    let subscription_tier: String?
    let upgrade_recommended: Bool
    let pricing: PricingInfo?
}

struct PricingInfo: Codable {
    let weekly_plan: PricingPlan
}

struct PricingPlan: Codable {
    let price: String
    let billing: String
    let features: [String]
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
    let calls_remaining: Int?
    let trial_ends: String?
    let app_type: String?
    let message: String?
    let pricing: PricingInfo?
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

```swift
struct Scenario: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let icon: String
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

### **2. Make a Call**

```swift
struct MakeCallRequest: Codable {
    let phone_number: String
    let scenario: String
}

struct CallResponse: Codable {
    let call_sid: String
    let status: String
    let usage_stats: UsageStatsUpdate
}

struct UsageStatsUpdate: Codable {
    let trial_calls_remaining: Int
    let calls_made_total: Int
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
            return "Your 3 free trial calls have been used. Upgrade to $4.99/week for unlimited calls!"
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
    let upgrade_url: String?
    let pricing: PricingInfo?
}
```

---

## Subscription Management

### **1. App Store Integration**

```swift
import StoreKit

class SubscriptionManager: NSObject, ObservableObject {
    @Published var isSubscribed = false

    private let productID = "speech_assistant_weekly"
    private var product: Product?

    override init() {
        super.init()
        Task {
            await loadProducts()
        }
    }

    func loadProducts() async {
        do {
            let products = try await Product.products(for: [productID])
            self.product = products.first
        } catch {
            print("Failed to load products: \(error)")
        }
    }

    func purchaseSubscription() async throws {
        guard let product = product else {
            throw SubscriptionError.productNotFound
        }

        let result = try await product.purchase()

        switch result {
        case .success(let verification):
            let transaction = try checkVerified(verification)

            // Send to backend
            try await upgradeSubscription(transactionID: String(transaction.id))

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
    let app_store_transaction_id: String
    let subscription_tier: String
}

struct UpgradeResponse: Codable {
    let success: Bool
    let message: String
    let subscription_tier: String
    let usage_stats: UsageStats
}

func upgradeSubscription(transactionID: String) async throws -> UpgradeResponse {
    let url = URL(string: "\(baseURL)/mobile/upgrade-subscription")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    authManager.getAuthHeaders().forEach { key, value in
        request.setValue(value, forHTTPHeaderField: key)
    }

    let upgradeData = UpgradeRequest(
        app_store_transaction_id: transactionID,
        subscription_tier: "mobile_weekly"
    )
    request.httpBody = try JSONEncoder().encode(upgradeData)

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(UpgradeResponse.self, from: data)
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

            // Upgrade Button (if needed)
            if usageStats?.upgrade_recommended == true {
                Button("Upgrade to Unlimited ($4.99/week)") {
                    Task {
                        try await subscriptionManager.purchaseSubscription()
                    }
                }
                .buttonStyle(.borderedProminent)
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
        return stats.is_subscribed || stats.trial_calls_remaining > 0
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
                Text("Trial Status")
                    .font(.headline)
                Spacer()
                if stats.is_subscribed {
                    Text("Subscribed ✅")
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
                    Text("Calls Remaining:")
                    Spacer()
                    Text("\(stats.trial_calls_remaining)")
                        .fontWeight(.bold)
                        .foregroundColor(stats.trial_calls_remaining > 0 ? .green : .red)
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
        baseURL: "https://api.speechassistant.com",
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

This comprehensive guide provides everything your iOS development team needs to integrate with the Speech Assistant backend API. The mobile app will have a clean, simple user experience focused on fun calling scenarios with a straightforward trial-to-subscription conversion flow.
