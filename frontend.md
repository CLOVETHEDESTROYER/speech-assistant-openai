# AIFriend Web - Frontend Documentation

## Overview

AIFriend Web is a React-based SaaS application that enables users to create and manage AI-powered voice calls with custom scenarios. Each user has their own isolated workspace with personalized scenarios, call history, and Google Calendar integration.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   External      │
│   (React)       │    │   (FastAPI)     │    │   Services      │
│                 │    │                 │    │                 │
│ • Authentication│◄──►│ • JWT Auth      │    │ • Google OAuth  │
│ • Scenarios     │    │ • User Data     │    │ • OpenAI API    │
│ • Call History  │    │ • Call Logic    │    │ • Twilio        │
│ • Calendar      │    │ • Transcripts   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Frontend-Backend Connection

### 1. API Client Configuration

The frontend connects to the backend through a centralized API client:

**File: `src/services/apiClient.ts`**

```typescript
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL, // Backend URL (e.g., http://localhost:5050)
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000,
  withCredentials: false,
});

// Automatic token injection
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### 2. Environment Configuration

**File: `.env`**

```bash
VITE_API_URL=http://localhost:5050  # Backend API URL
```

### 3. Authentication Flow

```typescript
// Login Process
const loginResponse = await api.auth.login({
  username: email,
  password: password,
});

// Store JWT token
localStorage.setItem("token", loginResponse.token.access_token);

// All subsequent API calls automatically include the token
```

## Google Calendar Integration

### Current Implementation Status

- ✅ OAuth flow initiated from frontend
- ✅ Frontend retry logic for token timing
- ❌ Backend redirect to frontend (needs fix)
- ✅ Calendar events display
- ✅ Schedule AI calls for meetings

### Required Backend Changes

#### 1. Update OAuth Callback Endpoint

**Backend File: `main.py` (or equivalent)**

```python
from fastapi.responses import HTMLResponse, FileResponse
import os

@app.get("/google-calendar/callback")
async def google_calendar_callback(
    request: Request,
    code: str = None,
    state: str = None,
    current_user: User = Depends(get_current_user)
):
    try:
        # Process OAuth callback (existing logic)
        # ... existing OAuth token processing ...

        # Instead of returning JSON, serve redirect HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Calendar Connected</title>
            <script>
                setTimeout(() => {{
                    const frontendUrl = window.location.hostname === 'localhost'
                        ? 'http://localhost:5174'  // Dev environment
                        : 'https://your-frontend-domain.com';  // Production

                    window.location.href = `${{frontendUrl}}/scheduled-meetings?code={code}&state={state}`;
                }}, 2000);
            </script>
        </head>
        <body>
            <h1>✅ Google Calendar Connected!</h1>
            <p>Redirecting you back to the application...</p>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 2. User-Specific Calendar Storage

```python
# Add to your User model
class GoogleCalendarCredentials(Base):
    __tablename__ = "google_calendar_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    token_expiry = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="calendar_credentials")

# Update User model
class User(Base):
    # ... existing fields ...
    calendar_credentials = relationship("GoogleCalendarCredentials", back_populates="user", uselist=False)
```

### Frontend Calendar Integration

**File: `src/pages/ScheduledMeetings.tsx`**

The frontend handles:

- OAuth initiation
- Callback parameter processing
- Retry logic for token timing
- Calendar events display
- AI call scheduling

## User-Specific Features Implementation

### 1. Custom Scenarios (Per User)

#### Backend Requirements

```python
# Update CustomScenario model for user isolation
class CustomScenario(Base):
    __tablename__ = "custom_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # User isolation
    name = Column(String, nullable=False)
    persona = Column(Text, nullable=False)
    prompt = Column(Text, nullable=False)
    voice_type = Column(String, nullable=False)
    temperature = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="scenarios")

# Update User model
class User(Base):
    # ... existing fields ...
    scenarios = relationship("CustomScenario", back_populates="user")

# Update API endpoints for user isolation
@app.get("/custom-scenarios")
async def list_user_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    scenarios = db.query(CustomScenario).filter(
        CustomScenario.user_id == current_user.id
    ).all()
    return scenarios

@app.post("/custom-scenarios")
async def create_scenario(
    scenario_data: CustomScenarioCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    scenario = CustomScenario(
        user_id=current_user.id,  # Ensure user isolation
        **scenario_data.dict()
    )
    db.add(scenario)
    db.commit()
    return scenario
```

#### Frontend Implementation

**File: `src/context/ScenarioContext.tsx`**

```typescript
export const ScenarioProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const { user } = useAuth(); // Get current user

  const loadUserScenarios = async () => {
    if (!user) return;

    try {
      const userScenarios = await api.scenarios.list(); // Only returns user's scenarios
      setScenarios(userScenarios);
    } catch (error) {
      console.error("Failed to load user scenarios:", error);
    }
  };

  useEffect(() => {
    loadUserScenarios();
  }, [user]);

  // ... rest of context implementation
};
```

### 2. Call Notes & Transcripts (Per User)

#### Backend Requirements

```python
# Enhanced transcript model with user isolation
class CallTranscript(Base):
    __tablename__ = "call_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # User isolation
    transcript_sid = Column(String, unique=True, nullable=False)
    call_sid = Column(String, nullable=False)
    scenario_id = Column(Integer, ForeignKey("custom_scenarios.id"), nullable=True)
    scenario_name = Column(String, nullable=False)

    # Call metadata
    call_direction = Column(String, nullable=False)  # 'outbound', 'inbound'
    phone_number = Column(String, nullable=False)
    call_date = Column(DateTime, nullable=False)
    duration = Column(Integer, nullable=False)  # seconds

    # Transcript data
    full_text = Column(Text, nullable=False)
    conversation_flow = Column(JSON, nullable=True)  # Enhanced transcript data
    participant_info = Column(JSON, nullable=True)
    summary_data = Column(JSON, nullable=True)

    # User notes
    user_notes = Column(Text, nullable=True)  # User can add personal notes
    tags = Column(JSON, nullable=True)  # User-defined tags
    is_favorite = Column(Boolean, default=False)

    # Metadata
    status = Column(String, default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="call_transcripts")
    scenario = relationship("CustomScenario", back_populates="transcripts")

# API endpoints with user isolation
@app.get("/call-transcripts")
async def get_user_transcripts(
    skip: int = 0,
    limit: int = 10,
    scenario_filter: str = None,
    date_from: str = None,
    date_to: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CallTranscript).filter(
        CallTranscript.user_id == current_user.id
    )

    # Apply filters
    if scenario_filter:
        query = query.filter(CallTranscript.scenario_name.ilike(f"%{scenario_filter}%"))

    if date_from:
        query = query.filter(CallTranscript.call_date >= date_from)

    if date_to:
        query = query.filter(CallTranscript.call_date <= date_to)

    transcripts = query.offset(skip).limit(limit).all()
    return transcripts

@app.put("/call-transcripts/{transcript_id}/notes")
async def update_transcript_notes(
    transcript_id: int,
    notes_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    transcript = db.query(CallTranscript).filter(
        CallTranscript.id == transcript_id,
        CallTranscript.user_id == current_user.id  # Ensure user owns this transcript
    ).first()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    transcript.user_notes = notes_data.get('notes')
    transcript.tags = notes_data.get('tags', [])
    transcript.is_favorite = notes_data.get('is_favorite', False)

    db.commit()
    return transcript
```

#### Frontend Implementation

**File: `src/pages/CallNotes.tsx`**

```typescript
export const CallNotes: React.FC = () => {
  const [transcripts, setTranscripts] = useState<CallTranscript[]>([]);
  const [filters, setFilters] = useState({
    scenario: "",
    dateFrom: "",
    dateTo: "",
    tags: [],
  });
  const { user } = useAuth();

  const loadUserTranscripts = async () => {
    if (!user) return;

    try {
      const userTranscripts = await api.calls.getEnhancedTranscripts(
        0,
        50,
        filters
      );
      setTranscripts(userTranscripts);
    } catch (error) {
      console.error("Failed to load user transcripts:", error);
    }
  };

  const updateTranscriptNotes = async (
    transcriptId: string,
    notes: string,
    tags: string[]
  ) => {
    try {
      await api.calls.updateTranscriptNotes(transcriptId, {
        notes,
        tags,
        is_favorite: false,
      });

      // Refresh the list
      loadUserTranscripts();
      toast.success("Notes updated successfully");
    } catch (error) {
      toast.error("Failed to update notes");
    }
  };

  // ... rest of component implementation
};
```

## SaaS Multi-Tenancy Implementation

### 1. User Isolation Strategy

```typescript
// All API calls automatically include user context via JWT token
// Backend enforces user isolation at the database level

// Example: Scenario creation
const createScenario = async (scenarioData: ScenarioData) => {
  // Token automatically attached by interceptor
  // Backend extracts user_id from token and associates with scenario
  return await api.scenarios.create(scenarioData);
};
```

### 2. Data Segregation

```sql
-- All user-specific tables include user_id foreign key
-- Database queries always filter by current user

-- Example queries:
SELECT * FROM custom_scenarios WHERE user_id = ?;
SELECT * FROM call_transcripts WHERE user_id = ?;
SELECT * FROM google_calendar_credentials WHERE user_id = ?;
```

### 3. Frontend State Management

**File: `src/context/AuthContext.tsx`**

```typescript
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // On login, all user-specific data is loaded
  const login = async (email: string, password: string) => {
    const response = await api.auth.login({ username: email, password });

    setUser(response.user);
    setIsAuthenticated(true);

    // Trigger loading of user-specific data across the app
    // This happens automatically via context providers
  };

  // On logout, clear all user-specific data
  const logout = async () => {
    localStorage.removeItem("token");
    setUser(null);
    setIsAuthenticated(false);

    // Clear all cached user data
    // Navigate to login page
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
```

## Required Implementation Steps

### Phase 1: Google Calendar Integration

1. ✅ Frontend OAuth flow (completed)
2. ❌ **Backend OAuth callback redirect** (needs implementation)
3. ❌ **User-specific calendar credentials storage** (needs implementation)
4. ❌ **Calendar events API with user isolation** (needs implementation)

### Phase 2: User-Specific Scenarios

1. ❌ **Database schema updates** (add user_id to scenarios table)
2. ❌ **Backend API updates** (enforce user isolation)
3. ❌ **Frontend context updates** (load user-specific scenarios)
4. ❌ **Scenario management UI** (CRUD operations)

### Phase 3: User-Specific Call Notes

1. ❌ **Enhanced transcript model** (add user_id, notes, tags)
2. ❌ **Call notes API endpoints** (CRUD for notes)
3. ❌ **Frontend call notes interface** (enhanced CallNotes.tsx)
4. ❌ **Search and filtering** (by scenario, date, tags)

### Phase 4: SaaS Features

1. ❌ **User registration/billing integration**
2. ❌ **Usage tracking and limits**
3. ❌ **Admin dashboard**
4. ❌ **Multi-tenant deployment**

## Security Considerations

### 1. JWT Token Management

- Tokens stored in localStorage (consider httpOnly cookies for production)
- Automatic token refresh on expiry
- Secure token validation on backend

### 2. User Data Isolation

- All database queries filtered by user_id
- No cross-user data access possible
- API endpoints validate user ownership

### 3. OAuth Security

- State parameter validation
- Secure token storage per user
- Proper scope limitations

## Development Workflow

1. **Start Backend**: `uvicorn app.main:app --reload --port 5050`
2. **Start Frontend**: `npm run dev` (runs on port 5174)
3. **Environment Setup**: Ensure `.env` files configured for both frontend and backend
4. **Database Migrations**: Run Alembic migrations for schema updates
5. **Testing**: Test user isolation and multi-tenancy features

## Production Deployment

### Frontend

- Build: `npm run build`
- Deploy to CDN/Static hosting
- Environment variables for production API URL

### Backend

- Deploy FastAPI application
- Configure production database
- Set up proper OAuth redirect URLs
- Implement proper logging and monitoring

This documentation provides a comprehensive roadmap for implementing the user-specific features and Google Calendar integration needed for your SaaS application.
