# Backend Enhancement Request: Mobile App Integration Issues

## 🚨 Critical Issues Found

### **1. Mobile Scenarios Missing Persona/Prompt Data**

**Problem**: Mobile scenarios endpoint (`/mobile/scenarios`) returns only metadata, missing the crucial persona/prompt/voice_config that the voice agent needs.

**Current Response**:

```json
{
  "scenarios": [
    {
      "id": "fake_doctor",
      "name": "Fake Doctor Call",
      "description": "Emergency exit with medical urgency",
      "icon": "🏥",
      "category": "emergency_exit",
      "difficulty": "easy"
    }
  ]
}
```

**Required Response** (like test scenarios):

```json
{
  "scenarios": [
    {
      "id": "fake_doctor",
      "name": "Fake Doctor Call",
      "description": "Emergency exit with medical urgency",
      "icon": "🏥",
      "category": "emergency_exit",
      "difficulty": "easy",
      "persona": "You are Dr. Smith, a concerned physician...",
      "prompt": "Emergency medical call about urgent health issue...",
      "voice_config": {
        "voice": "coral",
        "temperature": 0.8
      }
    }
  ]
}
```

**Impact**: Users get default persona ("Mike Thompson") instead of scenario-specific personas, breaking the core functionality.

---

### **2. Mobile Onboarding Endpoints Missing**

**Problem**: The mobile app expects onboarding endpoints that don't exist on the backend.

**Missing Endpoints**:

- `POST /onboarding/initialize` - Initialize onboarding for new user
- `POST /onboarding/complete-step` - Complete individual onboarding steps
- `GET /onboarding/status` - Get onboarding completion status

**Current Error**: `HTTP 400` when trying to complete onboarding steps.

**Impact**: New users can't complete onboarding, breaking the user experience flow.

---

### **3. Scenario ID Mismatch Between Endpoints**

**Problem**: Different endpoints expect different scenario formats.

**Test Endpoints** (`/testing/*`):

- Use scenarios like: `"sister_emergency"`, `"long_distance_love"`, `"caring_sibling"`
- Have full persona/prompt data
- Work correctly with voice agent

**Mobile Endpoints** (`/mobile/*`):

- Use scenarios like: `"fake_doctor"`, `"fake_celebrity"`, `"fake_boss"`
- Missing persona/prompt data
- Voice agent falls back to default

---

## 🔧 Required Backend Changes

### **Priority 1: Fix Mobile Scenarios Data**

**Option A: Enhance Existing Endpoint**

```python
# Modify /mobile/scenarios to include full scenario data
@app.get("/mobile/scenarios")
async def get_mobile_scenarios(include_details: bool = True):
    if include_details:
        # Return full scenario data with persona/prompt
        return get_full_scenario_data()
    else:
        # Return current metadata-only response
        return get_scenario_metadata()
```

**Option B: New Detailed Endpoint**

```python
# New endpoint for detailed scenario data
@app.get("/mobile/scenarios/{scenario_id}/details")
async def get_scenario_details(scenario_id: str):
    return get_scenario_with_persona_prompt(scenario_id)
```

### **Priority 2: Implement Mobile Onboarding**

```python
# New onboarding endpoints
@app.post("/onboarding/initialize")
async def initialize_onboarding(user_id: int):
    return {"status": "initialized", "current_step": 1}

@app.post("/onboarding/complete-step")
async def complete_onboarding_step(user_id: int, step: int, data: dict):
    return {"status": "completed", "next_step": step + 1}

@app.get("/onboarding/status")
async def get_onboarding_status(user_id: int):
    return {"completed": False, "current_step": 2, "total_steps": 3}
```

### **Priority 3: Standardize Scenario System**

**Recommendation**: Use the test scenario format for all endpoints.

**Current Test Scenarios** (working):

```json
{
  "sister_emergency": {
    "persona": "You are Sarah, a 35-year-old woman...",
    "prompt": "Call your sibling about mom's accident...",
    "voice_config": { "voice": "coral", "temperature": 0.8 }
  }
}
```

**Convert Mobile Scenarios** to match this format:

```json
{
  "fake_doctor": {
    "persona": "You are Dr. Smith, an emergency physician...",
    "prompt": "Emergency medical call requiring immediate attention...",
    "voice_config": { "voice": "coral", "temperature": 0.7 }
  }
}
```

---

## 📱 Frontend Impact

### **Current iOS App Status**

- ✅ Registration works
- ✅ Login works
- ✅ Calls are initiated successfully
- ❌ Wrong personas used (default instead of scenario-specific)
- ❌ Onboarding flow broken
- ❌ Scenario selection doesn't work as expected

### **After Backend Fixes**

- ✅ All scenarios will use correct personas
- ✅ Onboarding will complete properly
- ✅ User experience will be fully functional

---

## 🚀 Implementation Priority

### **Phase 1 (Immediate - 1-2 days)**

1. Fix mobile scenarios to include persona/prompt data
2. Test with existing mobile endpoints

### **Phase 2 (Short-term - 3-5 days)**

1. Implement mobile onboarding endpoints
2. Standardize scenario format across all endpoints

### **Phase 3 (Long-term - 1-2 weeks)**

1. Add new mobile-specific scenarios
2. Enhance voice agent integration
3. Add scenario analytics and usage tracking

---

## 🔍 Testing Requirements

### **Mobile Scenarios Test**

1. Call `/mobile/scenarios` - should return full scenario data
2. Make call with `fake_doctor` - should use doctor persona, not default
3. Verify all mobile scenarios have unique personas

### **Onboarding Test**

1. Register new user
2. Complete onboarding steps
3. Verify onboarding status updates correctly

### **Integration Test**

1. Test call flow from registration → onboarding → first call
2. Verify scenario personas work correctly
3. Check rate limiting and subscription features

---

## 📋 Backend Team Action Items

1. **Review current scenario data structure**
2. **Identify which scenarios need persona/prompt data**
3. **Implement mobile onboarding endpoints**
4. **Test mobile scenarios with voice agent**
5. **Verify scenario ID consistency across endpoints**
6. **Update API documentation**

---

## 💬 Questions for Backend Team

1. **Do you have the persona/prompt data for mobile scenarios?**
2. **Should we use test scenario format for all endpoints?**
3. **What's the preferred approach for mobile onboarding?**
4. **Are there any voice agent configuration requirements?**
5. **What's the timeline for implementing these changes?**

---

**Priority**: 🔴 **HIGH** - Core functionality broken  
**Effort**: 🟡 **MEDIUM** - Data structure changes + new endpoints  
**Impact**: 🟢 **HIGH** - Fixes entire user experience flow
