# schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

    class Config:
        from_attributes = True


class TokenData(BaseModel):
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

    class Config:
        from_attributes = True


class RealtimeSessionCreate(BaseModel):
    scenario: str
    scenario_id: Optional[str] = None  # For backward compatibility
    user_id: Optional[int] = None


class RealtimeSessionResponse(BaseModel):
    session_id: str
    ice_servers: list
    created_at: str


class SignalingMessage(BaseModel):
    type: str
    sdp: Optional[str] = None
    candidate: Optional[dict] = None
    session_id: str


class SignalingResponse(BaseModel):
    type: str
    sdp: Optional[str] = None
    ice_servers: Optional[list] = None
    error: Optional[str] = None


class ConversationResponse(BaseModel):
    id: int
    call_sid: str
    phone_number: Optional[str]
    direction: str
    scenario: str
    transcript: Optional[str]
    created_at: str
    user_id: Optional[int]

    class Config:
        from_attributes = True


class CallScheduleCreate(BaseModel):
    phone_number: str
    scheduled_time: datetime
    scenario: str

    class Config:
        from_attributes = True  # Updated from orm_mode in newer Pydantic versions


__all__ = ["UserCreate", "UserLogin", "TokenSchema", "TokenData", "RealtimeSessionCreate",
           "RealtimeSessionResponse", "SignalingMessage", "SignalingResponse", "ConversationResponse",
           "CallScheduleCreate"]
