# Speech Assistant SaaS API - Dual Platform Backend

A comprehensive **dual-platform SaaS solution** for creating and managing AI voice assistants, supporting both **consumer mobile apps** and **business web applications** with distinct feature sets and pricing models.

## 🎯 Overview

This application provides a complete SaaS backend that powers two different types of applications:

### **📱 Consumer Mobile App** (Fun & Social)

- **7-Day Free Trial**: 3 free calls to test the service
- **Simple Pricing**: $4.99/week for unlimited calls
- **Fun Scenarios**: Pre-selected entertaining conversation scenarios
- **Easy Setup**: Just sign up and start calling - no complex onboarding
- **Shared Infrastructure**: Uses system phone numbers (no individual provisioning)

### **💼 Business Web App** (Professional)

- **7-Day Free Trial**: 4 free calls before upgrade
- **Professional Pricing**: Starting at $49.99/month for 20 calls/week
- **Complete Onboarding**: Phone number provisioning, calendar integration
- **Custom Scenarios**: Create unlimited personalized conversation flows
- **Advanced Features**: Transcripts, analytics, calendar integration, dedicated phone numbers

---

## ✨ Latest Major Features (Current Update)

### **🔥 Dual-Platform Architecture**

- **Mobile Consumer API** (`/mobile/*`): Streamlined endpoints for iOS/Android apps
- **Business Web API**: Full-featured professional endpoints
- **Auto-Detection**: Platform automatically detected from request headers
- **Usage Tracking**: Separate trial and subscription management per platform
- **App Store Integration**: Ready for mobile subscription handling

### **📊 Advanced Usage & Trial Management**

- **Platform-Specific Trials**: 3 calls (mobile) vs 4 calls (business)
- **Real-time Usage Tracking**: Calls per day/week/month with automatic resets
- **Smart Upgrade Prompts**: Context-aware subscription recommendations
- **Trial Expiration**: Automatic trial management with grace periods
- **Subscription Tiers**: Multiple tiers for different user types

### **💳 Comprehensive Subscription System**

- **Mobile**: $4.99/week unlimited calling
- **Business Basic**: $49.99/month (20 calls/week)
- **Business Professional**: $99/month (50 calls/week)
- **Business Enterprise**: $299/month (unlimited calls)
- **App Store Integration**: Ready for iOS in-app purchases
- **Usage Limits**: Automatic enforcement of subscription limits

### **📞 Enhanced Phone Number Management**

- **User-Specific Numbers**: Each business user gets dedicated Twilio phone numbers
- **Mobile Shared Numbers**: Consumer app uses system-wide phone numbers
- **Development Mode**: Easy testing with system phone numbers
- **Production Ready**: Full user isolation and phone number provisioning

### **🚀 Complete User Onboarding**

- **Business Onboarding**: Step-by-step setup wizard with progress tracking
- **Mobile Onboarding**: Instant access with minimal setup
- **Automatic Initialization**: Usage limits and onboarding set up on registration
- **Progress Persistence**: Users can resume onboarding where they left off

---

## 🏗️ Core Architecture

### **Platform Detection & Routing**

The backend automatically detects platform type based on:

- **Request Headers**: `X-App-Type: mobile` or `X-App-Type: web`
- **User Agent**: `Speech-Assistant-Mobile-iOS` or browser agents
- **Endpoint Prefix**: `/mobile/*` vs standard endpoints

### **Usage Tracking System**

```python
# Automatic usage initialization on registration
- Mobile users → 3 trial calls, mobile_free_trial tier
- Business users → 4 trial calls, business_free_trial tier
- 7-day trial period for both platforms
- Real-time call counting and limit enforcement
```

### **Database Schema**

```sql
-- New tables for dual-platform support
usage_limits          # Usage tracking per user
user_phone_numbers     # Business user phone numbers
user_onboarding_status # Onboarding progress tracking

-- Enhanced existing tables
users                  # Core user management
custom_scenarios       # User-specific conversation scenarios
conversations          # Call history and transcripts
```

---

## 📱 Mobile Consumer API Endpoints

### **Authentication**

```bash
POST /auth/register     # Register with mobile headers
POST /auth/login        # Login with mobile detection
```

### **Usage & Trial Management**

```bash
GET  /mobile/usage-stats           # Get trial/subscription status
POST /mobile/check-call-permission # Check if user can make calls
GET  /mobile/pricing               # Get mobile pricing ($4.99/week)
```

### **Core Mobile Features**

```bash
GET  /mobile/scenarios              # Get 5 fun scenario options
POST /mobile/make-call              # Make call with usage tracking
POST /mobile/schedule-call          # Schedule future calls
GET  /mobile/call-history           # Get call history
POST /mobile/upgrade-subscription   # Handle App Store purchases
```

### **Mobile Response Examples**

```json
// Usage stats response
{
  "app_type": "mobile_consumer",
  "is_trial_active": true,
  "trial_calls_remaining": 2,
  "calls_made_total": 1,
  "is_subscribed": false,
  "upgrade_recommended": false,
  "pricing": {
    "weekly_plan": {
      "price": "$4.99",
      "billing": "weekly",
      "features": ["Unlimited calls", "Fun scenarios", "Call friends"]
    }
  }
}

// Mobile scenarios
{
  "scenarios": [
    {"id": "default", "name": "Friendly Chat", "icon": "💬"},
    {"id": "celebrity", "name": "Celebrity Interview", "icon": "🌟"},
    {"id": "comedian", "name": "Stand-up Comedian", "icon": "😂"},
    {"id": "therapist", "name": "Life Coach", "icon": "🧠"},
    {"id": "storyteller", "name": "Storyteller", "icon": "📚"}
  ]
}
```

---

## 💼 Business Web API Endpoints

### **Enhanced Call Management**

```bash
GET  /make-call/{phone_number}/{scenario}    # Make call with usage tracking
GET  /make-custom-call/{phone}/{scenario_id} # Custom scenario calls
POST /schedule-call                          # Schedule future calls
```

### **Onboarding & Setup**

```bash
GET  /onboarding/status                      # Get onboarding progress
POST /onboarding/complete-step               # Mark step complete
GET  /onboarding/next-action                 # Get next onboarding action
POST /onboarding/initialize                  # Force reinitialize onboarding
```

### **Phone Number Management**

```bash
GET  /twilio/account                         # Get Twilio account info
GET  /twilio/search-numbers                  # Search available numbers
POST /twilio/provision-number                # Provision user phone number
GET  /twilio/user-numbers                    # Get user's phone numbers
GET  /twilio/user-primary-number             # Get primary phone number
```

### **Advanced Features**

```bash
GET  /custom-scenarios                       # User's custom scenarios
POST /realtime/custom-scenario               # Create custom scenario
GET  /google-calendar/auth                   # Calendar OAuth
GET  /stored-transcripts/                    # Enhanced transcripts
```

---

## 🚦 Usage Limits & Trial Management

### **Mobile Consumer Limits**

```bash
Trial: 3 calls over 7 days
Subscription: Unlimited calls at $4.99/week
Payment: App Store in-app purchase
Features: 5 fun scenarios, shared phone numbers
```

### **Business Web Limits**

```bash
Trial: 4 calls over 7 days
Basic: 20 calls/week at $49.99/month
Professional: 50 calls/week at $99/month
Enterprise: Unlimited calls at $299/month
Features: Custom scenarios, dedicated phone numbers, transcripts
```

### **Usage Enforcement**

- **Real-time checking**: Before each call
- **Automatic counting**: After successful calls
- **Smart resets**: Daily/weekly/monthly counters
- **Upgrade prompts**: When limits approached
- **Grace periods**: Trial extensions for engagement

---

## 🔧 Environment Configuration

### **Required Environment Variables**

```bash
# Core Configuration
SECRET_KEY=your_secret_key_here
DATABASE_URL=sqlite:///./sql_app.db

# Platform Mode
DEVELOPMENT_MODE=true  # false for production usage limits

# URLs
PUBLIC_URL=your-ngrok-id.ngrok-free.app
FRONTEND_URL=http://localhost:5173

# OpenAI (Updated to latest model)
OPENAI_API_KEY=your_openai_api_key

# Twilio
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890  # System number (mobile users)

# Google Calendar
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5050/google-calendar/callback
```

### **Development vs Production**

```bash
# Development Mode
DEVELOPMENT_MODE=true
- Bypasses usage limits for testing
- Uses system phone number for all users
- Allows unlimited calling for development

# Production Mode
DEVELOPMENT_MODE=false
- Enforces all usage limits and trials
- Requires user-specific phone numbers for business users
- Mobile users share system phone number
```

---

## 🚀 Getting Started

### **1. Installation**

```bash
git clone https://github.com/yourusername/speech-assistant-api.git
cd speech-assistant-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### **2. Configuration**

```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

### **3. Database Setup**

```bash
alembic upgrade head  # Apply all migrations including new dual-platform tables
```

### **4. Run the Application**

```bash
# Development server
python -m uvicorn app.main:app --host 0.0.0.0 --port 5050 --reload

# Server will start with both mobile and business APIs available
```

### **5. Test the APIs**

```bash
# Test mobile endpoints
curl http://localhost:5050/mobile/pricing
curl http://localhost:5050/mobile/scenarios

# Test business endpoints
curl http://localhost:5050/twilio/account
curl http://localhost:5050/onboarding/status
```

---

## 📚 Integration Guides

### **📱 Mobile App Integration**

- See `mobileApp.md` for complete iOS Swift integration guide
- Includes authentication, usage tracking, App Store subscriptions
- SwiftUI examples and best practices
- Error handling and user experience guidelines

### **💼 Business Web App Integration**

- See `backend_integration.md` for complete React integration guide
- Comprehensive API documentation with examples
- Authentication flows and error handling
- Advanced features and onboarding integration

---

## 🏃‍♂️ Quick Testing

### **Test Mobile Flow**

```bash
# Register mobile user
curl -X POST http://localhost:5050/auth/register \
  -H "Content-Type: application/json" \
  -H "X-App-Type: mobile" \
  -d '{"email":"mobile@test.com","password":"password123"}'

# Check usage stats
curl -X GET http://localhost:5050/mobile/usage-stats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Test Business Flow**

```bash
# Register business user (default)
curl -X POST http://localhost:5050/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"business@test.com","password":"password123"}'

# Check onboarding status
curl -X GET http://localhost:5050/onboarding/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📊 Monitoring & Analytics

### **Usage Tracking**

- Real-time call counting per user
- Platform-specific usage analytics
- Trial conversion tracking
- Subscription renewal monitoring

### **Business Metrics**

- Mobile vs Business user acquisition
- Trial-to-paid conversion rates
- Average revenue per user (ARPU)
- Feature usage analytics

---

## 🔐 Security Features

- **JWT Authentication**: Secure token-based auth
- **Rate Limiting**: Prevent API abuse
- **User Isolation**: Complete data separation
- **Usage Validation**: Server-side limit enforcement
- **App Store Verification**: Transaction validation ready
- **Development Safeguards**: Safe testing environment

---

## 🚢 Deployment Ready

### **Mobile App Deployment**

- App Store ready with subscription handling
- Production API endpoints configured
- Usage limits enforced
- Subscription management integrated

### **Business Web App Deployment**

- Complete onboarding flow
- Phone number provisioning
- Advanced feature access
- Scalable architecture

---

## 📈 Future Enhancements

- **Analytics Dashboard**: Usage insights and metrics
- **Advanced Subscription Tiers**: Custom pricing plans
- **Multi-language Support**: International expansion
- **Advanced AI Features**: Custom voice models
- **Enterprise Features**: SSO, team management
- **API Rate Limiting**: Advanced usage controls

---

This dual-platform backend provides everything needed to launch both a consumer mobile app and a professional business web application, with distinct user experiences, pricing models, and feature sets - all from a single, well-architected backend! 🚀
