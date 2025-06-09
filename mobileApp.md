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

This comprehensive guide provides everything your iOS development team needs to integrate with the Speech Assistant backend API. The mobile app will have a clean, simple user experience focused on fun calling scenarios with a straightforward trial-to-subscription conversion flow.
