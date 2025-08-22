# Backend Onboarding System Fixes

## 🚨 Critical Issues Found

### 1. **Step Name Mismatch (400 Bad Request Errors)**

The mobile app is sending step names that don't match what the backend expects:

**Mobile App Sends:**

- `welcome`
- `profile`
- `tutorial`
- `firstCall`

**Backend Currently Expects:**

- `phone_setup`
- `calendar`
- `scenarios`
- `welcome_call`

**Result:** All onboarding step completions return HTTP 400 "Invalid step" errors.

### 2. **Data Format Issues**

The `/onboarding/complete-step` endpoint expects different data structures than what the mobile app provides.

### 3. **Authentication Flow Problems**

The current flow tries to do onboarding after authentication, but onboarding should happen before registration.

## 🎯 Required Backend Changes

### **Priority 1: Fix Step Names (CRITICAL)**

Update the `/onboarding/complete-step` endpoint to accept the mobile app's step names:

```python
# Current backend validation (WRONG)
VALID_STEPS = ['phone_setup', 'calendar', 'scenarios', 'welcome_call']

# Should be updated to (CORRECT)
VALID_STEPS = ['welcome', 'profile', 'tutorial', 'firstCall']
```

**OR** create a mapping system:

```python
STEP_MAPPING = {
    'welcome': 'phone_setup',
    'profile': 'calendar',
    'tutorial': 'scenarios',
    'firstCall': 'welcome_call'
}

# Then map internally
internal_step = STEP_MAPPING.get(step, step)
```

### **Priority 2: Fix Data Format**

The mobile app sends:

```json
{
  "step": "welcome",
  "data": {
    "name": "John Doe",
    "phone_number": "+1234567890",
    "preferred_voice": "coral",
    "notifications_enabled": true
  }
}
```

Ensure the backend can handle this format properly.

### **Priority 3: Update Response Format**

The mobile app expects responses like:

```json
{
  "step": "welcome",
  "isCompleted": true,
  "completedAt": "2025-08-22T22:13:52.489676",
  "nextStep": "profile"
}
```

## 🔄 Correct User Flow

### **Current Broken Flow:**

1. User signs in → Gets authenticated
2. App tries onboarding → Backend rejects step names → 400 errors
3. User stuck in onboarding loop

### **Correct Flow Should Be:**

1. **Anonymous onboarding** (no auth required) → Complete profile setup
2. **Register with onboarding data** → Create account with completed profile
3. **Sign in** → Access app with full profile already set up

## 🛠️ Implementation Details

### **Endpoint: `/onboarding/complete-step`**

**Current Issues:**

- Wrong step name validation
- Inconsistent data format handling
- Missing error messages for mobile app

**Required Changes:**

```python
@app.post("/onboarding/complete-step")
async def complete_step(step: str, data: dict = None):
    # Accept mobile app step names
    VALID_STEPS = ['welcome', 'profile', 'tutorial', 'firstCall']

    if step not in VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step. Must be one of: {VALID_STEPS}"
        )

    # Process step with provided data
    result = process_onboarding_step(step, data)

    return {
        "step": step,
        "isCompleted": True,
        "completedAt": datetime.utcnow().isoformat(),
        "nextStep": get_next_step(step)
    }
```

### **Endpoint: `/onboarding/initialize`**

Ensure this endpoint works for mobile app initialization and returns proper step progression.

### **Endpoint: `/onboarding/status`**

Return current onboarding progress in mobile app format.

## 📱 Mobile App Requirements

### **Step Progression:**

1. **Welcome** → Basic app introduction
2. **Profile** → Collect name, phone, preferences
3. **Tutorial** → How to use the app
4. **First Call** → Test call functionality

### **Data Collection:**

- User name
- Phone number
- Voice preference
- Notification settings

## 🧪 Testing Requirements

### **Test Cases:**

1. **Step Completion:** Each step should complete without 400 errors
2. **Data Persistence:** Profile data should save correctly
3. **Step Progression:** Should move through steps sequentially
4. **Error Handling:** Clear error messages for mobile app
5. **Authentication:** Onboarding should work before registration

### **Test Data:**

```json
{
  "step": "profile",
  "data": {
    "name": "Test User",
    "phone_number": "+1234567890",
    "preferred_voice": "coral",
    "notifications_enabled": true
  }
}
```

## 🚀 Implementation Priority

### **Phase 1 (CRITICAL - Fix 400 errors):**

1. Update step name validation
2. Fix data format handling
3. Test basic step completion

### **Phase 2 (IMPORTANT - Improve flow):**

1. Ensure proper step progression
2. Fix response formats
3. Add proper error handling

### **Phase 3 (NICE TO HAVE - Enhance UX):**

1. Add step validation
2. Improve error messages
3. Add onboarding analytics

## 📋 Summary

**Previous Status:** ❌ BROKEN - All onboarding steps returned 400 errors
**Current Status:** ✅ FIXED - Mobile app onboarding flow now working
**Impact:** Users can now complete onboarding and access app features
**Priority:** COMPLETE - Mobile app integration working properly

## ✅ FIXES IMPLEMENTED

### 1. **Step Name Mapping (RESOLVED)**

- ✅ Backend now accepts both mobile app step names AND original backend step names
- ✅ Added mapping system: `welcome` → `phone_setup`, `profile` → `calendar`, etc.
- ✅ No breaking changes to existing backend functionality

### 2. **Data Format Handling (RESOLVED)**

- ✅ Enhanced `StepCompletionRequest` to accept optional `data` field
- ✅ Backend properly processes profile data (name, phone, voice preference, notifications)
- ✅ Added profile fields to User model: `full_name`, `preferred_voice`, `notifications_enabled`
- ✅ Created database migration for new profile fields

### 3. **Response Format (RESOLVED)**

- ✅ Mobile app now receives properly formatted responses:
  ```json
  {
    "step": "profile",
    "isCompleted": true,
    "completedAt": "2025-08-22T22:13:52.489676",
    "nextStep": "tutorial",
    "status": {...}
  }
  ```

### 4. **New Endpoints Added**

- ✅ `/onboarding/status` - Returns mobile-compatible onboarding status
- ✅ Enhanced `/onboarding/complete-step` - Now handles mobile data format
- ✅ Enhanced `/onboarding/check-step/{step}` - Supports mobile step names

## 🔗 Related Endpoints

- `/onboarding/start` - ✅ Working (anonymous onboarding)
- `/onboarding/set-name` - ✅ Working (anonymous onboarding)
- `/onboarding/select-scenario` - ✅ Working (anonymous onboarding)
- `/onboarding/complete` - ✅ Working (anonymous onboarding)
- `/onboarding/complete-step` - ✅ FIXED (authenticated onboarding + mobile support)
- `/onboarding/initialize` - ✅ Working (authenticated onboarding)
- `/onboarding/status` - ✅ ADDED (mobile-compatible status endpoint)
- `/onboarding/check-step/{step}` - ✅ ENHANCED (mobile step name support)

## 📞 Questions for Backend Team

1. **Why are the step names different between anonymous and authenticated onboarding?**
2. **What is the intended data format for `/onboarding/complete-step`?**
3. **Should onboarding happen before or after registration?**
4. **Can we standardize the step names across all onboarding endpoints?**

---

**Created:** August 22, 2025  
**Priority:** CRITICAL  
**Status:** AWAITING BACKEND FIXES
