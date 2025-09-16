# Speech Assistant SaaS API - Complete Backend Solution

A comprehensive **dual-platform SaaS solution** for creating and managing AI voice assistants, supporting both **consumer mobile apps** and **business web applications** with complete payment processing, subscription management, and advanced features.

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

---

## 💳 **NEW: Complete Stripe Payment Integration**

### **🔧 Payment Processing Features**

- ✅ **Subscription Management**: Monthly/yearly recurring billing
- ✅ **One-time Payments**: Pay-as-you-go usage billing
- ✅ **Multiple Plans**: Basic, Pro, Enterprise, and Custom plans
- ✅ **Usage Tracking**: Real-time usage monitoring and billing
- ✅ **Webhook Processing**: Automatic subscription updates
- ✅ **Plan Management**: Dynamic subscription plan creation/updates

### **💰 Subscription Plans**

#### **Business Plans**

```json
{
  "basic_monthly": {
    "name": "Basic Monthly",
    "price": "$49.99/month",
    "features": {
      "voice_minutes": 100,
      "sms_messages": 500,
      "custom_scenarios": 3,
      "transcription_storage": "30_days"
    }
  },
  "pro_monthly": {
    "name": "Pro Monthly",
    "price": "$99.99/month",
    "features": {
      "voice_minutes": 500,
      "sms_messages": 2000,
      "custom_scenarios": 10,
      "transcription_storage": "90_days",
      "advanced_analytics": true
    }
  },
  "enterprise_monthly": {
    "name": "Enterprise Monthly",
    "price": "$299.99/month",
    "features": {
      "voice_minutes": "unlimited",
      "sms_messages": "unlimited",
      "custom_scenarios": "unlimited",
      "transcription_storage": "1_year",
      "advanced_analytics": true,
      "priority_support": true,
      "white_label": true
    }
  }
}
```

#### **Usage-Based Plan**

```json
{
  "usage_based": {
    "name": "Pay As You Go",
    "pricing": {
      "voice_per_minute": 0.05,
      "sms_per_message": 0.01,
      "transcription_per_minute": 0.02,
      "custom_scenario_setup": 5.0
    }
  }
}
```

### **🔌 Payment API Endpoints**

#### **Subscription Management**

```bash
# Get available subscription plans
GET /payments/subscription-plans

# Create subscription
POST /payments/create-subscription
{
  "price_id": "price_stripe_price_id",
  "plan_name": "pro_monthly",
  "payment_method_id": "pm_card_visa"
}

# Cancel subscription
POST /payments/cancel-subscription?at_period_end=true

# Get subscription status
GET /payments/subscription-status
```

#### **One-time Payments**

```bash
# Create payment intent
POST /payments/create-payment-intent
{
  "amount": 1000,
  "currency": "usd",
  "description": "Custom scenario setup"
}
```

#### **Usage Tracking**

```bash
# Record usage for billing
POST /payments/record-usage
{
  "service_type": "voice_call",
  "usage_amount": 5,
  "usage_unit": "minutes"
}

# Get usage summary
GET /payments/usage-summary?billing_period=2025-09

# Get billing history
GET /payments/billing-history?limit=10
```

#### **Admin Plan Management**

```bash
# Create custom subscription plan
POST /payments/admin/subscription-plans
{
  "plan_id": "starter_monthly",
  "name": "Starter Monthly",
  "plan_type": "monthly",
  "features": {
    "voice_minutes": 50,
    "sms_messages": 200,
    "custom_scenarios": 1
  }
}

# Update plan
PUT /payments/admin/subscription-plans/{plan_id}

# Delete plan
DELETE /payments/admin/subscription-plans/{plan_id}
```

#### **Webhook Processing**

```bash
# Stripe webhook endpoint
POST /payments/stripe-webhook
# Automatically processes:
# - invoice.payment_succeeded
# - invoice.payment_failed
# - customer.subscription.updated
# - customer.subscription.deleted
```

---

## 📅 Google Calendar Integration

### **Real-Time Calendar Booking**

- ✅ **Conflict Detection**: Prevents double-booking by checking existing events
- ✅ **Employee-Based Limits**: Configurable booking policies (strict, flexible, unlimited)
- ✅ **Real-Time Integration**: AI agent can create calendar events during live calls
- ✅ **Smart Conflict Resolution**: AI suggests alternative times when conflicts occur

#### **API Endpoints:**

- `POST /tools/createCalendarEvent` - Real-time event creation (called by AI)
- `GET /booking/config` - Get current booking configuration
- `PUT /booking/config` - Update booking policies and limits

---

## 🏗️ Architecture

### **Single Backend Strategy**

✅ **Cost Effective**: One server, one database, one deployment  
✅ **Shared Infrastructure**: Authentication, Twilio, OpenAI costs are shared  
✅ **Easier Maintenance**: One codebase to update and monitor  
✅ **Platform Detection**: Automatic platform detection via headers  
✅ **Complete Integration**: Stripe, Twilio, OpenAI all unified

### **Platform Detection**

The backend automatically detects platform type based on:

- **Request Headers**: `X-App-Type: mobile` or `X-App-Type: web`
- **User Agent**: `Speech-Assistant-Mobile-iOS` or browser agents
- **Endpoint Prefix**: `/mobile/*` vs standard endpoints

---

## 🚀 Core Features

### **🔥 Dual-Platform Architecture**

- **Mobile Consumer API** (`/mobile/*`): Streamlined endpoints for iOS/Android apps
- **Business Web API**: Full-featured professional endpoints
- **Auto-Detection**: Platform automatically detected from request headers
- **Usage Tracking**: Separate trial and subscription management per platform
- **Payment Integration**: Complete Stripe integration for both platforms

### **📊 Advanced Usage & Trial Management**

- **Platform-Specific Trials**: 3 calls (mobile) vs 4 calls (business)
- **Real-time Usage Tracking**: Calls per day/week/month with automatic resets
- **Smart Upgrade Prompts**: Context-aware subscription recommendations
- **Trial Expiration**: Automatic trial management with grace periods
- **Subscription Tiers**: Multiple tiers for different user types

### **💳 Complete Payment System**

- **Stripe Integration**: Full payment processing with webhooks
- **Subscription Management**: Recurring billing with multiple plans
- **Usage-Based Billing**: Pay-per-use for specific services
- **Plan Customization**: Dynamic plan creation and management
- **Billing Analytics**: Comprehensive usage and billing reporting

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

---

## 💼 Business Web API Endpoints

### **Enhanced Call Management**

```bash
GET  /make-call/{phone_number}/{scenario}    # Make call with usage tracking
GET  /make-custom-call/{phone}/{scenario_id} # Custom scenario calls
POST /schedule-call                          # Schedule future calls
```

### **Payment & Subscription Management**

```bash
GET  /payments/subscription-plans            # Get available plans
POST /payments/create-subscription           # Create subscription
POST /payments/cancel-subscription           # Cancel subscription
GET  /payments/subscription-status           # Get current status
GET  /payments/billing-history               # Get payment history
GET  /payments/usage-summary                 # Get usage analytics
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
# Core API Keys
OPENAI_API_KEY=your_openai_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1234567890

# Stripe Configuration (NEW)
STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/speech_assistant

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
cp production.env.example .env
# Edit .env with your API keys

# 4. Initialize database
alembic upgrade head

# 5. Run backend
uvicorn app.main:app --reload --port 5051
```

---

## 🧪 Testing

### **Test Stripe Integration**

```bash
# Test subscription plans endpoint
curl http://localhost:5051/payments/subscription-plans

# Test webhook (development mode)
curl -X POST http://localhost:5051/payments/stripe-webhook \
  -H "Content-Type: application/json" \
  -d '{"id": "evt_test_123", "type": "test.event", "data": {"object": "test"}}'

# Test payment intent creation (needs auth)
curl -X POST http://localhost:5051/payments/create-payment-intent \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"amount": 1000, "currency": "usd"}'
```

### **Test Mobile Flow**

```bash
# Register mobile user
curl -X POST http://localhost:5051/auth/register \
  -H "Content-Type: application/json" \
  -H "X-App-Type: mobile" \
  -d '{"email":"mobile@test.com","password":"password123"}'

# Check usage stats
curl -X GET http://localhost:5051/mobile/usage-stats \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-App-Type: mobile"
```

### **Test Business Flow**

```bash
# Register business user (default)
curl -X POST http://localhost:5051/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"business@test.com","password":"password123"}'

# Check subscription status
curl -X GET http://localhost:5051/payments/subscription-status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🚀 Deployment

### **Production Deployment**

1. **Set up Stripe Dashboard**:

   - Create webhook endpoint: `https://yourdomain.com/payments/stripe-webhook`
   - Select events: `invoice.payment_succeeded`, `customer.subscription.updated`, etc.
   - Copy webhook secret to environment variables

2. **Environment Variables**:

   ```bash
   DEVELOPMENT_MODE=false
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

3. **Database Migration**:

   ```bash
   alembic upgrade head
   ```

4. **Service Restart**:
   ```bash
   sudo systemctl restart aifriendchatbeta
   ```

---

## 📊 Monitoring & Analytics

### **Usage Tracking**

- Real-time call counting per user
- Platform-specific usage analytics
- Trial conversion tracking
- Subscription renewal monitoring
- Payment success/failure tracking

### **Business Metrics**

- Mobile vs Business user acquisition
- Trial-to-paid conversion rates
- Average revenue per user (ARPU)
- Feature usage analytics
- Subscription churn analysis

---

## 🔐 Security Features

- **JWT Authentication**: Secure token-based auth
- **Rate Limiting**: Prevent API abuse
- **User Isolation**: Complete data separation
- **Usage Validation**: Server-side limit enforcement
- **Webhook Security**: Stripe signature validation
- **Payment Security**: PCI-compliant through Stripe

---

## 🎯 Documentation

- **API Documentation**: Available at `/docs` when running
- **Integration Guides**: See `docs/` folder for detailed guides
- **Stripe Integration**: See `STRIPE_INTEGRATION_GUIDE.md`
- **Mobile Integration**: See `mobile_onboarding_implementation_summary.md`
- **Calendar Integration**: See `CALENDAR_INTEGRATION_SUMMARY.md`

---

## 🎯 Current Status

**✅ Production Ready Features:**

- Complete dual-platform architecture
- Full Stripe payment integration
- Google Calendar integration
- Twilio phone number management
- Advanced usage tracking
- Comprehensive API endpoints
- Production deployment ready

**🚀 Ready for Launch:**
Your application is now fully equipped for production deployment with complete payment processing, subscription management, and all core features operational.

---

## 🎯 Bottom Line

**Your Speech Assistant SaaS is production-ready** with:

1. **Complete Payment Processing** - Stripe integration for subscriptions and one-time payments
2. **Dual Platform Support** - Mobile and business applications from single backend
3. **Advanced Features** - Calendar integration, usage tracking, custom scenarios
4. **Production Deployment** - Database migrations, environment configuration, monitoring
5. **Scalable Architecture** - Ready for growth with proper usage limits and billing

**Ready to launch both your mobile and business applications! 🚀**
