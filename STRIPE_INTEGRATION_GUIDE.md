# 🎯 **Stripe Integration Guide - Speech Assistant Backend**

## ✅ **Integration Complete!**

Your speech assistant app now has a complete Stripe backend integration for handling subscriptions, usage-based billing, and payments.

---

## 🏗️ **What Was Implemented**

### **1. Database Models** ✅

- **UserSubscription**: Manages user subscription plans and status
- **PaymentRecord**: Tracks all payments and invoices
- **UsageRecord**: Records usage for billing (transcription minutes, calls, SMS)
- **StripeWebhookEvent**: Ensures webhook events are processed only once

### **2. Stripe Service** ✅

- **Customer Management**: Create/retrieve Stripe customers
- **Subscription Management**: Create, cancel, update subscriptions
- **Payment Processing**: Handle one-time payments and payment intents
- **Usage Tracking**: Record billable usage with automatic cost calculation
- **Webhook Processing**: Handle all Stripe webhook events securely

### **3. API Endpoints** ✅

All endpoints are available at `/payments/` prefix:

- `GET /payments/subscription-plans` - View available plans
- `POST /payments/create-subscription` - Create new subscription
- `POST /payments/cancel-subscription` - Cancel subscription
- `POST /payments/create-payment-intent` - One-time payments
- `GET /payments/subscription-status` - User's current status
- `POST /payments/record-usage` - Track usage (internal)
- `GET /payments/billing-history` - Payment history
- `GET /payments/usage-summary` - Usage analytics
- `POST /payments/stripe-webhook` - Webhook handler

### **4. Configuration** ✅

- Environment variables added to `dev.env` and `production.env.example`
- Stripe keys validation for production
- Webhook secret verification

---

## 🔧 **Setup Instructions**

### **Step 1: Install Dependencies**

```bash
cd /Users/carlosalvarez/speech-assistant-openai-realtime-api-python
source venv/bin/activate
pip install stripe>=7.0.0
```

### **Step 2: Configure Stripe Keys**

You mentioned you have Stripe keys - add them to your environment:

```bash
# In your .env or dev.env file:
STRIPE_PUBLISHABLE_KEY="pk_test_your_key_here"
STRIPE_SECRET_KEY="sk_test_your_key_here"
STRIPE_WEBHOOK_SECRET="whsec_your_webhook_secret_here"
```

### **Step 3: Run Database Migration**

```bash
source venv/bin/activate
python -m alembic upgrade head
```

### **Step 4: Test the Integration**

```bash
python start_dev_server.py
```

Visit: `http://localhost:8000/docs` to see the new payment endpoints!

---

## 💳 **Subscription Plans**

The system includes pre-configured plans:

### **Basic Monthly** - `basic_monthly`

- 100 voice minutes
- 500 SMS messages
- 3 custom scenarios
- 30-day transcript storage

### **Pro Monthly** - `pro_monthly`

- 500 voice minutes
- 2,000 SMS messages
- 10 custom scenarios
- 90-day transcript storage
- Advanced analytics

### **Enterprise Monthly** - `enterprise_monthly`

- Unlimited voice minutes
- Unlimited SMS messages
- Unlimited custom scenarios
- 1-year transcript storage
- Advanced analytics
- Priority support
- White label

### **Pay As You Go** - `usage_based`

- $0.05 per voice minute
- $0.01 per SMS message
- $0.02 per transcription minute
- $5.00 per custom scenario setup

---

## 🔌 **API Usage Examples**

### **Create Subscription**

```python
POST /payments/create-subscription
{
    "price_id": "price_1234567890",  # From Stripe Dashboard
    "plan_name": "pro_monthly",
    "payment_method_id": "pm_1234567890"  # Optional
}
```

### **Check User Status**

```python
GET /payments/subscription-status
# Returns:
{
    "has_subscription": true,
    "plan_name": "pro_monthly",
    "status": "active",
    "current_usage": {
        "transcription": {"amount": 45, "cost": 90, "unit": "minutes"},
        "voice_call": {"amount": 23, "cost": 115, "unit": "minutes"}
    },
    "features": {
        "voice_minutes": 500,
        "sms_messages": 2000,
        "advanced_analytics": true
    }
}
```

### **Record Usage (Internal)**

```python
POST /payments/record-usage
{
    "service_type": "transcription",
    "usage_amount": 5,
    "usage_unit": "minutes",
    "resource_id": 123  # transcript_id
}
```

---

## 🎣 **Integration Points**

### **Voice Call Billing**

Automatically track usage when calls complete:

```python
# In your call completion handler:
from app.services.stripe_service import StripeService

await StripeService.record_usage(
    user=current_user,
    service_type="voice_call",
    usage_amount=call_duration_minutes,
    usage_unit="minutes",
    db=db,
    resource_id=conversation.id
)
```

### **Transcription Billing**

Track transcription usage:

```python
# When transcript is processed:
await StripeService.record_usage(
    user=current_user,
    service_type="transcription",
    usage_amount=transcript_duration_minutes,
    usage_unit="minutes",
    db=db,
    resource_id=transcript.id
)
```

### **SMS Billing**

Track SMS usage:

```python
# When SMS is sent:
await StripeService.record_usage(
    user=current_user,
    service_type="sms",
    usage_amount=1,
    usage_unit="messages",
    db=db,
    resource_id=sms_conversation.id
)
```

---

## 🎯 **Webhook Configuration**

### **In Stripe Dashboard:**

1. Go to **Developers → Webhooks**
2. Add endpoint: `https://yourdomain.com/payments/stripe-webhook`
3. Select events:
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy webhook signing secret to `STRIPE_WEBHOOK_SECRET`

---

## 🔒 **Security Features**

- ✅ **Webhook Signature Verification**: All webhooks validated
- ✅ **User Isolation**: All data filtered by user ID
- ✅ **Idempotent Processing**: Webhooks processed only once
- ✅ **Environment Validation**: Required keys checked in production
- ✅ **JWT Authentication**: All endpoints require valid user session

---

## 📊 **Usage Analytics**

### **Track Everything:**

- Voice call minutes
- Transcription processing time
- SMS messages sent
- Custom scenarios created
- API calls made

### **Billing Periods:**

- Monthly aggregation (`YYYY-MM` format)
- Real-time usage tracking
- Cost calculation per service
- Overage detection

---

## 🚀 **Next Steps**

### **Frontend Integration:**

1. **Install Stripe.js**: `npm install @stripe/stripe-js @stripe/react-stripe-js`
2. **Create Payment Forms**: Use Stripe Elements for secure card input
3. **Subscription Management**: Build user dashboard for plan changes
4. **Usage Display**: Show current usage and limits

### **Stripe Dashboard Setup:**

1. **Create Products/Prices**: Set up your subscription tiers
2. **Configure Webhooks**: Point to your webhook endpoint
3. **Test Payments**: Use test cards for development
4. **Go Live**: Switch to live keys when ready

### **Advanced Features:**

- **Proration**: Handle mid-cycle plan changes
- **Coupons**: Implement discount codes
- **Trials**: Offer free trial periods
- **Metered Billing**: Real-time usage reporting to Stripe

---

## 📝 **File Structure**

```
app/
├── models.py                 # ✅ Stripe database models
├── config.py                 # ✅ Stripe configuration
├── services/
│   └── stripe_service.py     # ✅ Core Stripe logic
└── routers/
    └── payments.py           # ✅ Payment API endpoints

alembic/versions/
└── 68f2b8091655_add_stripe_payment_tables_and_.py  # ✅ Migration

dev.env                       # ✅ Development Stripe keys
production.env.example        # ✅ Production template
requirements.txt              # ✅ Stripe dependency added
```

---

## 🎉 **You're Ready!**

Your speech assistant now has enterprise-grade payment processing:

- **✅ Subscription Management**
- **✅ Usage-Based Billing**
- **✅ Secure Webhook Processing**
- **✅ Comprehensive Analytics**
- **✅ Production-Ready Security**

Just add your Stripe keys and you're ready to start billing customers! 🚀

---

## 🆘 **Need Help?**

- **Stripe Documentation**: https://stripe.com/docs
- **Test Cards**: https://stripe.com/docs/testing#cards
- **Webhook Testing**: Use Stripe CLI for local testing
- **Dashboard**: https://dashboard.stripe.com

Happy billing! 💰
