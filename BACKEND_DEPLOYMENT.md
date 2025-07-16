# AiFriendChat Backend Deployment Guide

## 🚨 Critical Issues Fixed

This deployment addresses the following critical issues identified in your iOS app:

### ✅ **RESOLVED ISSUES**
1. **Registration Endpoint Fixed** - Now properly returns tokens and initializes usage limits
2. **Trial Call Enforcement** - Users are properly limited to 2 free trial calls
3. **Token Validation** - Consistent authentication across all endpoints
4. **Mobile Endpoints Added** - All required `/mobile/*` endpoints implemented
5. **Usage Statistics** - Consistent usage data across all endpoints
6. **Error Handling** - Proper HTTP status codes and error messages

---

## 🔧 **Deployment Steps**

### **Step 1: Backup Current Production**
```bash
# On your production server
cd /var/www/AiFriendChatBeta

# Stop the service
sudo systemctl stop aifriendchatbeta

# Create backup
cp -r . ../AiFriendChatBeta.backup.$(date +%Y%m%d_%H%M%S)
```

### **Step 2: Deploy New Code**
```bash
# Option A: Replace files manually
# Copy all updated files from your local development to production

# Option B: Git pull (if using git)
git pull origin main
```

### **Step 3: Install New Dependencies**
```bash
# Update Python packages
source venv/bin/activate
pip install -r requirements.txt
```

### **Step 4: Run Database Migration**
```bash
# Run the migration script
python3 migrate_database.py
```

### **Step 5: Set Environment Variables**
```bash
# Add to your .env file
echo "DEVELOPMENT_MODE=False" >> .env

# For testing, you can temporarily set:
# echo "DEVELOPMENT_MODE=True" >> .env
```

### **Step 6: Restart Services**
```bash
# Restart the application
sudo systemctl start aifriendchatbeta
sudo systemctl status aifriendchatbeta

# Check logs
sudo journalctl -u aifriendchatbeta -f --lines=50
```

---

## 📱 **New API Endpoints**

### **Authentication Endpoints**
```
POST /auth/register     - User registration with usage limits
POST /auth/login        - User login  
POST /auth/refresh      - Refresh access token
POST /auth/logout       - User logout
```

### **Mobile Endpoints (NEW)**
```
GET  /mobile/usage-stats           - Get usage statistics
POST /mobile/check-call-permission - Check if user can make call
POST /mobile/make-call             - Make a call with usage tracking
```

### **User Management**
```
GET  /user/me              - Get current user info
POST /user/update-name     - Update user name
POST /update-user-name     - Legacy endpoint (compatibility)
```

### **Legacy Endpoints (Still Supported)**
```
POST /token                - Legacy login endpoint
GET  /make-call/{phone}/{scenario} - Legacy make call endpoint
```

---

## 🎯 **Usage Limits Configuration**

### **Mobile App Users**
- **Trial**: 2 free calls
- **Basic**: $4.99/month (configurable)
- **Premium**: $9.99/month (configurable)

### **Web Business Users**
- **Trial**: 4 free calls
- **Basic**: $49.99/month for 20 calls/week

### **Development Mode**
Set `DEVELOPMENT_MODE=True` to bypass all usage limits for testing.

---

## 🔍 **Testing the Deployment**

### **1. Test Registration**
```bash
curl -X POST "https://your-domain.com/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

**Expected Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### **2. Test Usage Stats**
```bash
curl -X GET "https://your-domain.com/mobile/usage-stats" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Expected Response:**
```json
{
  "trial_calls_remaining": 2,
  "calls_made_total": 0,
  "is_trial_active": true,
  "is_subscribed": false,
  "subscription_status": null,
  "app_type": "mobile"
}
```

### **3. Test Call Permission**
```bash
curl -X POST "https://your-domain.com/mobile/check-call-permission" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Expected Response:**
```json
{
  "can_make_call": true,
  "status": "trial_active",
  "details": {
    "message": "2 trial calls remaining",
    "calls_remaining": 2,
    "trial_calls_used": 0
  }
}
```

### **4. Test Trial Enforcement**
Make 3 calls, the 3rd should fail with:
```json
{
  "detail": "Please upgrade to continue making calls"
}
```

---

## 🚨 **Troubleshooting**

### **Common Issues:**

1. **500 Errors on Registration**
   - Check database migration ran successfully
   - Verify all environment variables are set
   - Check logs: `sudo journalctl -u aifriendchatbeta -f`

2. **Token Validation Errors**
   - Ensure `SECRET_KEY` is set in environment
   - Check token format in Authorization header: `Bearer <token>`

3. **Usage Limits Not Working**
   - Verify `DEVELOPMENT_MODE=False` in production
   - Check if usage_limits table exists and has data
   - Ensure new users have usage limits initialized

4. **Database Errors**
   - Check if migration script ran successfully
   - Verify database permissions
   - Check for missing columns: `sqlite3 sql_app.db ".schema"`

### **Debug Commands:**
```bash
# Check database schema
sqlite3 sql_app.db ".schema usage_limits"

# Check user usage limits
sqlite3 sql_app.db "SELECT * FROM usage_limits LIMIT 5;"

# Check service status
sudo systemctl status aifriendchatbeta

# View real-time logs
sudo journalctl -u aifriendchatbeta -f
```

---

## 📊 **Monitoring**

### **Health Check Endpoint**
```bash
curl https://your-domain.com/health
```

### **Key Metrics to Monitor**
1. Trial call conversion rates
2. Registration success rates  
3. Authentication failures
4. API response times
5. Usage limit enforcement accuracy

---

## 🔐 **Security Notes**

1. **Production Security:**
   - Set `DEVELOPMENT_MODE=False`
   - Use strong `SECRET_KEY`
   - Enable HTTPS only
   - Monitor authentication failures

2. **Rate Limiting:**
   - Consider adding rate limiting to auth endpoints
   - Monitor for abuse patterns

3. **Data Privacy:**
   - Ensure call recordings are handled securely
   - Implement data retention policies

---

## 📈 **Next Steps: Apple App Store Integration**

To complete the premium membership flow:

1. **Implement StoreKit in iOS app**
2. **Add receipt validation endpoints**
3. **Create subscription management endpoints**
4. **Add webhook for App Store notifications**

This backend is now ready to support Apple App Store integration when you're ready to implement it.

---

## ✅ **Deployment Checklist**

- [ ] Backup created
- [ ] New code deployed
- [ ] Dependencies updated
- [ ] Database migrated
- [ ] Environment variables set
- [ ] Service restarted
- [ ] Registration tested
- [ ] Trial limits tested
- [ ] Usage stats tested
- [ ] iOS app tested

**The backend is now fully functional and ready for your iOS app!** 