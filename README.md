# Speech Assistant SaaS API - Dual Platform Backend

A comprehensive **dual-platform SaaS solution** for creating and managing AI voice assistants, supporting both **consumer mobile apps** and **business web applications** with distinct feature sets and pricing models.

## 🎯 Overview

This application provides a complete SaaS backend that powers two different types of applications from a **single, unified backend**:

### **📱 Consumer Mobile App** (Fun & Social)

- **7-Day Free Trial**: 3 free calls to test the service
- **Simple Pricing**: $4.99/week for unlimited calls
- **Fun Scenarios**: Pre-selected entertaining conversation scenarios
- **Easy Setup**: Just sign up and start calling - no complex onboarding
- **Shared Infrastructure**: Uses system phone numbers (no individual provisioning)
- **App Store Ready**: Complete iOS integration with in-app purchases

### **💼 Business Web App** (Professional)

- **7-Day Free Trial**: 4 free calls before upgrade
- **Professional Pricing**: Starting at $49.99/month for 20 calls/week
- **Complete Onboarding**: Phone number provisioning, calendar integration
- **Custom Scenarios**: Create unlimited personalized conversation flows
- **Advanced Features**: Transcripts, analytics, calendar integration, dedicated phone numbers

## 📅 Google Calendar Integration

### **Real-Time Calendar Booking**

The system now supports **real-time calendar event creation** during voice calls using OpenAI's function calling capability:

#### **Features:**

- ✅ **Conflict Detection**: Prevents double-booking by checking existing events
- ✅ **Employee-Based Limits**: Configurable booking policies (strict, flexible, unlimited)
- ✅ **Real-Time Integration**: AI agent can create calendar events during live calls
- ✅ **Smart Conflict Resolution**: AI suggests alternative times when conflicts occur

#### **Booking Policies:**

- **Strict**: Only 1 booking per time slot (default for single employee)
- **Flexible**: Multiple bookings allowed up to employee limit
- **Unlimited**: No booking restrictions

#### **API Endpoints:**

- `POST /tools/createCalendarEvent` - Real-time event creation (called by AI)
- `GET /booking/config` - Get current booking configuration
- `PUT /booking/config` - Update booking policies and limits

#### **Configuration:**

```json
{
  "employee_count": 1,
  "max_concurrent_bookings": 1,
  "booking_policy": "strict",
  "allow_overbooking": false
}
```

---

## 🏗️ Architecture Decision: Single Backend

### **Why Single Backend? (Recommended)**

✅ **Cost Effective**: One server, one database, one deployment  
✅ **Shared Infrastructure**: Authentication, Twilio, OpenAI costs are shared  
✅ **Easier Maintenance**: One codebase to update and monitor  
✅ **Your Current Setup**: Already working perfectly with platform detection  
✅ **Faster to Ship**: No need to split and redeploy

### **Platform Detection**

The backend automatically detects platform type based on:

- **Request Headers**: `X-App-Type: mobile` or `X-App-Type: web`
- **User Agent**: `Speech-Assistant-Mobile-iOS` or browser agents
- **Endpoint Prefix**: `/mobile/*` vs standard endpoints

```python
# Automatic platform detection
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
POST /auth/refresh      # Refresh expired tokens
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

## 🚀 Deployment Strategy

### **Single Backend Deployment**

```bash
# One deployment serves both platforms
api.speechassistant.com
├── Mobile App (iOS) → X-App-Type: mobile
└── Business Web (React) → X-App-Type: web (or no header)
```

### **Environment Variables**

```bash
# .env
FRONTEND_URL=http://localhost:5173  # Business web app
MOBILE_APP_ENABLED=true
BUSINESS_APP_ENABLED=true
```

### **Cost Comparison**

**Single Backend (Current)**

- **Server**: $50-100/month (one instance)
- **Database**: $20-50/month (shared)
- **Twilio**: Shared costs
- **OpenAI**: Shared costs
- **Total**: ~$100-200/month

**Separate Backends (Future - Only if needed)**

- **Mobile Server**: $50-100/month
- **Business Server**: $100-200/month
- **Mobile Database**: $20-50/month
- **Business Database**: $50-100/month
- **Total**: ~$220-450/month

---

## 🔧 Environment Configuration

### **Required Environment Variables**

```bash
# Core API Keys
OPENAI_API_KEY=your_openai_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1234567890

# Database
DATABASE_URL=sqlite:///./sql_app.db

# Security
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Google Calendar (Business only)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Frontend URLs
FRONTEND_URL=http://localhost:5173
PUBLIC_URL=https://your-domain.com

# Development
DEVELOPMENT_MODE=true
```

### **Quick Setup**

```bash
# 1. Clone repository
git clone <repository-url>
cd speech-assistant-openai-realtime-api-python

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 4. Initialize database
python -c "from app.db import engine; from app.models import Base; Base.metadata.create_all(bind=engine)"

# 5. Run backend
uvicorn app.main:app --reload --port 5050

# 6. Run frontend (in separate terminal)
cd frontend
npm install
npm run dev
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
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-App-Type: mobile"
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

---

## 🎯 When to Consider Separate Backends

You should only consider separate backends when:

### **🚀 Scale Indicators**

- **Mobile app**: 10,000+ active users
- **Business app**: 1,000+ paying customers
- **Different growth rates**: One platform growing much faster
- **Different requirements**: Mobile needs different features than business

### **💰 Business Reasons**

- **Different pricing models**: Mobile $4.99/week vs Business $299/month
- **Different compliance needs**: Business might need SOC2, HIPAA, etc.
- **Different SLAs**: Business users need 99.9% uptime, mobile can be 99%
- **Different support**: Business needs dedicated support, mobile can be self-service

### **🔧 Technical Reasons**

- **Different databases**: Mobile needs simple storage, business needs complex analytics
- **Different APIs**: Mobile needs simple endpoints, business needs advanced features
- **Different deployment cycles**: Mobile updates weekly, business updates monthly

---

## 🚀 Recommended Timeline

### **Phase 1: Launch (Next 3-6 months)**

```
Single Backend: api.speechassistant.com
├── Mobile App → /mobile/* endpoints
└── Business Web → /business/* endpoints
```

### **Phase 2: Scale (6-12 months)**

```
Monitor usage and growth:
- Mobile: 5,000+ users
- Business: 500+ customers
- Revenue: $50K+ monthly
```

### **Phase 3: Separate (12+ months)**

```
If needed:
├── Mobile API: mobile-api.speechassistant.com
└── Business API: business-api.speechassistant.com
```

---

## 🎯 Bottom Line

**Keep your current single backend** because:

1. **It's already working** - your mobile app is connected and functional
2. **Cost effective** - one deployment, shared resources
3. **Easier to manage** - one codebase, one deployment pipeline
4. **Faster to ship** - no need to split and redeploy
5. **Your architecture supports it** - platform detection already implemented

**Focus on shipping instead** of over-engineering. Your current setup is perfect for launching both products! 🚀
